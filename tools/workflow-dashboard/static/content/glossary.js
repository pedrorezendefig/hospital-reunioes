'use strict';

/* Glossário de jargão do workflow — alimenta os tooltips "?" em todo o painel.
   Definições curtas e em linguagem simples (público menos técnico).
   Fonte do vocabulário: docs/onboarding/dev.md + claude-setup.md + docs/agents/. */

export const TERMS = {
  gate: 'Um "portão" de qualidade: uma verificação automática que precisa passar antes da mudança seguir. O /ship tem 3 — code-review, security-review e CI.',
  worktree: 'Uma cópia isolada do projeto numa pasta separada, compartilhando o mesmo histórico do git. Permite trabalhar em várias issues ao mesmo tempo sem uma atrapalhar a outra.',
  'claim atômico': 'Pegar uma issue de um jeito que ninguém mais pegue a mesma ao mesmo tempo: o /pegar-issue tira a issue da fila e marca você como dono, tudo num passo só.',
  PRD: 'Product Requirements Document — o documento que descreve O QUE construir (problema, solução, histórias de usuário, critérios de aceite). Vira 1 issue no GitHub.',
  'fatia vertical': 'Um pedaço de funcionalidade completo de ponta a ponta (banco + API + tela + testes), pequeno o bastante para entregar sozinho. O contrário de fatiar por camada.',
  semver: 'Versionamento semântico: vMAIOR.MENOR.CORREÇÃO (ex. v0.16.0). O número sobe conforme o tipo da mudança — correção, funcionalidade nova ou quebra de compatibilidade.',
  'ready-for-agent': 'Label do GitHub: a issue está 100% especificada e pronta para alguém (pessoa ou agente) pegar e desenvolver.',
  'in-progress': 'Label do GitHub: alguém já pegou essa issue e está trabalhando nela agora. Sai da fila para os outros.',
  blocked: 'Label do GitHub: a issue depende de outra que ainda não terminou. Só volta para a fila quando o bloqueio fecha.',
  'security-review': 'Revisão de segurança automática (Gate 2 do /ship). Nunca é pulada quando a mudança toca login, permissões, banco de dados, variáveis de ambiente ou webhooks.',
  'code-review': 'Revisão de código automática (Gate 1 do /ship). Roda sempre, procurando bugs e problemas de qualidade no que mudou.',
  'health check': 'Uma chamada automática que pergunta ao serviço "você está vivo e respondendo?" logo após o deploy. Se falhar, o deploy é revertido.',
  rollback: 'Voltar a produção para a versão anterior, automaticamente, quando algo dá errado no deploy.',
  'version match': 'Conferência de que a versão que subiu em produção é exatamente a que era esperada — evita servir código antigo achando que é o novo.',
  snapshot: 'O mapa factual da app (rotas, tabelas, integrações) gerado automaticamente a partir do código a cada deploy. Vive em docs/spec/snapshots/.',
  ADR: 'Architecture Decision Record — registro curto de uma decisão de arquitetura importante e o porquê dela. Vive em docs/adr/.',
  migration: 'Um arquivo SQL que altera a estrutura do banco de dados (cria tabela, adiciona coluna). É aplicado em produção de forma controlada.',
  MCP: 'Model Context Protocol — a forma do Claude conversar com serviços externos (ex. o Coolify, para fazer deploy).',
  plugin: 'Uma extensão do Claude Code que adiciona skills (ex. code-review, security-guidance). Instala com /plugin install.',
  gh: 'A ferramenta de linha de comando do GitHub. O painel e as skills usam ela para ler issues e PRs e abrir pull requests.',
  CI: 'Integração contínua: o GitHub Actions roda os testes, o lint e o build a cada PR, automaticamente. É o Gate 3 do /ship.',
  Coolify: 'A plataforma onde a app roda em produção (na VPS). O /deploy conversa com ela via MCP para subir versões novas.',
  'self-approval': 'Aprovar o próprio Pull Request. É permitido aqui porque os 3 gates (code-review, security-review e CI) já validaram a mudança.',
  'Closes #N': 'Uma linha no Pull Request que, ao dar merge, fecha a issue #N automaticamente no GitHub.',
  collaborator: 'Quem tem acesso de escrita ao repositório no GitHub. Você precisa ser adicionado pelo Pedro para clonar e abrir PRs.',
  'package-manager': 'O programa que instala ferramentas na sua máquina: Homebrew (brew) no Mac, winget no Windows, apt no Linux.',
  worktree_claim: 'Combinação de worktree (pasta isolada) + claim atômico (pegar sem colisão) que permite várias sessões em paralelo.',
};
