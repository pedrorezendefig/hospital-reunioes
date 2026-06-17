---
status: accepted
---

# Auditoria de Pessoal: terceiro contexto no mesmo app, com Funcionário como população própria

O diretor recebe todo mês dois PDFs — o Espelho de Ponto do RH iD (460 págs., 1 por funcionário) e a Folha definitiva do Domínio/Thomson Reuters (~500 funcionários) — e precisa de auditoria sistemática: horas pagas vs batidas, extras acima do teto legal, descontos que não batem com o ponto, cadastro podre. Decidimos construir isso como **terceiro contexto de domínio** do app (padrão do ADR 0007), não como sistema separado nem ferramenta local.

1. **Mesmo app físico, contexto separado.** Namespace próprio e glossário em `docs/auditoria-pessoal/CONTEXT.md`. O motor (parsers dos 2 PDFs + Vínculo + Regras) nasce como biblioteca Python pura, desacoplada do FastAPI — roda local na calibração e pluga no app sem reescrita.
2. **Eixo de acesso próprio e mínimo.** Flag de **Auditor** concedida explicitamente — hoje, só o diretor. Nenhum papel de Reuniões/POPs herda acesso; menu e endpoints aplicam gating na camada de app (disciplina do ADR 0002).
3. **Funcionário é população própria do contexto.** Vem dos documentos-fonte, com as matrículas dos dois sistemas unidas pelo Vínculo. **Sem FK para `participantes`** e sem relação com Colaborador: populações distintas, cruzá-las não tem caso de uso e espalharia dado sensível.
4. **Extração é determinística; IA só traduz.** Os dois PDFs são digitais com layout estável (PDFsharp/RH iD; Amyuni/Domínio) — parsing por código, sem OCR e sem LLM. A IA entra na tradução executiva dos Achados (postura de privacidade no ADR 0010).
5. **Sem reuso das Pendências.** Achado confirmado **não** vira Pendência: a cobrança por link-sem-login das Pendências vazaria dado de RH por design. Tratativa na v1 acontece fora do sistema.

## Por que é surpreendente

- Salário, CPF e situação de saúde de ~500 pessoas dentro do "app de atas" — a expectativa seria sistema isolado. O racional é o do ADR 0007: o único usuário (diretor) já loga aqui, e auth, deploy, pipeline de IA com fallback, geração de PDF e storage já existem; a separação que importa é de domínio e permissão, não de infraestrutura.
- O cruzamento entre os dois sistemas de origem está quebrado na fonte: **176 dos 460 cadastros do RH iD têm o PIS gravado no campo CPF**, e as matrículas dos dois sistemas são numerações independentes (matrícula 3 = pessoas diferentes em cada um). Por isso o Vínculo (cascata CPF → nome exato → fuzzy + confirmação humana, persistido) é entidade de primeira classe, não um join.

## Alternativas descartadas

- **Ferramenta local rodada pelo dev**: protege os dados, mas o diretor não opera sozinho — recria a dependência mensal que o produto veio eliminar.
- **App separado**: isolamento máximo, custo de infra e operação dobrado para um dev solo (mesma conclusão do ADR 0007).
- **Pipeline de captura por email (n8n)**: ingestão frágil (assunto/anexo/remetente mudam sem aviso) e dado sensível transitando em mais um sistema. Upload manual são 2 arquivos/mês.
- **Estender Pendência para a tratativa de Achados**: vazamento por design (item 5).

## Consequências

- Terceiro eixo de permissão no mesmo app; cada endpoint novo do contexto é candidato permanente de `/security-review`.
- O app passa a custodiar o dado mais sensível do sistema — a postura de privacidade vira decisão própria (ADR 0010).
- A fase B (gestão contínua: banco de horas, advertências automáticas) e a reparametrização do RH iD → arquivo MTE → Domínio (projeto com o fornecedor) ficam fora deste escopo; os relatórios da v1 — sobretudo Batidas Automáticas e cadastro podre — são o instrumento de medição dessa reparametrização.
