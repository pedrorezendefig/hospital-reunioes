"""O Código do erro da conta (issue #1337, PRD #1335).

Todo caminho de Erro da análise passa por `classificar`: ela recebe a falha (a
leitura que não fecha, o erro da IA ou o defeito inesperado) e a etapa em que a
análise estava, e devolve o código, a frase para quem enviou, o detalhe técnico
para a TI, o arquivo afetado e a ação que resolve. Os códigos e as frases vivem
só aqui, no `CATALOGO`, em quatro famílias:

- `CM-ARQ-*`: o PDF tem problema, quem enviou manda outro (Enviar de novo);
- `CM-CFG-*`: falta configuração que a gestão faz no app (Analisar de novo);
- `CM-IA-*`: a IA não respondeu ou recusou (Analisar de novo, menos o tamanho,
  que repetir não resolve);
- `CM-APP-*`: defeito do app ou análise que não terminou, para a TI.

O detalhe técnico guarda o tipo do erro, o código HTTP, a etapa, o arquivo e a
linha do código. Nunca a mensagem da exceção nem a da resposta da IA: as duas
podem citar o prontuário.

O arquivo afetado é o da etapa em que a análise parou: a leitura da conta e as
etapas que comparam a conta apontam a Conta; a leitura do prontuário, o
dicionário e o Passo A apontam o Prontuário.
"""

from __future__ import annotations

import traceback
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal

from app.services.contas_medicas.ia import ErroDaIA

Arquivo = Literal["conta", "prontuario"]
Acao = Literal["analisar_de_novo", "enviar_de_novo"]

ANALISAR_DE_NOVO: Acao = "analisar_de_novo"
ENVIAR_DE_NOVO: Acao = "enviar_de_novo"

# A etapa como quem enviou lê, na frase do defeito e da análise que não terminou.
ETAPAS = {
    "texto_da_conta": "leitura do PDF da conta",
    "leitura_da_conta": "leitura da conta",
    "texto_do_prontuario": "leitura do PDF do prontuário",
    "leitura_do_prontuario": "leitura do prontuário",
    "dicionario": "consulta do dicionário",
    "conferencia": "conferência",
    "passo_a": "leitura do prontuário pela IA",
    "conferencia_com_eventos": "conferência com a leitura da IA",
    "passo_b": "comparação com a memória pela IA",
    "gravacao": "gravação do guia",
}

_DO_PRONTUARIO = frozenset({"texto_do_prontuario", "leitura_do_prontuario", "dicionario", "passo_a"})


@dataclass(frozen=True)
class _Linha:
    codigo: str
    frase: str
    acao: Acao | None


