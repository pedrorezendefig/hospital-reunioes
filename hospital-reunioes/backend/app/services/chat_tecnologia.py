"""O chat da aba Tecnologia, com o Roteiro do bug (issue #1381, PRD #1380, ADR 0077).

A aba abre na conversa com o Assistente de Tecnologia: "bug ou melhoria?", dois
botoes e um campo livre. O diretor relata, o Assistente classifica e confirma,
e no bug segue o Roteiro do bug: uma pergunta por vez, no maximo cinco (onde, o
que aconteceu, o que esperava, como repetir, o print). Termina num resumo com
"Criar o card" e "Nao bateu".

Mesma separacao do Planejamento da Demanda, e pelo mesmo motivo:

* **o turno** (`turno`) e sem estado: recebe a conversa, o kit e os Produtos e
  devolve a fala da IA, a classificacao e, no fim do roteiro, o resumo. Nao le
  nem grava nada;
* **a guarda** e a do planejamento (`planejamento_demanda.ler`, `gravar`,
  `gravar_chamada`): a conversa mora na mesma tabela, uma por Demanda (ADR 0077,
  decisao 2), e a rota costura.

O modelo e o do planejamento (`LLM_MODEL_PLANEJAMENTO`, decisao 9), pelo mesmo
`chamar_o_modelo`: o prefixo fixo em cache e o custo gravado por chamada.

As regras que a IA nao decide moram aqui, em codigo: o teto de cinco perguntas,
a confirmacao antes do roteiro e o "nao informado" de rotulo sem resposta.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.services import ai_processor, assistente_tecnologia, ferramentas_do_codigo, planejamento_demanda
from app.services.tecnologia import recuar_continuacao
from app.services.tecnologia_vinculo import NAO_INFORMADO, ROTULOS_DO_BUG
from app.utils.text_sanitizer import sanitizar_travessao

logger = logging.getLogger(__name__)

PROMPT = "chat_tecnologia_system"

# O teto do Roteiro do bug (ADR 0077, decisao 4). Quem decide parar antes e o
# modelo; passar daqui, nunca: com cinco perguntas feitas o resumo sai do que
# ja se sabe, queira o modelo perguntar mais ou nao.
TETO_DO_ROTEIRO = 5

ABERTURA = "Isso é um bug, algo que não funciona como deveria, ou uma melhoria?"
OPCOES_DA_ABERTURA = ["Bug", "Melhoria"]

# O botao da abertura vira a fala do diretor, com o texto do proprio botao.
ESCOLHAS: dict[str, str] = {"bug": "Bug", "melhoria": "Melhoria"}

# A Demanda continua no banco como o registro da conversa (decisao 2), com o
# Tipo de antes: bug e Defeito, melhoria e Novo.
TIPO_DA_CLASSIFICACAO: dict[str, str] = {"bug": "defeito", "melhoria": "novo"}

# A melhoria confirmada segue, no proprio chat, pelo Planejamento da Demanda
# (issue #1383): a conversa continua guardada, e dali em diante as falas sao as
# do planejamento (pergunta, resposta, encerrou), com as regras dele.
CAMINHO_DO_PLANEJAMENTO = "planejamento"

# As falas que so o planejamento escreve. A primeira delas, ou a fala da IA que
# passou a conversa ao planejamento (`planejar`), marca onde ele comeca.
TIPOS_DO_PLANEJAMENTO = ("pergunta", "resposta", "encerrou")

TITULO_SEM_RESPOSTA = "Conversa na aba Tecnologia"
LIMITE_DO_TITULO = 200
LIMITE_DO_CAMPO = 2000
LIMITE_DE_CRITERIOS = 8

# Os rotulos do Roteiro do bug, os mesmos que a issue publica. O print e a
# quinta pergunta, mas nao e texto: ele vira Anexo da Demanda e a issue diz so
# quantos ha.
CAMPOS_DO_BUG = ROTULOS_DO_BUG

TEXTO_DO_TETO = "Já tenho o que preciso. Confira o resumo e diga se ele bate com o que aconteceu."

# O criterio de aceite de quando o modelo nao escreveu nenhum: o que o diretor
# esperava, que e a unica coisa que ele disse sobre o "pronto". Sem nem isso, a
# frase nao inventa comportamento: so diz que o problema relatado deixa de
# acontecer.
CRITERIO_SEM_O_ESPERADO = "O problema descrito em O que aconteceu deixa de acontecer."

MOTIVO_SEM_TEXTO = "Escreva a sua mensagem ou escolha uma das opções."
MOTIVO_TURNO_FALHOU = planejamento_demanda.MOTIVO_TURNO_FALHOU

FALA_MOCK = "[MOCK] Conversar com o Assistente de Tecnologia exige a IA configurada."


# ─── As falas guardadas ──────────────────────────────────────────────────────


def mensagem_de_abertura() -> dict:
    """A pergunta com que a aba abre. Nao passa pelo modelo: e sempre a mesma."""
    return {"tipo": "ia", "texto": ABERTURA, "fonte": None, "opcoes": list(OPCOES_DA_ABERTURA)}


def fala_do_diretor(texto: str) -> dict:
    return {"tipo": "diretor", "texto": texto}


def aviso_da_parecida(titulo: str) -> str:
    """O aviso do pedido aberto parecido (issue #1385, ADR 0077, decisao 6):
    pelo titulo, nunca pelo numero, que e vocabulario do repositorio."""
    return (
        f'Antes de criar o card: já existe um pedido aberto parecido, "{_texto_limpo(titulo, LIMITE_DO_TITULO)}". '
        "Veja se não é o mesmo antes de clicar em Criar o card."
    )


def fala_do_aviso(titulo: str) -> dict:
    """O aviso como fala da IA, para o resumo da melhoria, que nao tem fala."""
    return {"tipo": "ia", "texto": aviso_da_parecida(titulo), "fonte": None, "opcoes": []}


def e_do_chat(linha: dict | None) -> bool:
    """Se a conversa guardada e a do chat, e nao a de um Planejamento.

    A regra mora no planejamento, que e quem precisa dela para nao tomar a
    conversa do chat por sua (`planejamento_demanda.e_conversa_do_chat`).
    """
    return planejamento_demanda.e_conversa_do_chat(linha)


def classificacao_atual(mensagens: list[dict]) -> tuple[str | None, bool]:
    """A classificacao da ultima fala da IA que tinha uma, e se ja foi confirmada."""
    for mensagem in reversed(mensagens):
        if mensagem.get("tipo") == "ia" and mensagem.get("classificacao"):
            return mensagem["classificacao"], bool(mensagem.get("confirmada"))
    return None, False


def perguntas_do_roteiro(mensagens: list[dict]) -> int:
    """Quantas perguntas do Roteiro do bug a IA ja fez."""
    return sum(1 for m in mensagens if m.get("tipo") == "ia" and m.get("roteiro"))


def textos_do_diretor(mensagens: list[dict]) -> list[str]:
    """O que o diretor escreveu, sem as falas que sao so o botao da abertura."""
    return [
        m.get("texto") or ""
        for m in mensagens
        if m.get("tipo") in ("diretor", "nao_bateu") and (m.get("texto") or "") not in ESCOLHAS.values()
    ]


def inicio_do_planejamento(mensagens: list[dict]) -> int | None:
    """Onde o planejamento da melhoria comeca na conversa, ou `None` se ele
    ainda nao comecou (a conversa e do bug, ou ainda nao foi classificada).

    O que vem antes e a abertura e o que o diretor contou ao Assistente; o que
    vem dali em diante e o planejamento, lido pelas regras dele.
    """
    for i, mensagem in enumerate(mensagens):
        if mensagem.get("tipo") == "ia" and mensagem.get("planejar"):
            return i + 1
        if mensagem.get("tipo") in TIPOS_DO_PLANEJAMENTO:
            return i
    return None


def em_planejamento(mensagens: list[dict]) -> bool:
    return inicio_do_planejamento(mensagens) is not None


def partes_da_melhoria(mensagens: list[dict]) -> tuple[list[dict], list[dict]]:
    """O que o diretor contou antes do planejamento, e o planejamento."""
    inicio = inicio_do_planejamento(mensagens)
    if inicio is None:
        inicio = len(mensagens)
    return mensagens[:inicio], mensagens[inicio:]


def descricao_da_melhoria(mensagens: list[dict]) -> str | None:
    """O que o diretor disse antes do planejamento: e de onde ele parte."""
    antes, _ = partes_da_melhoria(mensagens)
    return "\n\n".join(textos_do_diretor(antes)).strip() or None


def _fala_do_planejamento_para_a_tela(m: dict) -> dict:
    if m.get("tipo") == "pergunta":
        return {
            "autor": "ia",
            "texto": m.get("contexto") or "",
            "fonte": None,
            "opcoes": [o.get("texto") or "" for o in m.get("opcoes") or []],
            "recomendada": m.get("recomendada"),
            "nao_bateu": False,
        }
    if m.get("tipo") == "encerrou":
        return {"autor": "ia", "texto": m.get("contexto") or "", "fonte": None, "opcoes": [], "nao_bateu": False}
    return {"autor": "diretor", "texto": m.get("texto") or "", "fonte": None, "opcoes": [], "nao_bateu": False}


def para_a_tela(mensagens: list[dict]) -> list[dict]:
    """A conversa como a tela a mostra: quem falou, o texto, a fonte e as opcoes.

    A classificacao e a marca do roteiro sao do backend, e nao saem daqui. A
    pergunta do planejamento sai com as duas opcoes na ordem A e B e a letra da
    recomendada, que e o que a tela destaca e o que o clique devolve.
    """
    return [
        _fala_do_planejamento_para_a_tela(m)
        if m.get("tipo") in TIPOS_DO_PLANEJAMENTO
        else {
            "autor": "ia" if m.get("tipo") == "ia" else "diretor",
            "texto": m.get("texto") or "",
            "fonte": m.get("fonte") if m.get("tipo") == "ia" else None,
            "opcoes": list(m.get("opcoes") or []) if m.get("tipo") == "ia" else [],
            "nao_bateu": m.get("tipo") == "nao_bateu",
        }
        for m in mensagens
    ]


# ─── O turno ─────────────────────────────────────────────────────────────────


class _CamposDoBug(BaseModel):
    model_config = ConfigDict(extra="ignore")

    onde: str | None = None
    o_que_aconteceu: str | None = None
    o_que_esperava: str | None = None
    como_repetir: str | None = None


class _SaidaDoTurno(BaseModel):
    """O esquema da resposta do modelo. O que nao valida aqui e falha do turno."""

    model_config = ConfigDict(extra="ignore")

    classificacao: Literal["bug", "melhoria"]
    confirmada: bool = False
    produto_id: str | None = None
    titulo: str | None = None
    mensagem: str
    fonte: str | None = None
    opcoes: list[str] = Field(default_factory=list)
    campos: _CamposDoBug = Field(default_factory=_CamposDoBug)
    criterios: list[str] = Field(default_factory=list)
    pronto: bool = False
    # O numero do pedido aberto parecido (issue #1385), que o turno so aceita
    # se o modelo o viu na lista das issues abertas neste mesmo turno.
    parecida: int | None = None

    @model_validator(mode="after")
    def _fala_inteira(self):
        if not self.mensagem.strip():
            raise ValueError("mensagem vazia")
        return self


@dataclass(frozen=True)
class ResultadoDoTurno:
    """O que um turno produziu.

    `mensagem` e a fala da IA, pronta para entrar na conversa. `resumo` vem so
    quando o Roteiro do bug terminou. `caminho` e "planejamento" quando a
    melhoria foi confirmada e segue, no proprio chat, pelo Planejamento da
    Demanda (issue #1383). `erro` e a frase da tela quando o turno
    nao aconteceu, e entao o resto e nulo. `chamada` e a linha de custo, nula so
    no modo mock.
    """

    mensagem: dict | None
    classificacao: str | None
    produto_id: str | None
    titulo: str | None
    resumo: dict | None
    caminho: str | None
    erro: str | None
    chamada: dict | None


def _linha_da_conversa(mensagem: dict) -> str:
    """Uma fala como ela entra no pedido. O que veio de fora (print, documento,
    audio) entra cercado, pela mesma regra do Assistente."""
    texto = mensagem.get("texto") or ""
    if mensagem.get("tipo") == "ia":
        return recuar_continuacao(f"IA: {texto}")
    rotulo = "Diretor, sobre o resumo (o que não bateu)" if mensagem.get("tipo") == "nao_bateu" else "Diretor"
    if assistente_tecnologia.PREFIXO_DE_ORIGEM.match(texto):
        cercada = assistente_tecnologia._linha_da_conversa({"role": "user", "content": texto})
        return cercada.replace("Pessoa: ", f"{rotulo}: ", 1)
    return recuar_continuacao(f"{rotulo}: {texto}")


def pedido_do_turno(mensagens: list[dict], produtos: list[dict]) -> str:
    """O que varia de um turno para outro. Vai DEPOIS do bloco fixo em cache."""
    classificacao, confirmada = classificacao_atual(mensagens)
    if classificacao is None:
        onde_esta = "ainda não classificada"
    else:
        situacao = "confirmada pelo diretor" if confirmada else "ainda sem a confirmação do diretor"
        onde_esta = f"{classificacao}, {situacao}"
    feitas = perguntas_do_roteiro(mensagens)
    linhas = [
        "PRODUTOS (use o identificador exato em produto_id)",
        *[f"- {p['id']}: {p.get('nome') or ''}" for p in produtos],
        "",
        "A CONVERSA ATÉ AQUI",
        "\n".join(_linha_da_conversa(m) for m in mensagens),
        "",
        "ONDE A CONVERSA ESTÁ",
        f"Classificação: {onde_esta}",
        f"Perguntas do Roteiro do bug já feitas: {feitas} de {TETO_DO_ROTEIRO}",
    ]
    if feitas >= TETO_DO_ROTEIRO:
        linhas.append("Não pergunte mais nada: monte o resumo agora, com pronto true.")
    return "\n".join(linhas)


def _texto_limpo(valor: str | None, teto: int) -> str:
    return sanitizar_travessao(" ".join((valor or "").split()))[:teto].strip()


def resumo_do_bug(campos: _CamposDoBug, criterios: list[str], *, titulo: str) -> dict:
    """O resumo que o diretor confere: os quatro rotulos e os criterios.

    Rotulo sem resposta sai "nao informado" (ADR 0077, Roteiro do bug): o card
    nao deixa de nascer por falta de informacao, e o que faltou fica dito.
    """
    resumo: dict = {"titulo": titulo}
    for campo in CAMPOS_DO_BUG:
        resumo[campo] = _texto_limpo(getattr(campos, campo), LIMITE_DO_CAMPO) or NAO_INFORMADO
    limpos = [c for c in (_texto_limpo(c, LIMITE_DO_CAMPO) for c in criterios) if c][:LIMITE_DE_CRITERIOS]
    if not limpos:
        esperado = resumo["o_que_esperava"]
        limpos = [esperado if esperado != NAO_INFORMADO else CRITERIO_SEM_O_ESPERADO]
    resumo["criterios"] = limpos
    return resumo


def _mock(escolha: str | None, produtos: list[dict], titulo_atual: str | None) -> ResultadoDoTurno:
    logger.warning("Modo MOCK ativo para o chat da Tecnologia (sem chave LLM)")
    classificacao = escolha or "bug"
    return ResultadoDoTurno(
        mensagem={"tipo": "ia", "texto": FALA_MOCK, "fonte": None, "opcoes": [], "classificacao": classificacao},
        classificacao=classificacao,
        produto_id=produtos[0]["id"] if produtos else None,
        titulo=titulo_atual or TITULO_SEM_RESPOSTA,
        resumo=None,
        caminho=None,
        erro=None,
        chamada=None,
    )


def turno(
    *,
    mensagens: list[dict],
    kit: str,
    produtos: list[dict],
    escolha: str | None = None,
    titulo_atual: str | None = None,
    demanda_id: str | None = None,
) -> ResultadoDoTurno:
    """Um turno do chat. Sem estado: tudo chega por parametro.

    `mensagens` e a conversa inteira, ja com a fala nova do diretor no fim.
    `escolha` e o botao da abertura ("bug" ou "melhoria"): quem clicou ja
    confirmou, e o modelo nao desdiz.
    """
    if ai_processor._llm_provider() == "mock":
        return _mock(escolha, produtos, titulo_atual)

    consultas = ferramentas_do_codigo.Consultas()
    saida, chamada = planejamento_demanda.chamar_o_modelo(
        demanda={"id": demanda_id},
        passo="pergunta",
        conteudo=pedido_do_turno(mensagens, produtos),
        kit=kit,
        validar=_SaidaDoTurno.model_validate,
        prompt=PROMPT,
        consultas=consultas,
    )
    if saida is None:
        return ResultadoDoTurno(
            mensagem=None,
            classificacao=None,
            produto_id=None,
            titulo=None,
            resumo=None,
            caminho=None,
            erro=MOTIVO_TURNO_FALHOU,
            chamada=chamada,
        )

    anterior, confirmada_antes = classificacao_atual(mensagens)
    classificacao = escolha or saida.classificacao
    # So o diretor confirma. O botao da abertura ja e a confirmacao; fora dele,
    # o `confirmada` do modelo so vale quando o diretor ja viu uma
    # classificacao numa fala anterior da IA e respondeu a ela. No primeiro
    # turno de texto livre ele nao viu nenhuma, e o modelo nao confirma por ele.
    ja_viu = anterior is not None
    confirmada = escolha is not None or (
        ja_viu and (saida.confirmada or (confirmada_antes and classificacao == anterior))
    )
    ids = {p["id"] for p in produtos}
    titulo = _texto_limpo(saida.titulo, LIMITE_DO_TITULO) or titulo_atual or TITULO_SEM_RESPOSTA

    no_roteiro = classificacao == "bug" and confirmada
    resumo = None
    caminho = None
    texto = saida.mensagem
    if no_roteiro and (saida.pronto or perguntas_do_roteiro(mensagens) >= TETO_DO_ROTEIRO):
        resumo = resumo_do_bug(saida.campos, saida.criterios, titulo=titulo)
        if not saida.pronto:
            texto = TEXTO_DO_TETO
        parecida = consultas.issues_vistas.get(saida.parecida) if saida.parecida is not None else None
        if parecida:
            texto = f"{texto.strip()} {aviso_da_parecida(parecida)}"
    elif classificacao == "melhoria" and confirmada and saida.pronto:
        caminho = CAMINHO_DO_PLANEJAMENTO

    mensagem = {
        "tipo": "ia",
        "texto": sanitizar_travessao(texto.strip()),
        "fonte": _texto_limpo(saida.fonte, LIMITE_DO_TITULO) or None,
        "opcoes": [o for o in (_texto_limpo(o, LIMITE_DO_TITULO) for o in saida.opcoes) if o][:2],
        "classificacao": classificacao,
        "confirmada": confirmada,
        "roteiro": no_roteiro and resumo is None,
    }
    return ResultadoDoTurno(
        mensagem=mensagem,
        classificacao=classificacao,
        produto_id=saida.produto_id if saida.produto_id in ids else None,
        titulo=titulo,
        resumo=resumo,
        caminho=caminho,
        erro=None,
        chamada=chamada,
    )


# ─── A melhoria (issue #1383) ────────────────────────────────────────────────


def demanda_da_melhoria(mensagens: list[dict], *, demanda_id: str | None, titulo: str | None) -> dict:
    """A Demanda como o planejamento a le: o que o diretor contou e o titulo,
    menos o titulo provisorio, que nao diz nada ao modelo."""
    return {
        "id": demanda_id,
        "tipo": TIPO_DA_CLASSIFICACAO["melhoria"],
        "titulo": "" if titulo in (None, TITULO_SEM_RESPOSTA) else titulo,
        "descricao": descricao_da_melhoria(mensagens),
    }


def turno_da_melhoria(
    *, mensagens: list[dict], kit: str, demanda_id: str | None = None, titulo: str | None = None
) -> planejamento_demanda.ResultadoDoTurno:
    """Um turno do planejamento da melhoria dentro do chat. Sem estado.

    `mensagens` e a conversa inteira, ja com a resposta do diretor no fim. O
    turno e o do Planejamento da Demanda, com as regras dele (uma pergunta,
    duas opcoes, a recomendada, sem teto de perguntas), sobre a parte da conversa que e
    do planejamento.
    """
    _, planejamento = partes_da_melhoria(mensagens)
    return planejamento_demanda.turno(
        demanda=demanda_da_melhoria(mensagens, demanda_id=demanda_id, titulo=titulo),
        mensagens=planejamento,
        kit=kit,
        consultas=ferramentas_do_codigo.Consultas(),
    )


def resumo_da_melhoria(
    *, mensagens: list[dict], kit: str, demanda_id: str, titulo: str | None
) -> planejamento_demanda.ResultadoDoResumo:
    """O "Fechar e resumir" da melhoria: o resumo do Planejamento da Demanda,
    com o que ficou em aberto e a secao do glossario, sobre a parte da conversa
    que e do planejamento."""
    _, planejamento = partes_da_melhoria(mensagens)
    return planejamento_demanda.resumir(
        demanda=demanda_da_melhoria(mensagens, demanda_id=demanda_id, titulo=titulo),
        mensagens=planejamento,
        kit=kit,
        consultas=ferramentas_do_codigo.Consultas(),
    )
