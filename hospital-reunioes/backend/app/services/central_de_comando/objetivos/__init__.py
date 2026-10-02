"""Os Objetivos da Central de Comando (issue #820, PRD #809, ADR 0058).

Um pacote por assunto, como o resto da Central:

- `tipos`: os tipos da lente (Numero, Sugestao, Contexto, Extras).
- `catalogo`: o catálogo fechado dos seis Objetivos.
- `regras`: o motor de sugestões, uma regra pura por arquivo.
- `montador`: reúne os números de cada Objetivo pelos provedores e pelo cache,
  monta a galeria e a lente, e roda as regras. A rede vive só nos provedores.

A rota importa daqui o que serve as telas: `ler_galeria`, `ler_lente` e o
`tem_lente`, que decide o 404 da lente.
"""

from __future__ import annotations

from app.services.central_de_comando.objetivos.montador import (
    ler_galeria,
    ler_lente,
    tem_lente,
)

__all__ = ["ler_galeria", "ler_lente", "tem_lente"]
