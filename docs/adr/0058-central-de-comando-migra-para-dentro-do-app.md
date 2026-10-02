---
status: accepted
amends: 0057
amended_by: 0059
---

# Central de Comando migra para dentro do app do hospital, só para Super admin, com o servidor portado para o FastAPI

Decisão do Pedro (18/set/2026, grilling). A Central de Comando, o painel dos números do site e do Instagram do hospital, nasceu em junho de 2026 como aplicação separada (`pedroribbe/central-de-comando-hsm`, em `central.mala-ia.cloud`). Ela vira uma seção da área de Administração do app, o que funciona hoje passa a funcionar aqui, e o app antigo é desligado. Esta ADR fixa como.

## Contexto

Fatos que pesaram:

- A Central é um Next.js 16 só, sem backend à parte: o servidor em TypeScript busca GA4 e Instagram, guarda cache de 1 hora em memória e expõe um conector MCP com OAuth 2.1 pelo WorkOS AuthKit. Não tem banco, volume, fila nem tarefa agendada. No Coolify é 1 app com 13 variáveis de ambiente.
- O app do hospital é Next.js 15 no front e FastAPI no back. O front não guarda segredo: toda API externa e todo controle de acesso vivem em Python (ADR 0002, ADR 0038).
- A Central tinha login próprio (usuário e senha em variável de ambiente), casca própria, CSS Modules, gráficos em SVG caseiro e tema escuro. O app tem Supabase Auth, `AppShell`, Tailwind v4, `recharts` e só tema claro.
- O que funciona de verdade: Visão Geral, Objetivos (4 de 6 com número), Dados do Google, Instagram e o conector MCP com 3 ferramentas. Mapa de Calor, Google Ads, Editor do Site e Blog eram só tela de "em breve".
- O diretor já é Super admin do app e usa o app do hospital muito mais do que a Central.
- A ADR 0050 já tinha decidido o mesmo movimento para a aba Tecnologia: mora no app, só Super admin, visual do app.

## Decisões

1. **Mora no app, em seção própria do menu da Administração, só para Super admin.** A seção "Central de Comando" entra entre Atendimento e Tecnologia, no mesmo molde das outras (rótulo e itens embaixo), e a Ajuda continua sendo o último item (ADR 0057, decisão 11, intacta). O gate é `super_admin`, sem eixo de permissão próprio: todo Super admin vê, e quem precisa ver precisa ser Super admin. Cada rota ganha guard de Super admin no `layout.tsx`, além do 403 do backend, porque secretária e facilitador entram em `/admin`. Rejeitado: `perfil_central` (não existe ninguém que precise ver os números sem poder ser Super admin); item literalmente depois da Ajuda (custaria emendar a 0057 e deixaria o menu do Super admin diferente do dos outros papéis).

2. **O servidor é portado para o FastAPI. A Central se adapta ao app, nunca o contrário.** Endpoints em `/api/admin/central-de-comando/*` com `require_super_admin`, clientes do Google e do Instagram em `services/` no molde do Espelho da Global Health (segredo ausente é 503 honesto, falha não vira lista vazia), cache de 1 hora em memória no processo do backend, que roda com 1 processo só, como a Central rodava. O front vira tela Tailwind com os tokens e os componentes do app, gráficos em `recharts`, e as barras simples em Tailwind puro. Morrem o login próprio, a casca própria, os CSS Modules e a matemática de gráfico caseira. Os testes da Central são a especificação do porte: cada teste de regra vira um pytest equivalente antes de a fatia fechar. Rejeitado: manter o servidor em TypeScript dentro do front do hospital (barato, os testes viriam de graça, mas poria a credencial do Google e o token do Instagram no serviço do front, criaria um segundo gate de Super admin fora do Python e um segundo jeito de fazer backend no mesmo app, para sempre).

3. **O conector MCP vai para o backend e mantém o WorkOS AuthKit.** Mesmas 3 ferramentas, mesmo contrato, em `https://api.hospitalsaomatheus.cloud/api/mcp`. É o único OAuth da casa, e é forçado: conector personalizado do claude.ai só aceita OAuth ou nenhuma autenticação, então o `X-API-Key` da API da Ana não serve. No corte, cada pessoa remove o conector antigo e adiciona o novo, uma vez. Rejeitado: manter `central.mala-ia.cloud` apontando para o backend (domínio pessoal, prenderia o desligamento); trocar o MCP por um assistente dentro do app no molde da ADR 0056 (é funcionalidade nova paga na chave do projeto, não migração, e entrega menos do que o Claude de quem já tem assinatura).

4. **Quem pode conectar o MCP é quem é Super admin.** O backend pega o e-mail verificado do token, acha o participante e exige ativo e `super_admin`. A lista de e-mails em variável de ambiente morre. Rebaixou ou desligou a pessoa, o conector dela para na hora. Custo aceito: o e-mail usado no WorkOS tem de ser o do cadastro no app, o que vira item do checklist do corte. Rejeitado: portar a lista como está (segunda lista de acesso, que diverge da primeira em silêncio).

5. **O menu só lista o que funciona.** Quatro itens: Visão Geral, Objetivos, Dados do Google, Instagram. O que ainda não existe aparece num bloco único no pé da Visão Geral, "O que vem por aí". Rejeitado: portar as quatro telas de "em breve" como itens (a Central sozinha ficaria maior que o resto do menu, metade abrindo tela vazia, num app que não tem nenhum item assim); cortar o roadmap de vez (a visão de futuro para a diretoria era intenção do desenho original).

