# Feedback diretora super admin: limite de ciclos + cancelar reunião

## Plano

### Contexto

Email de uma diretora com perfil `super_admin` levantou dois pontos sobre o Hospital Reuniões em produção:

1. **"A IA só deixa realizarmos 5 ciclos de correção"**: verdade. O backend bloqueia hard em 5 correções por reunião, sem distinção de role.
2. **"Em relação a cancelamento de agendamento de reunião, meu usuário não tem acesso"**: o backend permite super_admin cancelar (`is_super_admin → autorizado = True`), mas a UI é confusa. No calendário o ícone de lixeira só aparece no hover (invisível em iPad/celular). No detalhe da reunião os botões já existem.

Objetivo das mudanças:

- Dar respiro à diretoria removendo o teto de 5 ciclos para `super_admin` (mantém para os demais como controle de custo da IA).
- Tornar o cancelamento descobrível em mobile/touch deixando o botão sempre visível no calendário.

### Decisões

- **Ciclos IA**: super_admin sem limite, demais permanecem com 5. Bypass dentro do próprio endpoint `/corrigir`.
- **Cancelar reunião**: botão sempre visível no card do calendário (mensal + semanal). Detalhe da reunião não precisa de mudança funcional, já tem botões corretos.

### Escopo

1. **Backend**: `hospital-reunioes/backend/app/routers/reunioes.py`, endpoint `POST /reunioes/{id_reuniao}/corrigir` (linhas 964 a 997).
   - Adicionar import de `is_super_admin` e `get_participante_for_user`.
   - Trocar `_: dict = Depends(get_current_user)` por `current_user: dict = Depends(get_current_user)`.
   - Resolver `me = await get_participante_for_user(current_user, supabase)` e bypassar `if ciclo >= 5` quando `is_super_admin(me)`.
   - Continuar incrementando `ciclo_correcao` (preserva contador histórico).

2. **Frontend**: `hospital-reunioes/frontend/src/app/reunioes/calendario/page.tsx`.
   - EventCard mensal (linha 642 a 653): remover `opacity-0 group-hover/card:opacity-100`, trocar `bg-indigo-200/80` por `bg-white/70` (menos poluído).
   - WeekEventCard semanal (linha 971 a 977): remover `opacity-0 group-hover/weekcard:opacity-100`, manter `bg-white/20`.
   - Botão de série recorrente (linha 984): NÃO mudar. Permanece no popover.

### Critérios de sucesso

- Super_admin consegue rodar 6ª, 7ª, 8ª correção via UI sem erro 400.
- Usuário regular recebe 400 idêntico ao atual ao tentar 6ª correção.
- Em viewport mobile/iPad, ícone de lixeira aparece nos cards do calendário (mensal e semanal) sem hover.
- Double-click confirmation (3s timeout) continua funcionando.

### Riscos

- Custo de IA pode subir com super_admin sem teto. Mitigação: `@limiter.limit("5/minute")` continua valendo (no máximo 5 chamadas por minuto por IP).
- Botão sempre visível pode poluir o calendário. Versão `bg-white/70` translúcida foi escolhida pra atenuar.

## Execução / Resultados

### 2026-05-20 11:33 — implementação local

**Backend** (`hospital-reunioes/backend/app/routers/reunioes.py`):
- Endpoint `corrigir_reuniao` (linha 966): trocado `_: dict = Depends(get_current_user)` por `current_user: dict = Depends(get_current_user)`.
- Antes do check de ciclo, agora resolve `me = await get_participante_for_user(current_user, supabase)` e condiciona o bloqueio: `if not is_super_admin(me) and ciclo >= 5`.
- Imports já existiam (`is_super_admin`, `get_participante_for_user`), não precisou tocar no topo do arquivo.
- `ruff check`: passou.
- `ruff format --check`: já formatado.

**Frontend** (`hospital-reunioes/frontend/src/app/reunioes/calendario/page.tsx`):
- EventCard mensal (linha 642): removido `opacity-0 group-hover/card:opacity-100`, trocado `bg-indigo-200/80` por `bg-white/70`.
- WeekEventCard semanal (linha 974): removido `opacity-0 group-hover/weekcard:opacity-100`. Estilo `bg-white/20` mantido.
- Botão de série recorrente da vista semanal (linha 984): mantido como estava (opacity-0 + hover), conforme plano.
- `tsc --noEmit`: passou (exit 0).
- `next lint --file <arquivo>`: sem warnings.

**Diff total**: 2 arquivos, +8 / -7 linhas.

### Pendente

- Subir local via `/atualizar-app` e testar o fluxo (Pedro).
- Comunicar a diretora super admin após deploy em prod.
- `/deploy ship` quando aprovado: vai renomear este plano automaticamente para 🟢 ou 🔴 e anexar a seção `## Implementação / Deploy` no final.
