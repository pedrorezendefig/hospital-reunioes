"""O envio da Conta e do Prontuário em Contas médicas (issue #1123, PRD #1113, ADR 0070).

A faturista arrasta os PDFs do MV e não digita nada. Para cada arquivo, o envio
extrai o texto, decide pela primeira página se é Conta ou Prontuário (nunca
pelo nome) e lê o número do Atendimento lá dentro. A Conta traz ainda o número,
o período da parcial e o plano, que reconhece a operadora; plano sem par é
recusado com o nome dele, e os outros atendimentos do mesmo envio seguem.

O pareamento é pelo Atendimento: uma `cm_conta` por parcial, `NA_FILA` quando
o Prontuário está no sistema (deste envio ou de outro, até 7 dias) e
`AGUARDANDO_ARQUIVO` quando falta um dos dois. Prontuário sem Conta deixa uma
conta à espera da Conta, para a fila mostrar "Falta a conta". Mesmo atendimento
e mesma conta de novo é reprocesso: a conta volta para a fila, sem duplicar.

Um envio pode chegar em mais de uma requisição: o teto do corpo do app é de
100 MiB e não muda, e um Prontuário sozinho pode chegar perto disso. A tela
manda os arquivos em lotes com o mesmo `envio_id`, e os limites de 10
atendimentos e 30 arquivos valem para o envio inteiro.

O texto dos PDFs tem dado de paciente: nada daqui vai para log, e a chave no
bucket não leva o número do atendimento.
"""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from app.services import storage
from app.services.contas_medicas.operadoras import listar_planos, reconhecer_plano
from app.services.contas_medicas.prontuario import atendimento_do_prontuario
from app.services.contas_medicas_conta import (
    CabecalhoDaConta,
    ErroLeitura,
    detectar_tipo_do_arquivo,
    ler_cabecalho_da_conta,
)
from app.services.contas_medicas_extrator import extrair_paginas
from app.services.contas_medicas_retencao import BUCKET

LIMITE_DE_ATENDIMENTOS = 10
LIMITE_DE_ARQUIVOS = 30
# 100 MB como o computador da faturista mostra o tamanho (mil vezes mil). Fica
# abaixo do teto do corpo do app e do teto do bucket, os dois de 100 MiB: o
# arquivo que passa daqui chega à rota e é recusado com a frase dela.
LIMITE_POR_ARQUIVO = 100 * 1000 * 1000
DIAS_NO_BUCKET = 7

MENSAGEM_ARQUIVO_GRANDE = "O arquivo passa de 100 MB, o limite por arquivo."
MENSAGEM_ARQUIVOS_DEMAIS = f"O envio já tem {LIMITE_DE_ARQUIVOS} arquivos, o limite. Mande este num próximo envio."
MENSAGEM_TIPO_DESCONHECIDO = "Não reconheci o arquivo como conta nem como prontuário do MV."
MENSAGEM_PRONTUARIO_SEM_ATENDIMENTO = "Não achei o número do atendimento no prontuário."
MENSAGEM_FALHA_NO_BUCKET = "Não consegui guardar o arquivo. Envie de novo."


def mensagem_plano_nao_configurado(plano: str) -> str:
    return f"Plano {plano} ainda não configurado"


def mensagem_atendimentos_demais(numero: str) -> str:
    return (
        f"O envio já tem {LIMITE_DE_ATENDIMENTOS} atendimentos, o limite. "
        f"Mande o atendimento {numero} num próximo envio."
    )


class EnvioNaoEncontradoError(LookupError):
    """O `envio_id` do lote não existe ou é de outra pessoa."""


@dataclass(frozen=True)
class ArquivoRecebido:
    nome: str
    conteudo: bytes


@dataclass(frozen=True)
class _Lido:
    indice: int
    nome: str
    conteudo: bytes
    tipo: str
    numero_atendimento: str
    paginas: int
    cabecalho: CabecalhoDaConta | None = None
    plano: dict | None = None


@dataclass(frozen=True)
class _Recusa:
    nome: str
    motivo: str
    numero_atendimento: str | None = None

    def como_dict(self) -> dict:
        return {"arquivo": self.nome, "numero_atendimento": self.numero_atendimento, "motivo": self.motivo}


def _iso(valor: date | datetime | None) -> str | None:
    return valor.isoformat() if valor else None


