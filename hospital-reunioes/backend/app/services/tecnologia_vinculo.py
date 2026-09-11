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

from app.utils.text_sanitizer import sanitizar_travessao

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

# Como o GitHub diz que a issue fechou. Ele manda `completed` ou `not_planned`
# em `state_reason`, e o campo pode vir NULO. So o `not_planned` e lido aqui:
# tudo o mais que fechou conta como entrega (ver `_entregue`), e por isso nao ha
# constante para o `completed`, que seria uma segunda porta para a mesma regra.
FECHAMENTO_NAO_PLANEJADA = "not_planned"


def _labels(no: dict[str, Any] | None) -> set[str]:
    """As labels de um no da foto, sempre em minusculas."""
    if not no:
        return set()
    return {str(nome).strip().lower() for nome in (no.get("labels") or [])}


def _fechada(no: dict[str, Any] | None) -> bool:
    return bool(no) and str(no.get("estado") or "").lower() == "closed"


def _entregue(no: dict[str, Any] | None) -> bool:
    """Se este no (raiz ou parte) conta como ENTREGUE.

    Fechada e entrega, a menos que o motivo diga o contrario. O GitHub devolve
    `state_reason: null` em varios caminhos de fechamento (issue antiga,
    fechamento por API sem o campo), e exigir `completed` faria o diretor ler
    "Não será feita" sobre algo que foi feito. `not_planned` e a excecao, e quem
    a escolhe a declara.

    `wontfix` tambem tira a entrega, e nao so o motivo do fechamento (issue
    #701, achado na auditoria do PRD #673). O protocolo nao obriga ninguem a
    escolher "nao planejada" ao fechar, entao quem recusa marca a label e clica
    no botao padrao do GitHub, que fecha como CONCLUIDA. A label e a decisao; o
    motivo do fechamento e so como o botao foi clicado. Sem isto, a issue
    recusada aparecia como Entregue, e Entregue nao para no selo: dispara a
    devolucao a quem pediu e o e-mail "Entregue, confira e conclua".

    Uma funcao so para a raiz e para as partes: "entregue" nao pode significar
    duas coisas diferentes no mesmo modulo, senao a Etapa e o "X de Y partes"
    contariam historias divergentes sobre a mesma issue.
    """
    if LABEL_WONTFIX in _labels(no):
        return False
    return _fechada(no) and str((no or {}).get("motivo_do_fechamento") or "").lower() != FECHAMENTO_NAO_PLANEJADA


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

    # 1. Fechada como concluida, ou fechada sem motivo declarado: entregue,
    #    aconteca o que acontecer com as partes e com as outras labels.
    #    `wontfix` e a unica label que tira a entrega, e ela sai dentro do
    #    proprio `_entregue` (issue #701), para a raiz e as partes contarem a
    #    mesma historia.
    #
    #    A ausencia de motivo entra AQUI, e nao na regra 2, porque fechar e o
    #    desfecho normal de uma issue que foi feita: `not_planned` e a excecao, e
    #    quem a escolhe a declara.
    if _entregue(foto):
        return ETAPA_ENTREGUE

    # 2. Fechada como NAO PLANEJADA, ou marcada `wontfix`: nao sera feita.
    #
    #    O motivo tem de ser explicito. O GitHub devolve `state_reason: null` em
    #    varios caminhos de fechamento (issue antiga, fechamento por API sem o
    #    campo), e tratar a ausencia como "nao planejada" faria o diretor ler
    #    "Não será feita" sobre uma entrega que aconteceu. Fechado sem motivo cai
    #    na regra 1 logo acima, que e o desfecho comum: a issue fechou.
    #
    #    A label conta mesmo com a issue aberta porque ela ja e a decisao; o
    #    fechamento vem depois, e a Etapa nao pode esperar por ele para parar de
    #    prometer entrega.
    if (_fechada(foto) and str(foto.get("motivo_do_fechamento") or "").lower() == FECHAMENTO_NAO_PLANEJADA) or (
        LABEL_WONTFIX in labels_raiz
    ):
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

    A excecao e a parte RECUSADA (issue #701). O GitHub conta como concluida
    toda sub-issue fechada pelo botao padrao, label nenhuma importa, entao uma
    fatia com `wontfix` entra no numero dele como entregue. Aqui ela nao e
    entregue, e o selo dela na lista diz "Nao sera feita". Manter o resumo
    nesse caso poria o card contando "2 de 3 partes" logo acima de uma lista
    que mostra uma parte recusada: o diretor veria duas historias sobre a mesma
    issue. Quando ha parte recusada entre as que lemos, a conta propria manda;
    no resto, o numero do GitHub continua mandando.
    """
    if not foto:
        return (None, None)

    partes_lidas = _partes(foto)
    ha_parte_recusada = any(LABEL_WONTFIX in _labels(parte) for parte in partes_lidas)
    resumo = foto.get("resumo_das_partes") or {}
    total = resumo.get("total")
    entregues = resumo.get("entregues")
    if isinstance(total, int) and isinstance(entregues, int) and not ha_parte_recusada:
        return (None, None) if total <= 0 else (entregues, total)

    if not partes_lidas:
        return (None, None)
    return (sum(1 for parte in partes_lidas if _entregue(parte)), len(partes_lidas))


# ─── 1b. O bloco "Para o diretor" (issue #676) ───────────────────────────────

# O cabecalho que abre o bloco. Todo PRD e toda fatia nascem com ele (ADR 0020,
# decisao 7), e o `/to-issues` costuma por um emoji no meio: "## 👔 Para o
# diretor". O emoji e enfeite, e nao pode decidir se o diretor ve o texto ou
# nao, entao o casamento e pela FRASE, em qualquer nivel de cabecalho.
_CABECALHO_DO_DIRETOR = re.compile(r"^#{1,6}[^\n]*?para o diretor[^\n]*$", re.IGNORECASE | re.MULTILINE)

# Onde o bloco acaba: o primeiro separador `---` ou o proximo cabecalho de
# nivel 1 ou 2, o que vier antes.
#
# `-{3,}` e nao `-+`: um item de lista ("- O texto vem do planejamento") e a
# forma mais comum de linha do bloco, e ele nao pode fechar o proprio bloco.
#
# `#{1,2}` e nao so `##`: o corpo tecnico comeca no cabecalho seguinte, e o
# nivel dele e convencao do `/to-issues`, nao contrato. Se um dia o "## Pai"
# virar "# Pai", um recorte que so conhecesse o nivel 2 mandaria o corpo
# tecnico INTEIRO para a tela do diretor sem nada quebrar. `###` continua de
# fora de proposito: um subtitulo dentro do bloco e do diretor tambem.
#
# O `\s` depois dos `#` e o que separa cabecalho de texto: "#673" no meio de uma
# frase nao e titulo de secao nenhum.
_FIM_DO_BLOCO = re.compile(r"^(?:-{3,}\s*|#{1,2}\s[^\n]*)$", re.MULTILINE)

# Comentario HTML, o marcador do Vinculo inclusive.
#
# Ele e retirado ANTES do recorte porque a issue cujo corpo e so o bloco recebe
# o marcador no fim dele (`corpo_com_marcador`), ou seja, DENTRO do que o
# diretor leria. O bloco tambem nao pode carregar HTML nenhum: a tela o mostra
# como texto, e uma tag apareceria crua no meio da frase.
_COMENTARIO_HTML = re.compile(r"<!--.*?-->", re.DOTALL)


def bloco_para_o_diretor(corpo: str | None) -> str | None:
    """O bloco "Para o diretor" deste corpo de issue, ou `None`.

    E o UNICO texto do GitHub que chega ao diretor (ADR 0054, decisao 7): o
    resto do corpo e tecnico, e traz numero de issue, nome de label e caminho de
    arquivo, que a decisao 9 mantem atras do `github_login`. O corte, portanto,
    erra para os dois lados: sobrar corpo poe o tecnico na tela dele, e faltar
    bloco o deixa sem saber o que a entrega muda.

    Nulo quando nao ha cabecalho, quando o corpo e vazio e quando o bloco esta
    em branco: os tres significam a mesma coisa para quem le ("ainda nao
    escreveram isto"), e a tela os traduz numa frase so.

    O texto sai SANITIZADO: ele nasce fora do app e vai para a tela do diretor e
    para o "Copiar para IA", onde a regra da casa contra travessao vale igual.
    """
    texto = _COMENTARIO_HTML.sub("", corpo or "")
    achado = _CABECALHO_DO_DIRETOR.search(texto)
    if not achado:
        return None

    resto = texto[achado.end() :]
    fim = _FIM_DO_BLOCO.search(resto)
    bloco = (resto[: fim.start()] if fim else resto).strip()
    return sanitizar_travessao(bloco) or None


def situacao_da_parte(parte: dict[str, Any] | None) -> str:
    """Em que pe esta ESTA parte, no vocabulario da Etapa (ADR 0054, decisao 7).

    Quatro das seis Etapas, e nao um vocabulario proprio: o diretor le o mesmo
    rotulo no selo do card e no selo de cada parte, e duas listas de palavras
    para a mesma ideia fariam "Entregue" significar coisas diferentes na mesma
    tela.

    A precedencia e a da raiz (`etapa_da_foto`), pelo mesmo motivo: a parte
    fechada com o `in-progress` preso nela esta ENTREGUE, e nao "em
    desenvolvimento para sempre".
    """
    if _entregue(parte):
        return ETAPA_ENTREGUE
    labels = _labels(parte)
    if _fechada(parte) or LABEL_WONTFIX in labels:
        return ETAPA_NAO_SERA_FEITA
    if LABEL_EM_ANDAMENTO in labels:
        return ETAPA_EM_DESENVOLVIMENTO
    return ETAPA_PLANEJADA


def partes_para_o_diretor(foto: dict[str, Any] | None) -> list[dict[str, Any]]:
    """A lista de partes como a Demanda a guarda: numero, texto e situacao.

    O numero e INTERNO: ele fica no cache para quem e da Vitta rastrear, e o
    funil da resposta (`_com_nomes`, no router) o omite para quem nao tem
    `github_login`. O titulo da fatia nao entra em lugar nenhum, porque e
    tecnico (ADR 0054, decisao 7).

    Parte sem bloco entra com texto nulo em vez de sumir da lista: o diretor
    precisa saber que a parte existe e em que pe ela esta, mesmo antes de
    alguem escrever o que ela muda.
    """
    return [
        {
            "numero": parte.get("numero"),
            "o_que_muda": parte.get("o_que_muda") or None,
            "situacao": situacao_da_parte(parte),
        }
        for parte in _partes(foto)
    ]


def o_que_muda_da_foto(foto: dict[str, Any] | None) -> str | None:
    """O bloco da RAIZ que a ultima leitura do GitHub trouxe, ou `None`.

    Le a foto em vez de reabrir o corpo da issue: quem ja leu do GitHub guardou
    o bloco no no da raiz, e uma segunda extracao aqui seria uma segunda versao
    da mesma regra.
    """
    return (foto or {}).get("o_que_muda") or None


# ─── 1c. O login no GitHub da pessoa ─────────────────────────────────────────

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


# ─── 2b. A issue que o app CRIA (issue #677) ─────────────────────────────────
#
# Aqui a direcao se inverte: no resto do modulo o GitHub e a fonte e o app o
# leitor; nesta secao o texto que alguem digitou no app vira o corpo de uma
# issue num repositorio PUBLICO, que qualquer pessoa le e que o proprio app
# depois relê.
#
# Duas regras saem disso, e as duas moram no `texto_do_diretor`:
#
# 1. **Nada do que o diretor escreve pode virar marcador.** O par do Vinculo e
#    o comentario HTML, e a reconciliacao encontra a Demanda pelo PRIMEIRO
#    marcador do corpo. Uma descricao que carregasse um `<!-- demanda-vitta -->`
#    apontaria a issue nova para outra Demanda, e nada quebraria. Vale igual
#    para o `<!-- revisor-app -->`, que acende a `revisor-comentou` na Action, e
#    para o `<!-- automacao -->`, que a faz calar.
# 2. **A primeira coluna e do backend.** E a mesma disciplina do "Copiar para
#    IA" (`recuar_continuacao`, no `tecnologia.py`), pela mesma razao: cabecalho
#    e separador so valem no comeco da linha, e e por eles que o corpo se
#    divide entre o que e do diretor e o que e da Vitta. Um "## Origem" digitado
#    na descricao fabricaria uma segunda secao dizendo que quem pediu foi outra
#    pessoa.

# O cabecalho com que a issue nasce. Igual ao que o `/to-issues` escreve, e nao
# uma variante nossa: e o mesmo que o `bloco_para_o_diretor` procura na volta.
CABECALHO_DO_BLOCO = "## 👔 Para o diretor"

LABEL_TRIAGEM = "needs-triage"

# O tipo da Demanda virando label de tipo (ADR 0054, decisao 1). Os tipos que
# NAO estao aqui (Decisao, Informacao, Terceiro, Consultoria) nascem sem label
# de tipo, de proposito: nem todo pedido vira codigo, e um `type:feature`
# chutado mentiria para quem cura.
LABEL_DO_TIPO: dict[str, str] = {
    "defeito": "type:fix",
    "ajuste": "type:feature",
    "novo": "type:feature",
}

# CR e CRLF viram LF antes de qualquer outra coisa.
#
# Nao e cosmetica: a neutralizacao abaixo casa fim de linha com `[ \t]*$`, e um
# `---\r\n` colado de um e-mail passaria batido por ela, enquanto o
# `_FIM_DO_BLOCO` da leitura (que aceita `\s*$`, e `\r` e espaco) o leria como
# separador. Os dois lados precisam ver a mesma linha.
_QUEBRA_DE_LINHA = re.compile(r"\r\n?")

# O que estrutura um corpo de issue quando comeca a linha: cabecalho, separador
# e sublinhado de titulo. A barra invertida do Markdown desliga o efeito e
# deixa o texto a vista, que e o que se quer: o diretor escreveu aquilo, e ele
# continua legivel, so nao manda mais na divisao do corpo.
_ESTRUTURA_NA_COLUNA_ZERO = re.compile(
    r"^([ \t]*)(#{1,6}(?=\s|$)|(?:-{3,}|\*{3,}|_{3,}|={3,})[ \t]*$)",
    re.MULTILINE,
)


def texto_do_diretor(bruto: str | None) -> str:
    """O texto digitado no app, pronto para entrar num corpo de issue publica.

    **Escapa em vez de remover**, e essa escolha e o coracao da funcao.

    Remover o delimitador parece a defesa obvia e nao e: a remocao COLA os
    vizinhos, e o que era inofensivo em duas partes vira sintaxe em uma. Com
    uma passada de "tire `<!--` e tire `-->`", a entrada

        <-->!-- demanda-vitta id="ROUBADA" --<!-->

    sai como um marcador PERFEITO, porque cada pedaco removido junta o que
    estava a esquerda com o que estava a direita. Iterar ate o ponto fixo
    fecharia esse buraco, mas ao preco de um laco com teto arbitrario e de
    apagar texto que a pessoa escreveu.

    O `<` virando `&lt;` nao tem esse problema: a saida NAO CONTEM `<` nenhum,
    e sem ele nao existe comentario HTML para remontar (um `-->` sozinho e
    texto inerte, no HTML e no Markdown). O Markdown ainda renderiza `&lt;`
    como `<`, entao quem le a issue ve exatamente o que o diretor escreveu, que
    e o motivo de o botao existir. Uma passada, sem laco, sem perda.

    Depois disso, desliga o que estruturaria o corpo a partir da coluna zero
    (regra 2 acima) e passa pelo sanitizador de travessao, que vale para o que
    sai do app tanto quanto para o que entra.

    Idempotente: `&lt;` nao tem `<` para escapar de novo, e a linha ja
    neutralizada comeca por `\\`, que nao casa a estrutura. Aplicar duas vezes
    da o mesmo texto.
    """
    texto = _QUEBRA_DE_LINHA.sub("\n", bruto or "")
    escapado = texto.replace("<", "&lt;")
    neutralizado = _ESTRUTURA_NA_COLUNA_ZERO.sub(r"\1\\\2", escapado)
    return sanitizar_travessao(neutralizado).strip()


def labels_da_issue_nova(tipo: str | None) -> list[str]:
    """As labels com que a issue nasce.

    `needs-triage` SEMPRE: e o contrato do protocolo de triagem
    (docs/agents/triage-labels.md), e sem ela a issue nasce fora da fila de
    quem cura, invisivel para a `/onda` e para o `/pegar-issue`.
    """
    label = LABEL_DO_TIPO.get(str(tipo or "").strip().lower())
    return [LABEL_TRIAGEM, label] if label else [LABEL_TRIAGEM]


def login_para_publicar(bruto: str | None) -> str | None:
    """O login que pode entrar num corpo de issue PUBLICA, ou `None`.

    Passa pelo MESMO alfabeto que o cadastro exige (`_LOGIN_RE`), e nao por uma
    peneira propria: um login so tem letra, digito e hifen, entao nada que saia
    daqui carrega `<`, quebra de linha ou marca de Markdown. Isso e mais forte
    do que escapar, porque a lista do que pode e fechada.

    `None` quando o campo esta vazio ou quando o texto gravado nao e um login de
    verdade (linha antiga, cadastro feito antes da validacao): nesse caso a
    Origem sai sem a mencao, e nao com um `@` grudado em algo que ninguem sabe
    o que e.
    """
    login = normalizar_github_login(bruto)
    if login is None or motivo_github_login_invalido(login) is not None:
        return None
    return login


def corpo_da_issue_nova(
    *,
    demanda_id: str,
    titulo: str,
    descricao: str | None,
    tipo_rotulo: str,
    produto_nome: str,
    levado_por_login: str | None,
    link: str,
) -> str:
    """O corpo da issue que o botao "Levar para desenvolvimento" cria.

    Tres partes, e cada uma com um leitor diferente:

    - o bloco **"Para o diretor"**, que e o que volta para o card pelo
      `bloco_para_o_diretor` (ADR 0054, decisao 7). Ele acaba no separador, e
      por isso nada abaixo dele chega ao diretor;
    - a **Origem**, para quem for curar a issue: o endereco da Demanda no app e
      quem a levou;
    - o **marcador**, o lado da issue do par do Vinculo.

    **Nome civil nenhum sai daqui** (decisao do diretor, rodada de seguranca do
    PR #688). A issue #677 pedia a Origem "com o autor", e a Origem levava o
    nome completo de quem pediu para um repositorio publico a cada clique. O
    que ficou no lugar responde a mesma pergunta sem publicar pessoa:

    - o **link da Demanda** e a rastreabilidade de verdade. Quem le a issue tem
      acesso ao app, e la esta o autor, o fio inteiro e o resto;
    - o **`@login`** e de quem LEVOU, nao de quem pediu, e e identificador que a
      propria pessoa ja tornou publico no GitHub. Ele existe sempre, porque a
      rota devolve 403 para quem nao tem `github_login`.

    Descricao vazia usa o TITULO: uma issue cujo "O que muda" viesse em branco
    mostraria "Descrição em preparação" no card de quem acabou de pedir.
    """
    o_que_muda = texto_do_diretor(descricao) or texto_do_diretor(titulo)
    login = login_para_publicar(levado_por_login)
    origem = "Pedido registrado na aba Tecnologia do aplicativo do hospital"
    origem = f"{origem}, levado para o desenvolvimento por @{login}." if login else f"{origem}."
    return "\n".join(
        [
            CABECALHO_DO_BLOCO,
            "",
            f"**O que muda:** {o_que_muda}",
            "",
            "**O que você precisa saber:**",
            f"- Tipo do pedido: {tipo_rotulo}",
            f"- Produto: {produto_nome}",
            "",
            "---",
            "",
            "## Origem",
            "",
            origem,
            f"Abrir a Demanda: {link}",
            "",
            marcador_da_demanda(demanda_id),
        ]
    )


# ─── 2c. A resposta espelhada na issue (issue #680) ──────────────────────────
#
# Toda resposta da Conversa de uma Demanda vinculada vira comentario na issue
# (ADR 0054, decisao 4). Do lado do GitHub o autor do comentario e SEMPRE a
# integracao, entao quem diz de quem e a voz e o marcador que abre o corpo, e
# nao o login de quem publicou. A Action de higiene le os dois:
#
# - `<!-- automacao -->` para quem tem `github_login`: e a Vitta respondendo ao
#   diretor, e a Action ja ignora esse marcador (senao o "vou ver" do Pedro
#   acenderia `revisor-comentou` e travaria a `/onda`);
# - `<!-- revisor-app autor="..." demanda="id" -->` para quem nao tem: e o
#   diretor, e a Action acende a label por ele (emenda ao ADR 0020, decisao 5).
#
# A forma do marcador do revisor e LITERAL, um espaco depois de `<!--`: o
# matcher da Action aceita exatamente esse espaco, e dois falhariam em
# silencio, sem label e sem erro. E ele sai em linha propria, como PRIMEIRA
# coisa do corpo, porque a Action o ancora ali (emenda de 10/09/2026 na issue
# #680): um comentario de curadoria que cite o marcador no meio do texto nao
# pode acender a label.
#
# **Nome civil nenhum sai daqui**, o mesmo invariante do `corpo_da_issue_nova`
# (decisao do diretor na review do PR #688, estendida a esta fatia na rodada 1
# do PR #696): o repositorio e publico. Quem tem login sai como `@login`, que a
# propria pessoa ja tornou publico no GitHub; quem nao tem sai com o rotulo
# neutro, no cabecalho e no `autor` do marcador. Quem tem acesso ao app ve o
# autor pelo link da Demanda, que ja esta no corpo da issue.
MARCADOR_AUTOMACAO = "<!-- automacao -->"

# O rotulo de quem nao tem login publicavel. Uma frase so, porque e o que fica
# no lugar do nome em TODOS os pontos (cabecalho, marcador, mencao no texto): a
# pessoa sem login e, por definicao, do lado do hospital (ADR 0054, decisao 4).
ROTULO_SEM_LOGIN = "Pessoa do hospital"

# O que o GitHub le como mencao: `@` no inicio ou depois de algo que nao e
# letra nem digito, seguido do login (letras, digitos, hifen, sublinhado) e,
# no caso de time, `/nome`. O `@` colado a uma palavra (`ana@hsm.com`) e
# autolink de e-mail, nao mencao, e o `@` sozinho antes de espaco nao chama
# ninguem. O sublinhado NAO entra no lookbehind: em `_@fulano_` ele abre
# enfase, o `@` estreia o conteudo do `<em>` e o filtro do GitHub acende a
# mencao (conferido no `gh api /markdown` na rodada 3 do PR #696). Em
# `fulano_@octocat` o sublinhado fica literal e o GitHub nao acende nada, mas
# tratar os dois casos igual custa um espaco num texto que ninguem escreve e
# evita depender de onde o CommonMark decide abrir enfase.
_MENCAO_DO_GITHUB = re.compile(r"(?<![A-Za-z0-9])@[A-Za-z0-9][A-Za-z0-9_-]*(?:/[A-Za-z0-9_-]+)?")

# Depois do nome mencionado tem de vir algo que nao e letra (ou o fim): sem
# isso, "Ana" mencionada casaria o comeco de "@Anastácia".
_FIM_DO_NOME = r"(?![^\W_])"


def rotulo_no_github(participante: dict[str, Any] | None) -> str:
    """Como esta pessoa aparece num texto publicado no GitHub: `@login` quando
    ha login publicavel (`login_para_publicar`, alfabeto fechado), senao o
    rotulo neutro. Nunca o nome."""
    login = login_para_publicar((participante or {}).get("github_login"))
    return f"@{login}" if login else ROTULO_SEM_LOGIN


def marcador_do_revisor_no_app(*, demanda_id: str) -> str:
    return f'<!-- revisor-app autor="{ROTULO_SEM_LOGIN}" demanda="{demanda_id}" -->'


def _neutralizar_mencoes(texto: str) -> str:
    """Um `@fulano` digitado a mao vira `@ fulano`: um espaco depois do `@`.

    O filtro de mencao do GitHub quer o login colado no `@`, entao o espaco
    desliga a mencao sem inserir delimitador nenhum no texto. As duas formas
    que parecem obvias nao servem, ambas conferidas no `gh api /markdown`
    deste repositorio:

    - `\\@fulano` (escape de barra, rodada 2 do PR #696): o CommonMark come a
      barra antes de o filtro rodar, e a mencao acende igual. `&#64;` tambem;
    - `` `@fulano` `` (code span, rodada 3): funciona em texto limpo, mas se o
      autor ja escreveu crase, a crase inserida QUEBRA o code span dele em
      dois e acende uma mencao que estava apagada. Em `` `ver @octocat
      agora` `` o GitHub nao notificava ninguem, e passava a notificar.

    O espaco nao tem essa borda: nao abre nem fecha nada, e sai neutro
    inclusive dentro do code span e do italico do autor.
    """
    return _MENCAO_DO_GITHUB.sub(lambda m: f"@ {m.group(0)[1:]}", texto)


def texto_espelhado(bruto: str | None, *, mencionados: list[dict[str, Any]]) -> str:
    """O texto da resposta, pronto para um comentario em repositorio publico.

    Passa pelo `texto_do_diretor` (o `<` vira `&lt;`, estrutura em coluna zero
    desligada, travessao sanitizado) e depois trata o `@`, que aquele funil
    nao conhece porque no corpo da issue nova nao ha mencao:

    1. a **mencao do app** (o `@Nome Completo` que o autocomplete grava, com o
       id da pessoa em `mencoes`) vira o rotulo dessa pessoa: `@login` quando
       ela tem, que e mencao de verdade no GitHub e chama quem o autor quis
       chamar, ou o rotulo neutro. O nome civil do mencionado nao sai;
    2. qualquer **outra** mencao (`@fulano` digitado a mao) sai com um espaco
       depois do `@`, que e o que desliga o filtro de mencao do GitHub sem
       criar delimitador no texto do autor. O e-mail digitado no texto nao e
       mencao e fica como esta.

    A troca do passo 1 roda sobre o texto BRUTO, antes do `texto_do_diretor`:
    e o nome do cadastro que tem de casar, e o funil transforma o texto (`<`
    vira `&lt;`, travessao vira virgula) sem transformar o nome. E e feita por
    trechos, com o passo 2 aplicado so ao que esta ENTRE as mencoes: aplicado
    ao texto inteiro depois, ele poria em crase o `@login` que o passo 1
    acabou de por. O nome mais longo ganha quando um e prefixo do outro ("Ana
    Paula" antes de "Ana"), e depois do nome tem de vir algo que nao e letra.
    """
    texto = _QUEBRA_DE_LINHA.sub("\n", bruto or "")
    rotulos = {
        nome: rotulo_no_github(pessoa)
        for pessoa in mencionados
        if (nome := str((pessoa or {}).get("nome_completo") or "").strip())
    }
    if not rotulos:
        return texto_do_diretor(_neutralizar_mencoes(texto))
    padrao = re.compile(
        "|".join(re.escape(f"@{nome}") + _FIM_DO_NOME for nome in sorted(rotulos, key=len, reverse=True))
    )
    partes: list[str] = []
    fim = 0
    for achado in padrao.finditer(texto):
        partes.append(_neutralizar_mencoes(texto[fim : achado.start()]))
        partes.append(rotulos[achado.group(0)[1:]])
        fim = achado.end()
    partes.append(_neutralizar_mencoes(texto[fim:]))
    return texto_do_diretor("".join(partes))


def corpo_do_comentario_espelhado(
    *,
    texto: str,
    autor: dict[str, Any] | None,
    demanda_id: str,
    mencionados: list[dict[str, Any]] | None = None,
) -> str:
    """O comentario que o app publica na issue quando alguem responde no card.

    O marcador vai pelo FATO de ter login (`tem_github_login`): e ele que separa
    a Vitta do hospital para a Action. O cabecalho vai pelo login PUBLICAVEL
    (`rotulo_no_github`): uma linha antiga com login fora do alfabeto ainda e
    da Vitta para o marcador, mas o cabecalho nao publica o que ninguem sabe o
    que e.

    O texto passa pelo `texto_espelhado`: sem isso, bastaria alguem digitar o
    marcador do revisor dentro da resposta para a Action acender a label em
    nome de outra pessoa (o teto de `author_association` do GitHub nao
    protegeria nada, porque o autor do comentario e a integracao), e um
    `@fulano` digitado a mao notificaria conta alheia.

    Uma linha em branco entre o cabecalho e o texto, para o Markdown nao colar
    os dois num paragrafo so.
    """
    marcador = MARCADOR_AUTOMACAO if tem_github_login(autor) else marcador_do_revisor_no_app(demanda_id=demanda_id)
    return "\n".join(
        [
            marcador,
            f"**{rotulo_no_github(autor)}** escreveu na Demanda:",
            "",
            texto_espelhado(texto, mencionados=list(mencionados or [])),
        ]
    )


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


# As duas linhas do Vinculo, SEM o numero da issue.
#
# O texto da Conversa e lido pelo diretor e sai do app inteiro dentro do
# "Copiar para IA": e a superficie mais larga que existe, e ela nao passa pelo
# funil que omite o Vinculo (`_com_nomes`). Um "#673" aqui furaria a decisao 9
# do ADR 0054 pela porta dos fundos, e o proprio bloco "Para o diretor" da issue
# #674 ("Você não vê número, link nem botão técnico") junto.
#
# Quem precisa do numero para rastrear le `movimento_de` e `movimento_para`, que
# o router omite para quem nao tem `github_login`.
TEXTO_VINCULO_CRIADO = "Vínculo com o desenvolvimento criado"
TEXTO_VINCULO_DESFEITO = "Vínculo com o desenvolvimento desfeito"


def texto_levou_para_desenvolvimento(nome: str | None) -> str:
    """A linha do fio quando alguem da Vitta leva o pedido para o
    desenvolvimento (issue #677).

    Esta tem NOME, ao contrario da linha da Etapa: aqui alguem agiu, e no app.
    Sem numero de issue, pelo mesmo motivo das duas acima.
    """
    return f"{nome or 'Alguém'} levou para o desenvolvimento"


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


MOTIVO_CRIACAO_EM_ANDAMENTO = (
    "Esta Demanda já está sendo levada para o desenvolvimento neste instante. "
    "Espere alguns segundos e recarregue o Quadro para ver a issue que nasceu."
)


def motivo_ja_vinculada_para_levar(numero: int) -> str:
    """A recusa de levar duas vezes (issue #677).

    Frase propria, e nao a do `vincular`: ali a saida e apontar para outra
    issue, aqui e nao criar uma SEGUNDA issue para o mesmo pedido, que e o dano
    que ninguem desfaz sozinho depois.
    """
    return (
        f"A Demanda já está vinculada à issue #{numero}. "
        "Desfaça o Vínculo antes de levá-la para o desenvolvimento de novo."
    )


MOTIVO_SEM_VINCULO_PARA_DESFAZER = "Esta Demanda não tem Vínculo com o desenvolvimento para desfazer."

MOTIVO_GITHUB_INDISPONIVEL = (
    "O GitHub não respondeu agora. O Vínculo não foi criado: tente de novo em alguns instantes."
)
