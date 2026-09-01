-- =====================================================
-- Migration 091: o vencimento conclusivo congelado na validacao
-- (issue #479, PRD #468, diagnostico D-10 e RN-55)
-- =====================================================
-- O caso ja guarda o prazo da AREA responder (`prazo_area_em`, migration 065).
-- O que faltava e o prazo do CASO: a data-limite de dar o desfecho a quem
-- manifestou, que a tabela de prazos chama de marco `conclusiva` e mede de T0
-- (entrada) ate T3 (encerramento).
--
-- A coluna nasce pelo mesmo motivo de `prazo_area_em`: o vencimento e
-- CONGELADO no despacho. Editar a tabela de prazos depois vale para validacao
-- nova e nao move caso ja despachado (RN-21). Derivar o numero na hora de ler
-- faria a Diretoria mudar o passado sem querer.
--
-- NULL e o normal em duas situacoes, e as duas sao legitimas:
--   1. caso ainda nao validado, que e onde todo caso comeca;
--   2. gravidade sem celula conclusiva na tabela (o critico, cujo valor e nulo
--      de proposito na migration 065). Ali o sistema nao inventa data.
-- Sem backfill, portanto: os casos ja despachados foram acionados sem esse
-- prazo, e carimbar um agora seria inventar um compromisso que ninguem assumiu
-- e que a tabela de prazos de hoje nao regia naquele dia.
--
-- Nenhuma tabela nova nasce aqui: nada de RLS a ligar, e as policies de
-- ouvidoria_protocolos seguem valendo para a linha inteira, coluna nova
-- inclusa.
-- =====================================================

ALTER TABLE ouvidoria_protocolos
  ADD COLUMN IF NOT EXISTS prazo_conclusivo_em TIMESTAMPTZ;

COMMENT ON COLUMN ouvidoria_protocolos.prazo_conclusivo_em IS
  'Vencimento do prazo CONCLUSIVO do caso (marco conclusiva da tabela ouvidoria_prazos, contado de T0), calculado e CONGELADO na validacao, como prazo_area_em (issue #479, RN-55). NULL quando o caso ainda nao foi validado ou quando a gravidade nao tem celula conclusiva na tabela (critico).';
