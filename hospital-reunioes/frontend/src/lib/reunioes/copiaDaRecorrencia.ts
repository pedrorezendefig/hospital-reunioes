// O pedido de `agendar` de cada cópia do painel Recorrência (issue #761).
// A série é a mesma reunião se repetindo, então a cópia herda o facilitador da
// original. Sem ele, o backend fazia de quem clicou o facilitador de toda a
// série, e a Secretária virava facilitadora de reuniões que não conduz.

interface ReuniaoOriginal {
  titulo: string | null;
  tipo: string | null;
  objetivo: string | null;
  facilitador_id: string | null;
  participantes_programada?: Array<{ id: string }>;
}

interface Serie {
  horario: string;
  idGrupo: string;
  nomeGrupo: string;
}

export interface CopiaDaRecorrencia {
  titulo: string;
  data: string;
  hora_inicio: string | null;
  tipo: string | null;
  objetivo: string | null;
  facilitador_id?: string;
  participante_ids: string[];
  id_grupo_recorrencia: string;
  nome_grupo_recorrencia: string | null;
}

export function copiaDaRecorrencia(original: ReuniaoOriginal, data: string, serie: Serie): CopiaDaRecorrencia {
  return {
    titulo: original.titulo || original.tipo || "Reunião",
    data,
    hora_inicio: serie.horario || null,
    tipo: original.tipo ?? null,
    objetivo: original.objetivo || null,
    ...(original.facilitador_id ? { facilitador_id: original.facilitador_id } : {}),
    participante_ids: (original.participantes_programada ?? []).map((p) => p.id),
    id_grupo_recorrencia: serie.idGrupo,
    nome_grupo_recorrencia: serie.nomeGrupo.trim() || null,
  };
}
