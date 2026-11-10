"""Menção por nome, no formato dos comentários de Pendência ("@Nome Completo").

Mora aqui, e não no router dos comentários, porque a Conversa da Demanda
(issue #1537, ADR 0083) menciona do mesmo jeito: duas leituras do "@" seriam
dois formatos.
"""

from __future__ import annotations


def extrair_mencoes(conteudo: str, candidatos: list[dict]) -> list[str]:
    """Extrai IDs de participantes mencionados com @nome no conteúdo, sem usar regex falível."""
    if not candidatos:
        return []

    # O filtro previne matches duplicados (ex. João não deve triggar João Pedro).
    # Como não temos regex garantido por pontuação, organizamos pelo tamanho, testando os maiores primeiro.
    participantes_ordenados = sorted(candidatos, key=lambda p: len(p.get("nome_completo", "")), reverse=True)
    mencionados_ids = []

    texto_restante = conteudo

    for p in participantes_ordenados:
        nome_completo = p.get("nome_completo", "").strip()
        if not nome_completo:
            continue

        assinatura = f"@{nome_completo}"
        if assinatura in texto_restante:
            mencionados_ids.append(p["id"])
            # Removemos do buffer de busca para não parear com nomes menores de base.
            texto_restante = texto_restante.replace(assinatura, "")

    return list(set(mencionados_ids))
