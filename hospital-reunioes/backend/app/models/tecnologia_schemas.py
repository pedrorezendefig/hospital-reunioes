"""Schemas Pydantic da aba Tecnologia (PRD #634, ADR 0050).

Desde a ADR 0077 a aba e o chat do agente e mais nada: aqui ficam a lista das
conversas, os turnos do chat e a leitura do print (issue #1386).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ParteDaEntrega(BaseModel):
    """Uma parte da entrega como o diretor a le (issue #676, ADR 0054, decisao 7).

    Duas coisas, e nada mais: o que aquela parte muda para ele e em que pe ela
    esta. O titulo e o numero da fatia NAO entram, porque sao tecnicos.

    `situacao` e opcional porque uma linha gravada antes desta fatia nao a tem: a
    tela desenha o texto sem selo em vez de derrubar a conversa inteira.
    """

    o_que_muda: str | None = None
    situacao: str | None = None


class DemandaResponse(BaseModel):
    """Uma conversa da lista lateral do chat (issue #1384, ADR 0077).

    So o que o diretor le: o titulo, a Etapa (com as partes e a versao) e O que
    muda. Numero e endereco da issue nao saem daqui (ADR 0054, decisao 9);
    `tem_vinculo` diz so que o card ja nasceu.
    """

    id: str
    titulo: str
    criado_em: str | None = None
    # `registrada` (o default do banco) e a conversa sem card.
    etapa: str = "registrada"
    partes_entregues: int | None = None
    partes_total: int | None = None
    tem_vinculo: bool = False
    # O bloco "Para o diretor" da issue-raiz e o de cada parte, lidos do GitHub
    # e NUNCA digitados no app (ADR 0054, decisao 7). Nulo e "a Vitta ainda nao
    # escreveu", e a tela o traduz numa frase.
    o_que_muda: str | None = None
    partes: list[ParteDaEntrega] = []
    # A versao em que a Demanda subiu, RESOLVIDA pelo backend: vem preenchida so
    # quando a Etapa e Em producao (`versao_da_entrega`), e o selo a mostra
    # ("Em producao desde v0.165.0", issue #1065). A tela nao repete a regra.
    versao: str | None = None
    # O selo ao lado da Etapa (issue #1438): o Tipo da Demanda traduzido de
    # volta para a pergunta do chat. Nulo no Tipo de antes do chat.
    classificacao: Literal["bug", "melhoria"] | None = None


# O teto de uma fala do chat. E do pydantic, e nao do router, porque aqui nao
# ha frase de gente a preservar: um texto de 50 mil caracteres nao veio da tela,
# veio de um cliente que resolveu mandar o que quisesse para uma rota que gasta
# token de LLM a cada chamada.
LIMITE_DA_MENSAGEM = 5000


# ─── A leitura do print (PRD #726, ADR 0056) ─────────────────────────────────


class AssistenteImagemResponse(BaseModel):
    """Resposta do POST /admin/tecnologia/assistente/descrever-imagem.

    So o texto, e nao o nome do arquivo: o prefixo de origem do print e
    `[print] ` seco, sem nome. O nome de um print e "Captura de tela
    2026-09-17 as 14.02.11.png", que nao diz nada a quem le a conversa, e a
    imagem nao e guardada em lugar nenhum para alguem querer achar depois
    (ADR 0056, decisao 4).

    `print_id` e o identificador efemero do print (issue #1062): a imagem fica
    so na memoria do backend e vira Anexo quando a fala do chat que o leva entra
    na conversa.
    """

    texto: str
    print_id: str | None = None


class AssistenteDocumentoResponse(BaseModel):
    """Resposta do POST /admin/tecnologia/assistente/ler-documento (issue #1520).

    O texto extraido NAO sai daqui: a tela mostra so o nome e o tamanho, e o
    texto fica no backend, na memoria e depois na fala. `caracteres` e quanto
    o agente vai ler.
    """

    documento_id: str
    nome: str
    tamanho_bytes: int
    caracteres: int


# ─── O resumo da melhoria (issue #1383, ADR 0077) ───────────────────────────


class DecisaoDoResumo(BaseModel):
    """Uma decisao do resumo: a pergunta da IA, a resposta do diretor e uma
    linha de porque. As duas primeiras vem da conversa, nunca do modelo."""

    pergunta: str
    escolha: str
    porque: str


class ResumoDoPlanejamento(BaseModel):
    decisoes: list[DecisaoDoResumo] = []
    em_aberto: list[str] = []
    # A secao "Para o glossario" do PRD do diretor (issue #1383).
    termos: list[str] = []
    candidatas_a_adr: list[str] = []


# ─── O chat da aba (issue #1381, PRD #1380, ADR 0077) ────────────────────────


class ChatPrimeiroTurnoPayload(BaseModel):
    """Corpo do POST /admin/tecnologia/chat: o primeiro turno, que faz a
    Demanda nascer. Leva o botao da abertura ("bug" ou "melhoria"), o texto
    livre, ou os dois; quem recusa o corpo vazio e a rota, com frase de gente.

    `prints` sao os identificadores efemeros dos prints que a rota
    `descrever-imagem` leu: viram Anexo da Demanda na hora em que o turno entra.
    """

    escolha: Literal["bug", "melhoria"] | None = None
    texto: str | None = Field(default=None, max_length=LIMITE_DA_MENSAGEM)
    prints: list[str] = Field(default_factory=list, max_length=10)
    # Os identificadores dos documentos que a rota `ler-documento` leu (issue
    # #1520): o texto entra na fala, fora do teto da mensagem, e o original
    # vira Anexo quando a fala entra na conversa.
    documentos: list[str] = Field(default_factory=list, max_length=10)


class ChatTurnoPayload(BaseModel):
    """Corpo do POST /admin/tecnologia/chat/{id}: a fala do diretor.

    Sem texto, o turno e o "tente de novo" da IA: vale so quando a ultima fala
    guardada e do diretor (o "nao bateu"). No planejamento da melhoria (issue
    #1383), `opcao` e a letra da opcao clicada, e a resposta e ela OU o texto.
    """

    opcao: Literal["A", "B"] | None = None
    texto: str | None = Field(default=None, max_length=LIMITE_DA_MENSAGEM)
    prints: list[str] = Field(default_factory=list, max_length=10)
    documentos: list[str] = Field(default_factory=list, max_length=10)
    # O "Continuar respondendo" do resumo da melhoria com lacuna (issue #1440):
    # a fala sai do "Ficou em aberto" guardado, sem opcao nem texto.
    continuar: bool = False


class ChatNaoBateuPayload(BaseModel):
    """Corpo do POST .../chat/{id}/nao-bateu: o que nao bateu no resumo."""

    texto: str | None = Field(default=None, max_length=LIMITE_DA_MENSAGEM)


class DocumentoDaFala(BaseModel):
    """O documento que uma fala do diretor trouxe, como a tela o mostra: o nome
    e o tamanho, e nunca o texto (issue #1520)."""

    nome: str
    tamanho_bytes: int


class FalaDoChat(BaseModel):
    autor: Literal["ia", "diretor"]
    texto: str
    fonte: str | None = None
    opcoes: list[str] = []
    # A letra da opcao recomendada, so na pergunta do planejamento da melhoria
    # (issue #1383): as `opcoes` vem na ordem A e B.
    recomendada: Literal["A", "B"] | None = None
    nao_bateu: bool = False
    documentos: list[DocumentoDaFala] = []


class ResumoDoBug(BaseModel):
    """O resumo do Roteiro do bug, como o diretor o confere."""

    titulo: str
    onde: str
    o_que_aconteceu: str
    o_que_esperava: str
    como_repetir: str
    criterios: list[str]


class CustoDaConversa(BaseModel):
    """O modelo da chamada mais recente, no nome de exibicao ("Opus 5.5"), e a
    soma em dolar das chamadas de IA da Demanda. `custo_usd` nulo = nao medido:
    alguma chamada com tokens gravou custo zero (modelo sem preco)."""

    modelo: str
    custo_usd: float | None = None


class ChatResponse(BaseModel):
    """A conversa do chat como a tela a mostra.

    `estado` segue o do planejamento: `em_andamento`, `resumido` (o resumo do
    bug esperando "Criar o card" ou "Nao bateu") e `enviado` (o card nasceu).
    `planejamento` verdadeiro e a melhoria confirmada, que segue no proprio
    chat pelo Planejamento da Demanda (issue #1383); o estado `encerrado` e o
    teto ou o fim das perguntas, esperando o "Fechar e resumir".
    Tokens nunca saem por aqui (ADR 0077, decisao 9). O custo sai, so na
    conversa aberta e nunca na lista: `custo` e nulo sem chamada nenhuma
    (ADR 0079, decisao 6, issue #1439).
    """

    demanda_id: str
    estado: str | None = None
    mensagens: list[FalaDoChat] = []
    resumo: ResumoDoBug | None = None
    # O resumo do planejamento da melhoria (issue #1383), com `planejamento`
    # verdadeiro: as decisoes e o que ficou em aberto.
    resumo_da_melhoria: ResumoDoPlanejamento | None = None
    anexos: int = 0
    planejamento: bool = False
    aviso_dos_anexos: str | None = None
    custo: CustoDaConversa | None = None
