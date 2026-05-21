# Webhook ClickSign: corrigir path para bater com painel

## Plano

### Contexto

Diretor confirmou que todas as 6 assinaturas da ata `RD_20260511_203049DD` foram concluídas no ClickSign (envelope `899d33f9-5714-4673-9127-01f14c3037c7`), mas o app continua mostrando a ata em `AGUARDANDO_ASSINATURA`. O painel "Envios de Webhooks" do ClickSign mostra **HTTP 404 Not Found** para todos os envios entre 08/05 e 15/05 (envelopes `899d33f9`, `c22cdcae`, `29370fb1`, `54db3ff7`, `1fd49dc1`, `02b69138`, `97b7afa3`, `1d1c8dc9`, `00dda427`).

Diagnóstico validado por curl em produção:

| Path testado | Resultado |
|---|---|
| `POST /api/webhooks/clicksign` (registrado no painel) | `HTTP 404 Not Found` |
| `POST /api/webhook/clicksign-completed` (rota do backend antes desta mudança) | `HTTP 401 sem HMAC`, `HTTP 200 com HMAC válido` |

Ou seja: o painel da ClickSign aponta para `/api/webhooks/clicksign` (plural, sem sufixo) mas o backend respondia em `/api/webhook/clicksign-completed` (singular, com sufixo). Os 200 que apareceram em 07/05 são porque até essa data a URL do painel batia com a do backend; em algum momento entre 07/05 e 08/05 a configuração do painel foi alterada.

A ClickSign **não permite editar a URL do webhook depois de criada** (ou exige procedimento manual via suporte). Por isso a correção foi feita do lado do backend: ajustar o path para o que o painel já tem registrado.

### Escopo

Trocar 2 linhas em `hospital-reunioes/backend/app/routers/webhooks.py`:

```diff
- router = APIRouter(prefix="/webhook", tags=["webhooks"])
+ router = APIRouter(prefix="/webhooks", tags=["webhooks"])

- @router.post("/clicksign-completed")
+ @router.post("/clicksign")
```

Após a mudança o path final do FastAPI passa a ser:

```
POST /api/webhooks/clicksign
```

Idêntico ao registrado no painel da ClickSign.

### Passos

1. ✅ Diagnosticar 404 do painel via curl (passo 1 do plano de validação): retornou 404.
2. ✅ Confirmar que rota antiga responde via curl (passo 2): retornou 401.
3. ✅ Validar secret HMAC com payload assinado (passo 3): retornou 200 + `{"message":"Documento não encontrado."}`. Secret do painel (`7e6ec77c478b302abdf479332c8272ab`) bate com `CLICKSIGN_WEBHOOK_SECRET` em produção.
4. ✅ Editar `webhooks.py` (`prefix="/webhooks"` + `@router.post("/clicksign")`).
5. ⏳ `/deploy ship` para subir backend para produção.
6. ⏳ Curl `POST /api/webhooks/clicksign` em produção: esperar 401 sem HMAC e 200 com HMAC válido.
7. ⏳ Reenviar os webhooks pendentes pelo painel ClickSign (ou esperar próximo evento natural). Atas pendentes confirmadas pelos prints:
   - `899d33f9-5714-4673-9127-01f14c3037c7` (AutoClose, 15/05 08:17) — ata `RD_20260511_203049DD`
   - `c22cdcae-bced-4e21-bfbc-00d62526fc5c` (AutoClose, 12/05 16:47)
   - `29370fb1-16b4-4602-9733-4331be6365ba` (AutoClose, 12/05 12:40)
   - `54db3ff7-262b-407a-8172-8248638e1e47` (AutoClose, 12/05 09:01)
   - `97b7afa3-483d-4d11-b888-a3cd4b351e25` (AutoClose, 11/05 11:43)
   - `1d1c8dc9-2070-43ab-a094-01957450f13b` (AutoClose, 08/05 11:25)
   - `00dda427-ba25-4398-bd5e-703fef8434e5` (AutoClose, 08/05 10:31)
   - `1fd49dc1-583d-4582-a26f-47f1afef6f8b` (Cancel, 11/05 16:48)
   - `02b69138-941b-4739-9423-c20ba2a25a3f` (Cancel, 11/05 16:47)
8. ⏳ Conferir no app que cada ata correspondente avança para `ASSINADA` (ou volta para `AGUARDANDO_VALIDACAO` no caso dos Cancel).

### Critérios de sucesso

- Curl de validação em prod retorna `200 + {"received":true}` quando o envelope existe, ou `200 + {"message":"Documento não encontrado."}` quando não existe.
- Próximo webhook real do ClickSign retorna 200 no painel "Envios de Webhooks".
- Ata `RD_20260511_203049DD` aparece como `ASSINADA` na UI, com PDF assinado no Storage e pendências liberadas.

### Riscos

- **Baixo**: a mudança é apenas no path. Nenhuma outra parte do código referencia `/clicksign-completed` (verificado por grep).
- **Reenvio manual no painel ClickSign**: depende do recurso de reenvio existir no painel. Se não existir, fallback é o endpoint admin `PATCH /api/reunioes/{id}/force-status` (`reunioes.py:997-1034`), com a limitação de não baixar PDF nem liberar pendências automaticamente.

### Arquivos

- `hospital-reunioes/backend/app/routers/webhooks.py` (linhas 9, 14): mudança aplicada.
- `hospital-reunioes/backend/app/main.py` (linha 81): inclui o router com prefix `/api`. Nada a alterar.

## Execução / Resultados

- 2026-05-15 17:22: diagnóstico via curl confirma 404 na URL antiga e 200 com HMAC válido na URL nova.
- 2026-05-15 17:27: edição de `webhooks.py` aplicada localmente (prefix singular → plural, remoção do `-completed`).
- Próximo passo: `/deploy ship` para promover a mudança para produção.

---

## Implementação / Deploy

**fix(webhooks): path do clicksign passa a bater com painel da ClickSign**

- **Data**: 2026-05-15 20:35 -0300
- **SHA**: `a98e3d5` (HEAD do deploy unificado; commit do fix é `6a1ab77`)
- **Modo**: ship
- **Resultado**: 🟢 healthy
- **Commit raw**: `fix(webhooks): path do clicksign passa a bater com painel da ClickSign`

### Serviços tocados
- backend (path real `/api/webhooks/clicksign` agora bate com o registrado no painel)

### Validação em produção
- `POST /api/webhooks/clicksign` sem HMAC: HTTP 401 `{"detail":"Assinatura HMAC inválida"}` (esperado).
- `POST /api/webhooks/clicksign` com HMAC válido (secret `7e6ec77c...`): HTTP 200 `{"message":"Documento não encontrado."}` (esperado pra payload de teste).
- `POST /api/webhook/clicksign-completed` (URL antiga): HTTP 404 (rota removida).

### Pendência aberta
Reenviar pelo painel ClickSign os 9 envelopes que ficaram em 404 entre 08 e 15/05 pra sincronizar as atas correspondentes na UI (incluindo `RD_20260511_203049DD` do envelope `899d33f9`).

---
_Atualizado automaticamente pelo `/deploy ship` em 2026-05-15._
