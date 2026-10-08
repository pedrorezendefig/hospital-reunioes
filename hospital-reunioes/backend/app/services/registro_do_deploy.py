"""O registro de uma subida, lido como o app precisa dele (issue #1065, ADR 0069).

Duas leituras, e as duas valem para os dois caminhos que marcam Em produção:
o webhook de deploy, que a Action pós-merge chama, e a reconciliação de hora em
hora, que lê o `history.json` da `main`.

Só biblioteca padrão, de propósito: a Action carrega este arquivo pelo caminho
(`tools/avisar_deploy_ao_app.py`) para montar o corpo do webhook com a MESMA
leitura que a reconciliação usa. Duas leituras do mesmo texto divergiriam, e a
issue que o webhook chama de "subiu" seria outra na passagem de hora em hora.
"""

from __future__ import annotations

import re

# A versão como a subida a grava ("0.169.0") ou como a tela a mostra
# ("v0.169.0"). Nada antes nem depois: um texto qualquer não vira versão.
_VERSAO = re.compile(r"v?(\d+\.\d+\.\d+)")


def versao_rotulada(bruta: object) -> str | None:
    """A versão no formato que a Demanda guarda e a tela mostra, `v0.169.0`,
    ou `None` quando o texto não é versão nenhuma."""
    if not isinstance(bruta, str):
        return None
    achado = _VERSAO.fullmatch(bruta.strip())
    return f"v{achado.group(1)}" if achado else None


# Um PR do lote nas `notes` do registro, como o `montar_registro` da subida o
# escreve (`fechar_onda.py`, rótulo do `rotulo_issues`):
#
# - na onda, "PR #1095 (issue #1064)" ou "PR #1101 (issues #700 #701)";
# - no PR avulso, "PR avulso: PR #1007, issue #1006.";
# - nos dois, "sem issue" quando o PR não fecha nenhuma.
#
# As issues vêm do `closingIssuesReferences` do GitHub, lido pela subida na hora
# do merge: é a mesma verdade que o `Closes #N` do corpo do PR. Entrada antiga,
# de antes deste formato, não casa e não lista PR nenhum.
_PR_DO_LOTE = re.compile(r"PR #(\d+)(?: \(|, )(?:issues? (#\d+(?: #\d+)*)|sem issue)")


def prs_do_registro(notas: object) -> list[dict]:
    """Os PRs do lote, cada um com as issues que fecha, na ordem do registro."""
    if not isinstance(notas, str):
        return []
    return [
        {"numero": int(pr), "fecha": [int(n) for n in re.findall(r"#(\d+)", issues)]}
        for pr, issues in _PR_DO_LOTE.findall(notas)
    ]


def aviso_da_entrada(entrada: object) -> dict | None:
    """O corpo do webhook de deploy para uma entrada do `history.json`:
    `{"versao", "data", "prs"}`. `None` quando a entrada não tem versão (as
    antigas podem não ter), porque não há o que dizer de uma subida sem ela."""
    if not isinstance(entrada, dict) or versao_rotulada(entrada.get("app_version")) is None:
        return None
    return {
        "versao": entrada["app_version"],
        "data": entrada.get("at"),
        "prs": prs_do_registro(entrada.get("notes")),
    }


def subida_de_cada_issue(deploys: object) -> dict[int, tuple[str, str]]:
    """Para cada issue que algum PR registrado fecha, a versão (rotulada) e a
    data da subida MAIS NOVA que a lista.

    A mais nova, e não a primeira: a issue reaberta para um ajuste volta a ser
    fechada por outro PR, e a Demanda que hoje está Entregue espera a subida
    desse fechamento, e não a do anterior. O `history.json` guarda a mais nova
    primeiro, então a primeira que aparece ganha.
    """
    subidas: dict[int, tuple[str, str]] = {}
    for entrada in deploys if isinstance(deploys, list) else []:
        aviso = aviso_da_entrada(entrada)
        if aviso is None or not isinstance(aviso["data"], str):
            continue
        versao = versao_rotulada(aviso["versao"])
        for pr in aviso["prs"]:
            for numero in pr["fecha"]:
                subidas.setdefault(numero, (versao, aviso["data"]))
    return subidas
