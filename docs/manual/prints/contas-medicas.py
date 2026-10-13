#!/usr/bin/env python3
"""Roteiro de prints do módulo Contas médicas (ADR 0057, decisão 3).

Cada print do manual é tela real do app rodando em localhost, capturada por
este roteiro, e não recorte feito à mão: quando a tela muda, é este arquivo que
roda de novo e refaz as imagens.

**Nenhum dado daqui é de paciente.** A conta, o atendimento e o rótulo da
paciente ("Ana P.") são inventados pelo `--semear`, e a operadora de exemplo
(AURORA) não existe: o repositório é público, e a memória e as tabelas de
verdade têm preço de contrato. A fila da faturista só mostra as contas dela,
então o print da fila nunca alcança conta de outra pessoa.

Duas telas não dá para mostrar sem fingir o servidor, e o roteiro diz isso em
voz alta: o quadro **Último envio** só aparece depois de subir conta e
prontuário de verdade do MV, e PDF do MV é dado de paciente. O roteiro sobe um
PDF vazio e responde o envio com o exemplo de `RESPOSTA_DO_ENVIO`; a tela que
desenha a resposta é a do app. A memória, ao contrário, sobe de verdade: é um
arquivo sintético, e o quadro verde é o que o servidor devolveu.

Receita:

1. Supabase local no ar (`supabase start` em `hospital-reunioes/`).
2. Stack do app com o código que o print vai mostrar:
   `bash .claude/skills/atualizar-app/scripts/apply.sh`.
3. Dados de exemplo (a faturista, a gestora, a coordenadora, a diretora, a
   operadora AURORA, as contas, os temas da Validação, o cenário com os
   lembretes e o contrato):
   `python3 docs/manual/prints/contas-medicas.py --semear`. É idempotente,
   refaz as contas do zero a cada rodada e recusa rodar contra qualquer banco
   que não seja o local. A memória da AURORA sobe pela própria tela (o app
   precisa estar no ar), para a Memória da operadora ter versão vigente.
4. `python3 docs/manual/prints/contas-medicas.py`.

Três telas da gestão chamam a IA e o roteiro não chama: a proposta de "Ensinar
uma regra nova" e a do mapeamento das colunas da tabela vêm dos exemplos
`PROPOSTA_DA_REGRA` e `PROPOSTA_DO_MAPEAMENTO`, e a leitura da IA da
observação nasce gravada no tema. A tela que desenha cada resposta é a do app.
O cenário é preenchido à mão, sem o "Preencher com a IA".

O balão numerado é o do roteiro do Admin, importado dele: é o mesmo círculo em
todo o manual.

Uso: python3 docs/manual/prints/contas-medicas.py [--base http://localhost:3000]
     [--saida docs/manual/src/assets/contas-medicas] [--print <nome>] [--semear]
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.sync_api import Page

COMPUTADOR = {"width": 1440, "height": 900}
PAUSA_ENTRE_PRINTS = 12  # segundos
ESCALA = 2

ENV_LOCAL = Path(__file__).resolve().parents[3] / "hospital-reunioes" / ".env"

_ADMIN = Path(__file__).resolve().parent / "admin.py"
_spec = importlib.util.spec_from_file_location("prints_admin", _ADMIN)
_admin = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_admin)
balao = _admin.balao
limpar_baloes = _admin.limpar_baloes
sem_foco = _admin.sem_foco

SENHA = "ManualContasMedicas2026!"

# Faixa P950 em diante: o banco local é um só para todos os roteiros.
# (id, nome, email, cargo, perfil em Contas médicas)
FATURISTA = ("P950", "Renata Lima", "renata.lima@exemplo.local", "Faturista", "faturista")
GESTORA = (
    "P951",
    "Marta Queiroz",
    "marta.queiroz@exemplo.local",
    "Gerente de Contas Médicas",
    "gestao_contas_medicas",
)
# P952 e P959 já servem a outros testes locais da faixa: a gestão começa no P953.
COORDENADORA = (
    "P953",
    "Sílvia Rocha",
    "silvia.rocha@exemplo.local",
    "Coordenadora de Faturamento",
    "coordenadora",
)
DIRETORA = ("P954", "Helena Prates", "helena.prates@exemplo.local", "Diretora Médica", "diretoria_medica")
# Quem a diretora habilita no print da Habilitação: nasce sem perfil no módulo.
SEM_PERFIL = ("P955", "Júlio Andrade", "julio.andrade@exemplo.local", "Assistente de Faturamento", None)
PESSOAS = (FATURISTA, GESTORA, COORDENADORA, DIRETORA, SEM_PERFIL)

# As duas faturistas que só aparecem no Painel (PRD #1128), na faixa P976: de
# P952 a P959 já é de outro roteiro no banco local. A fila da Renata
# não muda com elas.
FATURISTAS_DO_PAINEL = (
    ("P976", "Bianca Torres", "bianca.torres.cm@exemplo.local", "Faturista", "faturista"),
    ("P977", "Caio Moreira", "caio.moreira.cm@exemplo.local", "Faturista", "faturista"),
)

OPERADORA = ("AURORA", "Aurora Saúde")
PLANO = "AURORA ESSENCIAL"
SETOR = ("POSTO 3", "ENFERMARIA")

# O atendimento das telas do guia.
ATENDIMENTO_DO_GUIA = "900412"

# A conta concluída das telas do reenvio, e a semana que o Painel mostra (a
# segunda-feira). Datas fixas: o print sai igual em qualquer dia.
CONTA_CONCLUIDA = "51102"
SEMANA_DO_PAINEL = "2026-10-05"

# A memória sintética que o print sobe pela tela. A operadora não existe e os
# números não são de contrato nenhum.
MEMORIA = """---
operadora: AURORA
nome: Aurora Saúde
versao_memoria: "1.0"
data: 2026-10-01
origem: "Exemplo do Manual, sem contrato real"
situacao: PRONTA

colunas_de_preco:
  padrao: COMUM

diaria:
  hora_vencimento: "10:00"
  limite_madrugada: "05:00"
  sempre_integral: true
---

# MEMÓRIA DA OPERADORA, AURORA SAÚDE

Exemplo do Manual. Não contém dado de paciente.

## 1. PRINCÍPIOS

| ID | Regra | Tipo | Origem | Status | Data |
|---|---|---|---|---|---|
| AURORA-PRI-01 | Identificar sempre pelo número do atendimento. | OPERACIONAL | PRÁTICA | VIGENTE | 01/10/2026 |

## 3. DIÁRIAS

| ID | Regra | Tipo | Origem | Status | Data |
|---|---|---|---|---|---|
| AURORA-DIA-01 | A diária vence às 10h e é sempre integral. | CONTRATUAL | PRÁTICA | VIGENTE | 01/10/2026 |
| AURORA-DIA-02 | Transferência de setor antes das 10h gera diária extra na origem. | CONTRATUAL | PRÁTICA | PENDENTE | |

## 7. MEDICAMENTOS