def _ler(indice: int, arquivo: ArquivoRecebido, planos: list[dict]) -> _Lido | _Recusa:
    """Tipo pelo conteúdo, Atendimento lido no PDF e, na Conta, o plano reconhecido."""
    if len(arquivo.conteudo) > LIMITE_POR_ARQUIVO:
        return _Recusa(arquivo.nome, MENSAGEM_ARQUIVO_GRANDE)
    paginas = extrair_paginas(arquivo.conteudo)
    if isinstance(paginas, ErroLeitura):
        return _Recusa(arquivo.nome, paginas.motivo)
    textos = [pagina.texto for pagina in paginas]
    tipo = detectar_tipo_do_arquivo(textos[0] if textos else "")
    base = {"indice": indice, "nome": arquivo.nome, "conteudo": arquivo.conteudo, "paginas": len(textos)}
    if tipo == "CONTA":
        cabecalho = ler_cabecalho_da_conta(textos)
        if isinstance(cabecalho, ErroLeitura):
            return _Recusa(arquivo.nome, cabecalho.motivo)
        plano = reconhecer_plano(cabecalho.plano, planos)
        if plano is None:
            return _Recusa(arquivo.nome, mensagem_plano_nao_configurado(cabecalho.plano), cabecalho.atendimento)
        return _Lido(**base, tipo="CONTA", numero_atendimento=cabecalho.atendimento, cabecalho=cabecalho, plano=plano)
    if tipo == "PRONTUARIO":
        numero = atendimento_do_prontuario(textos)
        if numero is None:
            return _Recusa(arquivo.nome, MENSAGEM_PRONTUARIO_SEM_ATENDIMENTO)
        return _Lido(**base, tipo="PRONTUARIO", numero_atendimento=numero)
    return _Recusa(arquivo.nome, MENSAGEM_TIPO_DESCONHECIDO)


def _envio(supabase, faturista_id: str, envio_id: str | None, agora: datetime) -> dict:
    if envio_id is None:
        return (
            supabase.table("cm_envio")
            .insert({"usuario_id": faturista_id, "criado_em": agora.isoformat()})
            .execute()
            .data[0]
        )
    achados = supabase.table("cm_envio").select("*").eq("id", envio_id).limit(1).execute().data or []
    if not achados or achados[0].get("usuario_id") != faturista_id:
        raise EnvioNaoEncontradoError(envio_id)
    return achados[0]


def _arquivos_do_envio(supabase, envio_id: str) -> list[dict]:
    return supabase.table("cm_arquivo").select("*").eq("envio_id", envio_id).order("criado_em").execute().data or []


def _atendimento(supabase, numero: str) -> dict:
    achados = (
        supabase.table("cm_atendimento").select("*").eq("numero_atendimento", numero).limit(1).execute().data or []
    )
    if achados:
        return achados[0]
    return supabase.table("cm_atendimento").insert({"numero_atendimento": numero}).execute().data[0]


def _prontuarios_no_sistema(supabase, atendimento_id: str, agora: datetime) -> list[dict]:
    """Os Prontuários do Atendimento que ainda estão no bucket (até 7 dias)."""
    return (
        supabase.table("cm_arquivo")
        .select("*")
        .eq("atendimento_id", atendimento_id)
        .eq("tipo", "PRONTUARIO")
        .is_("apagado_em", "null")
        .gt("apagar_em", agora.isoformat())
        .execute()
        .data
        or []
    )


def _guardar(supabase, envio_id: str, atendimento: dict, lido: _Lido, agora: datetime) -> str | None:
    """O PDF no bucket privado e a linha em `cm_arquivo`. A chave não leva dado do paciente."""
    arquivo_id = str(uuid.uuid4())
    chave = f"{envio_id}/{arquivo_id}.pdf"
    if not storage.upload_private(supabase, BUCKET, chave, lido.conteudo, "application/pdf"):
        return None
    supabase.table("cm_arquivo").insert(
        {
            "id": arquivo_id,
            "envio_id": envio_id,
            "tipo": lido.tipo,
            "atendimento_id": atendimento["id"],
            "numero_atendimento": lido.numero_atendimento,
            "paginas": lido.paginas,
            "chave_bucket": chave,
            "hash": hashlib.sha256(lido.conteudo).hexdigest(),
            "apagar_em": (agora + timedelta(days=DIAS_NO_BUCKET)).isoformat(),
        }
    ).execute()
    return arquivo_id


def _primeira(consulta) -> dict | None:
    achados = consulta.limit(1).execute().data or []
    return achados[0] if achados else None


