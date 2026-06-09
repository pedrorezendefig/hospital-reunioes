"""Subpacote admin: routers administrativos restritos a super admins.

Cada router corresponde a um recorte da camada administrativa:
- super_admins: promover/rebaixar super admins.
- usuarios: CRUD cross-user de participantes.
- utilitarios: ferramentas utilitarias (conversao PDF/DOCX para Markdown).
- logs (futuro): consulta do audit_log.
- acoes_massa (futuro): operacoes em lote.

O modulo `legacy` mantem o router historico `/admin/email/*` e
`/admin/integracoes/*`. E reexportado como `router` deste pacote para preservar
a importacao antiga `from app.routers import admin; admin.router`.
"""

from app.routers.admin.legacy import router  # noqa: F401 — backcompat import
