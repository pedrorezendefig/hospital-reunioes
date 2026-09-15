-- =====================================================
-- Migration 109: canais de origem manuais da Ouvidoria (issue #721, PRD #720)
-- =====================================================
-- O ouvidor atende pacientes no WhatsApp do hospital (hoje no Kommo) e
-- acompanha avaliacao no Google, no Reclame Aqui e no Instagram, mas o CHECK
-- de `canal` so conhecia os tres canais do registro manual antigo (telefone,
-- presencial, email). Ele carimbava tudo como telefone, e o bloco "Canais de
-- entrada" do relatorio mensal mostrava telefone inflado e nenhum WhatsApp.
--
-- Esta migration SO reescreve o CHECK, no mesmo padrao das migrations 066
-- (registro manual) e 067 (canal aberto), que sao as outras duas que mexeram
-- nesta constraint. A lista passa de seis para dez valores.
--
-- NENHUM dado e reescrito, de proposito: canal e fixo depois do nascimento,
-- como o resto da identificacao. O caso carimbado como telefone continua
-- telefone, e o WhatsApp comeca do zero no mes da virada. Caso carimbado
-- errado ganha um movimento com a nota, nunca uma correcao em massa.
--
-- ORDEM DE APLICACAO: depois da 067, que e a dona da lista atual. Aplicar
-- antes dela estreitaria o CHECK de novo. A ordem por numero ja garante isso;
-- aplicar a mao no Studio exige conferir.
--
-- `ana` e `whatsapp` sao canais distintos, e a diferenca e quem atendeu: `ana`
-- e a agente de IA pela API da Ana, `whatsapp` e humano. Nao e integracao
-- automatica: o ouvidor le a conversa ou a avaliacao na plataforma e digita o
-- caso a mao, como faz com o telefonema.
-- =====================================================

ALTER TABLE ouvidoria_protocolos DROP CONSTRAINT IF EXISTS ouvidoria_protocolos_canal_check;
ALTER TABLE ouvidoria_protocolos
  ADD CONSTRAINT ouvidoria_protocolos_canal_check
  CHECK (canal IN (
    'ana', 'telefone', 'presencial', 'email', 'site', 'qr',
    'whatsapp', 'instagram', 'reclame_aqui', 'google'
  ));

COMMENT ON COLUMN ouvidoria_protocolos.canal IS
  'Por onde a manifestacao chegou ao hospital: ana (agente de IA), o canal aberto (site, qr) e os sete do registro manual do ouvidor (whatsapp, telefone, presencial, email, instagram, reclame aqui, google). Fixo depois do nascimento.';
