#!/usr/bin/env bash
# Roteiro dos prints da página de POPs do manual (issue #1722, ADR 0094, decisão 5).
#
# Semeia os dados de exemplo no Supabase local e refaz todos os PNGs de
# public/manual/pops/ com o playwright-cli, contra o app local. Quando a tela
# muda, é este arquivo que roda de novo.
#
# Precisa de:
#   1. Supabase local no ar (supabase start em hospital-reunioes/).
#   2. O app local respondendo em $BASE (padrão http://localhost:3000), com o
#      código que o print vai mostrar.
#   3. hospital-reunioes/.env com SUPABASE_URL local e SUPABASE_SERVICE_ROLE_KEY.
#
# Uso: bash hospital-reunioes/frontend/scripts/manual/pops/roteiro.sh
#      [--so-semear]
set -euo pipefail

AQUI="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FRONTEND="$(cd "$AQUI/../../.." && pwd)"
SAIDA="$FRONTEND/public/manual/pops"
ENV_LOCAL="${ENV_LOCAL:-$FRONTEND/../.env}"
BASE="${BASE:-http://localhost:3000}"
BANCO="${BANCO:-supabase_db_hospital-reunioes}"
SESSAO="manual-pops"

# A pessoa que entra nos prints e as outras duas do fluxo. Senha só do banco local.
SENHA="ManualPops2026!"
EMAILS=(carla.mendes@exemplo.local fabio.rangel@exemplo.local lucia.moraes@exemplo.local)

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

# 1. Os logins de exemplo (criar de novo devolve "already registered", e tudo bem).
for email in "${EMAILS[@]}"; do
  resposta="$(curl -s -X POST "$SUPABASE_URL/auth/v1/admin/users" \
    -H "apikey: $CHAVE" -H "Authorization: Bearer $CHAVE" -H "Content-Type: application/json" \
    -d "{\"email\":\"$email\",\"password\":\"$SENHA\",\"email_confirm\":true}")"
  case "$resposta" in
    *'"id"'*|*already*) ;;
    *) echo "login $email: $resposta" >&2; exit 1 ;;
  esac
done

