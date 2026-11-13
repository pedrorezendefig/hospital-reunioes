/**
 * A orientação embutida da Ouvidoria (issue #1629, PRD #1527, regras T1 e T9
 * da especificação da Diretoria, textos-base da seção 4.14).
 *
 * As frases do topo e os cinco passos moram juntos porque são o mesmo texto
 * contado de dois jeitos: o passo 2 da tela Como funciona é o que a frase de
 * Validar e acionar diz em uma linha. Quem trocar um lê o outro ao lado.
 */

/** A frase do topo de cada tela que a seção 4.14 escreve. */
export const FRASE_DO_TOPO = {
  avaliacoes:
    "Notas deixadas pelo QR. Não geram protocolo, a menos que a pessoa peça retorno ou a Ouvidoria converta.",
  painel: "O que precisa de atenção agora, do mais urgente ao menos urgente.",
  validar: "Confira o tipo, o setor e, se houver alerta, a decisão sobre o NSP. Depois, envie à área.",
  pontos: "Cada ponto é um cartaz. O local descrito aqui é o que aparece no painel.",
  como_funciona: "O caminho de um caso, da chegada ao encerramento, em cinco passos.",
} as const;

export interface PassoDaOuvidoria {
  /** O passo como a seção 4.14 o escreve. */
  titulo: string;
  /** Uma frase: onde isso acontece no app. Curta, para a tela caber no celular. */
  detalhe: string;
}

/** Os cinco passos de um caso, na ordem (seção 4.14, regra T9). */
export const PASSOS_DA_OUVIDORIA: readonly PassoDaOuvidoria[] = [
  {
    titulo: "A manifestação chega",
    detalhe: "Pelo QR, pelo formulário, pela Ana ou pelo seu registro. Ela entra na fila como Nova, com o assunto em uma linha.",
  },
  {
    titulo: "Você confere tipo, setor e gravidade",
    detalhe: "No botão Validar e acionar do caso. A gravidade decide o prazo que a área recebe.",
  },
  {
    titulo: "Se o sistema alertar, decide sobre o NSP",
    detalhe: "Confirme o envio ao Núcleo de Segurança do Paciente ou descarte, com o motivo em uma linha.",
  },
  {
    titulo: "Envia à área e acompanha o prazo",
    detalhe: "A área recebe o e-mail com o prazo. O Painel mostra o que venceu e tem o botão Cobrar.",
  },
  {
    titulo: "Revisa a resposta e envia ao manifestante",
    detalhe: "Leia o que a área respondeu, escreva o desfecho e encerre. Quem deixou e-mail recebe o aviso.",
  },
];
