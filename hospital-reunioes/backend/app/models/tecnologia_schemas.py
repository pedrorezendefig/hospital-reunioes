"""Schemas Pydantic da aba Tecnologia (PRD #634, ADR 0050).

Arquivo proprio, e nao mais um bloco em `admin_schemas.py`, porque a aba
Tecnologia e um contexto inteiro (Produto, Demanda, Conversa) que cresce nas
fatias seguintes.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class PessoaDaAba(BaseModel):
    """Alguem com acesso a aba: participante ativo com Super admin.

    A mesma lista serve para dono de Produto, responsavel de Demanda e
    @mencao (PRD #634).
    """

    id: str
    nome_completo: str
    email: str


class ProdutoResponse(BaseModel):
    """Produto como a tela o le."""

    id: str
    nome: str
    ativo: bool
    ordem: int
    dono_id: str | None = None
    # Resolvido pelo backend: o dono pode ter deixado de ser Super admin, e ai
    # o nome dele nao estaria na lista de pessoas que a tela carrega.
    dono_nome: str | None = None


class ProdutoCreatePayload(BaseModel):
    nome: str = Field(..., min_length=1, max_length=120)
    dono_id: str | None = None
    ordem: int | None = None


class ProdutoUpdatePayload(BaseModel):
    """Campos ausentes ficam como estao.

    `dono_id: null` explicito no JSON tira o dono, e por isso o router olha
    `model_fields_set` em vez de tratar `None` como "nao informado".
    """

    nome: str | None = Field(default=None, min_length=1, max_length=120)
    ativo: bool | None = None
    dono_id: str | None = None
    ordem: int | None = None


# ─── Demanda e Conversa (issue #637) ─────────────────────────────────────────

# As tres listas fechadas, como o payload as ve. Sao os mesmos valores das
# tuplas do servico e do CHECK da migration 102; `Literal` aqui e o que faz o
# FastAPI recusar com 422 um tipo, estado ou prioridade fora da lista, antes de
# a linha chegar ao banco. O teste amarra as duas pontas.
TipoDemanda = Literal["decisao", "informacao", "terceiro", "ajuste", "novo", "defeito", "consultoria"]
EstadoDemanda = Literal["nova", "em_andamento", "aguardando", "concluida", "cancelada"]
PrioridadeDemanda = Literal["baixa", "normal", "alta"]


class DemandaResponse(BaseModel):
    """Demanda como o card e o modal a leem.

    `produto_nome` e `responsavel_nome` sao resolvidos pelo backend: o card
    mostra os dois, e cruzar tabela na tela deixaria o nome em branco toda vez
    que a pessoa saisse da lista de quem tem acesso a aba.

    Os campos de estado e prioridade sao `str`, e nao `Literal`: aqui se le o
    que o banco tem. Uma linha antiga com valor fora da lista fechada deve
    aparecer na tela, e nao derrubar a listagem inteira com erro de validacao.
    """

    id: str
    titulo: str
    descricao: str | None = None
    tipo: str
    produto_id: str
    produto_nome: str | None = None
    estado: str
    responsavel_id: str | None = None
    responsavel_nome: str | None = None
    autor_id: str | None = None
    prioridade: str
    prazo: str | None = None
    criado_em: str | None = None
    atualizado_em: str | None = None
    concluida_em: str | None = None
    concluida_por: str | None = None
    cancelada_em: str | None = None
    cancelada_por: str | None = None


class DemandaCreatePayload(BaseModel):
    """A Demanda nasce com o que da para preencher em menos de um minuto.

    Nao ha `estado` nem `responsavel_id`: a Demanda nasce em `nova` e atribuida
    ao dono do Produto (ADR 0050, decisao 4). Quem manda esses campos na criacao
    estaria escolhendo por uma regra que e do backend.
    """

    # Sem `min_length` NEM `max_length`: quem cuida dos dois limites do titulo
    # e o router (`_titulo_valido`), com frase de gente. O pydantic responde
    # ANTES dele e devolve `detail` em LISTA, que a tela mostra como JSON cru
    # no alerta vermelho. Vale para os dois extremos: apagar o campo e colar um
    # texto de 300 caracteres sao enganos igualmente comuns.
    titulo: str
    tipo: TipoDemanda
    produto_id: str = Field(..., min_length=1)
    descricao: str | None = None
    prioridade: PrioridadeDemanda = "normal"
    # Texto ISO (`2026-10-01`) ou vazio. O router normaliza e valida: `""` nao e
    # NULL, e gravado numa coluna DATE seria erro de banco, nao 422.
    prazo: str | None = None


class DemandaUpdatePayload(BaseModel):
    """Os campos que o modal edita. Campo ausente fica como esta.

    `estado` e `responsavel_id` NAO entram: as portas deles sao `mover` e
    `atribuir`, que gravam a linha de movimento na Conversa. Aceitar os dois
    aqui moveria a Demanda sem deixar rastro no fio.

    `prazo: null` explicito limpa o prazo, e por isso o router olha
    `model_fields_set` em vez de tratar `None` como "nao informado".
    """

    # Sem limite de tamanho, pelo mesmo motivo do payload de criacao: apagar o
    # Título no modal, ou colar um texto longo nele, tem que devolver a frase
    # de gente, e nao o JSON do pydantic.
    titulo: str | None = None
    descricao: str | None = None
    tipo: TipoDemanda | None = None
    produto_id: str | None = Field(default=None, min_length=1)
    prioridade: PrioridadeDemanda | None = None
    prazo: str | None = None


class MoverPayload(BaseModel):
    """A coluna de destino. A maquina de estados decide se o caminho existe."""

    estado: EstadoDemanda


class AtribuirPayload(BaseModel):
    """Quem passa a responder pela Demanda, entre as pessoas com acesso a aba."""

    responsavel_id: str = Field(..., min_length=1)


class ConversaLinhaResponse(BaseModel):
    """Uma linha do fio: resposta de gente ou movimento automatico.

    `autor_nome` vem nulo na linha de movimento, que nao tem autor no banco: o
    nome de quem moveu ja esta no `texto` montado pelo backend.
    """

    id: str
    demanda_id: str
    autor_id: str | None = None
    autor_nome: str | None = None
    linha: str
    texto: str
    mencoes: list[str] = []
    movimento_campo: str | None = None
    movimento_de: str | None = None
    movimento_para: str | None = None
    criado_em: str | None = None
    editado_em: str | None = None
    # Ate quando ESTA pessoa pode corrigir ESTA linha, ou `None` quando ela nao
    # pode (linha de movimento, resposta de outra pessoa, data ilegivel).
    #
    # Quem calcula e o backend porque a tela nao sabe qual participante e o
    # usuario logado: o `useAuth` do front carrega o id do Supabase Auth, e nao
    # o `participantes.id` que assina a linha. Vai o INSTANTE, e nao um booleano
    # "pode": o modal fica aberto enquanto a janela corre, e um booleano
    # congelado no carregamento continuaria dizendo "pode" dez minutos depois.
    editavel_ate: str | None = None


class TextoParaIaResponse(BaseModel):
    """O texto do "Copiar para IA", ja montado (issue #640).

    O corpo e um objeto, e nao a string solta, porque uma resposta que e so um
    texto nao tem onde crescer: qualquer coisa que venha junto depois (um aviso
    de fio grande, por exemplo) quebraria quem le.
    """

    texto: str


class RespostaPayload(BaseModel):
    """O que a caixa de resposta manda, ao enviar e ao corrigir.

    `mencoes` sao os ids escolhidos no autocomplete do @, e nao um texto para o
    backend adivinhar: casar "@Fulano de Tal" dentro da frase por conta propria
    erraria em nome com espaco e em nome que e prefixo de outro. Quem escolheu
    na lista sabe de quem se trata; o backend confere se essa pessoa tem acesso
    a aba (a mesma regra da porta de atribuir) e grava.

    Sem `min_length`/`max_length`: os dois limites do texto saem do servico com
    frase de gente, porque o `detail` do pydantic vem em LISTA e a tela mostra o
    JSON cru no alerta vermelho.
    """

    texto: str
    mencoes: list[str] | None = None
