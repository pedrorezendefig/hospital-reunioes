-- Migration 062: protocolos de ouvidoria (Dados do Atendimento da Ana)
-- Issue #290, ADR 0031 (decisoes 5 e 7): ouvidoria ponta a ponta na API da Ana.
-- Quem numera e formata o protocolo e o banco (sequence + colunas geradas);
-- a aplicacao cliente nunca compoe o numero. NNNN continuo, nao reinicia por ano.
--
-- Indice, nao dossie: nenhuma coluna de dado pessoal do manifestante existe
-- aqui. Identificacao e manifestacao completa vivem na conversa do Chatwoot
-- da Ana, ligadas pelo conversa_id.
--
-- O import dos protocolos existentes do NocoDB NAO vive nesta migration
-- (dado operacional de ouvidoria nao entra no git): roda na virada via
-- app/scripts/import_ouvidoria_protocolos.py --sql, que insere preservando
-- numero/data e ajusta a sequence para continuar do ultimo numero usado.

CREATE SEQUENCE IF NOT EXISTS ouvidoria_protocolos_numero_seq;

CREATE TABLE IF NOT EXISTS ouvidoria_protocolos (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  numero BIGINT NOT NULL UNIQUE DEFAULT nextval('ouvidoria_protocolos_numero_seq'),
  data_abertura DATE NOT NULL DEFAULT CURRENT_DATE,
  protocolo TEXT UNIQUE GENERATED ALWAYS AS (
    extract(year from data_abertura)::text || '-' || lpad(numero::text, 4, '0')
  ) STORED,
  prazo_resposta DATE GENERATED ALWAYS AS (data_abertura + 7) STORED,
  status TEXT NOT NULL DEFAULT 'aberto' CHECK (status IN ('aberto', 'respondido', 'encerrado')),
  -- Campos criticos: NOT NULL + CHECK anti-vazio. Defesa contra a falha
  -- silenciosa de interpolacao do cliente da Ana (gravaria vazio com HTTP 200):
  -- mesmo contornando a API, o banco recusa.
  categoria TEXT NOT NULL CHECK (btrim(categoria) <> ''),
  setor TEXT NOT NULL CHECK (btrim(setor) <> ''),
  resumo TEXT NOT NULL CHECK (btrim(resumo) <> ''),
  conversa_id TEXT NOT NULL DEFAULT ''
);

ALTER SEQUENCE ouvidoria_protocolos_numero_seq OWNED BY ouvidoria_protocolos.numero;

COMMENT ON TABLE ouvidoria_protocolos IS
  'Indice das manifestacoes de ouvidoria registradas pela Ana (ADR 0031). Indice, nao dossie: sem dado pessoal do manifestante.';
COMMENT ON COLUMN ouvidoria_protocolos.numero IS
  'Base atomica da numeracao (sequence). Nunca e dito a quem manifesta; o numero comunicado e o protocolo.';
COMMENT ON COLUMN ouvidoria_protocolos.protocolo IS
  'ANO-NNNN, formatado pelo banco a partir de data_abertura e numero. Unico numero comunicado externamente.';
COMMENT ON COLUMN ouvidoria_protocolos.prazo_resposta IS
  'data_abertura + 7 dias corridos: aproximacao dos 5 dias uteis prometidos, para o painel enxergar o vencido.';
COMMENT ON COLUMN ouvidoria_protocolos.conversa_id IS
  'Ponte para a conversa no Chatwoot da Ana, onde mora a manifestacao completa. Pode ser vazio (vinculo na direcao inversa).';

-- RLS default-deny (padrao da casa: 009/041/051/057/060/061). Backend usa service_role.
ALTER TABLE ouvidoria_protocolos ENABLE ROW LEVEL SECURITY;
