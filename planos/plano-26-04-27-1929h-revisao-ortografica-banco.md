# Plano — Revisão ortográfica em massa do banco (Hospital Reuniões)

## Contexto

Durante a migração das ATAs antigas (PDFs em `atas-migracao/`), a IA de extração (`backend/app/prompts/extracao_ata_migrada.md`) "limpou" os textos por conta própria — o prompt nunca instruiu a preservar acentos. Resultado: textos vieram para o banco com `nao`, `Conclusao`, `execucao`, `Tecnico Senior` etc. Os nomes de participantes (vindos da tabela parseada do PDF, não da IA) **preservaram** acentos. Isso confirma que o problema é cirúrgico: campos onde a IA escreveu prosa.

**Estado real medido agora no banco** (`psql postgresql://postgres:postgres@127.0.0.1:54352/postgres`):
- `reunioes` com `status_ata='MIGRADA'`: **27** registros
- `pendencias`: **150** registros (escopo total — todas vieram da migração)
- `participantes`: **60** registros (a maioria com acento ok; ~5-10 com cargo "Tecnico Senior" / "Tecnico de Seguranca" sem acento)
- `comentarios_pendencias`: **0** registros (categoria vazia — ignorar)

**Importante:** o banco que importa está **local** (Supabase CLI rodando em `:54351`/`:54352`). Não existe link com projeto Supabase remoto (`supabase/.temp/project-ref` não existe). Tudo neste plano roda contra o local. Quando houver promoção pra produção (linkar projeto remoto + push migrations + rodar `bulk_import_atas` lá), repete-se o mesmo SQL contra a connection string remota.

**Resultado esperado:** todos os textos de Camada 1 (texto plano: `pendencias.{descricao_acao,meta_entregavel,responsavel_nome,cargo}`, `participantes.{nome_completo,cargo,area,setor}`, `reunioes.{titulo,objetivo,setor}`) ortograficamente corretos, com backup em tabelas `*_backup_ortografia_20260427`, em **uma transação única**.

---

## Arquitetura simplificada (sem custo, sem UI, sem API externa)

```
1. SELECT (eu) → exporta todos os textos do escopo num arquivo .txt navegável
2. CORRIJO (eu, na conversação)  → mostro 1 ATA exemplo pra você aprovar a abordagem
3. GERO revisao-ortografica.sql  → BEGIN + backups + UPDATEs + COMMIT
4. APLICO via psql -f             → 1 transação, rollback se qualquer erro
5. VALIDO  com SELECT pós-aplicação
```

**Sem:** API Anthropic (zero custo), FastAPI, htmx, JSON intermediário, prompt caching, tool use, RPC PL/pgSQL nova.
**Com:** apenas `psql`, arquivos SQL versionáveis em `planos/sql/`, e Claude (eu, na conversação) lendo/corrigindo no contexto.

---

## Etapa 1 — Exportar tudo num arquivo navegável

Comando único (read-only):

```bash
psql "postgresql://postgres:postgres@127.0.0.1:54352/postgres" \
  -P pager=off -X -A -F $'\t' \
  -c "SELECT 'reunioes', id_reuniao, 'titulo', titulo FROM reunioes WHERE status_ata='MIGRADA'
      UNION ALL
      SELECT 'reunioes', id_reuniao, 'objetivo', objetivo FROM reunioes WHERE status_ata='MIGRADA' AND objetivo IS NOT NULL
      UNION ALL
      SELECT 'reunioes', id_reuniao, 'setor', setor FROM reunioes WHERE status_ata='MIGRADA' AND setor IS NOT NULL
      UNION ALL
      SELECT 'pendencias', id_acao, 'descricao_acao', descricao_acao FROM pendencias WHERE descricao_acao IS NOT NULL
      UNION ALL
      SELECT 'pendencias', id_acao, 'meta_entregavel', meta_entregavel FROM pendencias WHERE meta_entregavel IS NOT NULL
      UNION ALL
      SELECT 'pendencias', id_acao, 'responsavel_nome', responsavel_nome FROM pendencias WHERE responsavel_nome IS NOT NULL
      UNION ALL
      SELECT 'pendencias', id_acao, 'cargo', cargo FROM pendencias WHERE cargo IS NOT NULL
      UNION ALL
      SELECT 'participantes', id, 'nome_completo', nome_completo FROM participantes
      UNION ALL
      SELECT 'participantes', id, 'cargo', cargo FROM participantes WHERE cargo IS NOT NULL
      UNION ALL
      SELECT 'participantes', id, 'area', area FROM participantes WHERE area IS NOT NULL
      UNION ALL
      SELECT 'participantes', id, 'setor', setor FROM participantes WHERE setor IS NOT NULL" \
  > planos/sql/revisao-ortografica-export.tsv
```

