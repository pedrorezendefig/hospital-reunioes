"""Regras puras da aba Tecnologia (PRD #634, ADR 0050).

Sem I/O: quem fala com o Supabase e o router. O que mora aqui e o que precisa
ser verdade independentemente de onde a linha veio, e por isso pode ser testado
direto, sem dubles.

Nesta fatia (issue #636) sao duas regras, as duas sobre Produto:

- quem tem acesso a aba (participante ativo com Super admin). E a MESMA lista
  para dono de Produto, responsavel de Demanda e @mencao, entao ela nasce como
  funcao unica em vez de repetir o filtro em cada endpoint;
- Produto ativo nao fica sem dono. Sem dono, toda Demanda daquele Produto
  nasceria sem ninguem (ADR 0050, decisao 4).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from app.dependencies import is_super_admin

# O motivo que a tela mostra quando a API recusa. Uma frase so, no lugar de
# uma por endpoint: e ela que o Super admin le no toast.
MOTIVO_PRODUTO_ATIVO_SEM_DONO = "Produto ativo precisa de dono. Escolha um dono ou desative o Produto."
MOTIVO_DONO_SEM_ACESSO = "O dono precisa ser um participante ativo com Super admin."


def e_pessoa_da_aba(participante: dict[str, Any] | None) -> bool:
    """True se este participante tem acesso a aba Tecnologia.

    Ativo E Super admin (ADR 0050, decisao 2: o eixo de permissao e o
    `is_super_admin` que ja existe, sem perfil proprio).

    `ativo` ausente ou NULL conta como ativo: a coluna nasceu com DEFAULT TRUE
    na migration 001 e linhas antigas podem nao ter valor. Tratar NULL como
    inativo esconderia da lista gente que usa o app todo dia.
    """
    if not participante:
        return False
    if participante.get("ativo") is False:
        return False
    return is_super_admin(participante)


def produto_ativo_sem_dono(*, ativo: bool, dono_id: str | None) -> bool:
    """True quando o Produto fica ativo e sem ninguem respondendo por ele."""
    return bool(ativo) and not dono_id


def edicao_deixa_produto_ativo_sem_dono(
    *,
    antes_ativo: bool,
    antes_dono: str | None,
    depois_ativo: bool,
    depois_dono: str | None,
) -> bool:
    """True quando a edicao CRIA o estado ruim, e nao quando ela o herda.

    O criterio da issue #636 e "recusa DEIXAR um Produto ativo sem dono". Isso
    e diferente de "recusa qualquer edicao em Produto ativo sem dono", e a
    diferenca nao e teorica: os sete Produtos do seed nascem ativos e SEM dono,
    porque e a propria migration que manda cria-los assim. Uma guarda que
    olhasse so o estado final devolveria 422 ao renomear "Ana" na primeira
    abertura, culpando o Super admin por uma falta de dono que ele nao causou,
    e travaria o criterio "cria, renomeia e desativa um Produto pela tela"
    justo no estado inicial do sistema.

    Quem cobra o dono desses sete e a tela, que marca o Produto ativo sem dono.
    """
    if not produto_ativo_sem_dono(ativo=depois_ativo, dono_id=depois_dono):
        return False
    return not produto_ativo_sem_dono(ativo=antes_ativo, dono_id=antes_dono)


# ─── A maquina de estados da Demanda (issue #637) ────────────────────────────

MOTIVO_PRODUTO_SEM_DONO = (
    "Produto sem dono nao recebe Demanda nova: ela nasceria sem responsavel. Defina o dono do Produto e tente de novo."
)
MOTIVO_PRODUTO_INATIVO = "Produto inativo nao recebe Demanda nova. Escolha outro Produto ou reative este."
MOTIVO_RESPONSAVEL_SEM_ACESSO = "O responsavel precisa ser um participante ativo com Super admin."

# A criacao recusa o mesmo estado que a porta de atribuir recusa: dono que
# perdeu o acesso a aba (saiu do Super admin ou foi desativado) nao pode virar
# responsavel, senao o card nasce com o nome de alguem que nao consegue abrir a
# aba. A frase diz ONDE consertar, porque a acao e possivel na mesma tela: a
# lista de Produtos fica logo abaixo do Quadro, e dentro da aba todos podem
# tudo (ADR 0050, decisao 11). Guarda-corpo que so diz "nao pode" vira
# indisponibilidade.
MOTIVO_DONO_DO_PRODUTO_SEM_ACESSO = (
    "O dono deste Produto não tem mais acesso à aba Tecnologia, então a Demanda nasceria sem responsável. "
    "Troque o dono na lista de Produtos, logo abaixo do Quadro, e abra a Demanda de novo."
)

ESTADOS: tuple[str, ...] = ("nova", "em_andamento", "aguardando", "concluida", "cancelada")

# O rotulo que a gente le, na tela e no texto da linha de movimento. O banco
# guarda o valor sem acento (CHECK da migration 102); a pessoa le "Concluída".
ESTADO_ROTULO: dict[str, str] = {
    "nova": "Nova",
    "em_andamento": "Em andamento",
    "aguardando": "Aguardando",
    "concluida": "Concluída",
    "cancelada": "Cancelada",
}

TIPOS: tuple[str, ...] = (
    "decisao",
    "informacao",
    "terceiro",
    "ajuste",
    "novo",
    "defeito",
    "consultoria",
)

PRIORIDADES: tuple[str, ...] = ("baixa", "normal", "alta")

# Quem pode ir para onde (PRD #634, ADR 0050, decisao 5). O que NAO esta aqui e
# recusado com 422, e a lista de proibidas do teste e o complemento desta.
#
# Tres coisas que a tabela diz de proposito:
#
# - ninguem volta para `nova`: a coluna e o comeco, nao um lugar para onde se
#   retrocede. A Demanda que voltou atras cai em `em_andamento`;
# - nenhum estado leva a si mesmo: mover para a coluna onde a Demanda ja esta
#   nao e movimento, e clique repetido, e gravaria uma linha de movimento
#   dizendo que algo mudou quando nada mudou;
# - de `concluida` nao se pula para `cancelada` (nem o contrario) sem reabrir:
#   trocar o desfecho e uma decisao, e passa por `em_andamento`.
TRANSICOES: dict[str, frozenset[str]] = {
    "nova": frozenset({"em_andamento", "aguardando", "concluida", "cancelada"}),
    "em_andamento": frozenset({"aguardando", "concluida", "cancelada"}),
    "aguardando": frozenset({"em_andamento", "concluida", "cancelada"}),
    "concluida": frozenset({"em_andamento"}),
    "cancelada": frozenset({"em_andamento"}),
}


def transicao_permitida(de: str, para: str) -> bool:
    """True se a Demanda pode andar de `de` para `para`."""
    return para in TRANSICOES.get(de, frozenset())


def motivo_transicao_invalida(de: str, para: str) -> str:
    """A frase que a tela mostra quando a API recusa o movimento.

    Duas causas, porque sao duas e o codigo as distingue: clicar na coluna onde
    a Demanda ja esta, e pedir um caminho que a maquina nao tem. Uma frase so
    para as duas mandaria quem clicou duas vezes procurar defeito onde nao ha.
    """
    aqui = ESTADO_ROTULO.get(de, de)
    if de == para:
        return f"A Demanda já está em {aqui}."
    destinos = sorted(ESTADO_ROTULO[d] for d in TRANSICOES.get(de, frozenset()))
    if not destinos:
        # Estado que a maquina nao conhece (linha antiga, ou valor que entrou
        # por fora do app). Sem esta saida a frase terminaria em "os destinos
        # sao: .", mandando a pessoa procurar uma lista que nao existe.
        return f"A Demanda está em um estado que o Quadro não conhece ({de}), e daí ela não sai por aqui."
    la = ESTADO_ROTULO.get(para, para)
    return f"De {aqui} não dá para ir direto a {la}. De {aqui}, os destinos são: {', '.join(destinos)}."


def carimbos_da_transicao(*, para: str, ator_id: str, agora: str) -> dict[str, str | None]:
    """Os quatro campos de desfecho depois do movimento.

    Concluir e cancelar carimbam data e pessoa; qualquer outro destino limpa os
    quatro. Devolver sempre os quatro (e nao so o que mudou) e o que faz reabrir
    apagar o carimbo antigo: um update parcial deixaria `concluida_em`
    preenchido numa Demanda que voltou para `em_andamento`, e o Historico diria
    que ela foi concluida numa data em que nao foi.
    """
    vazio: dict[str, str | None] = {
        "concluida_em": None,
        "concluida_por": None,
        "cancelada_em": None,
        "cancelada_por": None,
    }
    if para == "concluida":
        return {**vazio, "concluida_em": agora, "concluida_por": ator_id}
    if para == "cancelada":
        return {**vazio, "cancelada_em": agora, "cancelada_por": ator_id}
    return vazio


def texto_movimento_estado(*, autor_nome: str, para: str) -> str:
    """O texto legivel da linha de movimento de coluna.

    Montado aqui, e nao na tela: o de/para estruturado fica gravado na linha,
    mas quem escreve a frase e o backend, para o fio ser o mesmo em qualquer
    lugar que o leia (tela, e-mail e o "Copiar para IA" das fatias seguintes).
    """
    return f"{autor_nome} moveu para {ESTADO_ROTULO.get(para, para)}"


def texto_movimento_responsavel(*, autor_nome: str, para_nome: str) -> str:
    """O texto legivel da linha de movimento de responsavel."""
    return f"{autor_nome} atribuiu a {para_nome}"


# ─── A escrita no fio da Conversa (issue #638) ───────────────────────────────

# A janela de correcao da propria resposta (PRD #634, ADR 0050, decisao 6).
#
# Ela e uma regra de TEMPO, e por isso mora aqui, com o instante recebido de
# fora: uma regra que lesse o relogio por dentro nao teria borda testavel, e o
# criterio da issue #638 e justamente sobre a borda.
JANELA_DE_EDICAO = timedelta(minutes=10)

# Quantos caracteres cabem numa resposta. Nao e limite de banco (a coluna e
# TEXT): e o teto que evita colar um documento inteiro no fio, e a frase da
# recusa diz o numero, porque encurtar o texto e uma acao que quem escreveu
# consegue fazer na hora, com o texto ainda na caixa.
LIMITE_RESPOSTA = 5000

MOTIVO_RESPOSTA_VAZIA = "A resposta não pode ser vazia. Escreva o que você quer dizer e envie de novo."
MOTIVO_SO_O_AUTOR_EDITA = "Só quem escreveu corrige a própria resposta. Escreva uma resposta nova no fio."
MOTIVO_JANELA_ENCERRADA = (
    "O prazo de 10 minutos para corrigir esta resposta já passou. Ela fica como está; escreva uma resposta nova no fio."
)
MOTIVO_MOVIMENTO_NAO_SE_EDITA = (
    "Esta linha é o registro automático de um movimento da Demanda, e ela não se edita. "
    "Se o movimento foi enganado, mova a Demanda de novo: a correção entra como uma linha nova."
)
# A frase NAO afirma que a pessoa perdeu o acesso: o codigo so sabe que o id
# nao esta na lista de quem tem acesso a aba, e isso tanto pode ser alguem que
# saiu do Super admin quanto um id que veio por fora do app. O que ela diz e o
# desfecho e a saida, que a pessoa tem na propria caixa de texto.
MOTIVO_MENCAO_SEM_ACESSO = (
    "Uma das pessoas mencionadas não está na lista de quem tem acesso à aba Tecnologia. "
    "Tire a menção do texto e envie de novo."
)
# O byte NUL costuma vir colado de outro programa, e o texto parece normal na
# tela: por isso a frase diz de onde ele costuma vir, e nao so que "tem
# caractere invalido".
MOTIVO_RESPOSTA_COM_CARACTERE_INVALIDO = (
    "A resposta tem um caractere invisível que o banco não guarda. "
    "Ele costuma vir junto de texto colado de outro programa: apague o trecho colado e escreva de novo."
)


def instante_do_banco(valor: str | None) -> datetime | None:
    """O `TIMESTAMPTZ` do PostgREST como `datetime` consciente de fuso.

    Devolve `None` quando nao da para ler, e nunca "agora": um `criado_em`
    quebrado que virasse o instante atual abriria a janela de edicao para
    sempre em cima de dado corrompido.

    Data sem fuso conta como UTC porque comparar um `datetime` ingenuo com um
    consciente estoura `TypeError`, e a janela viraria 500 em vez de recusa.
    """
    if not valor:
        return None
    try:
        lido = datetime.fromisoformat(str(valor))
    except ValueError:
        return None
    return lido if lido.tzinfo else lido.replace(tzinfo=UTC)


def dentro_da_janela_de_edicao(*, criado_em: datetime, agora: datetime) -> bool:
    """True enquanto a resposta ainda pode ser corrigida pelo autor.

    A borda exata (10 minutos cravados) AINDA vale: a PRD fala em corrigir
    "por ate 10 minutos", e um limite exclusivo recusaria o clique dado no
    ultimo segundo do prazo prometido.
    """
    return agora - criado_em <= JANELA_DE_EDICAO


def limite_da_janela_de_edicao(criado_em: datetime) -> datetime:
    """Ate quando a resposta aceita correcao.

    A conta e sobre o ENVIO, e nao sobre a ultima edicao: uma janela que se
    renovasse a cada correcao deixaria uma resposta editavel para sempre, e o
    fio deixaria de ser trilha.
    """
    return criado_em + JANELA_DE_EDICAO


def motivo_edicao_recusada(*, linha: dict[str, Any], ator_id: str, agora: datetime) -> str | None:
    """A frase da recusa, ou `None` quando a edicao pode acontecer.

    A ordem das tres guardas e proposital, porque cada uma nomeia uma causa
    diferente e a primeira que responder e a que a pessoa le:

    1. linha de MOVIMENTO nao se edita nunca, nem por quem moveu. Ela vem com
       `autor_id` NULL no banco, entao a guarda de autor diria "nao e sua" a
       quem acabou de mover, e a de janela sugeriria que dentro do prazo daria;
    2. resposta de OUTRA pessoa: o prazo dela nao interessa, porque nem depois
       nem antes ela e sua;
    3. a JANELA, que e o unico caso em que a pessoa certa chegou tarde.
    """
    if linha.get("linha") != "resposta":
        return MOTIVO_MOVIMENTO_NAO_SE_EDITA
    if linha.get("autor_id") != ator_id:
        return MOTIVO_SO_O_AUTOR_EDITA
    criado_em = instante_do_banco(linha.get("criado_em"))
    if criado_em is None or not dentro_da_janela_de_edicao(criado_em=criado_em, agora=agora):
        return MOTIVO_JANELA_ENCERRADA
    return None


def motivo_resposta_invalida(texto: str) -> str | None:
    """Os limites do texto da resposta, com frase de gente.

    Sai daqui, e nao de `min_length`/`max_length` no payload, pelo mesmo motivo
    do titulo da Demanda: o `detail` do pydantic vem em LISTA e a tela mostra o
    JSON cru no alerta vermelho.

    O byte NUL entra na mesma peneira porque o Postgres nao aceita `\\x00` em
    coluna TEXT (erro 22P05): sem esta linha ele passaria a validacao e morreria
    no insert, e quem escreveu levaria o 500 "a sua resposta nao entrou" no
    lugar de uma frase que diz o que houve.
    """
    limpo = texto.strip()
    if not limpo:
        return MOTIVO_RESPOSTA_VAZIA
    if "\x00" in limpo:
        return MOTIVO_RESPOSTA_COM_CARACTERE_INVALIDO
    if len(limpo) > LIMITE_RESPOSTA:
        return f"A resposta pode ter no máximo {LIMITE_RESPOSTA} caracteres."
    return None


def normalizar_mencoes(mencoes: list[str] | None) -> list[str]:
    """A lista de menções limpa: sem espaco em volta, sem vazio, sem repetido.

    Item vazio e sujeira de payload, nao mencao a ninguem: mantido, ele sujaria
    a coluna e ainda faria a guarda de acesso recusar a resposta inteira por
    causa de um `""`, cobrando da pessoa uma correcao que ela nao tem onde
    fazer. A ordem de quem sobra e preservada.

    O controle de repetido e um `set` ao lado da lista, e nao um `in` na propria
    lista: `in` sobre lista e varredura linear, e a conta inteira ficaria
    quadratica. Nao e teoria, foi medido na rota (20 mil ids custavam 0,63s e
    200 mil chegavam perto de um minuto), e como a rota e `async` num uvicorn de
    um worker so, essa conta parava o app inteiro, nao so a aba.
    """
    vistos: set[str] = set()
    ordenados: list[str] = []
    for bruto in mencoes or []:
        limpo = str(bruto).strip()
        if limpo and limpo not in vistos:
            vistos.add(limpo)
            ordenados.append(limpo)
    return ordenados


def motivo_mencoes_demais(*, quantas: int, com_acesso: int) -> str:
    """A recusa da lista de menções maior que a lista de gente da aba.

    O teto natural e o numero de pessoas com acesso: chamar mais gente do que
    existe nao e resposta, e um payload com dezenas de milhares de ids so serve
    para queimar CPU do processo que atende todo mundo. A frase diz os DOIS
    numeros, e a saida (deixar so quem se quer chamar) esta na propria caixa de
    quem escreveu.

    "veio com", e nao "tem": o numero e o que chegou no payload, repetidos
    inclusive, e nao a conta de pessoas distintas chamadas. Dizer "tem 3
    menções" para uma lista com a mesma pessoa tres vezes seria contar uma
    coisa que o texto nao diz.
    """
    return (
        f"Esta resposta veio com {quantas} menções, e só {com_acesso} "
        f"{'pessoa tem' if com_acesso == 1 else 'pessoas têm'} acesso à aba Tecnologia. "
        "Deixe só as menções de quem você quer chamar e envie de novo."
    )


def mencoes_sem_acesso(mencoes: list[str], ids_com_acesso: set[str]) -> list[str]:
    """Quem foi mencionado mas nao esta na lista de pessoas da aba.

    E a mesma regra da porta de atribuir (ADR 0050, decisao 2): chamar para
    dentro do card quem nao consegue abrir a aba deixaria a Demanda esperando
    por alguem que nunca vai ler, e o e-mail da fatia seguinte mandaria um link
    que a pessoa nao abre.
    """
    return [pid for pid in mencoes if pid not in ids_com_acesso]


# ─── O texto do "Copiar para IA" (issue #640) ────────────────────────────────

# O fuso do hospital, o mesmo do resto do app (`ouvidoria_prazos.py`,
# `dados_atendimento.py`). O banco guarda TIMESTAMPTZ em UTC; quem le o texto
# colado numa IA le a hora em que a coisa aconteceu aqui.
FUSO_HOSPITAL = ZoneInfo("America/Sao_Paulo")

# O rotulo que a gente le, como no `ESTADO_ROTULO`. O banco guarda o valor sem
# acento (CHECK da migration 102); a pessoa, e a IA, leem "Decisão".
TIPO_ROTULO: dict[str, str] = {
    "decisao": "Decisão",
    "informacao": "Informação",
    "terceiro": "Terceiro",
    "ajuste": "Ajuste",
    "novo": "Novo",
    "defeito": "Defeito",
    "consultoria": "Consultoria",
}

# A linha de contexto do topo (PRD #634, historia 30). Ela existe porque quem
# cola isto numa IA de fora nao tem como explicar o que e a aba: o texto chega
# sozinho, sem o app em volta.
CABECALHO_PARA_IA = (
    "Este é um pedido de tecnologia registrado no aplicativo do hospital, na aba Tecnologia, "
    "onde o hospital e a Vitta (a empresa que cuida dos sistemas dele) conversam. "
    "Abaixo vão o pedido e a conversa até agora."
)

SEM_DESCRICAO = "(sem descrição)"
SEM_CONVERSA = "(sem conversa até agora)"
SEM_PRODUTO = "(sem Produto)"
# Resposta cujo autor nao foi resolvido. Mesma palavra que a linha de movimento
# usa quando o nome de quem moveu nao veio.
AUTOR_DESCONHECIDO = "Alguém"
SEM_DATA = "sem data"


def momento_para_ia(valor: str | None) -> str:
    """A hora da linha do fio, no fuso do hospital.

    Data ilegivel vira "sem data", e nao o instante atual nem uma linha sem
    marca: quem le precisa saber que aquela linha nao tem hora confiavel, e
    inventar uma seria pior do que dizer isso.
    """
    instante = instante_do_banco(valor)
    if instante is None:
        return SEM_DATA
    return instante.astimezone(FUSO_HOSPITAL).strftime("%d/%m/%Y às %Hh%M")


def linha_para_ia(linha: dict[str, Any]) -> str:
    """Uma linha do fio em texto simples.

    A linha de MOVIMENTO nao ganha prefixo de autor: o texto dela ja foi montado
    pelo backend com o nome de quem moveu ("Pedro moveu para Aguardando"), e
    prefixar de novo sairia "Pedro: Pedro moveu para Aguardando".
    """
    quando = momento_para_ia(linha.get("criado_em"))
    texto = str(linha.get("texto") or "").strip()
    if linha.get("linha") == "movimento":
        return f"[{quando}] {texto}"
    autor = linha.get("autor_nome") or AUTOR_DESCONHECIDO
    return f"[{quando}] {autor}: {texto}"


def texto_para_ia(*, demanda: dict[str, Any], linhas: list[dict[str, Any]]) -> str:
    """A Demanda inteira em texto simples, para colar numa IA (issue #640).

    Mora aqui, e nao na tela, para ser FONTE UNICA: o mesmo texto tem que sair
    do botao do modal, do e-mail e de qualquer outra tela que venha depois. Duas
    montagens divergiriam na primeira mudanca de formato.

    **O que entra**, exatamente o que a issue #640 lista: a linha de contexto,
    titulo, tipo, Produto, descricao e a Conversa inteira em ordem, com as
    linhas de movimento no meio.

    **O que fica de fora**, e por que:

    - **id e e-mail** (da Demanda, do Produto, de quem escreveu): o texto sai do
      app e vai para uma IA de fora. O nome de quem falou e o que a leitura
      precisa; a chave do nosso banco, nao;
    - **estado, prioridade, prazo e responsavel**: sao a operacao do Quadro, e
      quem le esta respondendo ao PEDIDO. A trilha de por onde a Demanda andou
      ja esta nas linhas de movimento do fio, em ordem;
    - **a lista de `mencoes`**: sao ids, e o "@Fulano" que a pessoa escreveu ja
      esta no proprio texto da resposta.

    **Fio enorme:** o texto vai INTEIRO, sem corte. Cortar seria pior do que o
    problema: a linha de contexto promete "o pedido e a conversa ate agora", e
    uma IA que recebesse metade responderia sobre metade sem saber disso. O que
    limita o tamanho na pratica e o teto de 5000 caracteres por resposta
    (`LIMITE_RESPOSTA`), e a rota e de Super admin, com a Demanda pedida uma por
    vez.
    """
    partes: list[str] = [
        CABECALHO_PARA_IA,
        "",
        f"Título: {str(demanda.get('titulo') or '').strip()}",
        f"Tipo: {TIPO_ROTULO.get(str(demanda.get('tipo')), str(demanda.get('tipo') or ''))}",
        f"Produto: {demanda.get('produto_nome') or SEM_PRODUTO}",
        "",
        "Descrição:",
        str(demanda.get("descricao") or "").strip() or SEM_DESCRICAO,
        "",
        "Conversa:",
    ]
    if linhas:
        partes.extend(linha_para_ia(linha) for linha in linhas)
    else:
        partes.append(SEM_CONVERSA)
    return "\n".join(partes)
