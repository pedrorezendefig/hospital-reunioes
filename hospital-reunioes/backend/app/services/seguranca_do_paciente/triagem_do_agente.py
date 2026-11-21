"""O que é puro no agente de triagem do Núcleo (issue #1990, ADR 0095 e 0107).

Duas peças, sem banco e sem modelo:

- `validar_saida`: confere a resposta do agente contra o formato de saída e as
  regras de coerência do Anexo B. Devolve a lista de violações, vazia quando a
  resposta serve. Cada violação é um código curto (`faixa`, `revisao`,
  `formato:<campo>`) que vai de volta ao modelo na segunda tentativa;
- `montar_notificacao`: o texto que vai à IA, no formato `<notificacao>` do
  Anexo B, com o relato pseudonimizado e só os campos do formato: nada de nome
  ou contato de quem notificou, leito ou anexo.

As 19 categorias e os 30 eventos que nunca deveriam ocorrer estão aqui e na
configuração do banco (migration 188); o teste confere que as duas listas e a
base de conhecimento dizem a mesma coisa.
"""

from __future__ import annotations

import re
from html import escape

from app.services.ouvidoria_pseudonimizacao import pseudonimizar

# A ordem da seção 4 do Anexo A.
CATEGORIAS = (
    "IDP",
    "MED",
    "SAN",
    "CIR",
    "PRO",
    "QUE",
    "LPP",
    "DIS",
    "INF",
    "EXA",
    "EQP",
    "GAS",
    "NUT",
    "COM",
    "ACE",
    "CMP",
    "EST",
    "MAT",
    "OUT",
)
ITENS_DA_LISTA = range(1, 31)

NATUREZAS = (
    "circunstancia_de_risco",
    "quase_erro",
    "incidente_sem_dano",
    "evento_adverso",
    "nao_e_do_nsp",
    "indeterminada",
)
GRAUS_DE_DANO = ("nenhum", "leve", "moderado", "grave", "obito", "nao_se_aplica")
FAIXAS = ("A", "B", "C", "D", "E", "nao_se_aplica")
REVISOES = ("campo_a_campo", "confirmacao_simples")
CONFIANCAS = ("alta", "media", "baixa")
SITUACOES_DA_LISTA = ("sim", "possivel", "nao")
PROTOCOLOS_BASICOS = (
    "identificacao",
    "higiene_das_maos",
    "cirurgia_segura",
    "medicamentos",
    "quedas",
    "lesao_por_pressao",
    "nenhum",
)
CANAIS = ("NSP", "OUV", "COND", "SST", "QT", "FORA")
MAXIMO_DE_PERGUNTAS = 2

_SEM_DANO = ("circunstancia_de_risco", "quase_erro", "incidente_sem_dano")
_DANO_DE_EVENTO_ADVERSO = ("leve", "moderado", "grave", "obito")

_CAMPOS_DE_TEXTO = ("incidente", "justificativa", "motivo_da_confianca")
_CAMPOS_DE_ESCOLHA = {
    "natureza": NATUREZAS,
    "grau_de_dano": GRAUS_DE_DANO,
    "categoria": CATEGORIAS,
    "protocolo_basico": PROTOCOLOS_BASICOS,
    "faixa": FAIXAS,
    "revisao": REVISOES,
    "confianca": CONFIANCAS,
}

# "Qualquer menção a morte" (Anexo B, regra de revisão), com e sem acento,
# como se escreve no plantão.
_MENCAO_A_MORTE = re.compile(
    r"\b(mort[eoa]s?|morr\w*|[oó]bitos?|falec\w*)\b",
    re.IGNORECASE,
)


def menciona_morte(relato: str | None) -> bool:
    return bool(_MENCAO_A_MORTE.search(relato or ""))


