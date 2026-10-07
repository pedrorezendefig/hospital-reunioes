// As atas que os cards do dashboard contam (issue #1055). O card mostra o
// tamanho da lista e o modal mostra a lista: uma fonte só, para o número e a
// lista nunca discordarem.

export interface AtaDoDashboard {
  id_reuniao: string;
  data: string;
  tipo?: string | null;
  objetivo?: string | null;
  status_ata: string;
  updated_at?: string | null;
}

// Ata parada: status intermediário e sem atualização há mais de 3 dias,
// contados da meia-noite UTC de hoje (o updated_at vem em UTC).
export function atasParadas<T extends AtaDoDashboard>(reunioes: T[], agora: Date = new Date()): T[] {
  const tresDiasAtras = new Date(agora);
  tresDiasAtras.setUTCHours(0, 0, 0, 0);
  tresDiasAtras.setUTCDate(tresDiasAtras.getUTCDate() - 3);

  return reunioes.filter((r) => {
    if (r.status_ata !== "AGUARDANDO_VALIDACAO" && r.status_ata !== "PROCESSANDO") return false;
    if (!r.updated_at) return true; // sem updated_at = conservador, conta como parada
    return new Date(r.updated_at) < tresDiasAtras;
  });
}

export function atasAguardandoAssinatura<T extends AtaDoDashboard>(reunioes: T[]): T[] {
  return reunioes.filter((r) => r.status_ata === "AGUARDANDO_ASSINATURA");
}