# A causa da falha, o código, a frase e a ação. A frase pode levar números da
# leitura (`{soma}`, `{paginas}`) ou a etapa (`{etapa}`).
CATALOGO: dict[str, _Linha] = {
    # O PDF: quem enviou manda outro.
    "sem_texto": _Linha("CM-ARQ-SEM-TEXTO", "Este PDF não tem texto. Exporte de novo pelo MV", ENVIAR_DE_NOVO),
    "ilegivel": _Linha(
        "CM-ARQ-ILEGIVEL",
        "Não consegui ler o PDF. Confira se ele abre no computador e envie de novo.",
        ENVIAR_DE_NOVO,
    ),
    "grande": _Linha(
        "CM-ARQ-GRANDE", "O PDF tem {paginas} páginas e é grande demais para ler de uma vez.", ENVIAR_DE_NOVO
    ),
    "soma": _Linha(
        "CM-ARQ-SOMA",
        "Não consegui ler a conta inteira: os itens lidos somam R$ {soma} e o total da conta é R$ {total}.",
        ENVIAR_DE_NOVO,
    ),
    "sem_total": _Linha(
        "CM-ARQ-SOMA",
        "Não consegui ler a conta inteira: os itens lidos somam R$ {soma} e o PDF não traz o total da conta.",
        ENVIAR_DE_NOVO,
    ),
    "item": _Linha(
        "CM-ARQ-SOMA",
        "Não consegui ler a conta inteira: no item {codigo} da página {pagina}, a quantidade vezes o unitário dá "
        "R$ {esperado} e a linha traz R$ {linha}.",
        ENVIAR_DE_NOVO,
    ),
    "cabecalho": _Linha("CM-ARQ-CABECALHO", "Não achei o atendimento e o plano no cabeçalho da conta.", ENVIAR_DE_NOVO),
    "incompleto": _Linha(
        "CM-ARQ-INCOMPLETO",
        "Prontuário com arquivo incompleto: o rodapé indica {declarado} páginas e vieram {vieram}.",
        ENVIAR_DE_NOVO,
    ),
    "sem_prontuario": _Linha(
        "CM-ARQ-SEM-PRONTUARIO",
        "O prontuário deste atendimento não está no sistema. Envie o prontuário de novo.",
        ENVIAR_DE_NOVO,
    ),
    "vencido": _Linha("CM-ARQ-VENCIDO", "O PDF já passou dos 7 dias e saiu do sistema.", ENVIAR_DE_NOVO),
    # As folhas digitalizadas que sustentam a conta não deram para ler (#1400).
    "digitalizada_da_cirurgia": _Linha(
        "CM-ARQ-DIGITALIZADO",
        "Não dá para analisar esta conta: {folha} é uma folha digitalizada que não consegui ler. "
        "Digitalize de novo, com a folha em pé, e envie o prontuário de novo.",
        ENVIAR_DE_NOVO,
    ),
    "digitalizadas_ilegiveis": _Linha(
        "CM-ARQ-DIGITALIZADO",
        "Não dá para analisar esta conta: {ilegiveis} das {paginas} páginas do prontuário deste período são "
        "folhas digitalizadas que não consegui ler. Digitalize de novo essas folhas, em pé, e envie o "
        "prontuário de novo.",
        ENVIAR_DE_NOVO,
    ),
    # A configuração: a gestão carrega, e a conta é analisada de novo.
    "sem_memoria": _Linha(
        "CM-CFG-MEMORIA",
        "A operadora {operadora} está sem memória carregada. A gestão carrega em Operadoras.",
        ANALISAR_DE_NOVO,
    ),
    # A IA.
    "chave": _Linha("CM-IA-CHAVE", "A chave da IA não está configurada.", ANALISAR_DE_NOVO),
    "credito": _Linha("CM-IA-CREDITO", "A IA está sem crédito. Avise o Pedro.", ANALISAR_DE_NOVO),
    "modelo": _Linha("CM-IA-MODELO", "O modelo da IA não foi encontrado.", ANALISAR_DE_NOVO),
    "fora_do_ar": _Linha("CM-IA-FORA-DO-AR", "A IA está fora do ar ou sobrecarregada agora.", ANALISAR_DE_NOVO),
    "tamanho": _Linha("CM-IA-TAMANHO", "O prontuário é maior do que a IA aceita de uma vez.", None),
    "formato": _Linha("CM-IA-FORMATO", "A resposta da IA veio fora do formato combinado.", ANALISAR_DE_NOVO),
    # Gravado só pela migration 122, nas contas com a frase de antes.
    "antigo": _Linha("CM-IA-ANTIGO", "Tente de novo em alguns minutos", ANALISAR_DE_NOVO),
    # O app.
    "defeito": _Linha("CM-APP-DEFEITO", "A análise parou na {etapa} por um defeito do app.", ANALISAR_DE_NOVO),
    "tentativas": _Linha(
        "CM-APP-TENTATIVAS",
        "A análise não terminou em três tentativas: o app reiniciou ou travou na {etapa}.",
        ANALISAR_DE_NOVO,
    ),
}

# A recusa da IA que não é de chave, crédito, modelo nem tamanho (um 400 de
# campo inválido, por exemplo) é a requisição que o app montou errado.
_CAUSA_DA_IA = {"recusa": "defeito"}


class FalhaDeLeitura(Exception):  # noqa: N818, a leitura que não fecha, não um defeito
    """Leitura que não fecha: Erro na hora, sem nova tentativa (o mesmo arquivo
    daria o mesmo erro). `causa` é a linha do catálogo e `dados`, os números da
    frase. Nada aqui vem do texto do prontuário."""

    def __init__(self, causa: str, **dados: Any):
        super().__init__(causa)
        self.causa = causa
        self.dados = dados


