"""O Vinculo da Demanda com a issue do GitHub, sem I/O (issue #674, ADR 0054).

Tudo aqui e funcao pura: a tabela de Etapas, o marcador oculto que a issue
carrega no corpo, a comparacao entre a foto nova e a guardada, e os textos das
linhas automaticas da Conversa.

O I/O mora ao lado, no `github_client.py`. A separacao nao e gosto de arquivo:
a Etapa e a regra que o diretor le na tela, e ela precisa ser testavel nas seis
saidas e na precedencia entre elas sem depender de rede nenhuma. O cliente e
dublado nos testes; isto aqui e chamado de verdade.
"""

from __future__ import annotations

import re
from typing import Any

# ─── 1. A Etapa ──────────────────────────────────────────────────────────────

# As seis, na ordem em que a entrega anda (ADR 0054, decisao 3). A mesma lista
# do CHECK da migration 103; o teste amarra as duas pontas.
ETAPA_REGISTRADA = "registrada"
ETAPA_EM_ANALISE = "em_analise"
ETAPA_PLANEJADA = "planejada"
ETAPA_EM_DESENVOLVIMENTO = "em_desenvolvimento"
ETAPA_ENTREGUE = "entregue"
ETAPA_NAO_SERA_FEITA = "nao_sera_feita"

ETAPAS = (
    ETAPA_REGISTRADA,
    ETAPA_EM_ANALISE,
    ETAPA_PLANEJADA,
    ETAPA_EM_DESENVOLVIMENTO,
    ETAPA_ENTREGUE,
    ETAPA_NAO_SERA_FEITA,
)

# O rotulo em palavras do diretor. Ele NAO ve label, numero nem estado de issue:
# ve estas seis frases (ADR 0054, decisao 9).
ETAPA_ROTULO: dict[str, str] = {
    ETAPA_REGISTRADA: "Registrada",
    ETAPA_EM_ANALISE: "Em análise",
    ETAPA_PLANEJADA: "Planejada",
    ETAPA_EM_DESENVOLVIMENTO: "Em desenvolvimento",
    ETAPA_ENTREGUE: "Entregue",
    ETAPA_NAO_SERA_FEITA: "Não será feita",
}

# As labels que a Etapa le. Sao as do protocolo de triagem
# (docs/agents/triage-labels.md), e nao uma lista nova.
LABEL_EM_ANDAMENTO = "in-progress"
LABEL_WONTFIX = "wontfix"
LABELS_PLANEJADA = ("ready-for-agent", "ready-for-human")

# Como o GitHub diz que a issue fechou.
FECHAMENTO_CONCLUIDA = "completed"


def _labels(no: dict[str, Any] | None) -> set[str]:
    """As labels de um no da foto, sempre em minusculas."""
    if not no:
        return set()
    return {str(nome).strip().lower() for nome in (no.get("labels") or [])}


def _fechada(no: dict[str, Any] | None) -> bool:
    return bool(no) and str(no.get("estado") or "").lower() == "closed"


def _partes(foto: dict[str, Any] | None) -> list[dict[str, Any]]:
    return list((foto or {}).get("partes") or [])


def etapa_da_foto(foto: dict[str, Any] | None) -> str:
    """A Etapa que esta foto da issue significa (ADR 0054, decisao 3).

    A ordem das regras E a regra: elas se sobrepoem de proposito, e a primeira
    que casa manda. Uma issue fechada como concluida com o `in-progress` preso
    nela (o caso comum: ninguem tira a label ao fechar) e ENTREGUE, e nao "em
    desenvolvimento para sempre".

    Sem foto nenhuma nao ha o que derivar: e a ausencia de Vinculo, que e
    `registrada`.
    """
    if not foto:
        return ETAPA_REGISTRADA

    labels_raiz = _labels(foto)
    partes = _partes(foto)

    # 1. Fechada como concluida: entregue, aconteca o que acontecer com as
    #    labels e com as partes.
    if _fechada(foto) and str(foto.get("motivo_do_fechamento") or "").lower() == FECHAMENTO_CONCLUIDA:
        return ETAPA_ENTREGUE

    # 2. Fechada por outro motivo (`not_planned`), ou marcada `wontfix`: nao
    #    sera feita. A label conta mesmo com a issue aberta porque ela ja e a
    #    decisao; o fechamento vem depois, e a Etapa nao pode esperar por ele
    #    para parar de prometer entrega.
    if _fechada(foto) or LABEL_WONTFIX in labels_raiz:
        return ETAPA_NAO_SERA_FEITA

    # 3. `in-progress` na raiz ou em QUALQUER parte: alguem esta com a mao nisso.
    if LABEL_EM_ANDAMENTO in labels_raiz:
        return ETAPA_EM_DESENVOLVIMENTO
    if any(LABEL_EM_ANDAMENTO in _labels(parte) for parte in partes):
        return ETAPA_EM_DESENVOLVIMENTO

    # 4. Planejada: a fila de agente ou de humano, ou um PRD que ja tem partes e
    #    nenhuma delas comecou (as partes existirem E o plano).
    if labels_raiz & set(LABELS_PLANEJADA):
        return ETAPA_PLANEJADA
    if partes:
        return ETAPA_PLANEJADA

    # 5. O resto que esta aberto: alguem ainda vai olhar. `needs-triage` e
    #    `needs-info` caem aqui, e uma issue sem label nenhuma tambem.
    return ETAPA_EM_ANALISE


