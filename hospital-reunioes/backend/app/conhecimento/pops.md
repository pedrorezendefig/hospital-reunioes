# POPs

POP é o Procedimento Operacional Padrão: o documento que diz como um procedimento do hospital deve ser feito, sempre do mesmo jeito. O módulo de POPs cuida do caminho do documento: escrever, revisar, validar, assinar e publicar. O treinamento da equipe nos POPs publicados é a leva seguinte, e ainda não está no aplicativo.

Ele mora no mesmo aplicativo das Reuniões, mas com gente própria: quem tem acesso aqui não enxerga reunião, ata nem pendência, e quem cuida das Reuniões não enxerga POP. Uma pessoa pode ter os dois acessos, e aí ela vê os dois.

## Quem participa

Por acesso: a diretoria executiva e o gestor de qualidade enxergam todos os setores; o gerente enxerga os setores que ele gerencia; o coordenador enxerga o setor dele. Os colaboradores que executam o procedimento (técnicos, enfermeiros, ASG) não entram no aplicativo: eles leem o POP publicado e são treinados fora dele.

Por POP, três pessoas são escolhidas na criação: quem elabora, quem revisa e quem valida. Elas não são o mesmo que o acesso: são designações daquele documento.

## Como um POP nasce

Quem elabora sobe o material de referência que já existe (POP antigo, norma, resolução, artigo) e conversa com um agente de inteligência artificial, que lê esse material e escreve o procedimento a partir dele. Quando o material traz um modelo de POP do hospital, o agente segue a estrutura desse modelo, em vez de encaixar tudo num formulário fixo. A única seção que sempre existe, mesmo quando o modelo não a traz, é o fluxograma, que o aplicativo desenha.

Cada POP recebe um código travado, montado com a sigla do setor e um número em sequência. Ninguém edita esse código.

## O caminho até publicar

O conteúdo de um POP vive em versões, e cada versão percorre o mesmo caminho: a elaborar, em elaboração, em revisão, em validação, em assinatura e publicado.

Quem revisa ou quem valida pode devolver, com comentários, para quem elaborou. A devolução volta direto para quem devolveu, sem repassar por quem já tinha aprovado, e não existe limite de idas e vindas.

Publicar exige assinatura digital das três pessoas do fluxo. O POP publicado entra na **Biblioteca**, organizado por setor, com o documento assinado para baixar e as datas de cada etapa do caminho que ele percorreu.

## O que ainda não está no aplicativo

Três coisas já foram decididas e ainda não foram construídas. Quem procurar por elas hoje não vai achar tela nenhuma:

- **A revisão periódica correndo sozinha.** Cada POP já escolhe, na criação, de quanto em quanto tempo deve ser revisto (três meses, seis meses, um ano ou dois anos), e o agente sugere esse prazo. O que não existe ainda é o aplicativo contar esse prazo, avisar quem precisa e reabrir o caminho sozinho. Hoje quem controla isso é o setor, fora do aplicativo.
- **O sinal de validade na Biblioteca**, que mostraria qual POP está em dia, qual está perto de vencer e qual está com a revisão atrasada.
- **Os treinamentos.** A tela existe com o aviso de que vêm depois. A lista de presença gerada pelo aplicativo, a leitura das notas da folha assinada e os indicadores por turma são parte dessa leva, e nada disso funciona hoje.

## O que ele não faz

- Não publica POP sem as três assinaturas.
- Não deixa ninguém editar o código do POP: ele nasce na criação e é travado.
- Não decide sozinho a estrutura do procedimento: ele segue o modelo que foi anexado.

## O que costuma virar Demanda

- POP saindo com estrutura diferente do modelo anexado (Defeito).
- Setor novo, ou sigla errada no código de um setor (Ajuste).
- Mudança em quem assina, ou nos prazos de revisão oferecidos (Decisão).
- Treinamento, sinal de validade e relatório, que ainda não existem (Novo).
