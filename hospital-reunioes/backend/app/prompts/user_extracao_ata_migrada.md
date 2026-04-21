Importação de ATA antiga (migrada do sistema legado).

DATA DA REUNIÃO ORIGINAL: {{data_reuniao}}  (use esta data, NÃO hoje, para calcular prazos relativos)

--- DIRETÓRIO DE PARTICIPANTES ATIVOS NO SISTEMA NOVO ---
Lista de pessoas já cadastradas. Quando um nome da ATA bater com alguém daqui,
use EXATAMENTE o `nome_completo` listado. Se não houver correspondência clara,
retorne o nome como aparece na ATA.
{{participantes_ativos_dir}}
--- FIM DIRETÓRIO ---

--- ESTRUTURA JÁ PARSEADA DO PDF ---
documento_id_origem: {{documento_id_origem}}

metadados_brutos:
{{metadados_brutos_json}}

tabela_participantes (fonte primária de quem esteve presente):
{{tabela_participantes_json}}

tabela_atribuicoes (fonte primária de pendências):
{{tabela_atribuicoes_json}}
--- FIM ESTRUTURA ---

--- TEXTO_COMPLETO DO PDF ---
{{texto_completo}}
--- FIM TEXTO_COMPLETO ---

Retorne SOMENTE o JSON válido com o schema completo especificado no system prompt. Todos os prazos absolutos DEVEM estar em YYYY-MM-DD; prazos ambíguos ficam null com prazo_original preservado.