def partes_da_foto(foto: dict[str, Any] | None) -> tuple[int | None, int | None]:
    """Quantas partes ja entregues e quantas ao todo, ou `(None, None)`.

    Nulo, e nao zero, quando nao ha sub-issue nenhuma: "0 de 0 partes" e uma
    barra vazia onde nao existe barra, e o card precisa distinguir "issue
    simples" de "PRD que ainda nao entregou nada".

    O `sub_issues_summary` do GitHub manda quando veio, porque e o numero que a
    propria tela do GitHub mostra; sem ele, a conta sai da lista de partes que
    ja foi lida para as labels. Duas fontes que divergem seriam pior do que uma
    so, mas aqui a segunda so entra quando a primeira nao existe.
    """
    if not foto:
        return (None, None)

    resumo = foto.get("resumo_das_partes") or {}
    total = resumo.get("total")
    entregues = resumo.get("entregues")
    if isinstance(total, int) and isinstance(entregues, int):
        return (None, None) if total <= 0 else (entregues, total)

    partes = _partes(foto)
    if not partes:
        return (None, None)
    concluidas = sum(
        1
        for parte in partes
        if _fechada(parte) and str(parte.get("motivo_do_fechamento") or "").lower() == FECHAMENTO_CONCLUIDA
    )
    return (concluidas, len(partes))


# ─── 1b. O login no GitHub da pessoa ─────────────────────────────────────────

# O que o GitHub aceita num login: letras, numeros e hifen, ate 39 caracteres,
# sem comecar nem terminar em hifen e sem hifen dobrado. A regra e do GitHub, e
# nao nossa: um login que ele nao aceita nunca vai casar com autor nenhum, e o
# lugar de dizer isso e o cadastro, nao a hora de vincular.
_LOGIN_RE = re.compile(r"^[a-z0-9](?:[a-z0-9]|-(?=[a-z0-9])){0,38}$")

MOTIVO_LOGIN_INVALIDO = (
    "Login no GitHub inválido. Use apenas letras, números e hífen (até 39 caracteres), "
    "sem começar nem terminar com hífen."
)


def normalizar_github_login(bruto: str | None) -> str | None:
    """Texto do campo virando o que se grava: minusculas, ou `None`.

    Campo apagado (`""`, so espacos) e "esta pessoa nao trabalha no GitHub", e
    isso e NULL. Gravar texto vazio faria o indice unico tratar duas pessoas
    sem login como duas donas do mesmo login, e o `tem_github_login` da aba
    diria "sim" para quem nao tem nada.

    Minusculas porque o GitHub nao distingue maiusculas em login: "Pedro" e
    "pedro" sao a mesma conta, e duas linhas assim seriam duas pessoas
    diferentes para o app.
    """
    if bruto is None:
        return None
    limpo = bruto.strip().lower()
    # O `@` que a pessoa cola junto do login e ruido de interface, nao dado.
    limpo = limpo.removeprefix("@")
    return limpo or None


def motivo_github_login_invalido(login: str | None) -> str | None:
    """A frase de recusa, ou `None` quando o login serve (nulo inclusive)."""
    if login is None:
        return None
    return None if _LOGIN_RE.match(login) else MOTIVO_LOGIN_INVALIDO


def motivo_github_login_repetido(login: str, nome: str | None) -> str:
    de_quem = nome or "outro participante"
    return f"O login {login} já está em {de_quem}. Um login do GitHub responde por uma pessoa só."


def tem_github_login(participante: dict[str, Any] | None) -> bool:
    """Se esta pessoa e da Vitta (ADR 0054, decisao 9).

    Le o dict do participante como ele vem do banco. Coluna ausente (backend
    que subiu antes da migration 103) conta como NAO tem, que e o lado seguro:
    os controles do Vinculo somem em vez de aparecerem e falharem.
    """
    if not participante:
        return False
    return bool(str(participante.get("github_login") or "").strip())


# ─── 2. O marcador oculto no corpo da issue ──────────────────────────────────

# O par do Vinculo e guardado nos dois lados (ADR 0054, decisao 1): a Demanda
# guarda o numero da issue, a issue guarda o id da Demanda AQUI. Comentario HTML
# porque ele sobrevive no `body` e nao aparece renderizado em lugar nenhum.
_MARCADOR_RE = re.compile(r"<!--\s*demanda-vitta id=\"[^\"]*\"\s*-->")


def marcador_da_demanda(demanda_id: str) -> str:
    return f'<!-- demanda-vitta id="{demanda_id}" -->'