# 2. Pessoas, setores e um POP em cada etapa do caminho.
# O SQL mora aqui dentro: o repositório é público e o CI recusa arquivo .sql
# fora das pastas liberadas.
docker exec -i "$BANCO" psql -q -U postgres -v ON_ERROR_STOP=1 <<'SQL'
-- Dados de exemplo da página de POPs do manual (issue #1722, ADR 0094, decisão 5).
--
-- Só para o Supabase local: o roteiro.sh recusa qualquer outro banco. Tudo é
-- fictício (nomes, e-mails @exemplo.local, setores e POPs), porque o
-- repositório é público e os prints vão para a página.
--
-- Faixa própria deste módulo: participantes P995 a P999, setores PA e LAB.
-- Outros roteiros usam P900 a P980; reusar a faixa de outro troca as pessoas
-- dele (o e-mail é único e o upsert reescreve a linha).
--
-- Idempotente: rodar de novo devolve cada POP ao estado de exemplo.

begin;

insert into participantes (id, nome_completo, email, cargo, area, setor, role, ativo, access_profile, perfil_pop, auth_user_id)
select p.id, p.nome, p.email, p.cargo, 'Assistencial', 'Qualidade', 'coordenador', true, null, p.perfil,
       (select u.id from auth.users u where u.email = p.email)
from (values
  ('P995', 'Carla Mendes',  'carla.mendes@exemplo.local',  'Gerente de Enfermagem',        'gerente'),
  ('P996', 'Fábio Rangel',  'fabio.rangel@exemplo.local',  'Coordenador do Laboratório',   'coordenador'),
  ('P997', 'Lúcia Moraes',  'lucia.moraes@exemplo.local',  'Coordenadora do Pronto Atendimento', 'coordenador')
) as p(id, nome, email, cargo, perfil)
on conflict (id) do update set
  nome_completo = excluded.nome_completo,
  email = excluded.email,
  cargo = excluded.cargo,
  ativo = true,
  access_profile = null,
  perfil_pop = excluded.perfil_pop,
  auth_user_id = excluded.auth_user_id;

insert into pops_setores (nome, sigla) values
  ('Pronto Atendimento', 'PA'),
  ('Laboratório', 'LAB')
on conflict do nothing;

-- Cada pessoa de exemplo vê só os dois setores daqui: a lista dos prints não
-- mistura os POPs de exemplo de outros roteiros.
delete from pops_setores_participantes where participante_id in ('P995', 'P996', 'P997');
insert into pops_setores_participantes (setor_id, participante_id)
select s.id, p.id
from pops_setores s cross join (values ('P995'), ('P996'), ('P997')) as p(id)
where s.sigla in ('PA', 'LAB');

-- Os POPs, um em cada etapa do caminho: (código, número, setor, nome,
-- criticidade, estado, quem elabora, quem revisa, quem valida). A Carla, que
-- entra nos prints, elabora um, revisa outro e valida um terceiro.
create temporary table exemplo_pops (codigo text, numero int, sigla text, nome text, criticidade text, estado text, elab text, rev text, val text) on commit drop;
insert into exemplo_pops values
  ('HSM_LAB-001', 1, 'LAB', 'POP Coleta de Sangue Venoso',  'ALTA',    'PUBLICADO',     'P996', 'P997', 'P995'),
  ('HSM_LAB-002', 2, 'LAB', 'POP Transporte de Amostras',   'MEDIA',   'EM_ASSINATURA', 'P996', 'P995', 'P997'),
  ('HSM_PA-001',  1, 'PA',  'POP Classificação de Risco',   'CRITICA', 'EM_REVISAO',    'P997', 'P995', 'P996'),
  ('HSM_PA-002',  2, 'PA',  'POP Acolhimento do Paciente',  'ALTA',    'EM_VALIDACAO',  'P997', 'P996', 'P995'),
  ('HSM_PA-003',  3, 'PA',  'POP Troca de Curativo',        'MEDIA',   'EM_ELABORACAO', 'P995', 'P996', 'P997');

insert into pops (setor_id, numero, codigo, nome, criticidade, periodicidade_revisao, base_normativa, elaborador_id, revisor_id, validador_id, criado_por)
select s.id, e.numero, e.codigo, e.nome, e.criticidade,
       case when e.criticidade = 'CRITICA' then '6_meses' else '1_ano' end,
       'RDC 63/2011; Manual ONA', e.elab, e.rev, e.val, 'P995'
from exemplo_pops e join pops_setores s on s.sigla = e.sigla
on conflict (codigo) do update set
  nome = excluded.nome,
  criticidade = excluded.criticidade,
  periodicidade_revisao = excluded.periodicidade_revisao,
  elaborador_id = excluded.elaborador_id,
  revisor_id = excluded.revisor_id,
  validador_id = excluded.validador_id;

-- Uma versão por POP, recriada a cada rodada (a devolução e o material
-- anexado vão junto, pelo cascade).
delete from pops_versoes where pop_id in (select id from pops where codigo in (select codigo from exemplo_pops));

insert into pops_versoes (pop_id, numero_versao, estado, rascunho, data_publicacao)
select p.id, '1.0', e.estado,
  case
    when e.estado = 'EM_ELABORACAO' then jsonb_build_object('secoes', jsonb_build_array(
      jsonb_build_object('id', 'a1', 'tipo', 'texto', 'titulo', 'Objetivo',
        'conteudo', 'Padronizar a troca de curativo no Pronto Atendimento, reduzindo o risco de infecção da ferida.'),
      jsonb_build_object('id', 'a2', 'tipo', 'texto', 'titulo', 'Aplicação',
        'conteudo', 'Equipe de enfermagem do Pronto Atendimento, em todos os turnos.')
    ))
    else jsonb_build_object('secoes', jsonb_build_array(
      jsonb_build_object('id', 's1', 'tipo', 'texto', 'titulo', 'Objetivo',
        'conteudo', 'Padronizar o procedimento em todos os turnos, com o mesmo passo a passo para toda a equipe.'),
      jsonb_build_object('id', 's2', 'tipo', 'texto', 'titulo', 'Aplicação',
        'conteudo', 'Equipe assistencial do setor, em todos os turnos.'),
      jsonb_build_object('id', 's3', 'tipo', 'texto', 'titulo', 'Materiais necessários',
        'conteudo', E'- Luvas de procedimento\n- Etiquetas de identificação\n- Formulário do setor'),
      jsonb_build_object('id', 's4', 'tipo', 'texto', 'titulo', 'Descrição do procedimento',
        'conteudo', E'1. Higienize as mãos e reúna o material.\n2. Confira a identificação do paciente com a pulseira.\n3. Execute o procedimento conforme a técnica do setor.\n4. Registre o que foi feito no prontuário.'),
      jsonb_build_object('id', 's5', 'tipo', 'fluxograma', 'titulo', 'Fluxograma',
        'conteudo', jsonb_build_object('nos', jsonb_build_array(
          jsonb_build_object('id', 'n1', 'tipo', 'passo', 'texto', 'Higienizar as mãos e reunir o material'),
          jsonb_build_object('id', 'n2', 'tipo', 'decisao', 'texto', 'A identificação confere com a pulseira?',
            'ramos', jsonb_build_array(
              jsonb_build_object('rotulo', 'Sim', 'vai_para', 'n3'),
              jsonb_build_object('rotulo', 'Não', 'desvio', jsonb_build_object('texto', 'Parar e chamar o enfermeiro responsável', 'retorna_para', 'n1'))
            )),
          jsonb_build_object('id', 'n3', 'tipo', 'passo', 'texto', 'Executar o procedimento'),
          jsonb_build_object('id', 'n4', 'tipo', 'passo', 'texto', 'Registrar no prontuário')
        ))),
      jsonb_build_object('id', 's6', 'tipo', 'texto', 'titulo', 'Referências',
        'conteudo', 'ANVISA. Segurança do paciente em serviços de saúde.')
    ))
  end,
  case when e.estado = 'PUBLICADO' then timestamptz '2026-10-05 14:10:00-03' end
from exemplo_pops e join pops p on p.codigo = e.codigo;

commit;
SQL
echo "dados de exemplo da página de POPs prontos."
[ "${1:-}" = "--so-semear" ] && exit 0

# 3. Os prints, todos de uma vez, pela mesma sessão do navegador.
mkdir -p "$SAIDA"
playwright-cli -s="$SESSAO" open "$BASE/login" >/dev/null
trap 'playwright-cli -s="$SESSAO" close >/dev/null 2>&1 || true' EXIT
playwright-cli -s="$SESSAO" resize 1440 900 >/dev/null
CODIGO="$(sed -e "s#__BASE__#$BASE#g" -e "s#__SAIDA__#$SAIDA#g" \
  -e "s#__EMAIL__#${EMAILS[0]}#g" -e "s#__SENHA__#$SENHA#g" "$AQUI/prints.js")"
playwright-cli -s="$SESSAO" run-code "$CODIGO"
ls -1 "$SAIDA"/*.png
