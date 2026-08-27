-- =====================================================
-- Migration 081: nota externa manual do hospital (issue #347, PRD #319)
-- =====================================================
-- A nota que o hospital tem FORA dele: as estrelas do Google e o indice do
-- Reclame Aqui. Nenhum dos dois e medido pelo sistema, e nao da para calcula-lo
-- aqui: quem sabe e o ouvidor, que abre as duas paginas e digita o que leu. A
-- integracao automatica com o Google Business Profile e com o Reclame Aqui e
-- fase seguinte da spec (PRD #319, fora de escopo), e ate la esta tabela e a
-- unica porta desse numero.
--
-- **Cada registro e uma linha nova, nunca um UPDATE.** A tabela e um diario, e
-- a leitura devolve a ultima linha de cada fonte. Sobrescrever seria mais curto
-- e apagaria a serie: a evolucao da satisfacao e historia 8 do PRD, e ela so
-- existe se as notas antigas continuarem no banco. Guardar tambem e o que
-- permite ao relatorio de julho, reenviado em setembro, mostrar a nota de
-- julho: o relatorio congela a leitura dentro de `ouvidoria_relatorios.dados`,
-- e esta tabela e a fonte daquele instante.
--
-- **As duas escalas sao diferentes**, e essa e a armadilha da fatia. O Google
-- vai de 0 a 5, o Reclame Aqui de 0 a 10. Um relatorio que imprime "4,3" e
-- "7,8" lado a lado faz o leitor concluir que o hospital vai melhor no Reclame
-- Aqui, quando 4,3 de 5 e 86% e 7,8 de 10 e 78%. A escala mora no codigo
-- (`app/services/ouvidoria_nota_externa.py`), junto da apresentacao que a usa;
-- aqui o CHECK garante que nenhuma linha entra fora da regua da sua fonte,
-- inclusive por caminho que nao passe pela API.
--
-- Nada aqui identifica manifestacao: a nota e o agregado publico do hospital
-- inteiro. O unico nome proprio e o de quem digitou.
-- =====================================================

CREATE TABLE IF NOT EXISTS ouvidoria_nota_externa (
  id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),

  fonte                 TEXT NOT NULL CHECK (fonte IN ('google', 'reclame_aqui')),

  nota                  NUMERIC(4,2) NOT NULL,

  -- A regua de cada fonte, no banco e nao so na API. Sem ele, um script ou uma
  -- correcao manual no Studio grava "Google 8" e o PDF imprime "8,0 de 5".
  CONSTRAINT ouvidoria_nota_externa_escala_check CHECK (
    (fonte = 'google' AND nota >= 0 AND nota <= 5)
    OR (fonte = 'reclame_aqui' AND nota >= 0 AND nota <= 10)
  ),

  -- O instante do registro, no relogio da aplicacao. E por ele que a leitura
  -- escolhe a linha que vale, e e ele que data o retrato no relatorio.
  registrada_em         TIMESTAMPTZ NOT NULL,

  -- Quem digitou. O nome viaja junto porque a leitura do relatorio nao faz
  -- join: o PDF sai do participante, e o participante pode ser desligado.
  registrada_por        UUID REFERENCES participantes(id) ON DELETE SET NULL,
  registrada_por_nome   TEXT NOT NULL DEFAULT '',

  criada_em             TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- A leitura de todo dia: a ultima linha de UMA fonte.
CREATE INDEX IF NOT EXISTS idx_ouvidoria_nota_externa_fonte
  ON ouvidoria_nota_externa(fonte, registrada_em DESC);

COMMENT ON TABLE ouvidoria_nota_externa IS
  'Diario da nota do hospital no Google e no Reclame Aqui, digitada pelo ouvidor. Uma linha por registro: a leitura pega a mais recente de cada fonte (issue #347).';
COMMENT ON COLUMN ouvidoria_nota_externa.fonte IS
  'google (escala 0 a 5) ou reclame_aqui (escala 0 a 10). As duas escalas sao diferentes, e o numero nunca sai sem a sua.';
COMMENT ON COLUMN ouvidoria_nota_externa.registrada_em IS
  'Instante do registro. Ordena a leitura e data o retrato externo no relatorio.';
COMMENT ON COLUMN ouvidoria_nota_externa.registrada_por_nome IS
  'Nome de quem digitou, copiado no ato: o relatorio nao faz join, e o participante pode ser desligado.';

-- RLS default-deny (padrao da casa: 009/041/051/063/064/068/069/073/080).
-- Backend usa service_role; a anon_key do bundle do frontend fica de fora.
ALTER TABLE ouvidoria_nota_externa ENABLE ROW LEVEL SECURITY;