def demanda_id_do_marcador(corpo: str | None) -> str | None:
    """O id da Demanda que este corpo diz carregar, ou `None`."""
    achado = re.search(r"<!--\s*demanda-vitta id=\"([^\"]*)\"\s*-->", corpo or "")
    return achado.group(1) if achado else None


def corpo_com_marcador(corpo: str | None, demanda_id: str) -> str:
    """O corpo da issue com o marcador no fim, sem tocar no resto.

    Idempotente por construcao: um marcador que ja esteja no corpo e RETIRADO
    antes de o novo entrar, entao vincular duas vezes o mesmo numero deixa o
    corpo exatamente igual, e vincular uma issue que sobrou marcada de outra
    Demanda nao acumula dois donos.

    O texto do autor nao e reescrito: so se corta o marcador antigo e o espaco
    em branco que ele deixou no fim.
    """
    limpo = _MARCADOR_RE.sub("", corpo or "").rstrip()
    marcador = marcador_da_demanda(demanda_id)
    return f"{limpo}\n\n{marcador}" if limpo else marcador


def corpo_precisa_do_marcador(corpo: str | None, demanda_id: str) -> bool:
    """Se vale a pena escrever no GitHub.

    O corpo que ja termina exatamente como `corpo_com_marcador` o deixaria nao
    tem o que ganhar com um PATCH: a chamada gastaria cota e faria o GitHub
    disparar `issues.edited` a toa.
    """
    return corpo_com_marcador(corpo, demanda_id) != (corpo or "")


# ─── 3. A foto mudou? ────────────────────────────────────────────────────────


def foto_mudou(antiga: dict[str, Any] | None, nova: dict[str, Any] | None) -> bool:
    """Se a foto nova diz algo diferente da guardada.

    Foto igual nao escreve NADA: nem a linha da Conversa, nem o UPDATE da
    Demanda. Sem esta guarda, a reconciliacao de hora em hora (a fatia seguinte)
    encheria o fio do diretor de linhas repetidas dizendo a mesma coisa.
    """
    return antiga != nova


# ─── 4. As linhas automaticas do fio ─────────────────────────────────────────


def texto_partes(entregues: int | None, total: int | None) -> str:
    """ "3 de 7 partes", ou vazio quando nao ha partes."""
    if not isinstance(entregues, int) or not isinstance(total, int) or total <= 0:
        return ""
    return f"{entregues} de {total} partes"


def texto_movimento_etapa(*, para: str, entregues: int | None = None, total: int | None = None) -> str:
    """A linha que o diretor le quando o desenvolvimento anda.

    Sem nome de quem agiu, e de proposito: ninguem AGIU no app. Quem mudou foi o
    GitHub, e a linha diz o fato.
    """
    rotulo = ETAPA_ROTULO.get(para, para)
    partes = texto_partes(entregues, total)
    return f"Etapa: {rotulo} ({partes})" if partes else f"Etapa: {rotulo}"


def texto_vinculo_criado(numero: int) -> str:
    return f"Vínculo com o desenvolvimento criado na issue #{numero}"


TEXTO_VINCULO_DESFEITO = "Vínculo com o desenvolvimento desfeito"


# ─── 5. As frases de recusa ──────────────────────────────────────────────────

# Cada uma tem a SUA causa e a SUA saida: uma frase generica ("nao foi possivel
# vincular") mandaria a pessoa adivinhar entre digitar outro numero, procurar a
# outra Demanda e pedir acesso.
MOTIVO_SEM_GITHUB_LOGIN = (
    "O Vínculo com o desenvolvimento é de quem trabalha no GitHub. "
    "Preencha o campo Login no GitHub na tela de Usuários para usar este controle."
)

MOTIVO_INTEGRACAO_DESLIGADA = (
    "A integração com o GitHub não está configurada neste ambiente. "
    "Sem ela o app não consegue ler nem marcar a issue: peça para configurar antes de vincular."
)

MOTIVO_NUMERO_INVALIDO = "O número da issue precisa ser um inteiro maior que zero."


def motivo_issue_inexistente(numero: int) -> str:
    return f"A issue #{numero} não existe no repositório da integração. Confira o número e tente de novo."


def motivo_e_pull_request(numero: int) -> str:
    return (
        f"O número #{numero} é de um pull request, e o Vínculo é com a issue-raiz. "
        "Use o número do PRD ou da issue de correção."
    )


def motivo_numero_ja_usado(numero: int, titulo: str) -> str:
    return (
        f'A issue #{numero} já está vinculada à Demanda "{titulo}". '
        "Uma issue responde por uma Demanda só: desfaça o Vínculo lá antes de criar este."
    )


def motivo_demanda_ja_vinculada(numero: int) -> str:
    return (
        f"Esta Demanda já está vinculada à issue #{numero}. Clique em Desvincular antes de apontá-la para outra issue."
    )


MOTIVO_SEM_VINCULO_PARA_DESFAZER = "Esta Demanda não tem Vínculo com o desenvolvimento para desfazer."

MOTIVO_GITHUB_INDISPONIVEL = (
    "O GitHub não respondeu agora. O Vínculo não foi criado: tente de novo em alguns instantes."
)
