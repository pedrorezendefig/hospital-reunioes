"""O caso do Canal de Conduta (ADR 0097, decisões 1 e 8).

O relato entra cifrado; rota, etapa, categoria e datas ficam em claro, para a
lista e o prazo. O protocolo é sorteado, sem ordem e sem contagem: número em
sequência contaria os casos para quem relata e deixaria um buraco na fila
comum a cada caso da Rota Especial. A numeração da Ouvidoria não é tocada.

O código de acompanhamento é o mesmo da Ouvidoria (curto, legível, hash com
sal e derivação lenta), devolvido uma vez só a quem relatou.
"""

from __future__ import annotations

import secrets
from typing import Any

from postgrest.exceptions import APIError

from app.services.conduta import avisos, cifra, trilha
from app.services.ouvidoria_acompanhamento import ALFABETO, gerar_codigo, hash_do_codigo

_VIOLACAO_DE_UNICIDADE = "23505"
_TENTATIVAS_DO_PROTOCOLO = 3


def novo_protocolo() -> str:
    simbolos = "".join(secrets.choice(ALFABETO) for _ in range(8))
    return f"CC-{simbolos[:4]}-{simbolos[4:]}"


def registrar_caso(supabase, *, relato: str, categoria: str | None, rota: str = "comum") -> dict[str, Any]:
    """Grava o caso e a linha de recebimento na trilha. Devolve o id, o
    protocolo e o código de acompanhamento, que não fica guardado.

    Sem a chave de cifra levanta `CifraIndisponivelError` antes de gravar qualquer
    coisa."""
    relato_cifrado = cifra.cifrar_texto(relato)
    codigo = gerar_codigo()
    linha = {
        "codigo_hash": hash_do_codigo(codigo),
        "rota": rota,
        "etapa": "triagem",
        "categoria": categoria,
        "relato_cifrado": relato_cifrado,
    }
    for tentativa in range(1, _TENTATIVAS_DO_PROTOCOLO + 1):
        try:
            caso = supabase.table("conduta_casos").insert({**linha, "protocolo": novo_protocolo()}).execute().data[0]
            break
        except APIError as erro:
            if tentativa == _TENTATIVAS_DO_PROTOCOLO or getattr(erro, "code", None) != _VIOLACAO_DE_UNICIDADE:
                raise
    trilha.registrar(supabase, caso["id"], None, "recebimento", "caso recebido")
    avisos.avisar_tarefas_novas(supabase, caso["id"], {})
    return {"id": caso["id"], "protocolo": caso["protocolo"], "codigo": codigo}
