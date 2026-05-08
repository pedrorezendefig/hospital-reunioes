# Deploy `44c53c8` — 🟢 healthy

- **Data**: 2026-05-08 16:35 -0300
- **SHA**: `44c53c8`
- **Modo**: ship
- **Resultado**: healthy
- **Subject**: Super admin troca facilitador da reunião por outro super admin.

## Serviços tocados

- backend
- frontend

## Notas

POST /reunioes/{id}/transferir-facilitador valida que novo é super admin ativo, adiciona como participante de forma idempotente e grava audit_log. Frontend: TrocarFacilitadorModal listado por hover no card do facilitador (visível só para super admin). Health pós: api 200 1155ms, app 200 125ms.

---
_Gerado automaticamente pelo `/deploy ship` (Passo 9.4)._