# Instrução dirigida ao agente dentro do relato (seção 10.2 da especificação,
# caso N103): pedido para ignorar regras, mandar classificar ou falar com o
# "sistema". O alerta é do sistema e não depende de o agente perceber.
_INSTRUCAO_AO_AGENTE = re.compile(
    r"\b(ignor\w*|desconsider\w*|esque[cç]\w*)\s+(as\s+|todas\s+as\s+|a\s+|o\s+|os\s+)?"
    r"(regras|instru\w*|orienta\w*|prompt)"
    r"|\bclassifique\b|\bresponda\s+(apenas|somente|s[oó])\b|\baten[cç][aã]o,?\s+sistema\b",
    re.IGNORECASE,
)
ALERTA_DE_INSTRUCAO = (
    "O relato traz uma instrução dirigida ao agente. Ela foi tratada como texto do caso, "
    "e a classificação seguiu os fatos."
)


def tem_instrucao_ao_agente(relato: str | None) -> bool:
    return bool(_INSTRUCAO_AO_AGENTE.search(relato or ""))


def faixa_esperada(natureza: str, grau_de_dano: str, situacao_da_lista: str) -> str:
    """A faixa que a regra de coerência do Anexo B manda para essa natureza,
    esse dano e essa situação da lista."""
    if grau_de_dano == "obito" or situacao_da_lista == "sim":
        return "A"
    if grau_de_dano == "grave":
        return "B"
    if grau_de_dano == "moderado":
        return "C"
    if grau_de_dano == "leve" or natureza == "incidente_sem_dano":
        return "D"
    if natureza in ("quase_erro", "circunstancia_de_risco"):
        return "E"
    return "nao_se_aplica"


def _texto(valor) -> bool:
    return isinstance(valor, str) and bool(valor.strip())


def _lista_de_textos(valor) -> bool:
    return isinstance(valor, list) and all(isinstance(item, str) for item in valor)


def _evento_valido(evento) -> bool:
    if not isinstance(evento, dict) or evento.get("situacao") not in SITUACOES_DA_LISTA:
        return False
    if not isinstance(evento.get("motivo"), str):
        return False
    item = evento.get("item")
    if evento["situacao"] == "nao":
        return item in (0, None)
    return isinstance(item, int) and not isinstance(item, bool) and item in ITENS_DA_LISTA


def _violacoes_de_formato(saida: dict) -> list[str]:
    erros = []
    if not _texto(saida.get("assunto")) or "\n" in saida["assunto"].strip():
        erros.append("formato:assunto")
    for campo, opcoes in _CAMPOS_DE_ESCOLHA.items():
        if saida.get(campo) not in opcoes:
            erros.append(f"formato:{campo}")
    for campo in _CAMPOS_DE_TEXTO:
        if not _texto(saida.get(campo)):
            erros.append(f"formato:{campo}")
    if not _evento_valido(saida.get("evento_que_nunca_deveria_ocorrer")):
        erros.append("formato:evento_que_nunca_deveria_ocorrer")
    for campo in ("iras", "risco_de_imagem"):
        if not isinstance(saida.get(campo), bool):
            erros.append(f"formato:{campo}")
    canais = saida.get("canais")
    if not isinstance(canais, list) or not canais or any(canal not in CANAIS for canal in canais):
        erros.append("formato:canais")
    if not isinstance(saida.get("motivo_do_encaminhamento", ""), str):
        erros.append("formato:motivo_do_encaminhamento")
    if not _lista_de_textos(saida.get("alertas")):
        erros.append("formato:alertas")
    perguntas = saida.get("perguntas_ao_notificante")
    if not _lista_de_textos(perguntas) or len(perguntas) > MAXIMO_DE_PERGUNTAS:
        erros.append("formato:perguntas_ao_notificante")
    return erros


_ATINGIU_O_PACIENTE = {
    "nao": "nao_chegou",
    "sem_dano": "chegou_sem_dano",
    "com_dano": "houve_dano",
    "nao_sei": "nao_sei",
}
_TURNO = {"manha": "manhã", "tarde": "tarde", "noite": "noite", "madrugada": "madrugada"}
_PERCEPCAO = {
    "sim": "Sim, a família ou o paciente percebeu.",
    "nao": "Não.",
    "nao_sei": "Não sei.",
}
# Palavra do nome com menos letras que isso ("da", "de") não sai do relato.
_MENOR_PALAVRA_DO_NOME = 3
# Conectivo do nome com três letras ou mais também não sai do relato.
_CONECTIVOS_DO_NOME = {"das", "dos"}


