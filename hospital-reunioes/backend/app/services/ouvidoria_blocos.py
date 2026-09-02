"""Os três blocos que a área lê no acionamento (ADR 0041, RN-78 e RN-79).

Até o diagnóstico da Diretoria de 31/08/2026, o responsável do setor lia só o
Extrato para o setor. Quem lê apenas a interpretação da Ouvidoria responde à
interpretação, não ao paciente: por isso o acionamento passou a carregar
RESUMO, RELATO INTEGRAL e NOTA DA OUVIDORIA, nesta ordem e separados (RN-60,
nunca fundidos nem com a mesma formatação).

A montagem mora aqui, num lugar só, porque as duas superfícies (o email de
acionamento e a rota do token do responsável) precisam dizer exatamente a mesma
coisa sobre o mesmo caso. Superfície que monta o próprio texto é superfície que
diverge da outra na primeira mudança de regra.
"""

from __future__ import annotations

CHAVE_RESUMO = "resumo"
CHAVE_RELATO = "relato_integral"
CHAVE_NOTA = "nota_da_ouvidoria"

ROTULO_RESUMO = "RESUMO"
ROTULO_RELATO = "RELATO INTEGRAL"
ROTULO_NOTA = "NOTA DA OUVIDORIA"

SEM_RESUMO = "A Ouvidoria não registrou o resumo deste caso."
SEM_RELATO = "O relato original do manifestante não está registrado neste caso."
# O mesmo texto do email desde a issue #325: caso que chega ao acionamento sem
# extrato é caso a devolver para a Ouvidoria, não caso a responder no escuro.
SEM_EXTRATO = "A Ouvidoria não registrou o extrato deste caso. Procure a Ouvidoria pelo protocolo antes de responder."

# A variante da RN-79. O relato original não viaja, e quem lê precisa saber
# disso: sem o aviso, a área pensaria que o caso chegou incompleto por descuido.
AVISO_SIGILO = (
    "Caso sob sigilo reforçado: o relato original e o resumo do manifestante não são encaminhados, e o "
    "caso segue sem identificação de quem manifestou. A nota da Ouvidoria abaixo é o extrato pertinente ao setor."
)
# O mesmo silêncio, por outro motivo. Sem um aviso próprio, o acionamento
# anônimo chegaria à área com um bloco só e nenhuma explicação.
AVISO_ANONIMO = (
    "Manifestação anônima: o relato original e o resumo não são encaminhados, porque costumam trazer a "
    "identificação de quem preferiu não se identificar. A nota da Ouvidoria abaixo é o extrato pertinente ao setor."
)


def _texto(manifestacao: dict, campo: str, vazio: str) -> str:
    return (manifestacao.get(campo) or "").strip() or vazio


def sob_sigilo(manifestacao: dict) -> bool:
    return bool(manifestacao.get("sigilo_reforcado"))


def caso_protegido(manifestacao: dict) -> bool:
    """Quando a palavra crua de quem manifestou não sai da Ouvidoria.

    Sigilo reforçado é a exceção que a RN-79 nomeia. O caso anônimo entra pelo
    mesmo motivo e pela mesma porta de `_identificacao`: quem não quis se
    identificar costuma se identificar dentro do próprio texto ("sou a Maria
    Silva, do leito 302"), e mandar esse texto ao setor desfaz o anonimato que o
    canal prometeu."""
    return sob_sigilo(manifestacao) or bool(manifestacao.get("anonimo"))


def aviso_do_caso(manifestacao: dict) -> str | None:
    """O que explica à área por que o caso chegou com um bloco só.

    Nasce do mesmo gate de `montar_blocos`, e não de `sob_sigilo`: aviso que
    olha uma condição diferente da que corta os blocos deixa o acionamento
    anônimo mudo, que é exatamente o mal-entendido que o aviso existe para
    evitar."""
    if sob_sigilo(manifestacao):
        return AVISO_SIGILO
    if caso_protegido(manifestacao):
        return AVISO_ANONIMO
    return None


def montar_blocos(manifestacao: dict) -> list[dict]:
    """Os blocos de leitura do caso, na ordem em que a área os lê.

    Caso comum: RESUMO, RELATO INTEGRAL e NOTA DA OUVIDORIA.

    Caso protegido (RN-79): o extrato entra no lugar do relato integral, e a
    lista fica só com a NOTA DA OUVIDORIA. O resumo sai junto porque ele não é
    texto da Ouvidoria: no canal aberto são os primeiros caracteres do que o
    cidadão digitou, e no canal da Ana é texto gerado da conversa, os dois
    capazes de carregar nome e leito sem ninguém perceber. Manter o resumo aqui
    entregaria a identificação que a RN-79 manda tirar. Como o extrato JÁ é a
    nota da ouvidoria, o bloco do relato sai da lista em vez de repetir o mesmo
    texto duas vezes na tela e no email: o que a área lê no lugar do relato é a
    nota, e `AVISO_SIGILO` diz isso com todas as letras.

    Quem precisa distinguir as duas variantes lê a chave de cada bloco, nunca a
    posição."""
    nota = {
        "chave": CHAVE_NOTA,
        "rotulo": ROTULO_NOTA,
        "texto": _texto(manifestacao, "extrato_para_o_setor", SEM_EXTRATO),
    }
    if caso_protegido(manifestacao):
        return [nota]
    return [
        {"chave": CHAVE_RESUMO, "rotulo": ROTULO_RESUMO, "texto": _texto(manifestacao, "resumo", SEM_RESUMO)},
        {
            "chave": CHAVE_RELATO,
            "rotulo": ROTULO_RELATO,
            "texto": _texto(manifestacao, "relato_integral", SEM_RELATO),
        },
        nota,
    ]