def _gravar_conta(
    supabase, atendimento_id: str, lido: _Lido, arquivo_id: str, situacao: str, faturista_id: str, ordem: int, agora
) -> None:
    """Uma `cm_conta` por parcial. A mesma conta de novo é reprocesso; a conta à
    espera da Conta (deixada pelo Prontuário) é preenchida."""
    cabecalho = lido.cabecalho
    campos = {
        "arquivo_id": arquivo_id,
        "numero_conta": cabecalho.conta,
        "periodo_inicio": _iso(cabecalho.periodo_inicio),
        "periodo_fim": _iso(cabecalho.periodo_fim),
        "situacao": situacao,
        "erro_motivo": None,
        "processando_desde": None,
        "tentativas": 0,
        "faturista_id": faturista_id,
        "ordem_fila": ordem,
        "enviada_em": agora.isoformat(),
    }

    def do_atendimento():
        return supabase.table("cm_conta").select("*").eq("atendimento_id", atendimento_id)

    existente = None
    if cabecalho.conta:
        existente = _primeira(do_atendimento().eq("numero_conta", cabecalho.conta))
    if existente is None:
        existente = _primeira(do_atendimento().is_("arquivo_id", "null"))
    if existente:
        supabase.table("cm_conta").update(campos).eq("id", existente["id"]).execute()
    else:
        supabase.table("cm_conta").insert({"atendimento_id": atendimento_id, **campos}).execute()


def _gravar_atendimento(
    supabase, envio_id: str, numero: str, lidos: list[_Lido], faturista_id: str, ordem_base: int, agora: datetime
) -> list[_Recusa]:
    atendimento = _atendimento(supabase, numero)
    recusas: list[_Recusa] = []
    guardados: list[tuple[_Lido, str]] = []
    for lido in lidos:
        arquivo_id = _guardar(supabase, envio_id, atendimento, lido, agora)
        if arquivo_id is None:
            recusas.append(_Recusa(lido.nome, MENSAGEM_FALHA_NO_BUCKET, numero))
        else:
            guardados.append((lido, arquivo_id))

    contas = [(lido, arquivo_id) for lido, arquivo_id in guardados if lido.tipo == "CONTA"]
    chegou_prontuario = any(lido.tipo == "PRONTUARIO" for lido, _ in guardados)
    if contas:
        ultima = contas[-1][0]
        supabase.table("cm_atendimento").update(
            {
                "operadora_id": ultima.plano["operadora_id"],
                "plano": ultima.cabecalho.plano,
                "coluna_preco": ultima.plano.get("coluna_preco"),
            }
        ).eq("id", atendimento["id"]).execute()

    tem_prontuario = bool(_prontuarios_no_sistema(supabase, atendimento["id"], agora))
    situacao = "NA_FILA" if tem_prontuario else "AGUARDANDO_ARQUIVO"
    for lido, arquivo_id in contas:
        _gravar_conta(
            supabase, atendimento["id"], lido, arquivo_id, situacao, faturista_id, ordem_base + lido.indice, agora
        )

    if chegou_prontuario:
        _liberar_contas_a_espera(supabase, atendimento["id"], faturista_id, ordem_base, lidos, agora)
    return recusas


def _liberar_contas_a_espera(supabase, atendimento_id: str, faturista_id: str, ordem_base: int, lidos, agora) -> None:
    """O Prontuário chegou: a Conta que esperava por ele entra na fila. Sem
    Conta nenhuma, fica uma conta à espera dela."""
    contas = supabase.table("cm_conta").select("*").eq("atendimento_id", atendimento_id).execute().data or []
    esperando = [c["id"] for c in contas if c.get("situacao") == "AGUARDANDO_ARQUIVO" and c.get("arquivo_id")]
    if esperando:
        supabase.table("cm_conta").update({"situacao": "NA_FILA"}).in_("id", esperando).eq(
            "situacao", "AGUARDANDO_ARQUIVO"
        ).execute()
    if not contas:
        primeiro = next(lido for lido in lidos if lido.tipo == "PRONTUARIO")
        supabase.table("cm_conta").insert(
            {
                "atendimento_id": atendimento_id,
                "situacao": "AGUARDANDO_ARQUIVO",
                "faturista_id": faturista_id,
                "ordem_fila": ordem_base + primeiro.indice,
                "enviada_em": agora.isoformat(),
            }
        ).execute()


