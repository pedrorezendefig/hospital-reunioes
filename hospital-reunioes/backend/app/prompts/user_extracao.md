Tipo de reunião: {{tipo_reuniao}}
ID da reunião: {{reuniao_id}}
Objetivo registrado no agendamento (se houver): {{objetivo_agendado}}
DATA DE HOJE: {{hoje_str}} ({{dia_semana_pt}}) | ISO: {{hoje_iso}}
ATENÇÃO: Use a DATA DE HOJE acima como base para converter todos os prazos relativos da transcrição em datas YYYY-MM-DD. Se o `objetivo` do agendamento estiver preenchido, use-o como ponto de partida e refine com o que foi efetivamente discutido — respeitando o limite de 5 linhas.

--- PARTICIPANTES PRÉ-CADASTRADOS ---
Os seguintes participantes foram previamente vinculados a esta reunião pelo facilitador.
Use estes nomes como referência principal ao identificar participantes na transcrição.
Esta lista pode ser incompleta: inclua também em "participantes" quem participou da reunião mas não está pré-cadastrado. Não inclua quem foi apenas citado ou mencionado na conversa sem ter participado.
{{participantes_pre_cadastrados}}
--- FIM PARTICIPANTES PRÉ-CADASTRADOS ---

--- DIRETÓRIO DE PARTICIPANTES ATIVOS ---
Lista completa de pessoas já cadastradas no sistema. Quando a transcrição
mencionar APENAS o primeiro nome de alguém (ex: "Caroline", "Fernando"),
verifique se esse primeiro nome + o cargo/setor/área mencionados na fala
coincidem INEQUIVOCAMENTE com alguém deste diretório.
- Se houver apenas UMA pessoa compatível: retorne no campo "nome" o
  `nome_completo` EXATAMENTE como aparece aqui.
- Se houver ambiguidade (múltiplas pessoas com o mesmo primeiro nome e
  nenhum outro sinal claro), retorne apenas o primeiro nome que ouviu na
  transcrição (sem inventar sobrenome).
- Se a pessoa NÃO aparece no diretório, retorne o nome como falado.
{{participantes_ativos_dir}}
--- FIM DIRETÓRIO DE PARTICIPANTES ATIVOS ---

--- TRANSCRIÇÃO ---
{{transcricao_txt}}
--- FIM DA TRANSCRIÇÃO ---

Extraia as informações e retorne SOMENTE o JSON válido. Todos os prazos DEVEM ser datas absolutas no formato YYYY-MM-DD.
