"""Os ritos do Canal de Conduta, a triagem e a caixa "O QUE FAZER AGORA"
(issue #1824; especificação, seções 5, 6, 6.1, 6.2 e 18).

Regras puras: nada aqui lê ou grava o banco. Quem age é `triagem.py`.

O prazo conta do envio do relato (`recebido_em`, no fuso de São Paulo), nunca
da triagem. A Rota Especial e o agente entram em outras fatias: a triagem desta
fatia é manual e oferece só Encaminhamento, Rápido e Completo.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

FUSO = ZoneInfo("America/Sao_Paulo")

RITOS_DA_TRIAGEM = ("encaminhamento", "rapido", "completo")
ESCOPOS = ("dentro", "fora", "misto")
CATEGORIAS = {
    "A": "Conduta e relações",
    "B": "Patrimônio",
    "C": "Integridade nos negócios",
    "D": "Registros e informação",
    "E": "Segurança e conformidade",
    "F": "Não sei classificar",
}
# Para onde vai o que não é do canal (seção 4.1). O contato do DP chega com a
# tela de Configurações; até lá a orientação diz só o destino.
DESTINOS = {
    "dp": "o Departamento Pessoal",
    "ouvidoria": "a Ouvidoria",
    "nsp": "o Núcleo de Segurança do Paciente",
    "gestor": "a sua liderança ou o Departamento Pessoal",
}

DIAS_CORRIDOS = {"rapido": 20, "completo": 30, "especial": 60}
DIAS_UTEIS_DO_ENCAMINHAMENTO = 5
DIAS_DA_PRORROGACAO = 30

# Quem decide a contestação da triagem: os três votantes do Comitê.
PAPEIS_VOTANTES = ("coordenacao", "membro", "segundo_leitor")
VOTOS_PARA_DECIDIR = 2

ETAPA_DO_RITO = {"encaminhamento": "encaminhamento", "rapido": "apuracao", "completo": "apuracao"}

TRILHO = ("Triagem", "Apuração", "Voto", "Ata", "Medida", "Acompanhamento")
TRILHO_DO_ENCAMINHAMENTO = ("Triagem", "Encaminhado")
_POSICAO_NO_TRILHO = {"triagem": 0, "contestada": 0, "encaminhamento": 0, "apuracao": 1}


def orientacao_do_encaminhamento(destino: str) -> str:
    """A resposta padrão da seção 4.1, com o destino certo."""
    return (
        "Seu relato foi lido pelo Comitê. O assunto não é tratado neste canal. "
        f"Procure {DESTINOS[destino]}. Se houver assédio, ameaça ou retaliação envolvidos, "
        "registre um novo relato contando essa parte."
    )


# ── Prazo ───────────────────────────────────────────────────────────────────


def data_do_envio(recebido_em: str | datetime) -> date:
    momento = datetime.fromisoformat(recebido_em) if isinstance(recebido_em, str) else recebido_em
    return momento.astimezone(FUSO).date()


def _somar_dias_uteis(inicio: date, dias: int, feriados: frozenset[date]) -> date:
    dia = inicio
    while dias:
        dia += timedelta(days=1)
        if dia.weekday() < 5 and dia not in feriados:
            dias -= 1
    return dia


def prazo_do_rito(
    rito: str, recebido_em: str | datetime, *, prorrogado: bool = False, feriados: frozenset[date] = frozenset()
) -> date:
    """O último dia do prazo do rito, contado do envio do relato."""
    envio = data_do_envio(recebido_em)
    if rito == "encaminhamento":
        return _somar_dias_uteis(envio, DIAS_UTEIS_DO_ENCAMINHAMENTO, feriados)
    dias = DIAS_CORRIDOS[rito] + (DIAS_DA_PRORROGACAO if prorrogado and rito == "completo" else 0)
    return envio + timedelta(days=dias)


def prazo_venceu(caso: dict[str, Any], hoje: date) -> bool:
    prazo = caso.get("prazo_em")
    return bool(prazo) and not caso.get("encerrado_em") and date.fromisoformat(str(prazo)[:10]) < hoje


# ── Triagem ─────────────────────────────────────────────────────────────────


def erro_da_triagem(escopo: str, categoria: str, rito: str, destino: str | None) -> str | None:
    """O que está errado na triagem, numa linha, ou None."""
    if escopo not in ESCOPOS:
        return "Diga se o caso é do canal: dentro, fora ou misto."
    if categoria not in CATEGORIAS:
        return "Escolha a categoria do caso."
    if rito not in RITOS_DA_TRIAGEM:
        return "Escolha o rito do caso."
    if (escopo == "fora") != (rito == "encaminhamento"):
        return "Caso fora do canal vai ao Encaminhamento, e só ele."
    if escopo == "dentro" and destino:
        return "Caso dentro do canal não tem outro destino."
    if escopo != "dentro" and destino not in DESTINOS:
        return "Diga para onde vai a parte que não é do canal."
    return None


# ── A situação do caso para quem olha ───────────────────────────────────────


@dataclass(frozen=True)
class Olhar:
    """O caso visto por uma pessoa: o papel dela e o que já fez."""

    papel: str | None
    votante: bool
    contestacao: dict[str, Any] | None = None
    ja_votou_na_contestacao: bool = False


def trilho(caso: dict[str, Any]) -> list[dict[str, str]]:
    if caso.get("rito") == "encaminhamento":
        nomes, atual = TRILHO_DO_ENCAMINHAMENTO, (1 if caso.get("encerrado_em") else 0)
    else:
        nomes, atual = TRILHO, _POSICAO_NO_TRILHO.get(caso.get("etapa") or "triagem", 0)
    encerrado = bool(caso.get("encerrado_em"))
    return [
        {
            "nome": nome,
            "estado": "concluida" if i < atual or (encerrado and i == atual) else "atual" if i == atual else "pendente",
        }
        for i, nome in enumerate(nomes)
    ]


def _caixa(frase: str, botao: str | None, como: tuple[str, str, str], acao: str | None, bloqueio: str | None = None):
    return {"frase": frase, "botao": botao, "como_fazer": list(como), "acao": acao, "bloqueio": bloqueio}


_COMO_TRIAGEM = (
    "Leia o relato original",
    "Confira cada sugestão",
    "Se faltar informação, pergunte ao denunciante",
)
_COMO_FORA = (
    "Leia o relato inteiro",
    "Se houver qualquer sinal de assédio, fraude ou retaliação, mantenha no canal",
    "Confirme a resposta sugerida",
)
_COMO_APURACAO = (
    "Use o roteiro sugerido",
    "Grave e diga o consentimento no início",
    "Siga os passos do cartão até concluir o depoimento",
)
_COMO_CONFERIR = (
    "Leia o relato original",
    "Confira a triagem da coordenação",
    "Se discordar, conteste com o motivo em uma linha",
)
_COMO_CONTESTADA = (
    "Leia a triagem da coordenação",
    "Leia a contestação do segundo leitor",
    "Vale o que dois dos três escolherem",
)


def _precisa_conferir(caso: dict[str, Any], olhar: Olhar) -> bool:
    return (
        olhar.papel == "segundo_leitor"
        and bool(caso.get("triagem_em"))
        and not caso.get("conferida_em")
        and not caso.get("encerrado_em")
        and olhar.contestacao is None
    )


def o_que_fazer_agora(caso: dict[str, Any], olhar: Olhar) -> dict[str, Any]:
    """A caixa da tela do caso: uma frase, um botão e o "Como fazer" em três
    linhas. Botão que a pessoa não pode usar vem com o motivo em `bloqueio`."""
    etapa = caso.get("etapa") or "triagem"
    coordena = olhar.papel == "coordenacao"

    if caso.get("encerrado_em"):
        return _caixa(
            "Este caso foi encerrado como Encaminhado. A orientação já foi enviada.",
            None,
            ("Consulte a trilha do caso", "A orientação enviada fica guardada", "Novo assunto vira novo relato"),
            None,
        )
    if _precisa_conferir(caso, olhar):
        return _caixa(
            "Confira a triagem da coordenação. Se discordar, conteste.",
            "CONFERIR TRIAGEM",
            _COMO_CONFERIR,
            "conferir_triagem",
        )
    if etapa == "triagem":
        return _caixa(
            "Leia o resumo. Confirme se o caso é do canal e qual o rito.",
            "CONFIRMAR TRIAGEM",
            _COMO_TRIAGEM,
            "confirmar_triagem",
            None if coordena else "Só a coordenação confirma a triagem.",
        )
    if etapa == "contestada":
        bloqueio = None
        if not olhar.votante:
            bloqueio = "Só os três membros votantes decidem a contestação."
        elif olhar.ja_votou_na_contestacao:
            bloqueio = "Você já decidiu. Falta a decisão dos outros membros."
        return _caixa(
            "A triagem foi contestada. Decida com os outros dois membros qual triagem vale.",
            "DECIDIR TRIAGEM",
            _COMO_CONTESTADA,
            "decidir_contestacao",
            bloqueio,
        )
    if etapa == "encaminhamento":
        bloqueio = None
        if not coordena:
            bloqueio = "Só a coordenação envia a orientação."
        elif not caso.get("conferida_em"):
            bloqueio = "Falta o segundo leitor conferir a triagem."
        return _caixa(
            "Este relato parece não ser do canal. Confira e envie a orientação.",
            "ENVIAR ORIENTAÇÃO",
            _COMO_FORA,
            "enviar_orientacao",
            bloqueio,
        )
    return _caixa(
        "Ouça o acusado e até duas pessoas. Sempre em dupla.",
        "ADICIONAR PESSOA A OUVIR",
        _COMO_APURACAO,
        "adicionar_pessoa",
    )


ACOES_DA_MINHA_VEZ = {
    "confirmar_triagem": "Confirmar a triagem",
    "conferir_triagem": "Conferir a triagem",
    "decidir_contestacao": "Decidir a contestação da triagem",
    "enviar_orientacao": "Enviar a orientação",
}


def acao_pendente(caso: dict[str, Any], olhar: Olhar) -> str | None:
    """O que depende da pessoa neste caso agora: o botão da caixa que ela pode
    usar. Botão bloqueado não é dela."""
    caixa = o_que_fazer_agora(caso, olhar)
    if caixa["acao"] in ACOES_DA_MINHA_VEZ and caixa["bloqueio"] is None:
        return ACOES_DA_MINHA_VEZ[caixa["acao"]]
    return None


def chave_de_urgencia(caso: dict[str, Any]) -> tuple[str, str]:
    """Do mais urgente ao menos urgente: o prazo que vence antes. O caso ainda
    sem rito entra pelo menor prazo possível, o do Encaminhamento, porque o
    relógio já corre desde o envio."""
    prazo = caso.get("prazo_em") or prazo_do_rito("encaminhamento", caso["recebido_em"]).isoformat()
    return (str(prazo)[:10], str(caso.get("recebido_em") or ""))


def pode_prorrogar(caso: dict[str, Any], olhar: Olhar) -> str | None:
    """None quando a pessoa pode prorrogar; senão o motivo, numa linha."""
    if caso.get("rito") != "completo":
        return "Só o rito Completo prorroga."
    if caso.get("prorrogado_em"):
        return "O prazo já foi prorrogado uma vez."
    if caso.get("encerrado_em"):
        return "O caso já foi encerrado."
    if olhar.papel != "coordenacao":
        return "Só a coordenação prorroga o prazo."
    if not caso.get("conferida_em"):
        # Antes da conferência o rito ainda pode mudar pela contestação, e o
        # banco recusa prorrogação em rito que não é o Completo.
        return "Falta o segundo leitor conferir a triagem."
    return None


def situacao(caso: dict[str, Any]) -> str:
    if caso.get("encerrado_em"):
        return "encerrado"
    if (caso.get("etapa") or "triagem") in ("triagem", "contestada"):
        return "em_triagem"
    return "em_andamento"


def votante(papel: str | None, atribuicoes: list[dict[str, Any]]) -> bool:
    return papel in PAPEIS_VOTANTES or any(
        a.get("motivo") == "suplente_convocado" and not a.get("revogada_em") for a in atribuicoes
    )


def resultado_da_contestacao(votos: list[dict[str, Any]]) -> str | None:
    """`mantida`, `acatada` ou None enquanto dois não escolheram o mesmo."""
    for escolha, resultado in (("manter", "mantida"), ("acatar", "acatada")):
        if sum(1 for v in votos if v.get("escolha") == escolha) >= VOTOS_PARA_DECIDIR:
            return resultado
    return None


def agora_utc() -> datetime:
    return datetime.now(tz=ZoneInfo("UTC"))