6. **Paridade de 100% é de dado e de função, não de aparência.** Todo número, todo período, o Ao vivo, o Atualizar agora, a degradação honesta e o MCP têm de bater. O **tema escuro não vem**: o app só tem tema claro, tema escuro só no miolo ficaria quebrado dentro de uma casca clara, e tema escuro no app inteiro é outro projeto. Perda consciente.

7. **Vocabulário alinhado ao do app.** "Braço do Hospital" vira **Área do site** (o número fala das páginas do site, não da procura pelo serviço, e não tem vínculo com a taxonomia de Setores). "Objetivo" nunca é chamado de meta. "Origem" é sempre "Origem do público". "Site Oficial" e "Site Novo" viram só "Site". Os guarda-chuvas "Analytics" e "Marketing" e o estado "Em breve" morrem. Definições no `CONTEXT.md`. O vocabulário muda também em duas chaves do contrato do conector MCP (decisão 3), e quem lia o conector antigo lê as chaves novas: as áreas saem em `areasDoSite` (era `bracos`), e o canal Fale Conosco, em `contatos[].chave`, é `fale-conosco` (era `leads`, o nome interno da Central antiga). A troca de `leads` apareceu na conferência de paridade e foi mantida por decisão do Pedro (23/set/2026): `fale-conosco` é o nome do canal no app.

8. **Entrega dormente, validação em localhost, a última fatia liga.** Cada fatia é validada no ambiente local com as credenciais reais e sobe para a `main` em PR pequeno, pelo `/ship` de sempre. Em produção o código chega desligado: o item de menu só aparece fora de `production` (pela `NEXT_PUBLIC_ENVIRONMENT`, que já existe) e as credenciais não entram no Coolify até o fim. A última fatia tira a condição, cola as variáveis, e a Central aparece inteira, de uma vez. Rejeitado: branch longa com merge único (a `main` recebe vários deploys por dia e a migração mexe em `main.py`, `config.py` e `AdminSidebar.tsx`; os gates do `/ship` revisariam milhares de linhas de uma vez; o primeiro encontro do código com a produção seria o pacote inteiro); fatias visíveis em produção conforme ficam prontas (o Pedro quer ver tudo surgir de uma vez).

9. **Corte em quatro tempos, com quarentena.** Construção em paralelo com o app antigo intacto; prova de paridade lado a lado (mesma fonte, mesmo período, número idêntico, divergência é bug de porte); dia do corte (conferir cada e-mail da lista antiga do MCP contra o cadastro, trocar o Resource Indicator no WorkOS, reconectar os conectores, refazer o guia do conector em `docs/comunicacao/`); e o app antigo **parado**, não apagado, por 14 dias. Só depois: apagar o app no Coolify, remover o DNS e **arquivar** o repositório antigo, que guarda as specs e o histórico.

10. **Fora do Manual do usuário.** A Central não tem tarefa, tem leitura, é didática na própria tela e só Super admin vê. O PRD da migração não gera fatia de manual. A ADR 0057, decisão 1, passa a ter duas exceções: a aba Tecnologia e a Central de Comando. O que precisa de instrução é conectar o MCP, e isso é o guia do conector.

11. **O Blog não entra aqui.** Escrever post por dentro da Central é o destino combinado (o Sanity é a solução intermediária), mas é produto novo com decisões próprias em aberto. Vira o PRD seguinte, com grilling próprio. As issues vivas do repositório antigo (#13, #17, #18) são recriadas neste repo como semente dele; as #1 a #4, já entregues, são fechadas lá sem recriar.

## Decisões herdadas do repositório antigo

Continuam valendo, e o raciocínio completo fica em `pedroribbe/central-de-comando-hsm`, `docs/adr/`:

- **0002 de lá:** os números vêm da GA4 Data API e são desenhados em tela própria, sem embutir Looker nem iframe.
- **0003 de lá:** só se mostra o que o site de fato expõe; o que não é medido aparece como "em construção" ou "não medido". É a origem da honestidade do dado.
- **0004 de lá:** o site novo reporta para a mesma propriedade GA4 do antigo, para a série histórica não quebrar.
- **0005 de lá:** Instagram só orgânico, pela API do Instagram, com a terminologia nativa da rede.
- **0006 de lá:** os dados saem por um conector MCP só de leitura.

**Revertida:** a 0001 de lá, "a Central é um app separado e somente leitura". Separada deixou de ser com esta ADR; somente leitura deixará de ser com o Blog.

## Consequências

- Quem for Super admin vê os números do hospital e pode ligá-los ao próprio Claude. Promover alguém a Super admin passa a significar isso também.
- O backend ganha a primeira integração com Google e com Instagram e o primeiro resource server OAuth. Todo teste desses clientes precisa dublar a rede, por causa da trava de rede da suíte.
- O token do Instagram expira e é renovado à mão, como hoje. Só muda onde a variável é colada.
- Risco a responder na primeira fatia do MCP: se o AuthKit aceita dois Resource Indicators ao mesmo tempo. Se não aceitar, o MCP novo só é testado no dia do corte, com o antigo já parado.
- Deploy do backend zera o cache de 1 hora. O backend do hospital sobe com muito mais frequência do que a Central subia, então a primeira leitura depois de cada deploy vai à fonte. Emendado pela ADR 0059 (issue #867): o backend aquece o período padrão de cada tela uma vez, logo depois de subir, e a troca de período e a abertura depois de horas sem ninguém olhando continuam indo à fonte.