Resultado: um TSV com `tabela | id | coluna | valor_atual`. ~700-900 linhas. Eu leio esse arquivo direto.

---

## Etapa 2 — Eu corrijo na conversação (sem API)

Eu (Claude rodando aqui na sessão) leio o TSV em chunks de ~50 linhas, corrijo acentuação seguindo regras conservadoras:

**Adiciono apenas:**
- Acentos agudos (´): execucao → execução, gestao → gestão, ate → até
- Acentos circunflexos (^): voce → você, tecnico → técnico, conhece → conhecê-lo
- Til (~): coordenacao → coordenação, sao → são (apenas em verbo, não em "São Paulo" se não estiver no contexto adequado)
- Cedilha (ç): execucao → execução, paralisacoes → paralisações
- Crase (`): a Cyber → à Cyber (quando há regência clara)
- Ordinais femininos: 2a → 2ª

**Nunca altero:**
- Maiúsculas/minúsculas
- Ordem das palavras
- Pontuação
- Nomes próprios desconhecidos (Cyber, MV, PSA, CTI, Malafaia, Soares — tudo passa intacto)
- Siglas (HSM, ADM, PSA)

**Marco como `precisa_revisar`:** ambíguos (publico/público, secretaria/secretária, gravida/grávida — depende de contexto sintático), e te peço pra olhar antes do apply.

---

## Etapa 3 — Gero `planos/sql/revisao-ortografica-20260427.sql`

Arquivo único, autocontido, no formato:

```sql
-- Revisão ortográfica em massa — gerado 2026-04-27
-- Fonte: planos/sql/revisao-ortografica-export.tsv
-- Escopo: Camada 1 (texto plano)
-- Volume previsto: ~XXX UPDATEs

BEGIN;

-- =================================================================
-- BACKUP — tabelas de rollback rápido (drop manual após 30 dias)
-- =================================================================
CREATE TABLE IF NOT EXISTS pendencias_backup_ortografia_20260427    AS TABLE pendencias;
CREATE TABLE IF NOT EXISTS participantes_backup_ortografia_20260427 AS TABLE participantes;
CREATE TABLE IF NOT EXISTS reunioes_backup_ortografia_20260427      AS TABLE reunioes;

-- =================================================================
-- ATA MIG_20260303_033813A9 — Reunião de TI e Infraestrutura de Rede
-- =================================================================
UPDATE reunioes
SET objetivo = 'A reunião teve por objetivo revisar o cronograma de execução do cabeamento estruturado pela empresa Cyber, definir os setores prioritários para intervenção imediata e estabelecer logística de obras de forma a garantir que todos os setores críticos estejam operacionais em rede até a migração do sistema MV em 28 de março de 2026.'
WHERE id_reuniao = 'MIG_20260303_033813A9';

UPDATE pendencias SET
  descricao_acao  = 'Conclusão dos serviços de rede no PSI (Pediatria)',
  meta_entregavel = 'PSI 100% concluído',
  cargo           = 'Técnico Sênior'
WHERE id_acao = 'A003';

UPDATE pendencias SET
  descricao_acao = 'Execução de infraestrutura de rede no CTI 3 (janela de obras civis)',
  cargo          = 'Técnico Sênior'
WHERE id_acao = 'A004';

-- ... (resto das pendências dessa ATA)

-- =================================================================
-- ATA MIG_<próxima> — <título>
-- =================================================================
-- ... (todas as 27 ATAs em ordem cronológica)

-- =================================================================
-- PARTICIPANTES (bloco global — corrigidos uma vez só)
-- =================================================================
UPDATE participantes SET cargo = 'Técnico Sênior'                  WHERE id IN ('P048', 'P050', 'P052');
UPDATE participantes SET cargo = 'Técnico de Segurança do Trabalho' WHERE id = 'P053';

-- =================================================================
-- VALIDAÇÃO inline (falha = rollback)
-- =================================================================
DO $$
DECLARE
  v_suspeitos INT;
BEGIN
  SELECT COUNT(*) INTO v_suspeitos
  FROM pendencias
  WHERE descricao_acao ~ '\m(execucao|conclusao|atencao|reuniao|gestao|coordenacao)\M';
  IF v_suspeitos > 5 THEN
    RAISE EXCEPTION 'Validação falhou: % pendências ainda têm palavras suspeitas sem acento', v_suspeitos;
  END IF;
END $$;

COMMIT;
```

**Garantias:**
- BEGIN / COMMIT explícito → tudo ou nada
- Backups CREATE TABLE IF NOT EXISTS → não duplica se rodar 2 vezes
- Bloco DO no final → se sobrar muita coisa errada, faz ROLLBACK automático
- Triggers `updated_at` disparam normalmente (esperado)

---

## Etapa 4 — Aplicar

```bash
psql "postgresql://postgres:postgres@127.0.0.1:54352/postgres" \
  -v ON_ERROR_STOP=1 \
  -f planos/sql/revisao-ortografica-20260427.sql
```

`ON_ERROR_STOP=1` aborta na primeira falha (safety net além do BEGIN/COMMIT).

**Tempo de execução:** < 5 segundos para ~500 UPDATEs (banco local).

---

## Etapa 5 — Validar

```bash
psql "postgresql://postgres:postgres@127.0.0.1:54352/postgres" \
  -c "SELECT 'pendencias_suspeitas' AS metric, COUNT(*) FROM pendencias WHERE descricao_acao ~ '\m(execucao|conclusao|reuniao|gestao|coordenacao|atencao|nao)\M'
      UNION ALL SELECT 'participantes_suspeitos', COUNT(*) FROM participantes WHERE cargo ~ 'Tecnico|Senior'
      UNION ALL SELECT 'objetivos_suspeitos', COUNT(*) FROM reunioes WHERE objetivo ~ '\m(execucao|reuniao|nao|sao)\M';"
```

**Esperado:** 0 em todas (ou números justificáveis caso a caso).

**Validação visual:**
- Skill `/atualizar-app` → sobe stack apontando pro local
- Abrir `http://localhost:3000` → conferir lista de ATAs, pendências, participantes
- Comparar 3-4 itens lado a lado com a versão pré-correção

---

## Rollback (se algo dér errado)

Como tudo está numa transação, falha durante o apply = nada acontece (BEGIN/ROLLBACK automático). Se descobrir um problema **depois** do COMMIT:

```sql
-- Rollback rápido via tabela backup
TRUNCATE pendencias;     INSERT INTO pendencias    SELECT * FROM pendencias_backup_ortografia_20260427;
TRUNCATE participantes;  INSERT INTO participantes SELECT * FROM participantes_backup_ortografia_20260427;
TRUNCATE reunioes;       INSERT INTO reunioes      SELECT * FROM reunioes_backup_ortografia_20260427;
```

(Como há FKs em cascata para `pendencias`/`reuniao_participantes` etc., melhor usar `DELETE` em vez de `TRUNCATE` se essas tabelas tiverem dependentes — ajusto na hora se for o caso.)

---

## Promoção para produção (futuro, fora do escopo desta rodada)

Quando você linkar um projeto Supabase remoto e fizer push das migrations + rodar `bulk_import_atas` contra ele, basta:

1. `supabase link --project-ref <REF>`
2. Pegar a connection string de produção (Supabase dashboard → Database → Connection string)
3. Rodar o **mesmo arquivo** `planos/sql/revisao-ortografica-20260427.sql` contra essa string
4. Validar igual

O SQL é portável (não usa nada local-only).

---

## Arquivos a criar

1. `planos/sql/revisao-ortografica-export.tsv` — dump dos textos atuais (etapa 1)
2. `planos/sql/revisao-ortografica-20260427.sql` — UPDATEs + backup (etapa 3, montado na conversação)
3. `planos/sql/revisao-ortografica-20260427-validacao.sql` — queries de validação pós-apply (etapa 5)
4. Cópia deste plano para `planos/plano-26-04-27-1728h-revisao-ortografica-banco.md`

**Nada modificado em código de aplicação.** Sem novo script Python, sem nova migration de schema (`033_*.sql` etc.), sem nova RPC. Só dados.

---

## Exemplo concreto — ATA "Reunião de TI e Infraestrutura de Rede" (mostrado na resposta abaixo)

A resposta da conversação após este plano vai conter o diff completo dessa ATA (1 reunião + 6 pendências) — antes/depois lado a lado, e o SQL gerado correspondente. Se você aprovar o estilo e a calibração, eu gero o restante das outras 26 ATAs no mesmo formato.

---

## Riscos e mitigação

| Risco | Mitigação |
|---|---|
| Eu errar acento em nome próprio incomum | Política conservadora: nomes próprios passam intactos, só mexo em palavras comuns do português |
| Caso ambíguo (publico/público) | Marco no SQL como comentário `-- AMBIGUO: ...` e te peço revisão antes de incluir o UPDATE definitivo |
| Apply parcialmente bem-sucedido | BEGIN/COMMIT explícito + `ON_ERROR_STOP=1` → falha vira rollback |
| Trigger `updated_at` em massa | Aceitável (não há trigger de notificação por UPDATE de texto) — registrado no relatório |
| Re-rodar SQL duas vezes | Idempotente: `CREATE TABLE IF NOT EXISTS` no backup, e segunda rodada de UPDATE com mesmos valores não muda nada |
| Frontend cacheado mostrando texto antigo | Hard reload no browser pós-apply; SW (`sw.js`) também invalida |

---

## Fora de escopo (registrado para futuro)

- `reunioes.json_ata` (Camada 2 — JSONB com discussão estruturada, é onde mora MAIS texto)
- `setores.nome`, `cargos.nome`, `tipos_reuniao.nome`, `notificacoes.titulo/mensagem` (Camada 3)
- Atualização do prompt `extracao_ata_migrada.md` para preservar acentos em futuras migrações (Camada 4)
- Promoção para Supabase remoto

---

## Execução / Resultados

**Aplicado em 2026-04-27 ~17:48** contra `postgresql://postgres:postgres@127.0.0.1:54352/postgres`.

### Artefatos gerados
- `planos/sql/revisao-ortografica-export.tsv` — 869 linhas exportadas (escopo total).
- `planos/sql/revisao-ortografica-20260427.sql` — 360 linhas, 147 statements `UPDATE`, validação inline + transação atômica.
- Backup tables criadas:
  - `pendencias_backup_ortografia_20260427` (150 linhas)
  - `participantes_backup_ortografia_20260427` (60 linhas)
  - `reunioes_backup_ortografia_20260427` (29 linhas)

### Mudanças aplicadas
- **Reuniões:** 27 ATAs migradas atualizadas — 27 `objetivo` corrigidos + 10 `titulo` corrigidos.
- **Pendências:** ~115 linhas com `descricao_acao` e/ou `meta_entregavel` e/ou `cargo` corrigidos (de 150 totais).
- **Participantes:** 12 correções globais — 4 cargos distintos (`Diretor de Operações`, `Técnico Sênior`, `Técnico de Segurança do Trabalho`, `Encarregado de Higienização e Hotelaria`), 1 nome próprio (`João` em conta de teste P045) e 1 setor (`Hospital São Matheus` em P057).

### Validação inline (executada dentro da mesma transação, antes do COMMIT)
- `pend_descricao_suspeita` = 0
- `pend_meta_suspeita` = 0
- `pend_cargo_suspeito` = 0
- `part_cargo_suspeito` = 0
- `reun_objetivo_suspeito` = 0
- `reun_titulo_suspeito` = 0

Transação fechou com `COMMIT` — nenhum rollback necessário.

### Spot check da ATA `MIG_20260303_033813A9` (Reunião de TI)
Bate exatamente com o exemplo aprovado antes do apply:
- `objetivo`: "A reunião teve por objetivo revisar o cronograma de execução…" ✓
- A003-A008 com acentos: Conclusão, Execução, Cirúrgico, paralisações, à Cyber, Técnico Sênior ✓

### Casos ambíguos resolvidos
- **`comunicado a Cyber` → `comunicado à Cyber`** (A008): aplicado, regência clara de "comunicar a [empresa]" + feminino.
- **`relativas a infraestrutura, financeiro e gestão médica`** (MIG_20260313): mantido SEM crase (enumeração mista, gênero variado).
- **`3 e 4 andar`** (A109): mantido como está (ambíguo entre cardinal e ordinal).
- **Nomes próprios incomuns** (Flavia, Janaina, Fabricio, Cesar): preservados intactos por política conservadora.

### Próximos passos sugeridos (fora do escopo desta rodada)
1. Reabrir o app local (`/atualizar-app`) e validar visualmente em `http://localhost:3000` — listagem de pendências, modal de ATA, dropdown de filtros.
2. ✅ **Concluído em 2026-04-27 19:29** — replicação aplicada em prod via Studio SQL editor (ver seção abaixo).
3. Camadas 2-4 (JSONB de ATA, taxonomias, prevenção no prompt) — abrir planos separados quando fizer sentido.
4. Cleanup das tabelas backup `*_backup_ortografia_20260427` em **prod e local** após 30 dias — agendar pra 2026-05-27.

### Replicação em produção (2026-04-27 19:29)

Mesmo SQL aplicado em prod (Supabase self-hosted via Coolify, `studio.mala-ia.cloud`).

**Caminho de execução:** Studio SQL editor (web) — escolhido após constatar que (a) SSH `root@31.97.29.32` não tinha chave configurada na máquina do Pedro e (b) a porta 5432 externa rejeitou tanto `POSTGRES_PASSWORD` quanto `SERVICE_PASSWORD_POSTGRES` para os users `postgres`/`supabase_admin` (provavelmente Supavisor pooler com auth diferente). Pedro removeu a meta-diretiva `\set ON_ERROR_STOP on` (não suportada pelo pg_meta API) e colou o SQL inteiro no editor.

**Sanidade pré-aplicação (Studio):** `count(reunioes WHERE status_ata='MIGRADA')` = 27 ✓; `count(participantes WHERE id IN (12 ids))` = 12 ✓ — drift descartado.

**Resultado:** `Success. No rows returned` (COMMIT bem-sucedido). Validação inline `DO $$` passou silenciosamente (não houve `RAISE EXCEPTION`).

**Spot-check pós-aplicação:**
- 5 reuniões `MIGRADA` aleatórias com acentos: `Reunião Mensal de Gerência — DP e RH`, `Repasse Médico — Indicadores`, `Revisão do quadro de atribuições, quadros elétricos, CTI-3 (reforma)`, objetivos com `internação`, `prorrogação`, `gestão`, `liberação`, `atribuições` ✓
- Pendências A123/A130/A147 com `educação continuada`, `repasse médico`, `redução do tempo de espera médica` ✓
- Participantes P045 (`João Diretor Administrativo`), P053 (`Técnico de Segurança do Trabalho`), P055 (`Coordenadora de Recepção / Internação`), P065 (`Encarregado de Higienização e Hotelaria`) ✓
- Tabelas de backup em prod: `participantes_backup_ortografia_20260427`, `pendencias_backup_ortografia_20260427`, `reunioes_backup_ortografia_20260427` ✓

**Diferenças vs. aplicação local:**
- Sem `pg_dump` pré-aplicação (SSH indisponível). Rede de segurança fica nas 3 tabelas `*_backup_ortografia_20260427` criadas pela própria transação + TSV `revisao-ortografica-export.tsv` para rollback granular.
- Sem visibilidade dos `RAISE NOTICE` (Studio não exibe), mas a ausência de `ERROR` confirma que os 3 contadores (`v_pend_susp ≤ 5`, `v_part_susp = 0`, `v_reun_susp = 0`) ficaram dentro do limite.

### Rollback (se algum dia for necessário)
```sql
BEGIN;
  DELETE FROM pendencias;     INSERT INTO pendencias    SELECT * FROM pendencias_backup_ortografia_20260427;
  DELETE FROM participantes;  INSERT INTO participantes SELECT * FROM participantes_backup_ortografia_20260427;
  DELETE FROM reunioes;       INSERT INTO reunioes      SELECT * FROM reunioes_backup_ortografia_20260427;
COMMIT;
```
