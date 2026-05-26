---
status: accepted
---

# Controle de acesso na aplicação (SERVICE_ROLE_KEY), não RLS

O backend FastAPI acessa o Postgres sempre com a `SERVICE_ROLE_KEY` (que faz _bypass_ de RLS) e aplica **todo** o controle de acesso na camada de aplicação — filtrando por papel, `access_profile` e `is_super_admin` em Python, endpoint a endpoint. O frontend nunca fala direto com o banco. Escolhemos isso porque as regras de quem-vê-o-quê (Facilitador vs Secretária vs Super admin) são complexas e ficam mais legíveis e testáveis em Python do que em policies SQL.

## Por que é surpreendente

Quem chega a um projeto Supabase espera RLS protegendo as tabelas. Aqui **não há essa rede de segurança**: se um endpoint esquecer de aplicar o filtro de acesso, vaza dados. A disciplina vive no código, não no banco.

## Consequências

- Cada endpoint que lê dados de Colaborador/Reunião **precisa** aplicar o filtro de acesso explicitamente — isto é candidato natural a `/security-review`.
- Policies do Supabase ficam simples (quase tudo liberado para a service role), o que acelera migrations.
- É difícil de reverter: adicionar RLS depois exigiria reescrever as garantias de acesso como policies e auditar todos os endpoints.
