"""O Assistente de Tecnologia (PRD #726, ADR 0056).

O quarto agente conversacional do app, no mesmo molde dos tres que ja existem
em `ai_processor` (sem estado no servidor, resposta JSON, prompts em `.md`,
sanitizador de travessao, modo mock sem chave). Mora em modulo proprio, e nao
dentro do `ai_processor`, porque tudo que ele sabe e do dominio da aba
Tecnologia: as listas fechadas de Tipo e prioridade, os Produtos e o kit.

A diferenca de fundo para os outros tres: **ele nao grava nada**. O que sai
daqui e um rascunho para a pessoa conferir e clicar em "Criar Demanda", pela
mesma rota de sempre (ADR 0056, decisao 1).

O cliente do LLM vem por `ai_processor` de proposito, pelo MODULO e nao por
`from ... import`: e o que mantem o dublê dos testes (que troca
`ai_processor._llm_provider` e `ai_processor._get_llm`) valendo aqui tambem.
"""

from __future__ import annotations

import json
import logging
from datetime import date

from app.services import ai_processor
from app.services.prompt_loader import load_prompt, render_prompt
from app.services.tecnologia import PRIORIDADES, TIPOS, recuar_continuacao
from app.utils.text_sanitizer import sanitizar_estrutura, sanitizar_travessao

logger = logging.getLogger(__name__)

# A cerca do kit, no molde do "Copiar para IA" (ADR 0056; ver
# `MARCA_INICIO_CONVERSA` em `services/tecnologia.py`). O kit e texto curado
# pela Vitta, mas entra cercado do mesmo jeito: a moldura e o que deixa dito no
# prompt onde acaba a instrucao e comeca o material de consulta.
MARCA_INICIO_KIT = "--- início do kit ---"
MARCA_FIM_KIT = "--- fim do kit ---"

# A mesma cerca para as Demandas abertas.
#
# Nesta fatia o bloco chega vazio, mas ele nasce cercado porque o que vai
# carrega-lo e titulo e Produto escritos por OUTRAS pessoas, e sem a cerca esse
# texto entraria no prompt de quem esta conversando na coluna zero, no meio de
# um documento cujas secoes sao exatamente linhas em maiusculas seguidas de
# dois-pontos. Poe-la depois seria poe-la tarde.
MARCA_INICIO_DEMANDAS = "--- início das Demandas abertas ---"
MARCA_FIM_DEMANDAS = "--- fim das Demandas abertas ---"

# A primeira linha de dentro da cerca e do backend, e nao do kit: e ela que faz
# `recuar_continuacao` empurrar TODAS as linhas do material para a direita. Com
# a primeira coluna sempre nossa, nenhuma linha escrita la dentro consegue
# passar por marca de fim.
TITULO_DO_KIT = "Material escrito pela Vitta sobre a plataforma:"
TITULO_DAS_DEMANDAS = "Demandas que já estão abertas no Quadro:"

# Os tetos dos dois campos de TEXTO do rascunho.
#
# Eles existem pelo mesmo motivo dos tetos de `messages`, e fechavam um buraco
# que aqueles deixavam aberto: o rascunho volta inteiro no corpo de cada turno e
# vai para o prompt em `json.dumps`, entao sem teto aqui o unico limite do que
# chega ao provedor era o do corpo do app inteiro (100 MB), a dez chamadas por
# minuto. Os outros quatro campos ja eram peneirados contra listas fechadas.
#
# O titulo e o mesmo 200 do formulario de sempre (`LIMITE_TITULO` do router). A
# descricao e da ordem de uma fala do chat: o Roteiro por Tipo tem no maximo
# cinco rotulos, e 5000 caracteres cabem folgados.
LIMITE_DO_TITULO = 200
LIMITE_DA_DESCRICAO = 5000

# Duas frases, e nao uma, porque o codigo SABE qual dos dois campos estourou:
# uma frase so mandaria encurtar o titulo de quem escreveu demais na descricao.
MOTIVO_TITULO_GRANDE = (
    f"O título do rascunho passou de {LIMITE_DO_TITULO} caracteres. Encurte o título e mande de novo."
)
MOTIVO_DESCRICAO_GRANDE = (
    f"A descrição do rascunho passou de {LIMITE_DA_DESCRICAO} caracteres. "
    "Encurte a descrição, ou crie a Demanda com o que já tem e siga o texto por lá."
)

SEM_DEMANDAS_ABERTAS = "(nenhuma)"
SEM_PRODUTOS = "(nenhum Produto ativo)"
SEM_CONVERSA = "(a conversa ainda não começou)"

REPLY_MOCK = "[MOCK] Recebi sua mensagem. Montar a Demanda conversando exige a IA configurada."
REPLY_ERRO = "Desculpe, houve um erro ao processar sua mensagem. Tente novamente."

