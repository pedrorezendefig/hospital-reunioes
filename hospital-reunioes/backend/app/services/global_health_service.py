"""Espelho da Global Health (ADR 0038): o único ponto do app que fala com a
agenda online da Global Health (GH).

Módulo profundo, porta estreita: cada elo da cadeia da GH vira uma função que
devolve linhas prontas para a tela. Aqui moram a base, o header de
autenticação, o timeout e a tradução de erro; nenhum outro módulo importa
`httpx` para falar com a GH.

Três invariantes que o resto do app herda de graça:

- **Só homologação.** A base é constante fixa neste arquivo; produção
  (`app.agenda.globalhealth.mv`) jamais é chamada por este código.
- **Só leitura.** Nenhum verbo de escrita existe aqui: o Espelho não agenda,
  não cadastra e não altera nada na GH.
- **Falha é falha.** Timeout, 5xx e erro de rede viram `GlobalHealthError`,
  distinta de resposta vazia. Lista vazia é uma resposta ("nada publicado");
  falha é ausência de resposta, e a tela precisa saber a diferença.

Nada do que a GH responde é gravado em banco: é espelho, não cópia.
"""

from __future__ import annotations

import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

# Base de HOMOLOGAÇÃO da agenda online da Global Health (ADR 0038, decisão 6).
# Produção (`https://app.agenda.globalhealth.mv`) jamais é chamada por este
# código: trocar esta constante é decisão consciente, revisada em commit.
BASE_URL = "https://dem.agenda.globalhealth.mv/rest/whatsapp"

# Timeout curto: a secretária espera a resposta olhando a tela. Erro honesto
# em segundos vale mais que tela pendurada (padrão da casa: connect menor).
_TIMEOUT = httpx.Timeout(10.0, connect=3.0)


class GlobalHealthError(RuntimeError):
    """A Global Health não respondeu (timeout, 5xx, rede, corpo ilegível).

    Distinta de resposta vazia: a mensagem sobe para a tela como erro.
    """


class GlobalHealthNaoConfiguradaError(RuntimeError):
    """`GH_TOKEN_HOMOLOG` ausente: o app não tem como se autenticar na GH."""


def _headers() -> dict[str, str]:
    token = settings.gh_token_homolog
    if not token:
        raise GlobalHealthNaoConfiguradaError("GH_TOKEN_HOMOLOG não configurado no backend")
    return {"Token": token, "Accept": "application/json"}


def _id_inteiro(valor) -> int | None:
    """O `id` da GH vira inteiro, ou o item cai fora.

    O id não fica parado na tela: volta para a GH no elo seguinte e entra no
    caminho da URL que o navegador monta. Aceitar texto arbitrário aqui
    deixaria a GH escolher qual rota do app o navegador vai chamar com o
    Bearer de quem está olhando. Inteiro fecha essa porta na origem.

    `True` é `int` em Python e não identifica nada: fica de fora também.
    """
    if isinstance(valor, bool):
        return None
    if isinstance(valor, int):
        return valor
    if isinstance(valor, str) and valor.strip().lstrip("-").isdigit():
        return int(valor.strip())
    return None


def _booleano(valor) -> bool:
    """Lê o valor da GH, não a verdade que o Python daria a ele.

    `bool("false")` é `True`: uma string no lugar do booleano faria todo
    convênio virar particular e toda especialidade virar bloqueada na tela.
    Só as palavras afirmativas contam.

    `"s"` entra na lista porque a GH é um sistema MV, e MV costuma publicar
    flag como `"S"`/`"N"`. O formato real da homologação ainda não foi
    confirmado; até lá, errar para o lado de não destacar é o erro barato.

    Todo campo booleano vindo da GH passa por aqui: `bool()` cru sobre valor
    da GH é bug, não atalho (issue #406).
    """
    if isinstance(valor, str):
        return valor.strip().lower() in {"true", "1", "sim", "s"}
    return bool(valor)


