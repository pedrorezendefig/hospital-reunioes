"""Código e página de acompanhamento (issue #1623, ADR 0086 decisão 7).

O manifestante anônimo recebe, junto com o protocolo, um código mostrado uma
vez só. Só o hash dele é guardado, com sal e derivação lenta: o código é curto
o bastante para ser digitado, e um hash rápido sem sal se quebraria por força
bruta em quem um dia tivesse a tabela na mão.

A página pública recebe protocolo e código (anônimo) ou protocolo e o telefone
ou e-mail que a pessoa deixou (identificado), e devolve só o que o anexo da
Demanda permite (seção 4.3): o estado em linguagem simples, a data da última
movimentação e a resposta institucional. Nunca setor, responsável ou anotação.

Toda recusa é a mesma recusa: protocolo que não existe, código errado, contato
que não confere e caso do outro tipo (código num identificado, contato num
anônimo) devolvem `None`, e a rota responde igual. Dizer qual das duas metades
errou ensinaria a quem tenta adivinhar quais protocolos existem.
"""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets

from app.services.ouvidoria_notificacoes import ELOGIO_ENTREGUE

# Sem 0/O, 1/I/L: o código é lido no celular e digitado de novo depois, às
# vezes por outra pessoa. 31 símbolos, dez posições: perto de 2^50.
ALFABETO = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
TAMANHO = 10

_ALGORITMO = "pbkdf2_sha256"
_ITERACOES = 120_000

# Os quatro estados que o anexo da Demanda pede, na língua de quem manifestou.
# `respondido` é a área ter respondido à Ouvidoria, que é o nome que o app já
# dá ao estado; a resposta ao manifestante é a do encerramento.
RECEBIDA = "Recebida"
EM_ANALISE = "Em análise"
RESPONDIDA = "Respondida"
ENCERRADA = "Encerrada"
ESTADO_PUBLICO: dict[str, str] = {
    "novo": RECEBIDA,
    "em_classificacao": RECEBIDA,
    "aguardando_area": EM_ANALISE,
    "aguardando_manifestante": EM_ANALISE,
    "respondido": RESPONDIDA,
    "encerrado": ENCERRADA,
}

# O que a consulta lê do caso. Tupla fechada: o que não está aqui não tem como
# vazar para a página.
_CAMPOS_DO_CASO = (
    "id, protocolo, status, anonimo, data_abertura, codigo_acompanhamento_hash, "
    "manifestante_contato, manifestante_telefone, desfecho_descricao, tipo_manifestacao"
)

_DIGITOS_DO_MENOR_TELEFONE = 8

# Hash de um código qualquer, para a recusa por protocolo inexistente gastar o
# mesmo tempo que a recusa por código errado.
_HASH_DE_ESPERA: str | None = None


def gerar_codigo() -> str:
    """Dez símbolos em dois blocos de cinco, para ler e copiar sem errar."""
    simbolos = "".join(secrets.choice(ALFABETO) for _ in range(TAMANHO))
    return f"{simbolos[:5]}-{simbolos[5:]}"


def _normalizar_codigo(codigo: str) -> str:
    return re.sub(r"[^0-9A-Z]", "", (codigo or "").upper())


def _derivar(codigo: str, sal: bytes, iteracoes: int) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", _normalizar_codigo(codigo).encode("utf-8"), sal, iteracoes)


def hash_do_codigo(codigo: str) -> str:
    sal = secrets.token_bytes(16)
    return f"{_ALGORITMO}${_ITERACOES}${sal.hex()}${_derivar(codigo, sal, _ITERACOES).hex()}"


def codigo_confere(codigo: str, guardado: str | None) -> bool:
    try:
        algoritmo, iteracoes, sal, esperado = (guardado or "").split("$")
        if algoritmo != _ALGORITMO:
            return False
        calculado = _derivar(codigo, bytes.fromhex(sal), int(iteracoes))
        return hmac.compare_digest(calculado, bytes.fromhex(esperado))
    except ValueError:
        return False


def _gastar_o_tempo_de_uma_conferencia(codigo: str) -> None:
    global _HASH_DE_ESPERA
    if _HASH_DE_ESPERA is None:
        _HASH_DE_ESPERA = hash_do_codigo(gerar_codigo())
    codigo_confere(codigo, _HASH_DE_ESPERA)


def _digitos(texto: str | None) -> str:
    digitos = re.sub(r"\D", "", texto or "")
    # O mesmo número com e sem o código do país.
    if len(digitos) > 11 and digitos.startswith("55"):
        digitos = digitos[2:]
    return digitos.lstrip("0")


def contato_confere(informado: str, caso: dict) -> bool:
    """O e-mail sem diferença de caixa, ou o telefone só pelos dígitos."""
    informado = (informado or "").strip()
    if not informado:
        return False
    if "@" in informado:
        email = (caso.get("manifestante_contato") or "").strip()
        # Em bytes: o compare_digest recusa str com acento (TypeError, 500).
        return bool(email) and hmac.compare_digest(
            email.casefold().encode("utf-8"), informado.casefold().encode("utf-8")
        )
    digitos = _digitos(informado)
    if len(digitos) < _DIGITOS_DO_MENOR_TELEFONE:
        return False
    # O caso de antes da Manifestação guiada guardava o telefone no contato.
    return any(_digitos(caso.get(coluna)) == digitos for coluna in ("manifestante_telefone", "manifestante_contato"))


def resposta_institucional(caso: dict) -> str | None:
    """O que o encerramento disse à pessoa, e só depois do encerramento.

    É o mesmo texto do aviso por e-mail: o desfecho que o ouvidor escreveu para
    ela, ou a frase do elogio entregue. A reabertura zera a descrição, e a
    página volta a não ter resposta enquanto o caso corre de novo."""
    if caso.get("status") != "encerrado":
        return None
    if caso.get("tipo_manifestacao") == "elogio":
        return ELOGIO_ENTREGUE
    return (caso.get("desfecho_descricao") or "").strip() or None


def _ultima_movimentacao(supabase, caso: dict) -> str | None:
    resultado = (
        supabase.table("ouvidoria_movimentos")
        .select("ocorrido_em")
        .eq("manifestacao_id", caso["id"])
        .order("ocorrido_em", desc=True)
        .limit(1)
        .execute()
    )
    if resultado.data:
        return resultado.data[0]["ocorrido_em"]
    return caso.get("data_abertura")


def consultar(supabase, protocolo: str, codigo: str | None, contato: str | None) -> dict | None:
    """O que a página mostra, ou `None` para toda recusa."""
    resultado = (
        supabase.table("ouvidoria_protocolos")
        .select(_CAMPOS_DO_CASO)
        .eq("protocolo", (protocolo or "").strip())
        .limit(1)
        .execute()
    )
    caso = resultado.data[0] if resultado.data else None
    if caso is None:
        if codigo:
            _gastar_o_tempo_de_uma_conferencia(codigo)
        return None

    if caso.get("anonimo"):
        if not codigo or not codigo_confere(codigo, caso.get("codigo_acompanhamento_hash")):
            return None
    elif not contato or not contato_confere(contato, caso):
        return None

    return {
        "protocolo": caso["protocolo"],
        "estado": ESTADO_PUBLICO.get(caso.get("status"), RECEBIDA),
        "ultima_movimentacao": _ultima_movimentacao(supabase, caso),
        "resposta": resposta_institucional(caso),
    }
