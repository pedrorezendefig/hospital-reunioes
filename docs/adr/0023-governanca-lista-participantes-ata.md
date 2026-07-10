---
status: accepted
---

# Governança da lista de participantes da Ata

A lista de participantes exibida na Ata e no PDF vinha de `json_ata.participantes`, output cru da IA, sem filtro nem confirmação, desacoplada do roster oficial (`reuniao_participantes`, que dirige ClickSign e Pendências). A IA inflava a lista incluindo pessoas apenas citadas na transcrição (uma reunião de 6 presentes virava 28), e não havia caminho determinístico para corrigir: pedir a remoção via correção por IA reacionava o `correcao_ata`, que por regra preserva tudo e re-emite a lista inteira, readicionando os citados; o passo de resolução ("ignorar") só mexia no roster, nunca na lista exibida.

Decidimos que **a lista de participantes da Ata é proposta pela IA apenas na extração inicial (a partir da transcrição) e passa a ser governada pelo Facilitador a partir daí**:

- A **correção por IA nunca reescreve `participantes`**. Ela edita narrativa, discussão, quadro e objetivo; a lista de participantes é preservada como está. A correção da lista é sempre determinística (manual).
- O Facilitador **edita a lista diretamente** na validação (`AGUARDANDO_VALIDACAO`): excluir (X por participante) e adicionar (picker do cadastro). A edição é determinística, sem IA.
- Toda edição manual **espelha no roster**: excluir remove de `json_ata.participantes` e de `reuniao_participantes`, mantendo tela, PDF e ClickSign consistentes. Excluir alguém que é responsável de uma ação no Quadro é bloqueado com aviso (preserva o invariante do ADR 0008: responsável escolhível ⊆ roster).
- No passo de resolução, **"ignorar" um não reconhecido também o remove de `json_ata.participantes`**, não só do roster, tornando o passo um filtro real sobre a lista exibida.

Consideramos gatear na origem toda proposta da IA (confirmar cada participante antes de entrar), mas escolhemos o controle manual determinístico: resolve a dor aguda com menos mudança no pipeline e sem fricção de confirmar nome a nome. Um ajuste leve no prompt de extração (remover o incentivo contraditório a "incluir normalmente" e reforçar a regra de não incluir citados) reduz o volume inicial, mas não substitui o controle humano, porque a transcrição não distingue com segurança quem participou de quem foi só mencionado.