# O rascunho vazio: os campos do formulario de hoje, mais o prazo.
#
# `tipo` e `produto_id` nascem NULOS, e nao num valor de exemplo, porque quem
# escolhe os dois e a conversa. Um `tipo` de partida seria um palpite do app
# que o prompt mandaria o modelo preservar (regra "preserve o que ja esta
# preenchido"), e a Demanda nasceria com o Tipo errado calada.
RASCUNHO_VAZIO: dict = {
    "titulo": "",
    "tipo": None,
    "produto_id": None,
    "prioridade": "normal",
    "prazo": None,
    "descricao": "",
}


def _cercar(texto: str, *, titulo: str, inicio: str, fim: str) -> str:
    """Um bloco de texto de gente entre marcas, com todas as linhas recuadas.

    A primeira linha de dentro e o `titulo`, que e do backend: e ele que faz o
    `recuar_continuacao` empurrar TODO o resto para a direita, e com a primeira
    coluna sempre nossa nenhuma linha la dentro consegue passar por marca.
    """
    return "\n".join([inicio, recuar_continuacao(f"{titulo}\n{texto}"), fim])


def _bloco_produtos(produtos: list[dict]) -> str:
    if not produtos:
        return SEM_PRODUTOS
    return "\n".join(f"- {p['nome']} (produto_id: {p['id']})" for p in produtos)


def _bloco_demandas_abertas(demandas: list[dict]) -> str:
    """As Demandas abertas que o assistente enxerga.

    Só o cabeçalho de cada uma (nunca a Conversa, ADR 0056): o prompt não
    carrega o fio inteiro de nada.
    """
    if not demandas:
        return SEM_DEMANDAS_ABERTAS
    return "\n".join(
        f"- {d.get('titulo', '')} (Produto: {d.get('produto_nome') or 'sem Produto'}; estado: {d.get('estado', '')})"
        for d in demandas
    )


def _texto(valor, anterior: str, teto: int) -> str:
    """Texto que passa do teto volta ao anterior, como valor fora de lista.

    Na entrada, a rota ja recusou o que passa do teto com frase de gente, entao
    esta guarda nao chega a ser vista. Na saida do modelo ela e o que impede o
    painel de ficar com uma descricao que o proprio turno seguinte recusaria:
    guarda-corpo que vira beco nao e guarda-corpo.
    """
    return valor if isinstance(valor, str) and len(valor) <= teto else anterior


def _da_lista(valor, lista: tuple[str, ...], anterior):
    """Valor fora da lista fechada volta ao anterior (ADR 0008: o LLM conversa,
    o backend valida). Vale para Tipo e prioridade."""
    return valor if isinstance(valor, str) and valor in lista else anterior


def _prazo_iso(valor) -> str | None:
    """Prazo so em ISO valido; qualquer outra coisa e LIMPA, nao preservada.

    Limpar, e nao preservar, e o certo para o valor que CHEGOU errado: a data e
    o campo que o prompt manda so preencher quando a pessoa disser uma data de
    verdade, e uma data velha sobrevivendo a uma correcao ("esquece o prazo")
    viraria compromisso que ninguem assumiu.

    Isto vale para o prazo que veio. O prazo que NAO veio e outro caso, e quem
    decide e `normalizar_rascunho`.
    """
    if not isinstance(valor, str) or not valor.strip():
        return None
    try:
        return date.fromisoformat(valor.strip()).isoformat()
    except ValueError:
        return None


def motivo_rascunho_grande(bruto) -> str | None:
    """A frase de recusa quando o rascunho que chegou passa de um dos tetos.

    Mora aqui, e nao num `max_length` do pydantic, pelo mesmo motivo do titulo
    da Demanda (ver `DemandaCreatePayload`): o pydantic responde ANTES do router
    e devolve `detail` em LISTA, que a tela mostra como JSON cru no alerta
    vermelho. Devolvendo a frase, a recusa entra pela mesma porta do resto e
    chega legivel.
    """
    if not isinstance(bruto, dict):
        return None
    titulo = bruto.get("titulo")
    if isinstance(titulo, str) and len(titulo) > LIMITE_DO_TITULO:
        return MOTIVO_TITULO_GRANDE
    descricao = bruto.get("descricao")
    if isinstance(descricao, str) and len(descricao) > LIMITE_DA_DESCRICAO:
        return MOTIVO_DESCRICAO_GRANDE
    return None


def rascunho_de_entrada(bruto, *, ids_de_produto: set[str]) -> dict:
    """O rascunho que chegou da tela, com o shape completo garantido.

    O `produto_id` e peneirado contra os Produtos ATIVOS aqui tambem, e nao so
    na saida do modelo: ele vem do cliente, entra no prompt junto com o resto do
    rascunho, e um id que o app nao conhece nao tem o que fazer la.
    """
    bruto = bruto if isinstance(bruto, dict) else {}
    produto = bruto.get("produto_id")
    return {
        "titulo": _texto(bruto.get("titulo"), "", LIMITE_DO_TITULO),
        "tipo": _da_lista(bruto.get("tipo"), TIPOS, None),
        "produto_id": produto if produto in ids_de_produto else None,
        "prioridade": _da_lista(bruto.get("prioridade"), PRIORIDADES, "normal"),
        "prazo": _prazo_iso(bruto.get("prazo")),
        "descricao": _texto(bruto.get("descricao"), "", LIMITE_DA_DESCRICAO),
    }


