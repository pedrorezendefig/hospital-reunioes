-- =====================================================
-- Migration 090: a natureza que o manifestante informa no formulario publico
-- (issue #473, PRD #467, ADR 0040 decisao 3)
-- =====================================================
-- O cartaz do ponto de escuta promete quatro naturezas a quem le o QR (RN-88):
-- elogio, reclamacao, sugestao e informacao. O formulario passa a oferecer as
-- quatro, e a coluna abaixo guarda o que a pessoa marcou.
--
-- E SUGESTAO DE QUEM MANIFESTOU, nao classificacao. Quem classifica e o
-- ouvidor, e o campo dele e `tipo_manifestacao` (migration 077), que e o unico
-- que decide sigilo. O que a pessoa diz que o caso e nao e o que o caso e: por
-- isso sao duas colunas, e nao uma so. O caso vindo do canal aberto continua
-- nascendo SEM TIPO e fail-closed (ADR 0037, decisao 3), com natureza ou sem.
--
-- NULL e o normal: a escolha e opcional (ninguem precisa se classificar para
-- falar), e nenhum dos casos ja gravados escolheu nada. Sem backfill, portanto:
-- carimbar natureza em caso antigo seria inventar a palavra de quem manifestou.
--
-- O CHECK repete a lista que a aplicacao ja valida (`NATUREZAS_INFORMADAS` em
-- ouvidoria_taxonomia.py): a aplicacao recusa antes, o banco recusa depois, e
-- nenhuma das duas confia na outra. Os tipos do ouvidor (`denuncia`,
-- `relato_de_conduta`) NAO entram nesta lista: eles nao estao no papel, e
-- aceita-los aqui seria abrir a porta do banco para a sugestao do manifestante
-- parecer decisao de classificacao.
--
-- Nenhuma tabela nova nasce aqui: nada de RLS a ligar, e as policies de
-- ouvidoria_protocolos seguem valendo para a linha inteira, coluna nova
-- inclusa.
-- =====================================================

ALTER TABLE ouvidoria_protocolos
  ADD COLUMN IF NOT EXISTS natureza_informada TEXT;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'ouvidoria_protocolos_natureza_informada_check'
  ) THEN
    ALTER TABLE ouvidoria_protocolos
      ADD CONSTRAINT ouvidoria_protocolos_natureza_informada_check
      CHECK (natureza_informada IS NULL OR natureza_informada IN (
        'elogio', 'reclamacao', 'sugestao', 'informacao'
      ));
  END IF;
END $$;

COMMENT ON COLUMN ouvidoria_protocolos.natureza_informada IS
  'A natureza que o MANIFESTANTE marcou no formulario publico (issue #473, RN-88): elogio, reclamacao, sugestao ou informacao. E sugestao dele, nunca classificacao: nao decide tipo, estado nem sigilo, e o caso segue nascendo sem tipo e fail-closed. Quem classifica e o ouvidor, na coluna tipo_manifestacao. NULL significa que a pessoa nao quis escolher, o que e opcional de proposito.';
