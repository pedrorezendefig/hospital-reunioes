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