@dataclass(frozen=True)
class ErroDaConta:
    codigo: str
    frase: str
    detalhe: dict[str, Any] = field(default_factory=dict)
    arquivo: Arquivo | None = None
    acao: Acao | None = None


def _onde(erro: BaseException) -> tuple[str | None, int | None]:
    """O arquivo e a linha do código onde o erro nasceu: o lugar, sem a mensagem."""
    quadros = traceback.extract_tb(erro.__traceback__)
    if not quadros:
        return None, None
    return Path(quadros[-1].filename).name, quadros[-1].lineno


def _reais(valor: Decimal) -> str:
    return f"{valor:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")


def _rotulo_da_etapa(etapa: str | None) -> str:
    return ETAPAS.get(etapa or "", "análise")


def arquivo_da_etapa(etapa: str | None) -> Arquivo | None:
    """O quadrado do cartão que fica vermelho: o do arquivo em que a análise parou."""
    if etapa is None or etapa not in ETAPAS:
        return None
    return "prontuario" if etapa in _DO_PRONTUARIO else "conta"


def _erro(causa: str, etapa: str | None, detalhe: dict[str, Any], **dados: Any) -> ErroDaConta:
    linha = CATALOGO[causa]
    valores = {chave: _reais(valor) if isinstance(valor, Decimal) else valor for chave, valor in dados.items()}
    return ErroDaConta(
        codigo=linha.codigo,
        frase=linha.frase.format(etapa=_rotulo_da_etapa(etapa), **valores),
        detalhe={"etapa": etapa, **detalhe},
        arquivo=arquivo_da_etapa(etapa),
        acao=linha.acao,
    )


def classificar(erro: BaseException, etapa: str | None) -> ErroDaConta:
    """O Erro da conta para a falha que parou a análise na `etapa`."""
    arquivo, linha = _onde(erro)
    detalhe = {"tipo": type(erro).__name__, "http": None, "arquivo": arquivo, "linha": linha}
    if isinstance(erro, FalhaDeLeitura):
        return _erro(erro.causa, etapa, detalhe, **erro.dados)
    if isinstance(erro, ErroDaIA):
        # O tipo é o do erro da última tentativa (o do SDK ou o da validação).
        detalhe |= {"tipo": erro.tipo, "http": erro.http}
        return _erro(_CAUSA_DA_IA.get(erro.causa, erro.causa), etapa, detalhe)
    return _erro("defeito", etapa, detalhe)


def tentativas_esgotadas(etapa: str | None) -> ErroDaConta:
    """A conta que ficou presa em PROCESSANDO na terceira tentativa: o app
    reiniciou ou travou no meio da `etapa`, e não há exceção para ler."""
    return _erro("tentativas", etapa, {"tipo": "PrazoDaAnaliseEsgotado", "http": None, "arquivo": None, "linha": None})


def acao_do_codigo(codigo: str | None) -> Acao | None:
    """A ação da conta em Erro, pelo código gravado."""
    return next((linha.acao for linha in CATALOGO.values() if linha.codigo == codigo), None)


def detalhe_legivel(detalhe: dict[str, Any] | None) -> str | None:
    """O detalhe técnico numa linha, como "Ver detalhes" mostra e "Copiar para
    a TI" leva: o tipo, o código HTTP, a etapa, o lugar no código e, depois do
    OCR, quantas folhas digitalizadas saíram em cada faixa (#1398)."""
    if not detalhe:
        return None
    partes = [detalhe.get("tipo") or "Erro"]
    if detalhe.get("http") is not None:
        partes.append(f"HTTP {detalhe['http']}")
    if detalhe.get("etapa"):
        partes.append(f"etapa {detalhe['etapa']} ({_rotulo_da_etapa(detalhe['etapa'])})")
    if detalhe.get("arquivo"):
        partes.append(f"{detalhe['arquivo']}:{detalhe.get('linha')}")
    if contagem := detalhe.get("digitalizadas"):
        faixas = ", ".join(f"{_FAIXA_NO_DETALHE.get(faixa, faixa)} {n}" for faixa, n in contagem.items())
        partes.append(f"digitalizadas: {faixas}")
    return ", ".join(partes)


_FAIXA_NO_DETALHE = {"legivel": "legível", "duvidosa": "duvidosa", "ilegivel": "ilegível", "nao_lida": "não lida"}