| ID | Regra | Tipo | Origem | Status | Data |
|---|---|---|---|---|---|
| AURORA-MED-02 | Prescrição de horário fixo é cobrada em todos os dias prescritos. | OPERACIONAL | PRÁTICA | VIGENTE | 01/10/2026 |
"""

# O que o servidor responderia a um envio de três PDFs: dois atendimentos e uma
# conta de plano sem cadastro. As frases são as do servidor
# (`services/contas_medicas/envio.py`).
RESPOSTA_DO_ENVIO = {
    "envio_id": "00000000-0000-4000-8000-000000000950",
    "ultimo_envio": [
        {"numero_atendimento": "900412", "frase": "conta e prontuário", "texto": "900412, conta e prontuário", "aviso": None},
        {"numero_atendimento": "900431", "frase": "falta o prontuário", "texto": "900431, falta o prontuário", "aviso": None},
    ],
    "recusas": [
        {
            "arquivo": "conta-900450.pdf",
            "numero_atendimento": "900450",
            "motivo": "Plano AURORA PREMIUM ainda não configurado",
        }
    ],
}

# O que a IA responderia ao "Propor regra" da regra de exemplo, no formato da
# rota (`services/contas_medicas/regra_nova.py`).
PEDIDO_DA_REGRA = "Na Aurora a seringa de limpeza pronta não é paga, tem que tirar da conta."
PROPOSTA_DA_REGRA = {
    "regra": {
        "secao": "INS",
        "texto": "A seringa de limpeza pronta (flush) não é paga: retirar da conta.",
        "tipo": "OPERACIONAL",
        "origem": "PRÁTICA",
    },
    "parametro": None,
    "conflitos": [],
    "efeito_no_guia": "A seringa de limpeza pronta lançada na conta vira uma linha Retirar, com a regra nova.",
}

# O que a leitura de uma planilha de outro cabeçalho devolveria: as colunas que
# a IA apontou e as primeiras linhas convertidas. Códigos e preços inventados.
PROPOSTA_DO_MAPEAMENTO = {
    "cabecalho": ["COD_TUSS", "COD_INTERNO", "DESCRICAO_ITEM", "UN", "VALOR_COMUM", "VALOR_MASTER"],
    "mapeamento": {
        "codigo": "COD_TUSS",
        "codigo_alternativo": "COD_INTERNO",
        "descricao": "DESCRICAO_ITEM",
        "unidade": "UN",
        "precos": [{"chave": "comum", "coluna": "VALOR_COMUM"}, {"chave": "master", "coluna": "VALOR_MASTER"}],
    },
    "origem": "IA",
    "amostra": [
        {"codigo": "70031245", "codigo_alternativo": "A-1102", "descricao": "Agulha hipodérmica 25 x 7",
         "unidade": "UN", "precos": {"comum": 0.95, "master": 1.10}},
        {"codigo": "70044120", "codigo_alternativo": "S-0414", "descricao": "Sonda Foley 2 vias nº 14",
         "unidade": "UN", "precos": {"comum": 18.40, "master": 21.30}},
        {"codigo": "70044210", "codigo_alternativo": "C-0210", "descricao": "Coletor de urina sistema fechado",
         "unidade": "UN", "precos": {"comum": 12.90, "master": 14.80}},
    ],
    "total": 1840,
    "erro": None,
}

# O código bloqueado do tema de exemplo e o cenário da Conferência da coordenação.
CODIGO_BLOQUEADO = "70095001"
CENARIO = "CEN-950"
TERMO_DO_DICIONARIO = "FLUSH SF 10ML"


# --------------------------------------------------------------------------
# Banco local
# --------------------------------------------------------------------------


def _credenciais_locais() -> tuple[str, str]:
    """URL e chave de serviço do `.env` local, nunca de produção."""
    env = {}
    for linha in ENV_LOCAL.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if linha and not linha.startswith("#") and "=" in linha:
            chave, valor = linha.split("=", 1)
            env[chave] = valor.strip().strip('"')
    url = env.get("SUPABASE_URL", "")
    chave = env.get("SUPABASE_SERVICE_KEY") or env.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if "127.0.0.1" not in url and "localhost" not in url:
        raise SystemExit(f"recusado: '{url}' não é o Supabase local.")
    return url, chave


def _rest(caminho: str, metodo="GET", corpo=None, prefer=None):
    url, chave = _credenciais_locais()
    dados = json.dumps(corpo).encode() if corpo is not None else None
    cabecalhos = {"apikey": chave, "Authorization": f"Bearer {chave}", "Content-Type": "application/json"}
    if prefer:
        cabecalhos["Prefer"] = prefer
    req = urllib.request.Request(f"{url}/rest/v1/{caminho}", data=dados, headers=cabecalhos, method=metodo)
    try:
        with urllib.request.urlopen(req, timeout=20) as resposta:
            texto = resposta.read().decode()
            return json.loads(texto) if texto.strip() else None
    except urllib.error.HTTPError as e:
        raise SystemExit(f"{metodo} {caminho}: {e.code} {e.read().decode()[:300]}")


def _criar(tabela: str, linha: dict) -> dict:
    return _rest(tabela, "POST", [linha], prefer="return=representation")[0]


def _login_de_exemplo(email: str) -> str:
    """Cria (ou reaproveita) o login da pessoa de exemplo no Supabase local."""
    url, chave = _credenciais_locais()
    cabecalhos = {"apikey": chave, "Authorization": f"Bearer {chave}", "Content-Type": "application/json"}
    corpo = json.dumps({"email": email, "password": SENHA, "email_confirm": True}).encode()
    req = urllib.request.Request(f"{url}/auth/v1/admin/users", data=corpo, headers=cabecalhos)
    try:
        with urllib.request.urlopen(req, timeout=20) as resposta:
            return json.load(resposta)["id"]
    except urllib.error.HTTPError as e:
        texto = e.read().decode()
        if e.code not in (400, 422) or "already" not in texto:
            raise SystemExit(f"login {email}: {e.code} {texto[:300]}")
    busca = urllib.request.Request(f"{url}/auth/v1/admin/users?page=1&per_page=500", headers=cabecalhos)
    with urllib.request.urlopen(busca, timeout=20) as resposta:
        for usuario in json.load(resposta)["users"]:
            if usuario["email"] == email:
                return usuario["id"]
    raise SystemExit(f"login {email} não encontrado depois de criado.")


def _linha(acao, data, setor, codigo, descricao, **campos) -> dict:
    return {
        "acao": acao,
        "data": data,
        "setor": setor,
        "codigo": codigo,
        "descricao": descricao,
        "origem": "CODIGO",
        "estado": "ABERTA",
        **campos,
    }


# As linhas do guia da conta 900412, por dia e setor. Preços e códigos
# inventados.
LINHAS_DO_GUIA = [
    _linha(
        "INCLUIR", "2026-10-03", "CTI ADULTO", "90123456", "Pantoprazol 40 mg injetável",
        data_fim="2026-10-05", quantidade_lancada=3, quantidade_devida=6, preco_tabela=22.80,
        valor_diferenca=68.40, regra_codigo="AURORA-MED-02", motivo="Prescrito em 6 dias, lançado em 3.",
        evidencia_pagina=112, evidencia_trecho="PANTOPRAZOL 40MG EV 1X AO DIA, 06H", nivel_evidencia="PRESCRITO",
        causa_raiz="DISPENSACAO", confianca="ALTA",
    ),
    _linha(
        "CORRIGIR_PRECO", "2026-10-03", "CTI ADULTO", "70031245", "Agulha hipodérmica 25 x 7",
        quantidade_lancada=10, quantidade_devida=10, preco_lancado=1.42, preco_tabela=0.95, valor_diferenca=-4.70,
        regra_codigo="AURORA-PRI-01", motivo="Coluna errada: o lançado é o preço da outra coluna.",
        causa_raiz="CADASTRO_PRECO", confianca="ALTA",
    ),
    _linha(
        "VALIDAR", "2026-10-03", "CTI ADULTO", "60000775", "Diária de CTI adulto",
        quantidade_lancada=1, quantidade_devida=2, preco_tabela=1212.00, valor_diferenca=1212.00,
        regra_codigo="AURORA-DIA-02", motivo="Transferência entre 09h40 e 10h20: a janela atravessa o vencimento.",
        nivel_evidencia="POR_REGRA", causa_raiz="REGRA_AUTOMATICA", confianca="MEDIA",
    ),
    _linha(
        "INCLUIR", "2026-10-04", "CENTRO CIRURGICO", "90187733", "Ondansetrona 4 mg injetável",
        quantidade_lancada=0, quantidade_devida=1, preco_tabela=9.85, valor_diferenca=9.85,
        regra_codigo="AURORA-MED-02", motivo="Na ficha anestésica, sem item no centro cirúrgico.",
        evidencia_pagina=241, evidencia_trecho="ONDANSETRONA 4MG EV 14:10", nivel_evidencia="REGISTRADO",
        causa_raiz="REGISTRO_ASSISTENCIAL", confianca="ALTA",
    ),
    _linha(
        "AJUSTAR_QUANTIDADE", "2026-10-04", "CENTRO CIRURGICO", "60034021", "Oxigênio, até 3 L/min, por hora",
        quantidade_lancada=2, quantidade_devida=3, preco_tabela=18.50, valor_diferenca=18.50,
        regra_codigo="AURORA-PRI-01", motivo="Ficha anestésica: 2 L/min por 2h40, arredonda para 3 horas.",
        evidencia_pagina=240, evidencia_trecho="O2 2 L/MIN 11:30 A 14:10", nivel_evidencia="REGISTRADO",
        causa_raiz="LANCAMENTO_MANUAL", confianca="ALTA",
    ),
    _linha(
        "RETIRAR", "2026-10-08", "POSTO 3", "60000600", "Diária de enfermaria",
        quantidade_lancada=1, quantidade_devida=0, preco_lancado=480.00, valor_diferenca=-480.00,
        regra_codigo="AURORA-DIA-01", motivo="Alta às 09h15, antes do vencimento das 10h.",
        nivel_evidencia="POR_REGRA", causa_raiz="REGRA_AUTOMATICA", confianca="ALTA",
    ),
]

TOTAL_DO_GUIA = 18450.00


def _nota(linhas: list[dict], total: float) -> tuple[int, float]:
    """A nota de entrada e o R$ apontado, pela mesma conta do servidor."""
    apontado = sum(abs(l["valor_diferenca"]) for l in linhas if l["acao"] != "VALIDAR")
    com_sinal = sum(l["valor_diferenca"] for l in linhas if l["acao"] != "VALIDAR")
    devido = total + com_sinal
    return max(0, round(100 * (1 - apontado / devido))), round(apontado, 2)


def _nota_de_entrada(linhas: list[dict], total: float) -> int:
    """A nota da conta concluída: refeita sem as linhas Não procede."""
    return _nota([l for l in linhas if l.get("estado") != "NAO_PROCEDE"], total)[0]


def _apagar_contas_de_exemplo(faturista_id: str) -> None:
    """Refaz do zero: as contas da faturista de exemplo, os envios e os atendimentos."""
    contas = _rest(f"cm_conta?faturista_id=eq.{faturista_id}&select=atendimento_id")
    _rest(f"cm_conta?faturista_id=eq.{faturista_id}", "DELETE")
    _rest(f"cm_envio?usuario_id=eq.{faturista_id}", "DELETE")
    for atendimento in {c["atendimento_id"] for c in contas or []}:
        _rest(f"cm_atendimento?id=eq.{atendimento}", "DELETE")


def _conta(
    atendimento: str,
    operadora_id: str,
    ordem: int,
    situacao: str,
    linhas: list[dict],
    faturista: str = FATURISTA[0],
    **campos,
) -> None:
    at = _criar(
        "cm_atendimento",
        {
            "numero_atendimento": atendimento,
            "paciente_rotulo": campos.pop("rotulo", "Ana P."),
            "idade_anos": campos.pop("idade", 67),
            "operadora_id": operadora_id,
            "plano": PLANO,
            "coluna_preco": "COMUM",
            "acomodacao_contratada": "ENFERMARIA",
        },
    )
    total = campos.pop("total_lancado", None)
    if linhas and total:
        nota, apontado = _nota(linhas, total)
        campos.update(nota_bruta=nota, valor_apontado=apontado)
        if situacao.startswith("CONCLUIDA"):
            campos.update(nota_entrada=_nota_de_entrada(linhas, total))
    conta = _criar(
        "cm_conta",
        {
            "atendimento_id": at["id"],
            "situacao": situacao,
            "faturista_id": faturista,
            "ordem_fila": ordem,
            "total_lancado": total,
            **campos,
        },
    )
    for i, linha in enumerate(linhas):
        _criar("cm_guia_linha", {"conta_id": conta["id"], "ordem": i, **linha})


def semear(base: str = "http://localhost:3000") -> None:
    """As pessoas, a operadora AURORA com plano e setor, cinco contas e o que a
    gestão vê: a memória, os temas da Validação, o cenário e o contrato."""
    _credenciais_locais()
    for pid, nome, email, cargo, perfil in (*PESSOAS, *FATURISTAS_DO_PAINEL):
        _rest(
            "participantes",
            "POST",
            [
                {
                    "id": pid,
                    "nome_completo": nome,
                    "email": email,
                    "cargo": cargo,
                    "setor": "Faturamento",
                    "ativo": True,
                    "access_profile": "regular",
                    "is_super_admin": False,
                    "is_externo": False,
                    "perfil_contas_medicas": perfil,
                    "auth_user_id": _login_de_exemplo(email),
                }
            ],
            prefer="resolution=merge-duplicates",
        )

    sigla, nome = OPERADORA
    existente = _rest(f"cm_operadora?sigla=eq.{sigla}&select=id")
    operadora_id = existente[0]["id"] if existente else _criar("cm_operadora", {"sigla": sigla, "nome": nome})["id"]
    if not _rest(f"cm_operadora_plano?nome_mv=eq.{urllib.parse.quote(PLANO)}&select=id"):
        _criar("cm_operadora_plano", {"operadora_id": operadora_id, "nome_mv": PLANO, "coluna_preco": "COMUM"})
    if not _rest(f"cm_setor?nome_mv=eq.{urllib.parse.quote(SETOR[0])}&select=id"):
        _criar("cm_setor", {"nome_mv": SETOR[0], "acomodacao": SETOR[1]})

    for pid, *_ in (FATURISTA, *FATURISTAS_DO_PAINEL):
        _apagar_contas_de_exemplo(pid)

    feitas = [dict(l, estado="FEITO") if i < 2 else l for i, l in enumerate(LINHAS_DO_GUIA[:4])]
    _conta("900398", operadora_id, 1, "EM_CORRECAO", feitas, rotulo="José M.", idade=58,
           numero_conta="51190", periodo_inicio="2026-09-28", periodo_fim="2026-10-02", total_lancado=9320.00)
    _conta(ATENDIMENTO_DO_GUIA, operadora_id, 2, "A_FAZER", LINHAS_DO_GUIA,
           numero_conta="51230", periodo_inicio="2026-10-03", periodo_fim="2026-10-08", total_lancado=TOTAL_DO_GUIA)

    envio = _criar("cm_envio", {"usuario_id": FATURISTA[0]})
    _conta("900431", operadora_id, 3, "AGUARDANDO_ARQUIVO", [], rotulo="Clara D.", idade=34,
           numero_conta="51302", periodo_inicio="2026-10-05", periodo_fim="2026-10-09")
    conta_sem_prontuario = _rest("cm_conta?numero_conta=eq.51302&faturista_id=eq.P950&select=id,atendimento_id")[0]
    arquivo = _criar("cm_arquivo", {"envio_id": envio["id"], "tipo": "CONTA",
                                    "atendimento_id": conta_sem_prontuario["atendimento_id"],
                                    "numero_atendimento": "900431", "paginas": 4})
    _rest(f"cm_conta?id=eq.{conta_sem_prontuario['id']}", "PATCH", {"arquivo_id": arquivo["id"]})

    _conta("900377", operadora_id, 4, "ERRO", [], rotulo="Paulo R.", idade=71, numero_conta="51288",
           erro_motivo="Este PDF não tem texto. Exporte de novo pelo MV")
    # A conta das telas do reenvio: três linhas Feito, duas que entram e uma
    # diária que sai, mais a linha bloqueada que a Validação abre. Concluída
    # na semana do Painel.
    concluidas = [dict(LINHAS_DO_GUIA[i], estado="FEITO") for i in (0, 3, 5)] + [
        _linha(
            "INCLUIR", "2026-09-22", "POSTO 3", CODIGO_BLOQUEADO, "Cateter venoso central duplo lúmen",
            quantidade_lancada=0, quantidade_devida=1, preco_tabela=389.00, valor_diferenca=389.00,
            regra_codigo="AURORA-PRI-01", motivo="Na evolução de enfermagem, sem item na conta.",
            nivel_evidencia="REGISTRADO", causa_raiz="CADASTRO_PRECO", confianca="ALTA", estado="BLOQUEADO",
        )
    ]
    _conta("900355", operadora_id, 0, "CONCLUIDA", concluidas, rotulo="Lia F.", idade=45,
           numero_conta=CONTA_CONCLUIDA, periodo_inicio="2026-09-20", periodo_fim="2026-09-26",
           total_lancado=6210.00, concluida_em="2026-10-09T16:40:00-03:00", custo_usd=0.1034)
    _semear_painel(operadora_id)

    _semear_gestao(operadora_id, base)
    print("dados de exemplo do módulo Contas médicas prontos.")


# --------------------------------------------------------------------------
# A gestão: memória, Validação, Coordenação e Contratos
# --------------------------------------------------------------------------


def _token(email: str) -> str:
    """O acesso da pessoa de exemplo, pelo login do Supabase local."""
    url, chave = _credenciais_locais()
    corpo = json.dumps({"email": email, "password": SENHA}).encode()
    req = urllib.request.Request(
        f"{url}/auth/v1/token?grant_type=password",
        data=corpo,
        headers={"apikey": chave, "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=20) as resposta:
        return json.load(resposta)["access_token"]


def _subir_memoria(base: str) -> None:
    """A memória sintética entra pela rota da tela, como a gestora faria: é o
    servidor que lê o arquivo e cria a versão vigente."""
    fronteira = "----manual-contas-medicas"
    corpo = (
        f"--{fronteira}\r\n"
        'Content-Disposition: form-data; name="arquivo"; filename="MEMORIA-AURORA-v1.0.md"\r\n'
        "Content-Type: text/markdown\r\n\r\n"
        f"{MEMORIA}\r\n--{fronteira}--\r\n"
    ).encode()
    req = urllib.request.Request(
        f"{base}/api/contas-medicas/operadoras/memoria",
        data=corpo,
        headers={
            "Authorization": f"Bearer {_token(GESTORA[2])}",
            "Content-Type": f"multipart/form-data; boundary={fronteira}",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60):
            pass
    except urllib.error.HTTPError as e:
        raise SystemExit(f"memória de exemplo: {e.code} {e.read().decode()[:300]}")


def _semear_gestao(operadora_id: str, base: str) -> None:
    """A memória vigente, a conta com regra nova desde a análise, três temas da
    Validação, o cenário com dois lembretes e o contrato em Negociar reajuste."""
    from datetime import date, timedelta

    # As versões antigas da AURORA saem antes: o Histórico de versões do print
    # mostra só a memória de hoje e a edição do roteiro. Versão que alguma
    # conta de outro teste ainda aponta fica, e o roteiro segue.
    try:
        _rest(f"cm_memoria_versao?operadora_id=eq.{operadora_id}&vigente=eq.false", "DELETE")
    except SystemExit as erro:
        print(f"aviso: versões antigas da {OPERADORA[0]} ficaram ({erro}).")
    _subir_memoria(base)
    versoes = _rest(f"cm_memoria_versao?operadora_id=eq.{operadora_id}&select=id&order=criado_em.desc&limit=2")
    contas = {c["numero_conta"]: c["id"] for c in _rest(f"cm_conta?faturista_id=eq.{FATURISTA[0]}&select=id,numero_conta")}
    # A 51230 foi analisada com a memória de hoje; a 51190, com a anterior.
    _rest(f"cm_conta?id=eq.{contas['51230']}", "PATCH", {"memoria_versao_id": versoes[0]["id"]})
    if len(versoes) > 1:
        _rest(f"cm_conta?id=eq.{contas['51190']}", "PATCH", {"memoria_versao_id": versoes[1]["id"]})

    # Validação: os temas da AURORA e o do código bloqueado são refeitos do zero.
    _rest(f"cm_validacao_tema?operadora_id=eq.{operadora_id}", "DELETE")
    _rest(f"cm_validacao_tema?codigo_item=eq.{CODIGO_BLOQUEADO}", "DELETE")
    ids = ",".join(contas.values())
    validar = _rest(f"cm_guia_linha?conta_id=in.({ids})&acao=eq.VALIDAR&regra_codigo=eq.AURORA-DIA-02&select=id")
    tema = _criar("cm_validacao_tema", {"operadora_id": operadora_id, "tipo": "REGRA_PENDENTE",
                                        "titulo": "Regra AURORA-DIA-02", "regra_codigo": "AURORA-DIA-02"})
    for linha in validar:
        _criar("cm_validacao_tema_linha", {"tema_id": tema["id"], "guia_linha_id": linha["id"]})

    bloqueada = _rest(f"cm_guia_linha?conta_id=eq.{contas['51102']}&codigo=eq.{CODIGO_BLOQUEADO}&select=id")[0]
    tema = _criar("cm_validacao_tema", {"tipo": "BLOQUEADO", "titulo": f"Código {CODIGO_BLOQUEADO} bloqueado",
                                        "codigo_item": CODIGO_BLOQUEADO})
    _criar("cm_validacao_tema_linha", {"tema_id": tema["id"], "guia_linha_id": bloqueada["id"]})

    observacao = _criar("cm_observacao", {
        "conta_id": contas["51102"], "autor_id": FATURISTA[0],
        "texto": "A AURORA-MED-02 vale para a dose extra? O pantoprazol de resgate não está na prescrição de horário.",
    })
    tema = _criar("cm_validacao_tema", {
        "operadora_id": operadora_id, "tipo": "OBSERVACAO", "titulo": "Observações sobre a regra AURORA-MED-02",
        "regra_codigo": "AURORA-MED-02",
        "leitura_ia": "A regra atual não cobre o caso. Ela fala da prescrição de horário fixo; a dose de resgate "
                      "fica de fora. Sugestão: editar a regra.",
    })
    _criar("cm_validacao_tema_linha", {"tema_id": tema["id"], "observacao_id": observacao["id"]})

    # O termo que a IA propôs ao dicionário: a fila abre o tema dele sozinha.
    # Apagar o termo apaga o tema antigo junto.
    _rest(f"cm_item_dicionario?termo=eq.{urllib.parse.quote(TERMO_DO_DICIONARIO)}", "DELETE")
    _criar("cm_item_dicionario", {"termo": TERMO_DO_DICIONARIO, "codigo_conta": "70060310",
                                  "descricao_conta": "Seringa preenchida com soro fisiológico 10 ml",
                                  "origem": "IA", "situacao": "PROPOSTO"})

    # Coordenação: o cenário de exemplo e um lembrete em cada conta. Os
    # lembretes antigos saíram com as contas antigas.
    _rest(f"cm_cenario?codigo=eq.{CENARIO}", "DELETE")
    insumos = [
        ("70044120", "Sonda Foley 2 vias nº 14", 18.40),
        ("70044210", "Coletor de urina sistema fechado", 12.90),
        ("90076530", "Lidocaína gel 2% 30 g", 9.70),
    ]
    cenario = _criar("cm_cenario", {
        "codigo": CENARIO, "nome": "Sondagem vesical de demora", "operadora_id": operadora_id,
        "gatilho_texto": "Sondagem vesical de demora registrada na evolução de enfermagem.",
        "orientacao": "Confira a sonda, o coletor e a lidocaína gel no dia da sondagem.",
        "autor_id": GESTORA[0],
    })
    for codigo, descricao, _preco in insumos:
        _criar("cm_cenario_item", {"cenario_id": cenario["id"], "codigo": codigo, "descricao": descricao, "quantidade": 1})
    for conta, dia, setor, pagina, faltam in (
        ("51102", "2026-09-22", "POSTO 3", 87, insumos[:2]),
        ("51190", "2026-09-29", "CTI ADULTO", 54, insumos[2:]),
    ):
        lembrete = _criar("cm_lembrete", {
            "conta_id": contas[conta], "cenario_id": cenario["id"], "data": dia, "setor": setor,
            "evidencia_pagina": pagina,
            "evidencia_trecho": "SVD PASSADA COM TÉCNICA ASSÉPTICA, SONDA FOLEY 14, SEM INTERCORRÊNCIAS",
        })
        for codigo, descricao, preco in faltam:
            _criar("cm_lembrete_item", {"lembrete_id": lembrete["id"], "codigo": codigo, "descricao": descricao,
                                        "quantidade": 1, "preco_tabela": preco, "valor": preco})

    # Contratos: a vigência do último aditivo faz o vencimento cair daqui a 45
    # dias, calculado (vigência mais um ano), e o aviso de 60 dias já passou.
    hoje = date.today()
    vencimento = hoje + timedelta(days=45)
    _rest(f"cm_contrato?operadora_id=eq.{operadora_id}", "DELETE")
    _criar("cm_contrato", {
        "operadora_id": operadora_id, "data_assinatura": "2023-03-01", "aditivo_numero": "2",
        "aditivo_data": (vencimento - timedelta(days=380)).isoformat(),
        "vigencia_inicio": vencimento.replace(year=vencimento.year - 1).isoformat(),
        "vencimento": vencimento.isoformat(), "vencimento_calculado": True, "aviso_dias": 60,
    })


# As linhas que o Painel soma: (código, item, ação, valor, causa-raiz, nível).
# Códigos e preços inventados.
ITENS_DO_PAINEL = [
    ("90123456", "Pantoprazol 40 mg injetável", "INCLUIR", 68.40, "DISPENSACAO", "PRESCRITO"),
    ("70044190", "Equipo de bomba de infusão", "INCLUIR", 86.00, "REGRA_AUTOMATICA", "REGISTRADO"),
    ("90155012", "Dipirona 1 g injetável", "INCLUIR", 12.60, "DISPENSACAO", "PRESCRITO_SN"),
    ("60034021", "Oxigênio, até 3 L/min, por hora", "AJUSTAR_QUANTIDADE", 55.50, "LANCAMENTO_MANUAL", "REGISTRADO"),
    ("70072210", "Bolsa coletora de urina", "INCLUIR", 32.40, "REGISTRO_ASSISTENCIAL", "REGISTRADO"),
    ("70038812", "Cateter venoso central duplo lúmen", "CORRIGIR_PRECO", -48.00, "CADASTRO_PRECO", None),
    ("70060022", "Cateter nasal de oxigênio", "INCLUIR", 14.90, "LANCAMENTO_MANUAL", "PRESCRITO"),
    ("60010450", "Taxa de sala de observação", "RETIRAR", -95.00, "REGRA_AUTOMATICA", "POR_REGRA"),
    ("90187733", "Ondansetrona 4 mg injetável", "INCLUIR", 9.85, "DISPENSACAO", "REGISTRADO"),
    ("70081975", "Curativo com filme transparente", "INCLUIR", 41.80, "REGISTRO_ASSISTENCIAL", "REGISTRADO"),
]


def _semear_painel(operadora_id: str) -> None:
    """Oito semanas de contas concluídas das duas faturistas do Painel.

    A conta fica maior a cada semana e as linhas são as mesmas, então a nota
    média sobe: é o desenho que o Painel quer mostrar. Na semana escolhida, uma
    linha Não procede e uma conta com pendência.
    """
    from datetime import date, timedelta

    segunda = date.fromisoformat(SEMANA_DO_PAINEL)
    numero = 900600
    for semana in range(8):
        inicio = segunda - timedelta(weeks=7 - semana)
        quantas = 3 if semana == 7 else 2
        for k in range(quantas):
            numero += 1
            escolhidos = [ITENS_DO_PAINEL[(semana + k + i * 3) % len(ITENS_DO_PAINEL)] for i in range(4)]
            if semana == 7 and k == 0:
                escolhidos.append(ITENS_DO_PAINEL[9])
            linhas = []
            for i, (codigo, item, acao, valor, causa, nivel) in enumerate(escolhidos):
                estado = "FEITO"
                if semana == 7 and k == 1 and i == 0:
                    estado = "NAO_PROCEDE"
                if semana == 7 and k == 2 and i == 3:
                    estado = "ABERTA"
                linhas.append(
                    _linha(acao, inicio.isoformat(), "POSTO 3", codigo, item, valor_diferenca=valor,
                           preco_tabela=abs(valor),
                           causa_raiz=causa, nivel_evidencia=nivel, regra_codigo="AURORA-PRI-01",
                           confianca="ALTA", estado=estado)
                )
            pendencia = any(l["estado"] == "ABERTA" for l in linhas)
            dia = inicio + timedelta(days=1 + k)
            _conta(
                str(numero), operadora_id, 0, "CONCLUIDA_COM_PENDENCIA" if pendencia else "CONCLUIDA", linhas,
                faturista=FATURISTAS_DO_PAINEL[k % 2][0], rotulo="Teo B.", idade=50 + k,
                numero_conta=str(52000 + numero % 1000), total_lancado=1400.00 + 380 * semana,
                concluida_em=f"{dia.isoformat()}T15:00:00-03:00", custo_usd=round(0.08 + 0.01 * k + 0.002 * semana, 4),
            )


def _guia_a_fazer() -> None:
    """Abrir o guia muda A fazer para Em correção: cada print começa do mesmo lugar."""
    _rest(
        f"cm_conta?faturista_id=eq.{FATURISTA[0]}&numero_conta=eq.51230",
        "PATCH",
        {"situacao": "A_FAZER", "aberta_em": None},
    )


# --------------------------------------------------------------------------
# Prints
# --------------------------------------------------------------------------


def entrar(page: Page, base: str, email: str) -> None:
    """Login com a pessoa de exemplo. Cada print nasce num contexto novo."""
    page.goto(f"{base}/login", wait_until="networkidle")
    page.get_by_placeholder("seu@email.com").fill(email)
    page.get_by_placeholder("••••••••").fill(SENHA)
    page.get_by_role("button", name="Entrar").click()
    page.wait_for_url(lambda url: "/login" not in url, timeout=30000)


def _contas(page: Page, base: str, email: str = FATURISTA[2]) -> None:
    entrar(page, base, email)
    page.goto(f"{base}/contas-medicas", wait_until="networkidle")
    page.get_by_text("Atendimento 900412").wait_for()


def _menu(page: Page):
    return page.locator("aside a[href='/contas-medicas']").first


def contas(page: Page, base: str, saida: Path) -> None:
    """A tela inteira, para a Visão geral: sem balão, não ilustra passo."""
    _guia_a_fazer()
    _contas(page, base)
    sem_foco(page)
    page.screenshot(path=str(saida / "contas.png"), clip={"x": 0, "y": 0, "width": 1440, "height": 760})


def envio(page: Page, base: str, saida: Path) -> None:
    """Enviar, passos 1 e 2: o item do menu e o Selecionar arquivos."""
    _guia_a_fazer()
    _contas(page, base)
    sem_foco(page)
    balao(page, _menu(page), 1)
    balao(page, page.get_by_role("button", name="Selecionar arquivos"), 2)
    page.screenshot(path=str(saida / "envio.png"), clip={"x": 0, "y": 0, "width": 1440, "height": 420})
    limpar_baloes(page)


def ultimo_envio(page: Page, base: str, saida: Path) -> None:
    """Enviar, passo 3: o quadro Último envio, com a resposta de exemplo."""
    _guia_a_fazer()
    _contas(page, base)
    page.route(
        "**/api/contas-medicas/envios",
        lambda rota: rota.fulfill(status=200, content_type="application/json", body=json.dumps(RESPOSTA_DO_ENVIO)),
    )
    pdf = b"%PDF-1.4\n%exemplo do manual\n"
    page.locator("input[type=file][aria-label='Arquivos da conta e do prontuário']").set_input_files(
        [
            {"name": "conta-900412.pdf", "mimeType": "application/pdf", "buffer": pdf},
            {"name": "prontuario-900412.pdf", "mimeType": "application/pdf", "buffer": pdf},
            {"name": "conta-900450.pdf", "mimeType": "application/pdf", "buffer": pdf},
        ]
    )
    quadro = page.get_by_role("region", name="Último envio")
    quadro.wait_for()
    page.wait_for_load_state("networkidle")
    sem_foco(page)
    balao(page, quadro.get_by_role("heading", name="Último envio"), 3)
    caixa = quadro.bounding_box()
    page.screenshot(
        path=str(saida / "ultimo-envio.png"),
        clip={"x": caixa["x"] - 44, "y": caixa["y"] - 20, "width": caixa["width"] + 64, "height": caixa["height"] + 40},
    )
    limpar_baloes(page)


def fila(page: Page, base: str, saida: Path) -> None:
    """Enviar, passo 4: a fila com uma conta de cada situação."""
    _guia_a_fazer()
    _contas(page, base)
    sem_foco(page)
    secao = page.get_by_role("region", name="Fila de contas")
    balao(page, page.get_by_role("tab", name="Fila (4)"), 4)
    caixa = secao.bounding_box()
    page.screenshot(
        path=str(saida / "fila.png"),
        clip={"x": caixa["x"] - 40, "y": caixa["y"] - 70, "width": caixa["width"] + 60, "height": caixa["height"] + 78},
    )
    limpar_baloes(page)


def fila_abrir(page: Page, base: str, saida: Path) -> None:
    """Corrigir, passo 1: o Abrir da conta A fazer."""
    _guia_a_fazer()
    _contas(page, base)
    sem_foco(page)
    secao = page.get_by_role("region", name="Fila de contas")
    linha = secao.locator("li").filter(has_text="Atendimento 900412")
    balao(page, linha.get_by_role("link", name="Abrir"), 1, "acima")
    caixa = secao.bounding_box()
    page.screenshot(
        path=str(saida / "fila-abrir.png"),
        clip={"x": caixa["x"] - 40, "y": caixa["y"] - 70, "width": caixa["width"] + 60, "height": caixa["height"] + 78},
    )
    limpar_baloes(page)


def _guia(page: Page, base: str) -> None:
    _guia_a_fazer()
    _contas(page, base)
    page.get_by_role("region", name="Fila de contas").locator("li").filter(
        has_text="Atendimento 900412"
    ).get_by_role("link", name="Abrir").click()
    page.get_by_role("heading", name="Atendimento 900412").wait_for()
    page.wait_for_load_state("networkidle")


def _linha_do_guia(page: Page, nome: str):
    return page.locator(f"article[aria-label='{nome}']")


def guia(page: Page, base: str, saida: Path) -> None:
    """Corrigir, passo 2: o cabeçalho, os três números e o primeiro grupo."""
    _guia(page, base)
    sem_foco(page)
    balao(page, page.get_by_text("Nota de entrada", exact=True), 2)
    page.screenshot(path=str(saida / "guia.png"), clip={"x": 0, "y": 0, "width": 1440, "height": 760})
    limpar_baloes(page)


def guia_linha(page: Page, base: str, saida: Path) -> None:
    """Corrigir, passo 3: a linha com o código, a evidência aberta e o Feito."""
    _guia(page, base)
    linha = _linha_do_guia(page, "Pantoprazol 40 mg injetável")
    linha.get_by_role("button", name="Ver evidência").click()
    sem_foco(page)
    balao(page, linha.get_by_role("button", name="Feito"), 3)
    linha.scroll_into_view_if_needed()
    caixa = linha.bounding_box()
    page.screenshot(
        path=str(saida / "guia-linha.png"),
        clip={"x": caixa["x"] - 44, "y": caixa["y"] - 40, "width": caixa["width"] + 64, "height": caixa["height"] + 60},
    )
    limpar_baloes(page)


def guia_nao_procede(page: Page, base: str, saida: Path) -> None:
    """Corrigir, passo 4: os quatro motivos do Não procede, sem confirmar."""
    _guia(page, base)
    linha = _linha_do_guia(page, "Agulha hipodérmica 25 x 7")
    linha.get_by_role("button", name="Não procede").click()
    linha.get_by_label("A regra é outra").check()
    sem_foco(page)
    balao(page, linha.locator("legend"), 4)
    linha.scroll_into_view_if_needed()
    caixa = linha.bounding_box()
    page.screenshot(
        path=str(saida / "guia-nao-procede.png"),
        clip={"x": caixa["x"] - 44, "y": caixa["y"] - 40, "width": caixa["width"] + 64, "height": caixa["height"] + 60},
    )
    limpar_baloes(page)


def guia_concluir(page: Page, base: str, saida: Path) -> None:
    """Corrigir, passo 6: a observação e o Concluir e abrir a próxima, sem clicar."""
    _guia(page, base)
    rodape = page.locator("footer").filter(has_text="Concluir e abrir a próxima")
    rodape.locator("#observacao-gestao").fill(
        "A ficha anestésica cita um segundo cateter que não achei na conta."
    )
    sem_foco(page)
    balao(page, rodape.get_by_role("button", name="Concluir e abrir a próxima"), 6)
    rodape.scroll_into_view_if_needed()
    caixa = rodape.bounding_box()
    page.screenshot(
        path=str(saida / "guia-concluir.png"),
        clip={"x": caixa["x"] - 44, "y": caixa["y"] - 40, "width": caixa["width"] + 64, "height": caixa["height"] + 60},
    )
    limpar_baloes(page)


# A linha "se necessário" sem registro de uso (PRD #1128), como o servidor a
# monta (`services/contas_medicas/conferencia.py`). Ela entra só na resposta
# do guia que o print recebe, e não no banco: a fila da Renata fica igual.
LINHA_SE_NECESSARIO = {
    "id": "00000000-0000-4000-8000-000000000951",
    "acao": "INCLUIR",
    "data": "2026-10-05",
    "data_fim": "2026-10-06",
    "setor": "CTI ADULTO",
    "codigo": "90155012",
    "descricao": "Dipirona 1 g injetável",
    "quantidade_lancada": 0,
    "quantidade_devida": 2,
    "preco_tabela": 6.30,
    "valor_diferenca": 12.60,
    "regra_codigo": "AURORA-MED-02",
    "motivo": "Confira a checagem em papel. Sem uso, marque NÃO PROCEDE.",
    "evidencia_pagina": 118,
    "evidencia_trecho": "DIPIRONA 1G EV SE DOR OU FEBRE",
    "nivel_evidencia": "PRESCRITO_SN",
    "causa_raiz": "DISPENSACAO",
    "confianca": "ALTA",
    "origem": "CODIGO",
    "estado": "ABERTA",
}


def guia_se_necessario(page: Page, base: str, saida: Path) -> None:
    """A linha "se necessário", com a etiqueta amarela e o texto fixo."""

    def com_a_linha(rota):
        resposta = rota.fetch()
        guia = resposta.json()
        grupo = next((g for g in guia["grupos"] if g["setor"] == "CTI ADULTO"), guia["grupos"][0])
        grupo["linhas"].insert(0, dict(LINHA_SE_NECESSARIO, data=grupo["data"]))
        rota.fulfill(response=resposta, json=guia)

    page.route("**/api/contas-medicas/contas/*/guia", com_a_linha)
    _guia(page, base)
    linha = _linha_do_guia(page, LINHA_SE_NECESSARIO["descricao"])
    linha.scroll_into_view_if_needed()
    sem_foco(page)
    caixa = linha.bounding_box()
    page.screenshot(
        path=str(saida / "guia-se-necessario.png"),
        clip={"x": caixa["x"] - 24, "y": caixa["y"] - 20, "width": caixa["width"] + 48, "height": caixa["height"] + 40},
    )


def _concluidas(page: Page, base: str) -> None:
    _contas(page, base)
    page.get_by_role("tab", name="Concluídas (1)").click()
    page.get_by_text("Atendimento 900355").wait_for()


def _sem_reenvio() -> None:
    """A conta concluída volta a estar sem reenvio: cada print começa do mesmo lugar."""
    _rest(
        f"cm_conta?faturista_id=eq.{FATURISTA[0]}&numero_conta=eq.{CONTA_CONCLUIDA}",
        "PATCH",
        {"nota_saida": None, "reenviada_em": None, "faltantes": None},
    )


def concluidas_abrir(page: Page, base: str, saida: Path) -> None:
    """Reenviar, passo 2: a aba Concluídas e o Abrir da conta."""
    _sem_reenvio()
    _concluidas(page, base)
    sem_foco(page)
    secao = page.get_by_role("region", name="Fila de contas")
    linha = secao.locator("li").filter(has_text="Atendimento 900355")
    balao(page, page.get_by_role("tab", name="Concluídas (1)"), 2, "acima")
    balao(page, linha.get_by_role("link", name="Abrir"), 2, "acima")
    caixa = secao.bounding_box()
    page.screenshot(
        path=str(saida / "concluidas-abrir.png"),
        clip={"x": caixa["x"] - 40, "y": caixa["y"] - 104, "width": caixa["width"] + 60, "height": caixa["height"] + 112},
    )
    limpar_baloes(page)


def _guia_concluido(page: Page, base: str) -> None:
    _concluidas(page, base)
    page.get_by_role("region", name="Fila de contas").locator("li").filter(
        has_text="Atendimento 900355"
    ).get_by_role("link", name="Abrir").click()
    page.get_by_role("heading", name="Atendimento 900355").wait_for()
    page.wait_for_load_state("networkidle")


def reenviar(page: Page, base: str, saida: Path) -> None:
    """Reenviar, passo 3: o rodapé da conta concluída, sem enviar."""
    _sem_reenvio()
    _guia_concluido(page, base)
    rodape = page.locator("footer").filter(has_text="Reenviar conta corrigida")
    sem_foco(page)
    balao(page, rodape.get_by_role("button", name="Reenviar conta corrigida"), 3)
    rodape.scroll_into_view_if_needed()
    caixa = rodape.bounding_box()
    page.screenshot(
        path=str(saida / "reenviar.png"),
        clip={"x": caixa["x"] - 44, "y": caixa["y"] - 20, "width": caixa["width"] + 64, "height": caixa["height"] + 40},
    )
    limpar_baloes(page)


def reenvio_resultado(page: Page, base: str, saida: Path) -> None:
    """Reenviar, passo 4: o resultado de um reenvio, com a nota de saída.

    Ler a conta corrigida pede PDF do MV, que é dado de paciente. O roteiro
    grava no banco local o resultado que o servidor gravaria (duas linhas
    corrigidas, a diária ainda na conta) e responde o envio com o mesmo
    resumo; a tela que desenha tudo é a do app.
    """
    _sem_reenvio()
    conta = _rest(f"cm_conta?faturista_id=eq.{FATURISTA[0]}&numero_conta=eq.{CONTA_CONCLUIDA}&select=id")[0]
    linhas = _rest(f"cm_guia_linha?conta_id=eq.{conta['id']}&select=id,acao&estado=eq.FEITO")
    marcas = {l["id"]: ("AINDA_NA_CONTA" if l["acao"] == "RETIRAR" else "CORRIGIDA") for l in linhas}
    # A nota de saída pela mesma conta do servidor: só a diária que continua,
    # sobre o total da conta corrigida (6.210,00 mais as duas que entraram).
    continua = [l for l in LINHAS_DO_GUIA if l["acao"] == "RETIRAR"]
    nota_saida = _nota(continua, 6210.00 + 68.40 + 9.85)[0]
    resumo = {"nota_saida": nota_saida, "corrigidas": 2, "ainda_na_conta": 1, "linhas": marcas}
    try:
        _guia_concluido(page, base)

        def responder(rota):
            _rest(
                f"cm_conta?id=eq.{conta['id']}",
                "PATCH",
                {"nota_saida": nota_saida, "reenviada_em": "2026-10-13T09:10:00-03:00",
                 "faltantes": {"reenvio": {"linhas": marcas}}},
            )
            rota.fulfill(status=200, content_type="application/json", body=json.dumps(resumo))

        page.route("**/api/contas-medicas/contas/*/reenvio", responder)
        page.locator("input[type=file][aria-label='PDF da conta corrigida']").set_input_files(
            {"name": "conta-900355.pdf", "mimeType": "application/pdf", "buffer": b"%PDF-1.4\n%exemplo do manual\n"}
        )
        page.get_by_text("Nota de saída", exact=True).wait_for()
        page.wait_for_load_state("networkidle")
        page.evaluate("window.scrollTo(0, 0)")
        sem_foco(page)
        balao(page, page.get_by_text("Nota de saída", exact=True), 4, "acima-inicio", rolar=False)
        page.screenshot(path=str(saida / "reenvio-resultado.png"), clip={"x": 0, "y": 0, "width": 1440, "height": 900})
        limpar_baloes(page)
    finally:
        _sem_reenvio()


def _painel(page: Page, base: str) -> None:
    entrar(page, base, GESTORA[2])
    page.goto(f"{base}/contas-medicas/painel", wait_until="networkidle")
    page.locator("input[aria-label='Semana']").fill(SEMANA_DO_PAINEL)
    page.get_by_role("button", name="Operadora").or_(page.get_by_label("Operadora")).first.click()
    page.get_by_role("option", name=OPERADORA[0], exact=True).click()
    page.get_by_text("Semana de 05/10").wait_for()
    page.wait_for_load_state("networkidle")


def contas_painel(page: Page, base: str, saida: Path) -> None:
    """Painel, passo 1: o botão Painel na tela de contas."""
    entrar(page, base, GESTORA[2])
    page.goto(f"{base}/contas-medicas", wait_until="networkidle")
    botao = page.get_by_role("link", name="Painel")
    botao.wait_for()
    sem_foco(page)
    balao(page, botao, 1)
    page.screenshot(path=str(saida / "contas-painel.png"), clip={"x": 0, "y": 0, "width": 1440, "height": 420})
    limpar_baloes(page)


def painel(page: Page, base: str, saida: Path) -> None:
    """Painel, passos 2 e 3: os filtros e os cartões do topo."""
    page.set_viewport_size({"width": COMPUTADOR["width"], "height": 1000})
    _painel(page, base)
    sem_foco(page)
    balao(page, page.locator("input[aria-label='Semana']"), 2)
    balao(page, page.get_by_role("region", name="Nota média de entrada"), 3)
    # A janela alta cabe a segunda fileira de cartões (a da coordenação, para
    # quem tem a Conferência da coordenação), em vez de cortá-la ao meio.
    page.screenshot(path=str(saida / "painel.png"), clip={"x": 0, "y": 0, "width": 1440, "height": 664})
    limpar_baloes(page)


def painel_blocos(page: Page, base: str, saida: Path) -> None:
    """Painel, passos 4, 5 e 6: causa-raiz, itens que faltam e produção."""
    page.set_viewport_size({"width": COMPUTADOR["width"], "height": 2000})
    _painel(page, base)
    sem_foco(page)
    causa = page.get_by_role("region", name="R$ apontado por causa-raiz")
    itens = page.get_by_role("region", name="Os dez itens que mais faltam")
    producao = page.get_by_role("region", name="Produção por faturista")
    balao(page, causa.get_by_role("heading"), 4, rolar=False)
    balao(page, itens.get_by_role("heading"), 5, rolar=False)
    balao(page, producao.get_by_role("heading"), 6, rolar=False)
    topo = min(causa.bounding_box()["y"], itens.bounding_box()["y"])
    caixas = [causa.bounding_box(), itens.bounding_box(), producao.bounding_box()]
    esquerda = min(c["x"] for c in caixas)
    direita = max(c["x"] + c["width"] for c in caixas)
    baixo = max(c["y"] + c["height"] for c in caixas)
    page.screenshot(
        path=str(saida / "painel-blocos.png"),
        clip={"x": esquerda - 44, "y": topo - 20, "width": direita - esquerda + 64, "height": baixo - topo + 40},
    )
    limpar_baloes(page)


def _operadoras(page: Page, base: str) -> None:
    entrar(page, base, GESTORA[2])
    page.goto(f"{base}/contas-medicas/operadoras", wait_until="networkidle")
    page.get_by_role("heading", name="Operadoras", exact=True).first.wait_for()


def _secao(page: Page, nome: str):
    return page.get_by_role("region", name=nome)


def _capturar_ate(page: Page, secao, fim, arquivo: Path) -> None:
    """Do topo da seção até o fim de `fim`, com folga à esquerda para o balão.

    Recortar pelo elemento cortaria o balão, que fica 6 px para fora dele; e
    a tabela de planos e setores embaixo do formulário lista o que outros
    testes deixaram no banco local, que não é exemplo do manual.
    """
    # O recorte é em coordenada da janela: uma janela alta faz a seção caber
    # inteira, em vez de pedir a página inteira e errar a conta da rolagem.
    page.set_viewport_size({"width": COMPUTADOR["width"], "height": 1800})
    secao.scroll_into_view_if_needed()
    topo = secao.bounding_box()
    baixo = fim.bounding_box()
    page.screenshot(
        path=str(arquivo),
        clip={
            "x": topo["x"] - 44,
            "y": topo["y"] - 12,
            "width": topo["width"] + 64,
            "height": baixo["y"] + baixo["height"] - topo["y"] + 22,
        },
    )


def contas_operadoras(page: Page, base: str, saida: Path) -> None:
    """Memória, passo 1: o botão Operadoras, que só a gestão vê."""
    entrar(page, base, GESTORA[2])
    page.goto(f"{base}/contas-medicas", wait_until="networkidle")
    botao = page.get_by_role("link", name="Operadoras")
    botao.wait_for()
    sem_foco(page)
    balao(page, botao, 1, "acima")
    page.screenshot(path=str(saida / "contas-operadoras.png"), clip={"x": 0, "y": 0, "width": 1440, "height": 420})
    limpar_baloes(page)


def enviar_memoria(page: Page, base: str, saida: Path) -> None:
    """Memória, passos 2 e 3: a memória sintética sobe de verdade."""
    _operadoras(page, base)
    secao = _secao(page, "Enviar memória")
    secao.locator("input[type=file]").set_input_files(
        {"name": "MEMORIA-AURORA-v1.0.md", "mimeType": "text/markdown", "buffer": MEMORIA.encode()}
    )
    secao.get_by_role("button", name="Enviar memória").click()
    secao.get_by_role("status").wait_for()
    sem_foco(page)
    balao(page, secao.get_by_role("button", name="Enviar memória"), 2)
    balao(page, secao.get_by_role("status"), 3)
    _capturar_ate(page, secao, secao, saida / "enviar-memoria.png")
    limpar_baloes(page)


def _escolher(page: Page, secao, rotulo: str, opcao: str) -> None:
    secao.get_by_role("button", name=rotulo).or_(secao.get_by_label(rotulo)).first.click()
    page.get_by_role("option", name=opcao, exact=True).click()


def _biblioteca_da_aurora(page: Page):
    """O bloco da AURORA na Biblioteca de tabelas: o título e a tabela dela."""
    secao = _secao(page, "Biblioteca de tabelas")
    return secao, secao.get_by_role("table", name=f"Tabelas de preço de {OPERADORA[0]}")


def _nova_versao_de_materiais(page: Page):
    """O "Nova versão" da linha Materiais da AURORA, que abre o envio já escolhido."""
    _, tabela = _biblioteca_da_aurora(page)
    return tabela.get_by_role("row").filter(has_text="Materiais").get_by_role("button", name="Nova versão")


def biblioteca(page: Page, base: str, saida: Path) -> None:
    """Memória, passo 4: o Nova versão da biblioteca, só no bloco da AURORA."""
    _operadoras(page, base)
    secao, tabela = _biblioteca_da_aurora(page)
    sem_foco(page)
    balao(page, _nova_versao_de_materiais(page), 4, "acima")
    titulo = secao.get_by_role("heading", name=OPERADORA[0], exact=True)
    topo, baixo = titulo.bounding_box(), tabela.bounding_box()
    page.screenshot(
        path=str(saida / "biblioteca.png"),
        clip={"x": baixo["x"] - 44, "y": topo["y"] - 14, "width": baixo["width"] + 64,
              "height": baixo["y"] + baixo["height"] - topo["y"] + 28},
    )
    limpar_baloes(page)


def enviar_tabela(page: Page, base: str, saida: Path) -> None:
    """Memória, passo 5: o envio aberto pelo Nova versão, preenchido, sem enviar."""
    _operadoras(page, base)
    _nova_versao_de_materiais(page).click()
    secao = _secao(page, "Enviar tabela de preço")
    secao.get_by_label("Início da vigência").fill("2026-10-01")
    secao.locator("input[type=file]").set_input_files(
        {"name": "AURORA-materiais-2026-10.csv", "mimeType": "text/csv", "buffer": b"codigo;descricao;preco\n"}
    )
    sem_foco(page)
    balao(page, secao.get_by_role("button", name="Enviar tabela"), 5)
    _capturar_ate(page, secao, secao, saida / "enviar-tabela.png")
    limpar_baloes(page)


def mapeamento(page: Page, base: str, saida: Path) -> None:
    """Memória, passo 6: as colunas que a IA propôs e a amostra, sem gravar.

    A planilha de exemplo não sai da máquina: a leitura responde com
    `PROPOSTA_DO_MAPEAMENTO`, e quem desenha a proposta é a tela do app."""
    _operadoras(page, base)
    page.route(
        "**/tabelas/proposta",
        lambda rota: rota.fulfill(status=200, content_type="application/json",
                                  body=json.dumps(PROPOSTA_DO_MAPEAMENTO)),
    )
    _nova_versao_de_materiais(page).click()
    secao = _secao(page, "Enviar tabela de preço")
    secao.get_by_label("Início da vigência").fill("2026-10-01")
    secao.locator("input[type=file]").set_input_files(
        {"name": "AURORA-materiais-2026-10.xlsx",
         "mimeType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "buffer": b"PK"}
    )
    secao.get_by_role("button", name="Enviar tabela").click()
    proposta = secao.get_by_role("region", name="Mapeamento das colunas")
    proposta.wait_for()
    sem_foco(page)
    balao(page, proposta.get_by_role("button", name="Confirmar e gravar"), 6, "acima")
    _capturar_ate(page, proposta, proposta, saida / "mapeamento.png")
    limpar_baloes(page)


def operadora(page: Page, base: str, saida: Path) -> None:
    """Editar a regra, passo 1: só a linha da operadora de exemplo, sem as dos testes."""
    _operadoras(page, base)
    linha = page.get_by_test_id(f"operadora-{OPERADORA[0]}")
    sem_foco(page)
    balao(page, linha.get_by_text(OPERADORA[0], exact=True), 1)
    caixa = linha.bounding_box()
    page.screenshot(
        path=str(saida / "operadora.png"),
        clip={"x": caixa["x"] - 44, "y": caixa["y"] - 12, "width": caixa["width"] + 64, "height": caixa["height"] + 24},
    )
    limpar_baloes(page)


def planos(page: Page, base: str, saida: Path) -> None:
    """Planos e setores, passos 2 e 3: o plano preenchido, sem cadastrar."""
    _operadoras(page, base)
    secao = _secao(page, "Planos do MV")
    secao.get_by_label("Nome no MV").fill("AURORA MASTER QC")
    _escolher(page, secao, "Operadora", OPERADORA[0])
    secao.get_by_label("Coluna de preço").fill("COMUM")
    sem_foco(page)
    balao(page, secao.get_by_label("Nome no MV"), 2)
    balao(page, secao.get_by_role("button", name="Cadastrar plano"), 3)
    _capturar_ate(page, secao, secao.locator("form"), saida / "planos.png")
    limpar_baloes(page)


def setores(page: Page, base: str, saida: Path) -> None:
    """Planos e setores, passos 4 e 5: o setor preenchido, sem cadastrar."""
    _operadoras(page, base)
    secao = _secao(page, "Setores do MV")
    secao.get_by_label("Nome no MV").fill("UTI ADULTO 2")
    _escolher(page, secao, "Acomodação", "CTI")
    sem_foco(page)
    balao(page, secao.get_by_label("Nome no MV"), 4)
    balao(page, secao.get_by_role("button", name="Cadastrar setor"), 5)
    _capturar_ate(page, secao, secao.locator("form"), saida / "setores.png")
    limpar_baloes(page)


# --------------------------------------------------------------------------
# A gestão (PRD #1129)
# --------------------------------------------------------------------------


def _recortar(page: Page, primeiro, ultimo, arquivo: Path, folga_esquerda: int = 44) -> None:
    """Do topo de `primeiro` ao fim de `ultimo`, com folga para o balão."""
    topo, baixo = primeiro.bounding_box(), ultimo.bounding_box()
    esquerda = min(topo["x"], baixo["x"])
    direita = max(topo["x"] + topo["width"], baixo["x"] + baixo["width"])
    page.screenshot(
        path=str(arquivo),
        clip={
            "x": esquerda - folga_esquerda,
            "y": topo["y"] - 14,
            "width": direita - esquerda + folga_esquerda + 20,
            "height": baixo["y"] + baixo["height"] - topo["y"] + 28,
        },
    )


def _alto(page: Page) -> None:
    """Uma janela alta: a mesma tela num monitor maior, e o recorte cabe nela."""
    page.set_viewport_size({"width": COMPUTADOR["width"], "height": 1800})


def _botao_do_menu(page: Page, nome: str):
    import re

    return page.locator("main").get_by_role("link", name=re.compile(rf"^{nome}")).first


def _print_do_menu(page: Page, base: str, email: str, nome: str, arquivo: Path) -> None:
    """O passo 1 das telas da gestão: o botão no alto da tela Contas médicas."""
    entrar(page, base, email)
    page.goto(f"{base}/contas-medicas", wait_until="networkidle")
    botao = _botao_do_menu(page, nome)
    botao.wait_for()
    page.wait_for_load_state("networkidle")
    sem_foco(page)
    # Acima: à esquerda o balão cairia em cima do botão vizinho.
    balao(page, botao, 1, "acima")
    page.screenshot(path=str(arquivo), clip={"x": 0, "y": 0, "width": 1440, "height": 420})
    limpar_baloes(page)


def _memoria(page: Page, base: str) -> None:
    entrar(page, base, GESTORA[2])
    page.goto(f"{base}/contas-medicas/operadoras/{OPERADORA[0]}", wait_until="networkidle")
    page.get_by_role("heading", name=f"Memória da operadora {OPERADORA[0]}").wait_for()
    page.wait_for_load_state("networkidle")


def regras(page: Page, base: str, saida: Path) -> None:
    """Editar a regra, passos 2 e 3: a aba Pendentes e o Decidir da regra pendente."""
    _memoria(page, base)
    _alto(page)
    secao = page.get_by_role("region", name="Regras", exact=True)
    aba = secao.get_by_role("tab", name="Pendentes (1)")
    aba.click()
    sem_foco(page)
    balao(page, aba, 2, "acima")
    balao(page, secao.get_by_test_id("regra-AURORA-DIA-02").get_by_role("button", name="Decidir"), 3)
    _recortar(page, secao, secao, saida / "regras.png")
    limpar_baloes(page)


def _abrir_edicao(page: Page):
    linha = page.get_by_test_id("regra-AURORA-MED-02")
    linha.get_by_role("button", name="Editar").click()
    formulario = page.get_by_role("form", name="Editar a regra AURORA-MED-02")
    formulario.locator("textarea").fill(
        "Prescrição de horário fixo é cobrada em todos os dias prescritos, inclusive o dia da alta."
    )
    return linha, formulario


def regra_editar(page: Page, base: str, saida: Path) -> None:
    """Editar a regra, passos 4 e 5: o formulário aberto e preenchido, sem salvar."""
    _memoria(page, base)
    _alto(page)
    linha, formulario = _abrir_edicao(page)
    sem_foco(page)
    balao(page, formulario.locator("textarea"), 4)
    balao(page, formulario.get_by_role("button", name="Salvar"), 5)
    _recortar(page, linha, formulario, saida / "regra-editar.png")
    limpar_baloes(page)


def historico(page: Page, base: str, saida: Path) -> None:
    """Editar a regra, passo 6: salva de verdade e mostra a versão nova no histórico.

    A versão é da operadora de exemplo, e o `--semear` sobe a memória de novo."""
    _memoria(page, base)
    _alto(page)
    _, formulario = _abrir_edicao(page)
    formulario.get_by_role("button", name="Salvar").click()
    page.get_by_role("status").filter(has_text="da memória criada").wait_for()
    page.wait_for_load_state("networkidle")
    secao = page.get_by_role("region", name="Histórico de versões")
    # A versão desta edição: a que traz o texto de antes e o de depois.
    primeira = secao.locator("li").filter(has_text="Depois:").first
    sem_foco(page)
    balao(page, primeira.locator("span.font-semibold").first, 6)
    _recortar(page, primeira, primeira, saida / "historico.png")
    limpar_baloes(page)


def ensinar_abrir(page: Page, base: str, saida: Path) -> None:
    """Ensinar, passo 1: o botão Ensinar uma regra nova na Memória da operadora."""
    _memoria(page, base)
    botao = page.get_by_role("button", name="Ensinar uma regra nova")
    sem_foco(page)
    balao(page, botao, 1)
    _recortar(page, page.get_by_role("region", name="Cabeçalho da memória"), botao, saida / "ensinar-abrir.png")
    limpar_baloes(page)


def _ensinar(page: Page, base: str):
    _memoria(page, base)
    _alto(page)
    page.get_by_role("button", name="Ensinar uma regra nova").click()
    secao = page.get_by_role("region", name="Ensinar uma regra nova")
    secao.locator("textarea").fill(PEDIDO_DA_REGRA)
    return secao


def ensinar(page: Page, base: str, saida: Path) -> None:
    """Ensinar, passo 2: a regra escrita em linguagem comum, sem propor."""
    secao = _ensinar(page, base)
    sem_foco(page)
    balao(page, secao.get_by_role("button", name="Propor regra"), 2)
    _recortar(page, secao, secao, saida / "ensinar.png")
    limpar_baloes(page)


def ensinar_proposta(page: Page, base: str, saida: Path) -> None:
    """Ensinar, passos 3 a 5: a proposta, sem validar.

    A IA não é chamada: o "Propor regra" responde com `PROPOSTA_DA_REGRA`."""
    secao = _ensinar(page, base)
    page.route(
        "**/regras/proposta",
        lambda rota: rota.fulfill(status=200, content_type="application/json", body=json.dumps(PROPOSTA_DA_REGRA)),
    )
    secao.get_by_role("button", name="Propor regra").click()
    proposta = page.get_by_role("form", name="Proposta da regra nova")
    proposta.wait_for()
    sem_foco(page)
    balao(page, proposta.get_by_role("heading", name="Antes"), 3, "acima-inicio")
    balao(page, proposta.locator("textarea"), 4)
    balao(page, proposta.get_by_role("button", name="Validar regra"), 5)
    _recortar(page, proposta, proposta, saida / "ensinar-proposta.png")
    limpar_baloes(page)


def reanalisar(page: Page, base: str, saida: Path) -> None:
    """Ensinar, passo 6: a conta analisada com a memória anterior e o Reanalisar."""
    _memoria(page, base)
    secao = page.get_by_role("region", name="Contas com regra nova desde a análise")
    sem_foco(page)
    balao(page, secao.get_by_role("button", name="Reanalisar com a regra nova").first, 6)
    _recortar(page, secao, secao, saida / "reanalisar.png")
    limpar_baloes(page)


def menu_validacao(page: Page, base: str, saida: Path) -> None:
    _print_do_menu(page, base, GESTORA[2], "Validação", saida / "menu-validacao.png")


def _validacao(page: Page, base: str) -> None:
    entrar(page, base, GESTORA[2])
    _alto(page)
    page.goto(f"{base}/contas-medicas/validacao", wait_until="networkidle")
    page.get_by_role("article", name="Regra AURORA-DIA-02").wait_for()
    page.wait_for_load_state("networkidle")


def validacao(page: Page, base: str, saida: Path) -> None:
    """Validação, passo 2: os três números e o primeiro cartão."""
    _validacao(page, base)
    sem_foco(page)
    balao(page, page.get_by_text("Aguardando decisão", exact=True), 2)
    _recortar(page, page.locator("main").get_by_role("link", name="Contas médicas"),
              page.get_by_role("article", name="Regra AURORA-DIA-02"), saida / "validacao.png")
    limpar_baloes(page)


def validacao_regra(page: Page, base: str, saida: Path) -> None:
    """Validação, passo 3: o texto da regra aberto para conferir, sem validar."""
    _validacao(page, base)
    cartao = page.get_by_role("article", name="Regra AURORA-DIA-02")
    cartao.get_by_role("button", name="Validar regra").click()
    sem_foco(page)
    balao(page, cartao.get_by_role("button", name="Confirmar e validar"), 3)
    _recortar(page, cartao, cartao, saida / "validacao-regra.png")
    limpar_baloes(page)


def validacao_temas(page: Page, base: str, saida: Path) -> None:
    """Validação, passos 4 a 6: o código bloqueado, a observação e o termo."""
    _validacao(page, base)
    bloqueado = page.get_by_role("article", name=f"Código {CODIGO_BLOQUEADO} bloqueado")
    observacao = page.get_by_role("article", name="Observações sobre a regra AURORA-MED-02")
    termos = page.locator("article").filter(has_text="Termo do dicionário")
    sem_foco(page)
    balao(page, bloqueado.get_by_role("button", name="Enviar ao cadastro"), 4)
    balao(page, observacao.get_by_role("button", name="Responder ao time"), 5, "acima")
    ultimo = observacao
    if termos.count():
        ultimo = termos.first
        balao(page, ultimo.get_by_role("button", name="Confirmar"), 6)
    _recortar(page, bloqueado, ultimo, saida / "validacao-temas.png")
    limpar_baloes(page)


def menu_coordenacao(page: Page, base: str, saida: Path) -> None:
    _print_do_menu(page, base, COORDENADORA[2], "Coordenação", saida / "menu-coordenacao.png")


def cenario(page: Page, base: str, saida: Path) -> None:
    """Coordenação, passos 2 e 3: o cenário novo preenchido à mão, sem salvar."""
    entrar(page, base, GESTORA[2])
    _alto(page)
    page.goto(f"{base}/contas-medicas/coordenacao", wait_until="networkidle")
    page.get_by_role("tab", name="Cenários").click()
    page.get_by_role("button", name="Novo cenário").click()
    novo = page.get_by_role("region", name="Novo cenário")
    novo.get_by_label("Escreva o cenário").fill(
        "Curativo de cateter venoso central: conferir a película transparente e a clorexidina."
    )
    novo.get_by_label("Nome").fill("Curativo de cateter central")
    novo.get_by_label("Operadora").select_option(OPERADORA[0])
    novo.get_by_label("Quando dispara").fill("Troca de curativo de cateter venoso central registrada na evolução.")
    novo.get_by_label("Orientação para a coordenadora").fill("Confira a película e a clorexidina no dia da troca.")
    novo.get_by_label("Código do insumo 1").fill("70051230")
    novo.get_by_label("Descrição do insumo 1").fill("Película transparente 10 x 12 cm")
    novo.get_by_role("button", name="Adicionar insumo").click()
    novo.get_by_label("Código do insumo 2").fill("90044410")
    novo.get_by_label("Descrição do insumo 2").fill("Clorexidina alcoólica 0,5% 100 ml")
    sem_foco(page)
    balao(page, novo.get_by_role("button", name="Preencher com a IA"), 2)
    balao(page, novo.get_by_role("button", name="Salvar cenário"), 3)
    _recortar(page, novo, novo, saida / "cenario.png")
    limpar_baloes(page)


def lembretes(page: Page, base: str, saida: Path) -> None:
    """Coordenação, passos 4 e 5: a conta com o lembrete e a evidência aberta."""
    entrar(page, base, COORDENADORA[2])
    _alto(page)
    page.goto(f"{base}/contas-medicas/coordenacao", wait_until="networkidle")
    conta = page.get_by_role("region", name="Atendimento 900355")
    conta.wait_for()
    conta.get_by_role("button", name="Ver evidência").first.click()
    sem_foco(page)
    balao(page, conta.get_by_role("button", name="Ver evidência").first, 4)
    balao(page, conta.get_by_role("button", name="Incluído").first, 5)
    _recortar(page, page.locator("main").get_by_role("link", name="Contas médicas"), conta, saida / "lembretes.png")
    limpar_baloes(page)


def menu_contratos(page: Page, base: str, saida: Path) -> None:
    _print_do_menu(page, base, GESTORA[2], "Contratos", saida / "menu-contratos.png")


def _contrato(page: Page, base: str):
    entrar(page, base, GESTORA[2])
    _alto(page)
    page.goto(f"{base}/contas-medicas/contratos", wait_until="networkidle")
    cartao = page.get_by_role("listitem").filter(has=page.get_by_text("Aurora Saúde", exact=True))
    cartao.wait_for()
    return cartao


def contratos(page: Page, base: str, saida: Path) -> None:
    """Contratos, passos 2 e 3: a situação do contrato e o botão de envio."""
    cartao = _contrato(page, base)
    sem_foco(page)
    balao(page, cartao.get_by_text("Negociar reajuste", exact=True), 2, "acima")
    balao(page, cartao.get_by_role("button", name="Enviar contrato ou aditivo"), 3)
    _recortar(page, cartao, cartao, saida / "contratos.png")
    limpar_baloes(page)


def contrato_form(page: Page, base: str, saida: Path) -> None:
    """Contratos, passos 4 e 5: os campos para conferir, sem confirmar."""
    cartao = _contrato(page, base)
    cartao.get_by_role("button", name="Enviar contrato ou aditivo").click()
    sem_foco(page)
    balao(page, cartao.get_by_text("Vencimento", exact=True).last, 4)
    balao(page, cartao.get_by_role("button", name="Confirmar"), 5)
    _recortar(page, cartao, cartao, saida / "contrato-form.png")
    limpar_baloes(page)


def menu_habilitacao(page: Page, base: str, saida: Path) -> None:
    _print_do_menu(page, base, DIRETORA[2], "Habilitação", saida / "menu-habilitacao.png")


def _habilitacao(page: Page, base: str) -> None:
    entrar(page, base, DIRETORA[2])
    _alto(page)
    page.goto(f"{base}/contas-medicas/habilitacao", wait_until="networkidle")
    page.get_by_role("heading", name="Habilitação", exact=True).wait_for()
    page.wait_for_load_state("networkidle")


def habilitacao_pessoa(page: Page, base: str, saida: Path) -> None:
    """Habilitação, passos 2 e 3: a busca e o perfil da pessoa, sem mudar."""
    _habilitacao(page, base)
    secao = page.get_by_role("region", name="Pessoas")
    secao.get_by_label("Buscar pessoa pelo nome").fill("Júlio")
    secao.get_by_role("button", name="Buscar").click()
    pessoa = secao.get_by_role("listitem", name=SEM_PERFIL[1])
    pessoa.wait_for()
    sem_foco(page)
    balao(page, secao.get_by_role("button", name="Buscar"), 2)
    balao(page, pessoa.get_by_role("combobox"), 3)
    _recortar(page, secao, secao, saida / "habilitacao-pessoa.png")
    limpar_baloes(page)


def habilitacao_matriz(page: Page, base: str, saida: Path) -> None:
    """Habilitação, passo 4: a célula que a coordenadora ainda não tem."""
    _habilitacao(page, base)
    secao = page.get_by_role("region", name="Perfis e permissões")
    sem_foco(page)
    balao(page, secao.get_by_label("Incluir regra operacional: Coordenadora de faturamento"), 4)
    _recortar(page, secao, secao, saida / "habilitacao-matriz.png")
    limpar_baloes(page)


def ditar(page: Page, base: str, saida: Path) -> None:
    """Ditar, passo 2: o botão Ditar e o aviso, no rodapé do guia."""
    _guia(page, base)
    rodape = page.locator("footer").filter(has_text="Concluir e abrir a próxima")
    botao = rodape.get_by_role("button", name="Ditar: Observação para a gestão de contas médicas")
    sem_foco(page)
    balao(page, botao, 2)
    rodape.scroll_into_view_if_needed()
    _recortar(page, rodape, rodape, saida / "ditar.png")
    limpar_baloes(page)


PRINTS = {
    "contas": contas,
    "envio": envio,
    "ultimo-envio": ultimo_envio,
    "fila": fila,
    "fila-abrir": fila_abrir,
    "guia": guia,
    "guia-linha": guia_linha,
    "guia-nao-procede": guia_nao_procede,
    "guia-concluir": guia_concluir,
    "guia-se-necessario": guia_se_necessario,
    "concluidas-abrir": concluidas_abrir,
    "reenviar": reenviar,
    "reenvio-resultado": reenvio_resultado,
    "contas-painel": contas_painel,
    "painel": painel,
    "painel-blocos": painel_blocos,
    "contas-operadoras": contas_operadoras,
    "enviar-memoria": enviar_memoria,
    "biblioteca": biblioteca,
    "enviar-tabela": enviar_tabela,
    "mapeamento": mapeamento,
    "operadora": operadora,
    "planos": planos,
    "setores": setores,
    "regras": regras,
    "regra-editar": regra_editar,
    "historico": historico,
    "ensinar-abrir": ensinar_abrir,
    "ensinar": ensinar,
    "ensinar-proposta": ensinar_proposta,
    "reanalisar": reanalisar,
    "menu-validacao": menu_validacao,
    "validacao": validacao,
    "validacao-regra": validacao_regra,
    "validacao-temas": validacao_temas,
    "menu-coordenacao": menu_coordenacao,
    "cenario": cenario,
    "lembretes": lembretes,
    "menu-contratos": menu_contratos,
    "contratos": contratos,
    "contrato-form": contrato_form,
    "menu-habilitacao": menu_habilitacao,
    "habilitacao-pessoa": habilitacao_pessoa,
    "habilitacao-matriz": habilitacao_matriz,
    "ditar": ditar,
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:3000")
    ap.add_argument("--saida", default="docs/manual/src/assets/contas-medicas")
    ap.add_argument("--print", dest="escolhido", choices=list(PRINTS), help="captura só um print.")
    ap.add_argument("--semear", action="store_true", help="cria os dados de exemplo no Supabase local e sai.")
    args = ap.parse_args()

    if args.semear:
        semear(args.base.rstrip("/"))
        return 0

    saida = Path(args.saida)
    saida.mkdir(parents=True, exist_ok=True)
    escolhidos = [args.escolhido] if args.escolhido else list(PRINTS)

    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        navegador = p.chromium.launch()
        try:
            for i, nome in enumerate(escolhidos):
                # Cada tela de contas pergunta as permissões uma vez por botão
                # do topo, e a rota aceita 60 perguntas por minuto: sem a
                # pausa, a décima tela leva 429 e o app manda para o início.
                if i:
                    time.sleep(PAUSA_ENTRE_PRINTS)
                # Sem o service worker do app: com ele, a leitura do guia não
                # passa pelo `page.route` e a linha de exemplo nunca chega.
                contexto = navegador.new_context(
                    viewport=COMPUTADOR, device_scale_factor=ESCALA, locale="pt-BR", service_workers="block"
                )
                try:
                    PRINTS[nome](contexto.new_page(), args.base.rstrip("/"), saida)
                finally:
                    contexto.close()
                print(f"print: {saida / (nome + '.png')}")
        finally:
            _guia_a_fazer()
            _sem_reenvio()
            navegador.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
