-- Migration para adicionar o status REPACTUADA no check constraint da tabela pendencias
ALTER TABLE pendencias DROP CONSTRAINT pendencias_status_check;
ALTER TABLE pendencias ADD CONSTRAINT pendencias_status_check CHECK (status IN (
    'PENDENTE', 'EM_PROGRESSO', 'CONCLUIDO', 'ATRASADO', 'CANCELADO', 'REPACTUADA'
));