def _sem_quem_notificou(relato: str, nome: str | None, contato: str | None) -> str:
    """O nome e o contato do cadastro saem do relato pelo valor, antes da
    pseudonimização, que não garante nome fora da base de nomes."""
    if contato and contato.strip():
        relato = re.sub(re.escape(contato.strip()), "[CONTATO]", relato, flags=re.IGNORECASE)
    for palavra in (nome or "").split():
        if len(palavra) >= _MENOR_PALAVRA_DO_NOME and palavra.lower() not in _CONECTIVOS_DO_NOME:
            relato = re.sub(rf"\b{re.escape(palavra)}\b", "[NOME]", relato, flags=re.IGNORECASE)
    return relato


def entrada_da_notificacao(linha: dict, *, setor: str | None) -> dict:
    """Os campos do formato de entrada do Anexo B, e só eles, a partir da
    linha da notificação. O relato já sai pseudonimizado."""
    relato = _sem_quem_notificou(
        linha.get("relato") or "", linha.get("notificante_nome"), linha.get("notificante_contato")
    )
    grave = linha.get("grave_ou_morte")
    return {
        "relato": pseudonimizar(relato),
        "local": setor or "",
        "data": str(linha.get("data_ocorrencia") or ""),
        "turno": _TURNO.get(linha.get("turno"), ""),
        "atingiu_paciente": _ATINGIU_O_PACIENTE.get(linha.get("chegou_ao_paciente"), "nao_sei"),
        "grave_ou_morte": "nao_respondido" if grave is None else ("sim" if grave else "nao"),
        "percepcao_familia": _PERCEPCAO.get(linha.get("percebido_ou_reclamacao"), ""),
        "esclarecimentos": "",
    }


def entrada_do_caso_de_teste(caso: dict) -> dict:
    """A entrada de um dos 144 casos do teste de aceite, que já vêm no
    vocabulário do Anexo B e sem onde nem quando."""
    return {
        "relato": pseudonimizar(caso.get("relato") or ""),
        "local": "",
        "data": "",
        "turno": "",
        "atingiu_paciente": caso.get("atingiu_paciente") or "nao_sei",
        "grave_ou_morte": caso.get("grave_ou_morte") or "nao_respondido",
        "percepcao_familia": "",
        "esclarecimentos": "",
    }


_CAMPOS_DA_ENTRADA = (
    "relato",
    "local",
    "data",
    "turno",
    "atingiu_paciente",
    "grave_ou_morte",
    "percepcao_familia",
    "esclarecimentos",
)


def montar_notificacao(entrada: dict) -> str:
    """A mensagem do usuário: a notificação dentro de `<notificacao>`, com o
    texto escapado, para o relato não fechar a marca."""
    linhas = [
        f"  <{campo}>{escape(str(entrada.get(campo) or ''), quote=False)}</{campo}>" for campo in _CAMPOS_DA_ENTRADA
    ]
    return "<notificacao>\n" + "\n".join(linhas) + "\n</notificacao>"


def validar_saida(saida, relato: str | None) -> list[str]:
    """As violações da resposta do agente; lista vazia quando ela serve.

    Primeiro o formato da seção 3 do Anexo B; com o formato certo, as quatro
    regras de coerência: natureza e dano, faixa, revisão e canais."""
    if not isinstance(saida, dict):
        return ["formato:objeto"]
    erros = _violacoes_de_formato(saida)
    if erros:
        return erros
    natureza, dano = saida["natureza"], saida["grau_de_dano"]
    situacao = saida["evento_que_nunca_deveria_ocorrer"]["situacao"]
    if (natureza in _SEM_DANO and dano != "nenhum") or (
        natureza == "evento_adverso" and dano not in _DANO_DE_EVENTO_ADVERSO
    ):
        erros.append("natureza_e_dano")
    if saida["faixa"] != faixa_esperada(natureza, dano, situacao):
        erros.append("faixa")
    campo_a_campo = saida["faixa"] in ("A", "B") or situacao == "possivel" or menciona_morte(relato)
    if campo_a_campo and saida["revisao"] != "campo_a_campo":
        erros.append("revisao")
    if natureza != "nao_e_do_nsp" and "NSP" not in saida["canais"]:
        erros.append("canais")
    return erros
