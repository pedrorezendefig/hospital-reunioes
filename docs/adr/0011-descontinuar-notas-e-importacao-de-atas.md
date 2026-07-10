---
status: accepted
supersedes: 0004
---

# Descontinuar Notas e Importação de ATAs

Duas funcionalidades saíram de uso no dia a dia dos 5 Facilitadores e viraram peso morto no produto. A **Nota** (ADR 0004) — registro leve paralelo à Reunião, com extração de Pendências por IA — **nunca foi adotada em produção**: zero Notas criadas, zero Pendências com `id_nota`. A **Importação de ATAs** (`/reunioes/importar` + `bulk_import_atas`) cumpriu seu papel — a carga histórica de atas antigas já foi feita e as Reuniões importadas vivem como Reuniões normais — e não há nova carga prevista.

A decisão: **remover as duas de ponta a ponta**, não apenas escondê-las do menu.

- **Notas**: sai a UI (`/notas`, componentes), o router (`notas.py`), os ramos de origem-Nota no código de Pendências (escopo e permissão por `id_nota`), os testes e o schema — migration que desfaz 041/042/043 (`DROP CONSTRAINT chk_pendencias_origem_unica`, `DROP COLUMN id_nota`, `DROP TABLE nota_participantes`, `DROP TABLE notas`), com **gate de segurança**: aborta se existir qualquer Nota ou Pendência de Nota no banco. A Pendência volta a nascer de uma única porta: Reunião em estado terminal (ASSINADA ou APROVADA, ADR 0003).
- **Importação de ATAs**: sai a tela, o router (`importacao.py`), o item de menu e os testes. **Nenhuma migration** — os dados importados são Reuniões/Atas comuns e permanecem intactos.
- O que **fica**: a transcrição por voz (`useGravacaoVoz` + endpoint de transcrição), que a Nota introduziu mas a Ata Guiada e o chat de elaboração de POPs também usam.

O ADR 0004 passa a `superseded` por este.

## Por que é surpreendente

Quem ler as migrations em sequência verá 041–043 construírem o que uma migration posterior derruba poucos meses depois — sem este registro, parece erro ou retrabalho. E o código de Pendências volta a assumir `id_reuniao` sempre preenchido, exatamente a suposição que o ADR 0004 mandou parar de fazer: a "terceira porta" de origem fecha.

## Alternativas descartadas

- **Só esconder do menu** (código fica): superfície morta para manter — testes rodando à toa, glossário descrevendo entidade fantasma, e o CHECK XOR em `pendencias` complicando todo raciocínio sobre origem sem servir a ninguém.
- **Feature flag**: complexidade de configuração para uma funcionalidade sem demanda conhecida; se a necessidade voltar, o git e este ADR guardam o desenho — recriar é mais barato que carregar a flag.
- **Manter as tabelas vazias "por via das dúvidas"**: o schema passa a mentir sobre o domínio; a integridade (`CHECK` XOR) continuaria custando em cada mudança de Pendências.

## Consequências

- `pendencias` volta a ter **duas origens** lógicas (Reunião ASSINADA ou APROVADA) e `id_reuniao` como única FK de origem — código de escopo/permissão simplificado.
- Glossário (`CONTEXT.md`): sai o verbete **Nota**; **Pendência**, **Participante** e **Resolução** voltam a citar só a Reunião (e a Ata Guiada, que segue existindo — ADR 0005/0006/0008 não são afetados).
- O menu lateral enxuga: Dashboard, Calendário, Pendências, POPs (condicional a `perfil_pop`, ADR 0007) e Admin.
- A migration de drop é **irreversível com dados** — por isso o gate; recriar a feature no futuro = nova migration a partir deste ADR e do 0004.
- Implementação nas issues da reorganização do menu (remoção de Importação; descontinuação de Notas; bootstrap do Superadmin POPs).