def normalizar_rascunho(novo, atual: dict, *, ids_de_produto: set[str]) -> dict:
    """O rascunho que o modelo devolveu, peneirado contra as listas fechadas.

    Campo que nao veio, ou veio com valor que o app nao conhece, volta ao valor
    ANTERIOR: e isso que faz a correcao escrita a mao sobreviver a um turno em
    que o modelo se distraiu.

    O prazo tem os dois casos separados, e a diferenca importa: a pessoa digita
    a data no campo, manda a mensagem seguinte, e o modelo, que nao tinha nada
    a dizer sobre prazo, simplesmente omite a chave. Tratar a omissao como
    "limpe" apagaria a data dela sem aviso. Entao: chave AUSENTE preserva;
    chave PRESENTE com lixo (ou nula) limpa, que e o pedido explicito.
    """
    novo = novo if isinstance(novo, dict) else {}
    produto = novo.get("produto_id")
    return {
        "titulo": _texto(novo.get("titulo"), atual["titulo"], LIMITE_DO_TITULO),
        "tipo": _da_lista(novo.get("tipo"), TIPOS, atual["tipo"]),
        "produto_id": produto if produto in ids_de_produto else atual["produto_id"],
        "prioridade": _da_lista(novo.get("prioridade"), PRIORIDADES, atual["prioridade"]),
        "prazo": _prazo_iso(novo["prazo"]) if "prazo" in novo else atual["prazo"],
        "descricao": _texto(novo.get("descricao"), atual["descricao"], LIMITE_DA_DESCRICAO),
    }


def conversar(
    *,
    rascunho: dict,
    messages: list[dict],
    kit: str,
    produtos: list[dict],
    demandas_abertas: list[dict],
    hoje_iso: str,
) -> dict:
    """Um turno da conversa. Sem estado: tudo que ele sabe chega por parametro.

    Devolve `{reply, rascunho, demanda_parecida}`. `demanda_parecida` e sempre
    `None` nesta fatia: o campo ja nasce no contrato para a tela e os testes
    nao mudarem quando o aviso de Demanda repetida entrar.
    """
    ids_de_produto = {p["id"] for p in produtos}
    atual = rascunho_de_entrada(rascunho, ids_de_produto=ids_de_produto)

    provider = ai_processor._llm_provider()
    if provider == "mock":
        logger.warning("Modo MOCK ativo para o Assistente de Tecnologia (sem chave LLM)")
        return {"reply": REPLY_MOCK, "rascunho": atual, "demanda_parecida": None}

    client, model, extra = ai_processor._get_llm()
    ai_processor._log_llm_call("assistente-tecnologia", provider, model)

    chat_history = (
        "\n".join(f"{'Pessoa' if m['role'] == 'user' else 'Assistente'}: {m['content']}" for m in messages)
        or SEM_CONVERSA
    )
    user_content = render_prompt(
        "assistente_tecnologia_user",
        kit=_cercar(kit, titulo=TITULO_DO_KIT, inicio=MARCA_INICIO_KIT, fim=MARCA_FIM_KIT),
        produtos=_bloco_produtos(produtos),
        demandas_abertas=_cercar(
            _bloco_demandas_abertas(demandas_abertas),
            titulo=TITULO_DAS_DEMANDAS,
            inicio=MARCA_INICIO_DEMANDAS,
            fim=MARCA_FIM_DEMANDAS,
        ),
        rascunho_atual=json.dumps(atual, indent=2, ensure_ascii=False),
        chat_history=chat_history,
        hoje_iso=hoje_iso,
    )
    system_prompt = load_prompt("assistente_tecnologia_system")

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            temperature=0.3,
            response_format={"type": "json_object"},
            **extra,
        )
        parsed = json.loads(response.choices[0].message.content)
        if not isinstance(parsed, dict):
            raise ValueError("resposta da IA não é um objeto JSON")
    except Exception as e:
        # Sem failover, como nos outros tres: erro claro e o rascunho INTACTO.
        # Zerar o rascunho aqui jogaria fora a conversa inteira por causa de um
        # 502 do provedor.
        logger.error(f"Erro no Assistente de Tecnologia via {provider}: {e}")
        return {"reply": REPLY_ERRO, "rascunho": atual, "demanda_parecida": None}

    saida = normalizar_rascunho(parsed.get("rascunho"), atual, ids_de_produto=ids_de_produto)
    # ADR 0013: o rascunho vira a descricao da Demanda, e ela nao tem travessao.
    return {
        "reply": sanitizar_travessao(parsed.get("reply", "")),
        "rascunho": sanitizar_estrutura(saida),
        "demanda_parecida": None,
    }
