#!/usr/bin/env bash
# Roteiro dos prints da página de Dados do Atendimento do manual (issue #1726,
# ADR 0094, decisão 5).
#
# Semeia os dados de exemplo no Supabase local e refaz todos os PNGs de
# public/manual/dados-do-atendimento/ com o playwright-cli, contra o app local.
# Quando a tela muda, é este arquivo que roda de novo.
#
# Precisa de:
#   1. Supabase local no ar (supabase start em hospital-reunioes/).
#   2. O app local respondendo em $BASE (padrão http://localhost:3000), com o
#      código que o print vai mostrar.
#   3. hospital-reunioes/.env com SUPABASE_URL local e SUPABASE_SERVICE_ROLE_KEY.
#
# Uso: bash hospital-reunioes/frontend/scripts/manual/dados-do-atendimento/roteiro.sh
#      [--so-semear]
set -euo pipefail

AQUI="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FRONTEND="$(cd "$AQUI/../../.." && pwd)"
SAIDA="$FRONTEND/public/manual/dados-do-atendimento"
ENV_LOCAL="${ENV_LOCAL:-$FRONTEND/../.env}"
BASE="${BASE:-http://localhost:3000}"
BANCO="${BANCO:-supabase_db_hospital-reunioes}"
SESSAO="manual-dados-do-atendimento"

# A pessoa que entra nos prints, secretária (quem edita as tabelas). Senha só
# do banco local.
SENHA="ManualDadosAtendimento2026!"
EMAIL="renata.duarte@exemplo.local"

export PATH="/Applications/Docker.app/Contents/Resources/bin:$PATH"

ler_env() { { grep -E "^$1=" "$ENV_LOCAL" || true; } | head -1 | cut -d= -f2- | tr -d '"'; }

SUPABASE_URL="$(ler_env SUPABASE_URL)"
CHAVE="$(ler_env SUPABASE_SERVICE_ROLE_KEY)"

local_ou_recusa() {
  case "$1" in
    http://127.0.0.1:*|http://localhost:*) ;;
    *) echo "recusado: '$1' não é local. O roteiro só roda contra o app e o banco da máquina." >&2; exit 1 ;;
  esac
}
local_ou_recusa "$SUPABASE_URL"
local_ou_recusa "$BASE"

# 1. O login de exemplo (criar de novo devolve "already registered", e tudo bem).
resposta="$(curl -s -X POST "$SUPABASE_URL/auth/v1/admin/users" \
  -H "apikey: $CHAVE" -H "Authorization: Bearer $CHAVE" -H "Content-Type: application/json" \
  -d "{\"email\":\"$EMAIL\",\"password\":\"$SENHA\",\"email_confirm\":true}")"
case "$resposta" in
  *'"id"'*|*already*) ;;
  *) echo "login $EMAIL: $resposta" >&2; exit 1 ;;
esac

# 2. A pessoa e as linhas de exemplo das três tabelas.
# O SQL mora aqui dentro: o repositório é público e o CI recusa arquivo .sql
# fora das pastas liberadas.
docker exec -i "$BANCO" psql -q -U postgres -v ON_ERROR_STOP=1 <<'SQL'
-- Dados de exemplo da página de Dados do Atendimento do manual (issue #1726,
-- ADR 0094, decisão 5).
--
-- Só para o Supabase local: o roteiro.sh recusa qualquer outro banco. Tudo é
-- fictício (pessoa, e-mail @exemplo.local, especialidades, exames,
-- procedimentos e valores), porque o repositório é público e os prints vão
-- para a página. Nenhum nome repete os preços de verdade que as migrations 061
-- e 062 trazem: o teste da página confere.
--
-- Faixa própria deste módulo: participantes P17260 a P17269. Reusar a faixa
-- de outro roteiro troca as pessoas dele (o e-mail é único e o upsert
-- reescreve a linha).
--
-- Idempotente: rodar de novo devolve cada linha ao valor de exemplo.

begin;

insert into participantes (id, nome_completo, email, cargo, area, setor, ativo, access_profile, auth_user_id)
select p.id, p.nome, p.email, p.cargo, 'Administrativo', 'Recepção', true, 'secretaria',
       (select u.id from auth.users u where u.email = p.email)
from (values
  ('P17260', 'Renata Duarte', 'renata.duarte@exemplo.local', 'Secretária da Diretoria')
) as p(id, nome, email, cargo)
on conflict (id) do update set
  nome_completo = excluded.nome_completo,
  email = excluded.email,
  cargo = excluded.cargo,
  ativo = true,
  access_profile = 'secretaria',
  auth_user_id = excluded.auth_user_id;

insert into consultas_particulares (especialidade, valor_rs, descricao_servico, diferencial_1, diferencial_2, alta_demanda, ativo, ultima_atualizacao)
values
  ('Endocrinologia', 290.00, 'Consulta com endocrinologista para diabetes, tireoide e outros hormônios.', 'Exames de laboratório no mesmo prédio', 'Retorno em até 30 dias sem custo', true, true, '2026-11-10'),
  ('Reumatologia', 310.00, 'Consulta com reumatologista para dores nas articulações e doenças autoimunes.', 'Fisioterapia no mesmo complexo', 'Exames de imagem no mesmo dia', false, true, '2026-11-10'),
  ('Otorrinolaringologia', 300.00, 'Consulta com otorrino para ouvido, nariz e garganta.', 'Exame de audição no consultório', 'Atendimento de adultos e crianças', false, true, '2026-11-10')
