'use strict';

/* Conteúdo da aba "Começar aqui" (Setup).
   Adaptação interativa de docs/onboarding/claude-setup.md (§1-6).
   Se aquele doc mudar, reflita aqui. NUNCA coloque tokens/segredos reais —
   só placeholders ("peça ao Pedro"). Este arquivo vai pro git e é clonado por todo o time. */

export const OSES = ['mac', 'windows', 'linux'];
export const OS_LABEL = { mac: 'macOS', windows: 'Windows', linux: 'Linux' };

/* Cada passo: { n, title, intro?, tip?, blocks:[ {all|os, label?, note?, lang?, tip?} ] }
   - block.all  → mesmo comando nos 3 SOs
   - block.os   → { mac, windows, linux } (o renderer escolhe o do SO ativo) */
export const SETUP = [
  {
    n: '01', title: 'Instalar os pré-requisitos', tip: 'package-manager',
    intro: 'As ferramentas que o fluxo usa. Instale tudo de uma vez pelo gerenciador de pacotes do seu sistema.',
    blocks: [
      { label: 'ferramentas de base', os: {
          mac: 'brew install gh jq node@20 python@3.12',
          windows: 'winget install GitHub.cli jqlang.jq OpenJS.NodeJS Python.Python.3.12',
          linux: 'sudo apt update && sudo apt install -y gh jq nodejs npm python3',
        } },
      { label: 'Claude Code (o agente em si)', all: 'npm install -g @anthropic-ai/claude-code' },
      { label: 'Docker Desktop', note: 'Abra o app uma vez depois de instalar — backend e frontend rodam em docker para o dev local.', os: {
          mac: 'open https://www.docker.com/products/docker-desktop/',
          windows: 'start https://www.docker.com/products/docker-desktop/',
          linux: '# Docker Engine: https://docs.docker.com/engine/install/',
        } },
      { label: 'conferir que tudo instalou', all: 'claude --version\ngh --version\njq --version\npython3 --version\nnode --version\ndocker --version' },
    ],
  },
  {
    n: '02', title: 'Clonar o repositório', tip: 'collaborator',
    intro: 'Baixa o projeto para a sua máquina. Você precisa ter sido adicionado como colaborador — peça ao Pedro antes.',
    blocks: [
      { os: {
          mac: 'gh repo clone pedrorezendefig/hospital-reunioes\ncd hospital-reunioes',
          windows: 'gh repo clone pedrorezendefig/hospital-reunioes\ncd hospital-reunioes',
          linux: 'gh repo clone pedrorezendefig/hospital-reunioes\ncd hospital-reunioes',
        } },
      { label: 'conferir seu acesso', note: 'Esperado: WRITE ou ADMIN. Se vier outra coisa, peça acesso ao Pedro.',
        all: 'gh repo view --json viewerPermission --jq .viewerPermission' },
    ],
  },
  {
    n: '03', title: 'Autenticar no GitHub', tip: 'gh',
    intro: 'O fluxo lê issues, abre PRs e faz review pelo gh. Faça o login uma vez.',
    blocks: [
      { label: 'login (abre o navegador)', note: 'Escolha: GitHub.com → HTTPS → "Login with a web browser".',
        all: 'gh auth login' },
      { label: 'sua identidade nos commits', all: 'git config --global user.name "Seu Nome"\ngit config --global user.email "seu@email"' },
    ],
  },
  {
    n: '04', title: 'Rodar este painel',
    intro: 'O painel que você está vendo agora roda local e só lê dados — nunca escreve nada. Ele abre sozinho no navegador.',
    blocks: [
      { os: {
          mac: 'python3 tools/workflow-dashboard/serve.py',
          windows: 'python tools\\workflow-dashboard\\serve.py',
          linux: 'python3 tools/workflow-dashboard/serve.py',
        }, note: 'Abre em http://localhost:8765. Para parar, use Ctrl+C no terminal.' },
    ],
  },
  {
    n: '05', title: 'Instalar os plugins do Claude Code', tip: 'plugin',
    intro: 'As skills do time (/pegar-issue, /tdd, /ship…) já vêm no clone. Faltam os 5 plugins. Abra uma sessão (digite claude no terminal) e cole linha por linha.',
    blocks: [
      { lang: 'text', label: 'dentro de uma sessão claude',
        all: '/plugin install code-review@claude-plugins-official\n/plugin install security-guidance@claude-plugins-official\n/plugin install github@claude-plugins-official\n/plugin install context7@claude-plugins-official\n/plugin install skill-creator@claude-plugins-official' },
      { label: 'conferir os 5 plugins', all: "jq -r '.enabledPlugins | keys[]' ~/.claude/settings.json" },
    ],
  },
  {
    n: '06', title: 'Conectar o Coolify (deploy)', tip: 'MCP',
    intro: 'Sem isto, o /deploy não funciona. O Coolify é onde a app roda em produção. Peça o token ao Pedro — ele envia no seu setup individual.',
    blocks: [
      { label: 'exportar o token (cole o que o Pedro te passar)', note: 'O token tem o formato 1|abc… NUNCA comite ele em lugar nenhum.', os: {
          mac: 'echo \'export COOLIFY_ACCESS_TOKEN="1|peça-o-token-ao-Pedro"\' >> ~/.zprofile\necho \'export COOLIFY_BASE_URL="https://coolify.mala-ia.cloud"\' >> ~/.zprofile\nsource ~/.zprofile',
          windows: 'setx COOLIFY_ACCESS_TOKEN "1|peça-o-token-ao-Pedro"\nsetx COOLIFY_BASE_URL "https://coolify.mala-ia.cloud"',
          linux: 'echo \'export COOLIFY_ACCESS_TOKEN="1|peça-o-token-ao-Pedro"\' >> ~/.bashrc\necho \'export COOLIFY_BASE_URL="https://coolify.mala-ia.cloud"\' >> ~/.bashrc\nsource ~/.bashrc',
        } },
      { lang: 'json', label: 'registrar o MCP em ~/.claude.json (mescle se já existir)',
        note: 'No Windows o arquivo fica em %USERPROFILE%\\.claude.json. As variáveis ${...} puxam o token que você exportou acima — não escreva o token aqui.',
        all: '{\n  "mcpServers": {\n    "coolify": {\n      "type": "stdio",\n      "command": "npx",\n      "args": ["-y", "@masonator/coolify-mcp"],\n      "env": {\n        "COOLIFY_ACCESS_TOKEN": "${COOLIFY_ACCESS_TOKEN}",\n        "COOLIFY_BASE_URL": "${COOLIFY_BASE_URL}"\n      }\n    }\n  }\n}' },
    ],
  },
  {
    n: '07', title: 'Reduzir os pedidos de confirmação', tip: 'plugin',
    intro: 'Opcional, mas recomendado. Deixa o Claude rodar comandos de baixo risco sem perguntar a cada vez. Cole no ~/.claude/settings.json.',
    blocks: [
      { lang: 'json', label: '~/.claude/settings.json (troque <seu-user> pelo seu usuário — rode whoami)',
        note: 'defaultMode "auto" pausa só em ações destrutivas. language "pt-BR" faz o Claude responder em português.',
        all: '{\n  "permissions": {\n    "defaultMode": "auto",\n    "allow": [\n      "Bash(git:*)", "Bash(gh:*)", "Bash(jq:*)",\n      "Bash(python3:*)", "Bash(pnpm:*)", "Bash(npm:*)", "Bash(npx:*)",\n      "Bash(docker:*)", "Bash(docker-compose:*)",\n      "Bash(curl -sf http://localhost:*)",\n      "Read(/Users/<seu-user>/PedroDev/Hospital/**)",\n      "Edit(/Users/<seu-user>/PedroDev/Hospital/**)",\n      "Write(/Users/<seu-user>/PedroDev/Hospital/**)"\n    ]\n  },\n  "language": "pt-BR"\n}' },
    ],
  },
  {
    n: '08', title: 'Conferir que está tudo de pé',
    intro: 'Abra uma sessão Claude Code nova dentro do repo (cd hospital-reunioes && claude) e rode um por um.',
    blocks: [
      { lang: 'text', label: 'fila de issues', note: 'Esperado: a lista de issues prontas para pegar (pode estar vazia).', all: '/pegar-issue' },
      { lang: 'text', label: 'estado da produção', note: 'Esperado: containers + status + última implantação. Falhou? Revise o passo 06.', all: '/deploy status' },
      { lang: 'text', label: 'subir a app local', note: 'Esperado: backend em :8000 e frontend em :3000. Não toca produção.', all: '/atualizar-app' },
    ],
  },
];
