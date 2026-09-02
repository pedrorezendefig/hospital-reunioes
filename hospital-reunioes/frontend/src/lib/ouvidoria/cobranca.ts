/**
 * A cobrança do setor pela fila (issue #495, PRD #471).
 *
 * Cobrar não é um email novo: é o reenvio do acionamento, com a regra vigente
 * de reenvio (ADR 0034, decisão 7), que nasce como registro próprio e deixa
 * intacta a data do primeiro envio. Elevar a cobrança a botão de primeira
 * classe é dar ao ouvidor, na linha da fila, o que antes exigia abrir o caso e
 * caçar o registro certo na lista de notificações.
 *
 * Este módulo é puro: escolhe QUAL registro reenviar. Quem chama a rota é a
 * tela.
 */

/** O gatilho do email que acorda o setor (`ouvidoria_notificacoes`). */
export const GATILHO_DO_ACIONAMENTO = "nova_demanda";

export interface NotificacaoDoCaso {
  id: string;
  gatilho: string;
  criada_em: string;
  destinatario_nome: string;
  destinatario_email: string;
}

/**
 * O acionamento que a cobrança reenvia: o mais recente do caso.
 *
 * "Mais recente" é lido do carimbo, e não da posição na lista: a rota devolve
 * em ordem decrescente hoje, e uma linha a mais no `order` do servidor
 * mandaria a cobrança para o acionamento de um mês atrás sem nada quebrar.
 * Caso reaberto por reincidência é acionado de novo, e é do último que a área
 * está sendo cobrada.
 *
 * Sem acionamento registrado devolve nulo: setor sem responsável cadastrado é
 * acionado sem email nenhum, e a tela precisa dizer isso em vez de disparar um
 * POST que termina em 404.
 */
export function acionamentoParaCobrar<T extends NotificacaoDoCaso>(
  notificacoes: T[]
): T | null {
  const acionamentos = notificacoes.filter((n) => n.gatilho === GATILHO_DO_ACIONAMENTO);
  if (acionamentos.length === 0) return null;
  return acionamentos.reduce((maisNova, atual) =>
    Date.parse(atual.criada_em) > Date.parse(maisNova.criada_em) ? atual : maisNova
  );
}

/**
 * Quem responde pelo setor hoje, do jeito que a decisão da cobrança precisa.
 * Só nome e email: o resto do cadastro não decide nada aqui.
 */
export interface ResponsavelVigente {
  nome: string;
  email: string;
}

export type MotivoDeRecusa = "sem_acionamento" | "cadastro_desconhecido" | "outro_destinatario";

export type VereditoDaCobranca =
  | { pode: true; notificacaoId: string; destinatario: string }
  | { pode: false; motivo: MotivoDeRecusa; destinatario?: string };

/** Emails são iguais quando as pessoas são a mesma, e caixa não muda pessoa. */
function mesmoEmail(um: string | null | undefined, outro: string | null | undefined): boolean {
  const normal = (e: string | null | undefined) => (e ?? "").trim().toLowerCase();
  return normal(um) !== "" && normal(um) === normal(outro);
}

/**
 * Se a cobrança pode sair, e para quem (issue #495, rodada de review do #534).
 *
 * O reenvio copia o destinatário do registro ORIGINAL (`reenviar_notificacao`
 * em `routers/ouvidoria.py`) e emite um token novo do portal do setor para
 * aquele email. O acionamento carrega resumo, relato integral e nota (ADR
 * 0041), então mandar de novo é dar acesso novo ao caso.
 *
 * A linha da fila, porém, mostra o responsável de HOJE. Titular que saiu do
 * setor em julho continua sendo o destinatário do acionamento de julho: com o
 * botão ao lado do nome de quem entrou em agosto, um clique despacharia o
 * relato do manifestante para quem não responde mais pela área, com a tela
 * dizendo que cobrou o responsável.
 *
 * Por isso a cobrança de um clique só sai quando o destinatário do acionamento
 * É o responsável vigente. Fora disso a tela recusa e explica: reenviar mesmo
 * assim é decisão informada, e o lugar dela é o Dossiê, onde o email do
 * destinatário aparece ao lado do botão.
 *
 * Cadastro não lido também recusa: sem ele não há contra quem conferir, e
 * "não sei" não pode virar "pode mandar".
 */
export function decidirCobranca(
  notificacoes: NotificacaoDoCaso[],
  responsavel: ResponsavelVigente | null,
  cadastroLido: boolean
): VereditoDaCobranca {
  if (!cadastroLido) return { pode: false, motivo: "cadastro_desconhecido" };
  const acionamento = acionamentoParaCobrar(notificacoes);
  if (!acionamento) return { pode: false, motivo: "sem_acionamento" };
  if (!responsavel || !mesmoEmail(acionamento.destinatario_email, responsavel.email)) {
    return {
      pode: false,
      motivo: "outro_destinatario",
      destinatario: acionamento.destinatario_nome,
    };
  }
  return {
    pode: true,
    notificacaoId: acionamento.id,
    destinatario: acionamento.destinatario_nome,
  };
}

/**
 * O que a tela sabe da cobrança de uma linha. `reenviada` guarda o `entregue`
 * que a rota devolve: o provedor pode recusar o email na hora e a notificação
 * fica na fila, e afirmar entrega nesse caso é mentir para o ouvidor que
 * acabou de clicar.
 */
export type ResultadoDaCobranca =
  | { fase: "enviando" }
  | { fase: "reenviada"; destinatario: string; entregue: boolean }
  | { fase: "recusada"; motivo: MotivoDeRecusa; destinatario?: string }
  | { fase: "falha" };

const TEXTO_DA_RECUSA: Record<MotivoDeRecusa, string> = {
  // Setor sem responsável cadastrado é acionado sem email nenhum: não há
  // registro para reenviar, e a saída é cadastrar quem responde pela área.
  sem_acionamento: "Este caso não tem acionamento registrado para reenviar",
  cadastro_desconhecido:
    "Sem o cadastro de responsáveis não dá para conferir quem receberia a cobrança. Recarregue a página.",
  outro_destinatario: "",
};

/** A frase que a linha mostra. Afirma só o que a resposta confirma. */
export function textoDaCobranca(resultado: ResultadoDaCobranca): string {
  switch (resultado.fase) {
    case "enviando":
      return "Reenviando o acionamento...";
    case "reenviada":
      return resultado.entregue
        ? `Acionamento reenviado a ${resultado.destinatario}`
        : `O reenvio a ${resultado.destinatario} ficou na fila: o provedor recusou agora e o sistema tenta de novo.`;
    case "recusada":
      if (resultado.motivo === "outro_destinatario") {
        return `O acionamento saiu para ${resultado.destinatario ?? "outra pessoa"}, que não responde mais pelo setor. Confira o cadastro e reenvie pelo Dossiê.`;
      }
      return TEXTO_DA_RECUSA[resultado.motivo];
    case "falha":
      return "Não foi possível cobrar agora. Tente de novo em instantes.";
  }
}

/** Verde só para o que chegou; o resto pede atenção. */
export function tomDaCobranca(resultado: ResultadoDaCobranca): "ok" | "alerta" | "neutro" {
  if (resultado.fase === "reenviada") return resultado.entregue ? "ok" : "alerta";
  if (resultado.fase === "recusada" || resultado.fase === "falha") return "alerta";
  return "neutro";
}