def receber(
    supabase, faturista_id: str, envio_id: str | None, arquivos: Sequence[ArquivoRecebido], agora: datetime
) -> dict:
    """Recebe um lote de arquivos de um envio e devolve o "Último envio" do envio inteiro."""
    envio = _envio(supabase, faturista_id, envio_id, agora)
    ja_no_envio = _arquivos_do_envio(supabase, envio["id"])
    atendimentos = {a.get("numero_atendimento") for a in ja_no_envio}
    planos = listar_planos(supabase)

    aceitos: list[_Lido] = []
    recusas: list[_Recusa] = []
    for indice, arquivo in enumerate(arquivos):
        if len(ja_no_envio) + len(aceitos) >= LIMITE_DE_ARQUIVOS:
            recusas.append(_Recusa(arquivo.nome, MENSAGEM_ARQUIVOS_DEMAIS))
            continue
        lido = _ler(indice, arquivo, planos)
        if isinstance(lido, _Recusa):
            recusas.append(lido)
            continue
        if lido.numero_atendimento not in atendimentos and len(atendimentos) >= LIMITE_DE_ATENDIMENTOS:
            recusas.append(
                _Recusa(arquivo.nome, mensagem_atendimentos_demais(lido.numero_atendimento), lido.numero_atendimento)
            )
            continue
        atendimentos.add(lido.numero_atendimento)
        aceitos.append(lido)

    por_atendimento: dict[str, list[_Lido]] = {}
    for lido in aceitos:
        por_atendimento.setdefault(lido.numero_atendimento, []).append(lido)
    # A ordem da fila é a do envio e, dentro dele, a dos arquivos.
    ordem_base = int(agora.timestamp() * 1_000_000)
    for numero, lidos in por_atendimento.items():
        recusas += _gravar_atendimento(supabase, envio["id"], numero, lidos, faturista_id, ordem_base, agora)

    return {
        "envio_id": envio["id"],
        "ultimo_envio": ultimo_envio(supabase, envio["id"], agora),
        "recusas": [recusa.como_dict() for recusa in recusas],
    }


def _frase(parciais: int, tem_prontuario: bool) -> str:
    """As frases da spec do diretor; a contagem só aparece quando há parciais."""
    if parciais == 0:
        return "falta a conta"
    if tem_prontuario:
        return "conta e prontuário" if parciais == 1 else f"{parciais} parciais e prontuário"
    return "falta o prontuário" if parciais == 1 else f"{parciais} parciais, falta o prontuário"


def _data_br(texto: str) -> str:
    return date.fromisoformat(texto[:10]).strftime("%d/%m/%Y")


def _aviso_de_prontuario_atualizado(supabase, atendimento_id: str, contas: list[dict]) -> str | None:
    """A Conta pareou com o Prontuário que já estava no sistema e o período dela
    passa da última data dele: falta o Prontuário atualizado."""
    eventos = _primeira(
        supabase.table("cm_eventos").select("*").eq("atendimento_id", atendimento_id).order("criado_em", desc=True)
    )
    ate = (eventos or {}).get("prontuario_ate")
    fins = [c["periodo_fim"] for c in contas if c.get("periodo_fim")]
    if not ate or not fins or max(fins)[:10] <= str(ate)[:10]:
        return None
    return (
        f"O período da conta vai até {_data_br(max(fins))} e o prontuário no sistema, até {_data_br(str(ate))}. "
        "Envie o prontuário atualizado."
    )


def ultimo_envio(supabase, envio_id: str, agora: datetime) -> list[dict]:
    """Uma linha por Atendimento do envio, na ordem em que chegaram: "31302,
    conta e prontuário", "31310, 2 parciais e prontuário", "31318, falta o
    prontuário"."""
    arquivos = _arquivos_do_envio(supabase, envio_id)
    linhas = []
    for atendimento_id in dict.fromkeys(a["atendimento_id"] for a in arquivos):
        do_atendimento = [a for a in arquivos if a["atendimento_id"] == atendimento_id]
        numero = do_atendimento[0]["numero_atendimento"]
        ids_de_conta = [a["id"] for a in do_atendimento if a["tipo"] == "CONTA"]
        contas = (
            supabase.table("cm_conta").select("*").in_("arquivo_id", ids_de_conta).execute().data or []
            if ids_de_conta
            else []
        )
        prontuario_no_envio = any(a["tipo"] == "PRONTUARIO" for a in do_atendimento)
        tem_prontuario = prontuario_no_envio or bool(_prontuarios_no_sistema(supabase, atendimento_id, agora))
        aviso = None
        if contas and tem_prontuario and not prontuario_no_envio:
            aviso = _aviso_de_prontuario_atualizado(supabase, atendimento_id, contas)
        frase = _frase(len(contas), tem_prontuario)
        linhas.append({"numero_atendimento": numero, "frase": frase, "texto": f"{numero}, {frase}", "aviso": aviso})
    return linhas