def _obter(path: str, params: dict | None = None) -> dict:
    """GET na GH; devolve o corpo como dicionário, ou levanta.

    Único acesso à rede do módulo, e o único lugar onde falha vira
    `GlobalHealthError`. Só GET.
    """
    headers = _headers()
    url = f"{BASE_URL}{path}"
    try:
        with httpx.Client(timeout=_TIMEOUT) as client:
            resposta = client.get(url, params=params or None, headers=headers)
            resposta.raise_for_status()
            corpo = resposta.json()
    except httpx.HTTPStatusError as exc:
        codigo = exc.response.status_code
        logger.error(f"[GlobalHealth] {path} respondeu HTTP {codigo}")
        raise GlobalHealthError(f"A Global Health respondeu HTTP {codigo}.") from exc
    except httpx.TimeoutException as exc:
        logger.error(f"[GlobalHealth] timeout em {path}")
        raise GlobalHealthError("A Global Health não respondeu no tempo esperado.") from exc
    except httpx.HTTPError as exc:
        logger.error(f"[GlobalHealth] falha de rede em {path}: {type(exc).__name__}")
        raise GlobalHealthError("Não foi possível falar com a Global Health.") from exc
    except ValueError as exc:
        logger.error(f"[GlobalHealth] corpo ilegível em {path}")
        raise GlobalHealthError("A Global Health devolveu uma resposta ilegível.") from exc

    if not isinstance(corpo, dict):
        raise GlobalHealthError("A Global Health devolveu uma resposta fora do formato esperado.")
    return corpo


def _listar(path: str, params: dict | None = None) -> list[dict]:
    """GET numa lista paginada da GH; devolve o `conteudo` da página.

    O envelope paginado da GH é `{"conteudo": [...], "paginaAnterior": "",
    "paginaSeguinte": ""}`. Os elos 1 a 3 vivem nele; o elo 4 tem envelope
    próprio e usa o `_obter` direto.
    """
    corpo = _obter(path, params)
    # Item sem `id` inteiro é inútil: não identifica nada na GH, não serve de
    # chave na tela e não pode alimentar o elo seguinte da cadeia. Fica de fora.
    itens = []
    for item in corpo.get("conteudo") or []:
        if not isinstance(item, dict):
            continue
        identificador = _id_inteiro(item.get("id"))
        if identificador is None:
            continue
        itens.append({**item, "id": identificador})
    return itens


def listar_especialidades(pesquisa: str | None = None) -> list[dict]:
    """Elo 1: especialidades publicadas na agenda (`GET /consultas`).

    É a lista do que a Ana consegue agendar hoje. `pesquisa` filtra pelo nome
    na própria GH. Campos publicados: `id`, `nome`, `bloqueado`.
    """
    params = {"pesquisa": pesquisa} if pesquisa else None
    return [
        {
            "id": item.get("id"),
            "nome": item.get("nome"),
            # O selo da tela sai daqui: chega sempre booleano lido pelo valor.
            "bloqueado": _booleano(item.get("bloqueado")),
        }
        for item in _listar("/consultas", params)
    ]


def listar_convenios(id_especialidade: int) -> list[dict]:
    """Elo 2a: convênios aceitos na especialidade (`GET /convenios`).

    É a lista que decide se o agendamento acontece, e por isso a única fonte
    de cobertura do app (ADR 0038). `id_especialidade` vem do elo 1: sem ele
    a GH devolveria os convênios do hospital inteiro, que é outra pergunta.

    `size=100` pede a página inteira de uma vez; nenhuma especialidade da
    homologação chega perto disso, e paginar aqui esconderia convênio da
    secretária. Campos publicados: `id`, `nome`, `particular`.
    """
    params = {"idItemAgendamento": id_especialidade, "size": 100}
    return [
        {
            "id": item.get("id"),
            "nome": item.get("nome"),
            # A tela destaca a linha por este campo: chega sempre booleano.
            "particular": _booleano(item.get("particular")),
        }
        for item in _listar("/convenios", params)
    ]


def listar_profissionais(id_especialidade: int) -> list[dict]:
    """Elo 2b: profissionais disponíveis na especialidade (`GET /prestadores`).

    A GH só publica aqui quem está com o botão ligado no Painel de Controle:
    lista vazia é resposta ("ninguém ligado"), não falha. Campos: `id`, `nome`.
    """
    params = {"idItemAgendamento": id_especialidade}
    return [{"id": item.get("id"), "nome": item.get("nome")} for item in _listar("/prestadores", params)]