on conflict (especialidade) do update set
  valor_rs = excluded.valor_rs,
  descricao_servico = excluded.descricao_servico,
  diferencial_1 = excluded.diferencial_1,
  diferencial_2 = excluded.diferencial_2,
  alta_demanda = excluded.alta_demanda,
  ativo = true,
  ultima_atualizacao = excluded.ultima_atualizacao;

insert into exames (nome_exame, tipo_exame, convenio_aceito, valor_particular_rs, requer_pedido_medico, preparo_necessario, instrucoes_preparo_completas, tempo_resultado, local_realizacao, ativo, ultima_atualizacao)
values
  ('Glicemia de Jejum', 'Laboratorial', true, 25.00, true, true, 'Jejum de 8 horas. Pode beber água.', '1 dia útil', 'Laboratório, térreo', true, '2026-11-10'),
  ('Teste Ergométrico', 'Cardiológico', true, 210.00, true, true, 'Venha com roupa leve e tênis. Não tome café nas 6 horas antes do exame.', '2 dias úteis', 'Setor de cardiologia, 2º andar', true, '2026-11-10'),
  ('Densitometria Óssea', 'Imagem', true, 150.00, true, false, '', '3 dias úteis', 'Setor de imagem, 1º andar', true, '2026-11-10')
on conflict (nome_exame) do update set
  tipo_exame = excluded.tipo_exame,
  convenio_aceito = excluded.convenio_aceito,
  valor_particular_rs = excluded.valor_particular_rs,
  requer_pedido_medico = excluded.requer_pedido_medico,
  preparo_necessario = excluded.preparo_necessario,
  instrucoes_preparo_completas = excluded.instrucoes_preparo_completas,
  tempo_resultado = excluded.tempo_resultado,
  local_realizacao = excluded.local_realizacao,
  ativo = true,
  ultima_atualizacao = excluded.ultima_atualizacao;

insert into cirurgias_estimativas (procedimento, descricao_procedimento, honorarios_equipe_rs, valor_internacao_rs, estimativa_total_rs, o_que_inclui_honorarios, o_que_inclui_internacao, caveat_obrigatorio_ana, ativo, ultima_atualizacao)
values
  ('Correção de Hérnia Umbilical', 'Cirurgia para fechar a hérnia no umbigo.', 2400.00, 3100.00, 5500.00, 'Cirurgião, auxiliar e anestesista', 'Um dia de internação, centro cirúrgico e materiais', 'Valor estimado. O valor final só é confirmado depois da avaliação médica.', true, '2026-11-10'),
  ('Retirada de Amígdalas', 'Cirurgia para retirar as amígdalas.', 2200.00, 2800.00, 5000.00, 'Cirurgião, auxiliar e anestesista', 'Um dia de internação, centro cirúrgico e materiais', 'Valor estimado. O valor final só é confirmado depois da avaliação médica.', true, '2026-11-10'),
  ('Cirurgia de Varizes', 'Cirurgia para retirar as varizes de uma perna.', 2600.00, 3400.00, 6000.00, 'Cirurgião, auxiliar e anestesista', 'Um dia de internação, centro cirúrgico e materiais', 'Valor estimado. O valor final só é confirmado depois da avaliação médica.', true, '2026-11-10')
on conflict (procedimento) do update set
  descricao_procedimento = excluded.descricao_procedimento,
  honorarios_equipe_rs = excluded.honorarios_equipe_rs,
  valor_internacao_rs = excluded.valor_internacao_rs,
  estimativa_total_rs = excluded.estimativa_total_rs,
  o_que_inclui_honorarios = excluded.o_que_inclui_honorarios,
  o_que_inclui_internacao = excluded.o_que_inclui_internacao,
  caveat_obrigatorio_ana = excluded.caveat_obrigatorio_ana,
  ativo = true,
  ultima_atualizacao = excluded.ultima_atualizacao;

commit;
SQL
echo "dados de exemplo da página de Dados do Atendimento prontos."
[ "${1:-}" = "--so-semear" ] && exit 0

# 3. Os prints, todos de uma vez, pela mesma sessão do navegador.
mkdir -p "$SAIDA"
playwright-cli -s="$SESSAO" open "$BASE/login" >/dev/null
trap 'playwright-cli -s="$SESSAO" close >/dev/null 2>&1 || true' EXIT
playwright-cli -s="$SESSAO" resize 1440 900 >/dev/null
CODIGO="$(sed -e "s#__BASE__#$BASE#g" -e "s#__SAIDA__#$SAIDA#g" \
  -e "s#__EMAIL__#$EMAIL#g" -e "s#__SENHA__#$SENHA#g" "$AQUI/prints.js")"
playwright-cli -s="$SESSAO" run-code "$CODIGO"
ls -1 "$SAIDA"/*.png
