"""As ferramentas de leitura do codigo do agente da aba (issue #1385, ADR 0077, decisao 5).

O Assistente de Tecnologia, alem do Kit, le o repositorio publico pela API do
GitHub, so pelo `github_client`: um arquivo, a busca no codigo, o `CONTEXT.md`
ou uma ADR aceita, e as issues abertas. Nada escreve: as quatro ferramentas
caem em GETs do adapter.

Dois tetos, que moram aqui e nao no prompt:

* **consultas por turno** (`TETO_DE_CONSULTAS`): passada a conta, a consulta
  volta com o aviso do teto e o turno pede ao modelo a resposta com o que ja
  tem (`esgotou`);
* **tamanho por arquivo** (`TETO_DO_ARQUIVO`): o arquivo maior chega cortado,
  com o aviso do corte.

Falha do GitHub nao derruba o turno: a consulta volta com o erro, e o modelo
segue com o que sabe. `Consultas` e uma por turno e guarda as issues abertas
que o modelo viu, que e por onde o turno confere a "parecida" antes de avisar
o diretor.
"""

from __future__ import annotations

import logging
import re

from app.services import github_client

logger = logging.getLogger(__name__)

TETO_DE_CONSULTAS = 8
TETO_DO_ARQUIVO = 20_000

TEXTO_DO_TETO = "O teto de consultas deste turno acabou. Responda com o que você já sabe."
TEXTO_DO_CORTE = "\n\n(arquivo cortado em {teto} caracteres)"
TEXTO_NAO_ENCONTRADO = "Não encontrei isso no repositório."
TEXTO_INDISPONIVEL = "Não consegui consultar o repositório agora. Siga com o que você já sabe."
TEXTO_ADR_NAO_ACEITA = "Essa ADR não está aceita: não vale como decisão da casa."
TEXTO_SEM_RESULTADO = "Nenhum resultado."

PASTA_DAS_ADRS = "docs/adr"
CONTEXTO = "CONTEXT.md"

_STATUS_ACEITA = re.compile(r"^status:\s*accepted\s*$", re.MULTILINE)

DEFINICOES: list[dict] = [
    {
        "name": "ler_arquivo",
        "description": "Lê um arquivo (ou lista uma pasta) do repositório do aplicativo, na versão em produção. "
        "O caminho é relativo à raiz, por exemplo hospital-reunioes/backend/app/routers/admin/tecnologia.py.",
        "input_schema": {
            "type": "object",
            "properties": {"caminho": {"type": "string", "description": "Caminho a partir da raiz do repositório."}},
            "required": ["caminho"],
        },
    },
    {
        "name": "buscar_no_codigo",
        "description": "Busca um termo no código do repositório e devolve os caminhos dos arquivos onde ele aparece.",
        "input_schema": {
            "type": "object",
            "properties": {"termo": {"type": "string", "description": "Palavra ou trecho a buscar."}},
            "required": ["termo"],
        },
    },
    {
        "name": "ler_contexto_ou_adr",
        "description": "Sem número, lê o CONTEXT.md, o glossário do domínio. Com o número de uma ADR, lê essa "
        "ADR, se ela estiver aceita.",
        "input_schema": {
            "type": "object",
            "properties": {"adr": {"type": "integer", "description": "Número da ADR. Omita para ler o CONTEXT.md."}},
        },
    },
    {
        "name": "listar_issues_abertas",
        "description": "Lista as issues abertas do repositório, número e título: os pedidos que já estão na fila.",
        "input_schema": {"type": "object", "properties": {}},
    },
]


def disponiveis() -> bool:
    """Sem a integracao do GitHub configurada, o turno roda sem ferramentas."""
    return github_client.integracao_configurada()


def _cortado(texto: str) -> str:
    if len(texto) <= TETO_DO_ARQUIVO:
        return texto
    return texto[:TETO_DO_ARQUIVO] + TEXTO_DO_CORTE.format(teto=TETO_DO_ARQUIVO)


def _como_texto(conteudo: str | list[str]) -> str:
    if isinstance(conteudo, list):
        return "Pasta com:\n" + "\n".join(conteudo)
    return _cortado(conteudo)


class Consultas:
    """As consultas de UM turno: a conta do teto e as issues abertas vistas."""

    def __init__(self) -> None:
        self.feitas = 0
        self.issues_vistas: dict[int, str] = {}

    @property
    def esgotou(self) -> bool:
        return self.feitas >= TETO_DE_CONSULTAS

    def executar(self, nome: str, entrada: dict | None) -> tuple[str, bool]:
        """O texto que volta ao modelo e se e erro."""
        if self.esgotou:
            return TEXTO_DO_TETO, True
        self.feitas += 1
        entrada = entrada if isinstance(entrada, dict) else {}
        try:
            return self._consultar(nome, entrada), False
        except github_client.IssueNaoEncontradaError:
            return TEXTO_NAO_ENCONTRADO, True
        except (github_client.GithubIndisponivelError, github_client.GithubNaoConfiguradoError) as erro:
            logger.warning("[Ferramentas] %s sem resposta do GitHub: %s", nome, type(erro).__name__)
            return TEXTO_INDISPONIVEL, True

    def _consultar(self, nome: str, entrada: dict) -> str:
        if nome == "ler_arquivo":
            return _como_texto(github_client.ler_do_repositorio(str(entrada.get("caminho") or "")))
        if nome == "buscar_no_codigo":
            return "\n".join(github_client.buscar_no_codigo(str(entrada.get("termo") or ""))) or TEXTO_SEM_RESULTADO
        if nome == "ler_contexto_ou_adr":
            return self._contexto_ou_adr(entrada.get("adr"))
        if nome == "listar_issues_abertas":
            issues = github_client.listar_issues_abertas()
            self.issues_vistas.update({i["numero"]: i["titulo"] for i in issues})
            return "\n".join(f"#{i['numero']}: {i['titulo']}" for i in issues) or TEXTO_SEM_RESULTADO
        raise github_client.IssueNaoEncontradaError(nome)

    def _contexto_ou_adr(self, numero) -> str:
        if numero is None:
            return _como_texto(github_client.ler_do_repositorio(CONTEXTO))
        try:
            prefixo = f"{int(numero):04d}-"
        except (TypeError, ValueError) as erro:
            raise github_client.IssueNaoEncontradaError(str(numero)) from erro
        nomes = github_client.ler_do_repositorio(PASTA_DAS_ADRS)
        nome = next((n for n in nomes if isinstance(nomes, list) and n.startswith(prefixo)), None)
        if nome is None:
            raise github_client.IssueNaoEncontradaError(prefixo)
        texto = github_client.ler_do_repositorio(f"{PASTA_DAS_ADRS}/{nome}")
        if not isinstance(texto, str) or not _STATUS_ACEITA.search(texto.split("\n---", 1)[0]):
            return TEXTO_ADR_NAO_ACEITA
        return _cortado(texto)