def listar_planos(id_convenio: int, id_especialidade: int) -> list[dict]:
    """Elo 3: planos do convênio dentro da especialidade.

    `GET /convenios/{idConvenio}/planos?idItemAgendamento={id}`: os dois ids
    vêm dos elos anteriores da tela, cada um no seu lugar (o convênio no
    caminho, a especialidade no parâmetro). Trocá-los devolve 200 com a
    resposta de outra pergunta, sem erro nenhum.

    SubPlanos ficam fora desta passada. Campos: `id`, `nome`.
    """
    params = {"idItemAgendamento": id_especialidade}
    return [
        {"id": item.get("id"), "nome": item.get("nome")} for item in _listar(f"/convenios/{id_convenio}/planos", params)
    ]


def listar_horarios_livres(
    id_especialidade: int,
    id_convenio: int,
    id_plano: int,
    id_profissional: int | None = None,
    data_inicial: str | None = None,
) -> dict:
    """Elo 4: horários livres da combinação (`GET /agendas/v2`).

    Os **três** ids são obrigatórios na GH: faltando qualquer um (ou vindo
    vazio), a resposta é HTTP 500. Por isso eles são parâmetros posicionais
    aqui e segmentos do caminho na rota: chegam sempre dos elos anteriores da
    tela, nunca de campo digitado. Id inexistente não dá erro na GH, devolve
    200 com `agendas: []`, indistinguível de "sem horário livre"; a defesa é
    exatamente essa, nunca chamar com id que não veio do elo anterior.

    `id_profissional` e `data_inicial` são os filtros opcionais da tela e só
    descem quando preenchidos: parâmetro vazio é o mesmo 500.

    A resposta da GH vem em três níveis (`agendas` > `prestadores` >
    `horarios`) e sai daqui achatada em linhas de horário, que é como a
    secretária lê: unidade, profissional e valor descem para cada linha.

    Sobre fuso: o `descricaoHorario` já vem formatado pela GH para exibição
    ("03/Abr 11:00"), no relógio da agenda do hospital. Ele é repassado como
    texto, sem parse e sem conversão: nada aqui calcula data ou hora, e por
    isso não existe fuso do servidor para errar. `data_inicial` é a data
    escolhida na tela, mandada como veio.
    """
    params: dict = {
        "idItemAgendamento": id_especialidade,
        "idConvenio": id_convenio,
        "idPlano": id_plano,
    }
    if id_profissional is not None:
        params["idPrestador"] = id_profissional
    if data_inicial:
        params["dataInicial"] = data_inicial

    corpo = _obter("/agendas/v2", params)
    horarios: list[dict] = []
    for agenda in corpo.get("agendas") or []:
        if not isinstance(agenda, dict):
            continue
        unidade = agenda.get("nomeUnidade")
        for prestador in agenda.get("prestadores") or []:
            if not isinstance(prestador, dict):
                continue
            for horario in prestador.get("horarios") or []:
                if not isinstance(horario, dict):
                    continue
                # `idHorario` é a identidade da vaga: sem inteiro, a linha não
                # identifica nada e nem serve de chave na tabela da tela.
                id_horario = _id_inteiro(horario.get("idHorario"))
                if id_horario is None:
                    continue
                horarios.append(
                    {
                        "id_horario": id_horario,
                        "id_agenda": _id_inteiro(horario.get("idAgenda")),
                        "quando": horario.get("descricaoHorario"),
                        # Agenda por ordem de chegada não tem hora marcada: a
                        # tela avisa, e o valor é lido, não deduzido.
                        "ordem_chegada": _booleano(horario.get("ordemChegada")),
                        "id_profissional": _id_inteiro(prestador.get("idPrestador")),
                        "profissional": prestador.get("nomePrestadorRecurso"),
                        "valor_particular": prestador.get("valorParticular"),
                        "unidade": unidade,
                    }
                )

    return {
        "horarios": horarios,
        # A janela é o que torna honesto o "não há horário": sem ela, a frase
        # não diz de quando até quando a GH procurou.
        "data_inicial": corpo.get("dataInicial") or None,
        "data_final": corpo.get("dataFinal") or None,
        # Pode vir nula quando não há mais horário adiante (doc da GH).
        "data_pagina_seguinte": corpo.get("dataPaginaSeguinte") or None,
    }
