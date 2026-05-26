---
status: accepted
---

# Supabase self-hosted no Coolify (não managed)

O banco e o Auth do Hospital Reuniões rodam num **Supabase self-hosted** dentro do Coolify, na mesma VPS Hostinger da aplicação — em vez do Supabase Cloud gerenciado. Escolhemos isso por controle total dos dados (hospital, dados sensíveis), custo previsível de VPS e proximidade de rede com o backend.

## Consequências

- **Nós** somos responsáveis por backup, upgrades e monitoramento do Postgres/GoTrue — não há SLA gerenciado.
- Migrations destrutivas e ownership de objetos exigem cuidado: algumas rodam como `supabase_admin`, não como o usuário `postgres` padrão.
- Trocar para o Supabase Cloud depois é caro (migração de dados + Auth) — daí ser um ADR.
