"""Regras puras da aba Tecnologia (PRD #634, ADR 0050).

Sem I/O: quem fala com o Supabase e o router e os servicos ao lado. Desde a ADR
0077 a aba e o chat do agente, e o que sobrou aqui e o que o chat, a
sincronizacao da Etapa e o Anexo ainda leem (issue #1386).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.dependencies import is_super_admin
from app.services.github_client import FATO_ASSIGNEE
from app.services.tecnologia_vinculo import ETAPA_EM_PRODUCAO

# As tabelas da aba. Moram aqui, e nao no router, porque quem escreve nelas nao
# e so o router: o webhook do GitHub e o job de reconciliacao escrevem pelo
# `tecnologia_sincronizacao`, e um nome de tabela repetido em tres arquivos e
# uma renomeacao que passa em dois deles.
TABELA_DEMANDAS = "tecnologia_demandas"
TABELA_PRODUTOS = "tecnologia_produtos"

# O estado da Demanda de antes da ADR 0077, congelado na coluna ate o drop. A
# sincronizacao e o apagamento dos prints ainda o leem: a Demanda Concluida ou
# Cancelada a mao, no Quadro de antes, nao volta a ser tocada. Os dois grupos
# sao o COMPLEMENTO um do outro sobre o CHECK da migration 102, e o teste cobra
# isso (`test_admin_tecnologia.py`).
ESTADOS_ABERTOS: tuple[str, ...] = ("nova", "em_andamento", "aguardando")
ESTADOS_FECHADOS: tuple[str, ...] = ("concluida", "cancelada")

# O nome que a issue do bug leva quando a Demanda nao tem Produto.
SEM_PRODUTO = "(sem Produto)"

# O rotulo que a gente le de cada Tipo. O banco guarda o valor sem acento
# (CHECK da migration 102); o PRD do diretor escreve "Novo".
TIPO_ROTULO: dict[str, str] = {
    "decisao": "Decisão",
    "informacao": "Informação",
    "terceiro": "Terceiro",
    "ajuste": "Ajuste",
    "novo": "Novo",
    "defeito": "Defeito",
    "consultoria": "Consultoria",
}

RECUO_DA_CONTINUACAO = "    "


def instante_do_banco(valor: str | None) -> datetime | None:
    """O `TIMESTAMPTZ` do PostgREST como `datetime` consciente de fuso.

    Devolve `None` quando nao da para ler, e nunca "agora": um carimbo quebrado
    que virasse o instante atual seria uma janela (a da criacao do card, o
    prazo do print) aberta em cima de dado corrompido.

    Data sem fuso conta como UTC porque comparar um `datetime` ingenuo com um
    consciente estoura `TypeError`, e a janela viraria 500.
    """
    if not valor:
        return None
    try:
        lido = datetime.fromisoformat(str(valor))
    except ValueError:
        return None
    return lido if lido.tzinfo else lido.replace(tzinfo=UTC)


def recuar_continuacao(bloco: str) -> str:
    r"""As linhas depois da primeira entram recuadas.

    E o que impede um texto de varias linhas de derramar no nivel de cima e
    passar por moldura do prompt: a segunda linha de uma fala que diga
    "--- fim do kit ---" sai com quatro espacos na frente, e a marca que fecha
    a cerca continua sendo a unica que comeca na coluna zero.

    **Linha e o que o `splitlines()` diz que e linha** (issue #770). Com
    `split("\n")`, um `\r`, `\x0c` ou `\u2028` no corpo de uma issue nao virava
    linha aqui e escapava do recuo, mas virava linha para quem LE o prompt, e
    a marca de fim voltava para a coluna zero. O criterio e o proprio
    `splitlines()`, e nao uma tabela de caracteres: tabela e enumeracao, e foi
    enumeracao que divergiu do detector no PR #751. A saida so tem `\n`.

    A normalizacao mora AQUI, e nao em quem chama, porque esta funcao e o
    gargalo de todas as cercas do prompt (o `_cercar` do assistente, o kit e a
    conversa do chat). O `splitlines()` descarta a linha vazia final de um
    `"a\n"`, que o `split` mantinha como uma linha so de recuo.

    Docstring cru (prefixo `r`) de proposito: os separadores citados aqui nao
    podem virar quebra de verdade dentro dele.
    """
    primeira, *resto = bloco.splitlines() or [""]
    return "\n".join([primeira, *(f"{RECUO_DA_CONTINUACAO}{linha}" for linha in resto)])


def versao_da_entrega(demanda: dict[str, Any]) -> str | None:
    """A versao do app em que a Demanda subiu, so quando a Etapa e Em producao.

    A coluna pode guardar a versao de uma subida anterior com a Etapa que voltou
    atras (a issue reaberta para um ajuste): mostrar "v0.160.0" ao lado de
    "Entregue" diria que ja esta no ar o que ainda nao esta.
    """
    if demanda.get("etapa") != ETAPA_EM_PRODUCAO:
        return None
    return demanda.get("versao_em_producao") or None


def e_desenvolvedor(pessoa: dict[str, Any] | None) -> bool:
    """O Super admin com login do GitHub no cadastro (ADR 0083, decisao 2).

    Nao e perfil nem permissao propria: e o cadastro que diz. Login so de
    espacos conta como sem login.
    """
    return is_super_admin(pessoa) and bool(str((pessoa or {}).get("github_login") or "").strip())


def pode_ver(pessoa: dict[str, Any], demanda: dict[str, Any]) -> bool:
    """Quem ve uma Demanda: o autor, e o Desenvolvedor, que ve todas (ADR 0083).

    A regra e uma so, e a lista e a leitura da conversa leem daqui.
    """
    return demanda.get("autor_id") == pessoa.get("id") or e_desenvolvedor(pessoa)


def responsavel_da_demanda(demanda: dict[str, Any]) -> str | None:
    """O id do Responsavel, que so existe depois do "Criar o card" (ADR 0083,
    decisao 5).

    A conversa sem card nao tem Responsavel, mesmo com a coluna preenchida: a
    Demanda de antes desta versao nascia com o dono do Produto ali, e ninguem o
    escolheu.
    """
    if not demanda.get("github_issue_numero"):
        return None
    return demanda.get("responsavel_id") or None


def login_do_responsavel(demanda: dict[str, Any]) -> str | None:
    """O login do dono da issue, como a foto o guardou, ou `None`.

    E o que a tela mostra quando o dono do GitHub nao e usuario do app (issue
    #1534, ADR 0083, decisao 6): sem `responsavel_id`, o Responsavel aparece
    pelo login. A conversa sem card nao tem dono, como em
    `responsavel_da_demanda`.
    """
    if not demanda.get("github_issue_numero"):
        return None
    foto = demanda.get("github_foto")
    login = foto.get(FATO_ASSIGNEE) if isinstance(foto, dict) else None
    return login if isinstance(login, str) and login else None
