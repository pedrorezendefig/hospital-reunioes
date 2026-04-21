/**
 * Mapa de cargos do organograma hospitalar.
 * Cada cargo carrega seu setor e nível de acesso (role) automaticamente.
 * Isso elimina a necessidade de o usuário selecionar setor e perfil.
 *
 * TODO: Este mapeamento é duplicado em backend/app/services/cargo_mapping.py.
 *       Se atualizar aqui, atualizar lá também. Futuramente considerar um endpoint
 *       GET /api/cargos como fonte única da verdade.
 */

export type UserRole = "diretor" | "presidente" | "gerente" | "coordenador";

export interface CargoInfo {
  label: string;
  setor: string;
  area: string;
  role: UserRole;
}

export const CARGOS_MAP: Record<string, CargoInfo> = {
  // ─── PRESIDENTE ─────────────────────────────────────────────────
  "Presidente": {
    label: "Presidente",
    setor: "Presidência",
    area: "Diretoria",
    role: "presidente",
  },

  // ─── DIRETORES ────────────────────────────────────────────────────
  "Diretor Clínico": {
    label: "Diretor Clínico",
    setor: "Diretoria Clínica",
    area: "Assistencial",
    role: "diretor",
  },
  "Diretora Clínica": {
    label: "Diretora Clínica",
    setor: "Diretoria Clínica",
    area: "Assistencial",
    role: "diretor",
  },
  "Diretor Administrativo": {
    label: "Diretor Administrativo",
    setor: "Diretoria Administrativa",
    area: "Administrativa",
    role: "diretor",
  },
  "Diretora Administrativa": {
    label: "Diretora Administrativa",
    setor: "Diretoria Administrativa",
    area: "Administrativa",
    role: "diretor",
  },
  "Diretor de Recursos Humanos": {
    label: "Diretor de Recursos Humanos",
    setor: "Recursos Humanos",
    area: "RH e Qualidade",
    role: "diretor",
  },
  "Diretora de Recursos Humanos": {
    label: "Diretora de Recursos Humanos",
    setor: "Recursos Humanos",
    area: "RH e Qualidade",
    role: "diretor",
  },
  "Diretor de Enfermagem": {
    label: "Diretor de Enfermagem",
    setor: "Enfermagem",
    area: "Assistencial",
    role: "diretor",
  },
  "Diretora de Enfermagem": {
    label: "Diretora de Enfermagem",
    setor: "Enfermagem",
    area: "Assistencial",
    role: "diretor",
  },

  // ─── GERENTES ─────────────────────────────────────────────────────
  "Gerente de Enfermagem": {
    label: "Gerente de Enfermagem",
    setor: "Enfermagem",
    area: "Assistencial",
    role: "gerente",
  },
  "Gerente de TI Hospitalar": {
    label: "Gerente de TI Hospitalar",
    setor: "Tecnologia da Informação",
    area: "Administrativa",
    role: "gerente",
  },
  "Gerente de Manutenção": {
    label: "Gerente de Manutenção",
    setor: "Engenharia Clínica",
    area: "Administrativa",
    role: "gerente",
  },
  "Gerente Médico": {
    label: "Gerente Médico",
    setor: "Corpo Clínico",
    area: "Assistencial",
    role: "gerente",
  },
  "Gerente Médica": {
    label: "Gerente Médica",
    setor: "Corpo Clínico",
    area: "Assistencial",
    role: "gerente",
  },
  "Gerente de Apoio Diagnóstico": {
    label: "Gerente de Apoio Diagnóstico",
    setor: "Apoio Diagnóstico",
    area: "Assistencial",
    role: "gerente",
  },
  "Gerente de Suprimentos": {
    label: "Gerente de Suprimentos",
    setor: "Suprimentos e Compras",
    area: "Administrativa",
    role: "gerente",
  },
  "Gerente de Gestão de Pessoas": {
    label: "Gerente de Gestão de Pessoas",
    setor: "Recursos Humanos",
    area: "RH e Qualidade",
    role: "gerente",
  },
  "Gerente de Qualidade": {
    label: "Gerente de Qualidade",
    setor: "Qualidade e Segurança",
    area: "RH e Qualidade",
    role: "gerente",
  },
  "Gerente de Farmácia": {
    label: "Gerente de Farmácia",
    setor: "Farmácia Hospitalar",
    area: "Assistencial",
    role: "gerente",
  },
  "Gerente de Laboratório": {
    label: "Gerente de Laboratório",
    setor: "Laboratório Clínico",
    area: "Assistencial",
    role: "gerente",
  },

  // ─── COORDENADORES ────────────────────────────────────────────────
  "Coordenador da UTI": {
    label: "Coordenador da UTI",
    setor: "UTI",
    area: "Assistencial",
    role: "coordenador",
  },
  "Coordenadora da UTI": {
    label: "Coordenadora da UTI",
    setor: "UTI",
    area: "Assistencial",
    role: "coordenador",
  },
  "Coordenador de Cirurgia": {
    label: "Coordenador de Cirurgia",
    setor: "Centro Cirúrgico",
    area: "Assistencial",
    role: "coordenador",
  },
  "Coordenadora de Cirurgia": {
    label: "Coordenadora de Cirurgia",
    setor: "Centro Cirúrgico",
    area: "Assistencial",
    role: "coordenador",
  },
  "Coordenador do Pronto Atendimento": {
    label: "Coordenador do Pronto Atendimento",
    setor: "Pronto Atendimento",
    area: "Assistencial",
    role: "coordenador",
  },
  "Coordenadora do Pronto Atendimento": {
    label: "Coordenadora do Pronto Atendimento",
    setor: "Pronto Atendimento",
    area: "Assistencial",
    role: "coordenador",
  },
  "Supervisor de Enfermagem": {
    label: "Supervisor de Enfermagem",
    setor: "Internação",
    area: "Assistencial",
    role: "coordenador",
  },
  "Supervisora de Enfermagem": {
    label: "Supervisora de Enfermagem",
    setor: "Internação",
    area: "Assistencial",
    role: "coordenador",
  },
  "Coordenador de Farmácia": {
    label: "Coordenador de Farmácia",
    setor: "Farmácia Hospitalar",
    area: "Assistencial",
    role: "coordenador",
  },
  "Coordenadora de Farmácia": {
    label: "Coordenadora de Farmácia",
    setor: "Farmácia Hospitalar",
    area: "Assistencial",
    role: "coordenador",
  },
  "Coordenador do Laboratório": {
    label: "Coordenador do Laboratório",
    setor: "Laboratório Clínico",
    area: "Assistencial",
    role: "coordenador",
  },
  "Coordenadora do Laboratório": {
    label: "Coordenadora do Laboratório",
    setor: "Laboratório Clínico",
    area: "Assistencial",
    role: "coordenador",
  },
  "Coordenador de Sistemas": {
    label: "Coordenador de Sistemas",
    setor: "Tecnologia da Informação",
    area: "Administrativa",
    role: "coordenador",
  },
  "Coordenadora de Sistemas": {
    label: "Coordenadora de Sistemas",
    setor: "Tecnologia da Informação",
    area: "Administrativa",
    role: "coordenador",
  },
  "Coordenador de Infraestrutura": {
    label: "Coordenador de Infraestrutura",
    setor: "Engenharia Clínica",
    area: "Administrativa",
    role: "coordenador",
  },
  "Coordenadora de Infraestrutura": {
    label: "Coordenadora de Infraestrutura",
    setor: "Engenharia Clínica",
    area: "Administrativa",
    role: "coordenador",
  },
  "Coordenador de Compras": {
    label: "Coordenador de Compras",
    setor: "Suprimentos e Compras",
    area: "Administrativa",
    role: "coordenador",
  },
  "Coordenadora de Compras": {
    label: "Coordenadora de Compras",
    setor: "Suprimentos e Compras",
    area: "Administrativa",
    role: "coordenador",
  },
  "Coordenador de Qualidade": {
    label: "Coordenador de Qualidade",
    setor: "Qualidade e Segurança",
    area: "RH e Qualidade",
    role: "coordenador",
  },
  "Coordenadora de Qualidade": {
    label: "Coordenadora de Qualidade",
    setor: "Qualidade e Segurança",
    area: "RH e Qualidade",
    role: "coordenador",
  },
  "Coordenador de Apoio": {
    label: "Coordenador de Apoio",
    setor: "Apoio Institucional",
    area: "Administrativa",
    role: "coordenador",
  },
  "Coordenadora de Apoio": {
    label: "Coordenadora de Apoio",
    setor: "Apoio Institucional",
    area: "Administrativa",
    role: "coordenador",
  },

  // ─── ANALISTAS / COLABORADORES ────────────────────────────────────
  "Nutricionista Chefe": {
    label: "Nutricionista Chefe",
    setor: "Nutrição Clínica",
    area: "Assistencial",
    role: "coordenador",
  },
  "Analista de Ouvidoria": {
    label: "Analista de Ouvidoria",
    setor: "Ouvidoria",
    area: "RH e Qualidade",
    role: "coordenador",
  },
  "Farmacêutico Clínico": {
    label: "Farmacêutico Clínico",
    setor: "Farmácia Hospitalar",
    area: "Assistencial",
    role: "coordenador",
  },
  "Farmacêutica Clínica": {
    label: "Farmacêutica Clínica",
    setor: "Farmácia Hospitalar",
    area: "Assistencial",
    role: "coordenador",
  },
  "Técnico de Enfermagem": {
    label: "Técnico de Enfermagem",
    setor: "Internação",
    area: "Assistencial",
    role: "coordenador",
  },
  "Técnica de Enfermagem": {
    label: "Técnica de Enfermagem",
    setor: "Internação",
    area: "Assistencial",
    role: "coordenador",
  },
  "Analista de Infraestrutura": {
    label: "Analista de Infraestrutura",
    setor: "Tecnologia da Informação",
    area: "Administrativa",
    role: "coordenador",
  },
  "Biomédico": {
    label: "Biomédico",
    setor: "Laboratório Clínico",
    area: "Assistencial",
    role: "coordenador",
  },
  "Biomédica": {
    label: "Biomédica",
    setor: "Laboratório Clínico",
    area: "Assistencial",
    role: "coordenador",
  },
  "Técnico de Refrigeração": {
    label: "Técnico de Refrigeração",
    setor: "Engenharia Clínica",
    area: "Administrativa",
    role: "coordenador",
  },
  "Assistente de Compras": {
    label: "Assistente de Compras",
    setor: "Suprimentos e Compras",
    area: "Administrativa",
    role: "coordenador",
  },
  "Analista de Recrutamento": {
    label: "Analista de Recrutamento",
    setor: "Recursos Humanos",
    area: "RH e Qualidade",
    role: "coordenador",
  },
  "Enfermeiro Assistencial": {
    label: "Enfermeiro Assistencial",
    setor: "Enfermagem",
    area: "Assistencial",
    role: "coordenador",
  },
  "Enfermeira Assistencial": {
    label: "Enfermeira Assistencial",
    setor: "Enfermagem",
    area: "Assistencial",
    role: "coordenador",
  },
};

/** Lista ordenada de labels de cargo para o dropdown */
export const CARGOS_LIST = Object.values(CARGOS_MAP).sort((a, b) =>
  a.label.localeCompare(b.label, "pt-BR")
);

/** Retorna as informações de um cargo pelo label */
export function getCargoInfo(label: string): CargoInfo | undefined {
  return CARGOS_MAP[label];
}

/** Labels dos níveis de acesso para exibição */
export const ROLE_LABELS: Record<UserRole, string> = {
  diretor: "Diretor(a)",
  presidente: "Presidente",
  gerente: "Gerente",
  coordenador: "Coordenador(a)",
};
