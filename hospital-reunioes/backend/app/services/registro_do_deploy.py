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
