"""
Mapeamento de cargos do organograma hospitalar para uso no backend.
Replica a lógica de onboarding-data.ts do frontend para validação server-side.

TODO: Este mapeamento é duplicado em frontend/src/lib/onboarding-data.ts.
      Se atualizar aqui, atualizar lá também. Futuramente considerar um endpoint
      GET /api/cargos como fonte única da verdade.
"""

from typing import Optional
from dataclasses import dataclass


@dataclass
class CargoInfo:
    label: str
    setor: str
    area: str
    role: str  # diretor | presidente | gerente | coordenador


CARGOS_MAP: dict[str, CargoInfo] = {
    # ─── PRESIDENTE ─────────────────────────────────────────────────
    "Presidente": CargoInfo("Presidente", "Presidência", "Diretoria", "presidente"),

    # ─── DIRETORES ───────────────────────────────────────────────────
    "Diretor Clínico": CargoInfo("Diretor Clínico", "Diretoria Clínica", "Assistencial", "diretor"),
    "Diretora Clínica": CargoInfo("Diretora Clínica", "Diretoria Clínica", "Assistencial", "diretor"),
    "Diretor Administrativo": CargoInfo("Diretor Administrativo", "Diretoria Administrativa", "Administrativa", "diretor"),
    "Diretora Administrativa": CargoInfo("Diretora Administrativa", "Diretoria Administrativa", "Administrativa", "diretor"),
    "Diretor de Recursos Humanos": CargoInfo("Diretor de Recursos Humanos", "Recursos Humanos", "RH e Qualidade", "diretor"),
    "Diretora de Recursos Humanos": CargoInfo("Diretora de Recursos Humanos", "Recursos Humanos", "RH e Qualidade", "diretor"),
    "Diretor de Enfermagem": CargoInfo("Diretor de Enfermagem", "Enfermagem", "Assistencial", "diretor"),
    "Diretora de Enfermagem": CargoInfo("Diretora de Enfermagem", "Enfermagem", "Assistencial", "diretor"),

    # ─── GERENTES ────────────────────────────────────────────────────
    "Gerente de Enfermagem": CargoInfo("Gerente de Enfermagem", "Enfermagem", "Assistencial", "gerente"),
    "Gerente de TI Hospitalar": CargoInfo("Gerente de TI Hospitalar", "Tecnologia da Informação", "Administrativa", "gerente"),
    "Gerente de Manutenção": CargoInfo("Gerente de Manutenção", "Engenharia Clínica", "Administrativa", "gerente"),
    "Gerente Médico": CargoInfo("Gerente Médico", "Corpo Clínico", "Assistencial", "gerente"),
    "Gerente Médica": CargoInfo("Gerente Médica", "Corpo Clínico", "Assistencial", "gerente"),
    "Gerente de Apoio Diagnóstico": CargoInfo("Gerente de Apoio Diagnóstico", "Apoio Diagnóstico", "Assistencial", "gerente"),
    "Gerente de Suprimentos": CargoInfo("Gerente de Suprimentos", "Suprimentos e Compras", "Administrativa", "gerente"),
    "Gerente de Gestão de Pessoas": CargoInfo("Gerente de Gestão de Pessoas", "Recursos Humanos", "RH e Qualidade", "gerente"),
    "Gerente de Qualidade": CargoInfo("Gerente de Qualidade", "Qualidade e Segurança", "RH e Qualidade", "gerente"),
    "Gerente de Farmácia": CargoInfo("Gerente de Farmácia", "Farmácia Hospitalar", "Assistencial", "gerente"),
    "Gerente de Laboratório": CargoInfo("Gerente de Laboratório", "Laboratório Clínico", "Assistencial", "gerente"),

    # ─── COORDENADORES ───────────────────────────────────────────────
    "Coordenador da UTI": CargoInfo("Coordenador da UTI", "UTI", "Assistencial", "coordenador"),
    "Coordenadora da UTI": CargoInfo("Coordenadora da UTI", "UTI", "Assistencial", "coordenador"),
    "Coordenador de Cirurgia": CargoInfo("Coordenador de Cirurgia", "Centro Cirúrgico", "Assistencial", "coordenador"),
    "Coordenadora de Cirurgia": CargoInfo("Coordenadora de Cirurgia", "Centro Cirúrgico", "Assistencial", "coordenador"),
    "Coordenador do Pronto Atendimento": CargoInfo("Coordenador do Pronto Atendimento", "Pronto Atendimento", "Assistencial", "coordenador"),
    "Coordenadora do Pronto Atendimento": CargoInfo("Coordenadora do Pronto Atendimento", "Pronto Atendimento", "Assistencial", "coordenador"),
    "Supervisor de Enfermagem": CargoInfo("Supervisor de Enfermagem", "Internação", "Assistencial", "coordenador"),
    "Supervisora de Enfermagem": CargoInfo("Supervisora de Enfermagem", "Internação", "Assistencial", "coordenador"),
    "Coordenador de Farmácia": CargoInfo("Coordenador de Farmácia", "Farmácia Hospitalar", "Assistencial", "coordenador"),
    "Coordenadora de Farmácia": CargoInfo("Coordenadora de Farmácia", "Farmácia Hospitalar", "Assistencial", "coordenador"),
    "Coordenador do Laboratório": CargoInfo("Coordenador do Laboratório", "Laboratório Clínico", "Assistencial", "coordenador"),
    "Coordenadora do Laboratório": CargoInfo("Coordenadora do Laboratório", "Laboratório Clínico", "Assistencial", "coordenador"),
    "Coordenador de Sistemas": CargoInfo("Coordenador de Sistemas", "Tecnologia da Informação", "Administrativa", "coordenador"),
    "Coordenadora de Sistemas": CargoInfo("Coordenadora de Sistemas", "Tecnologia da Informação", "Administrativa", "coordenador"),
    "Coordenador de Infraestrutura": CargoInfo("Coordenador de Infraestrutura", "Engenharia Clínica", "Administrativa", "coordenador"),
    "Coordenadora de Infraestrutura": CargoInfo("Coordenadora de Infraestrutura", "Engenharia Clínica", "Administrativa", "coordenador"),
    "Coordenador de Compras": CargoInfo("Coordenador de Compras", "Suprimentos e Compras", "Administrativa", "coordenador"),
    "Coordenadora de Compras": CargoInfo("Coordenadora de Compras", "Suprimentos e Compras", "Administrativa", "coordenador"),
    "Coordenador de Qualidade": CargoInfo("Coordenador de Qualidade", "Qualidade e Segurança", "RH e Qualidade", "coordenador"),
    "Coordenadora de Qualidade": CargoInfo("Coordenadora de Qualidade", "Qualidade e Segurança", "RH e Qualidade", "coordenador"),
    "Coordenador de Apoio": CargoInfo("Coordenador de Apoio", "Apoio Institucional", "Administrativa", "coordenador"),
    "Coordenadora de Apoio": CargoInfo("Coordenadora de Apoio", "Apoio Institucional", "Administrativa", "coordenador"),

    # ─── COLABORADORES ───────────────────────────────────────────────
    "Engenheiro de IA": CargoInfo("Engenheiro de IA", "Tecnologia da Informação", "Administrativa", "coordenador"),
    "Nutricionista Chefe": CargoInfo("Nutricionista Chefe", "Nutrição Clínica", "Assistencial", "coordenador"),
    "Analista de Ouvidoria": CargoInfo("Analista de Ouvidoria", "Ouvidoria", "RH e Qualidade", "coordenador"),
    "Farmacêutico Clínico": CargoInfo("Farmacêutico Clínico", "Farmácia Hospitalar", "Assistencial", "coordenador"),
    "Farmacêutica Clínica": CargoInfo("Farmacêutica Clínica", "Farmácia Hospitalar", "Assistencial", "coordenador"),
    "Técnico de Enfermagem": CargoInfo("Técnico de Enfermagem", "Internação", "Assistencial", "coordenador"),
    "Técnica de Enfermagem": CargoInfo("Técnica de Enfermagem", "Internação", "Assistencial", "coordenador"),
    "Analista de Infraestrutura": CargoInfo("Analista de Infraestrutura", "Tecnologia da Informação", "Administrativa", "coordenador"),
    "Biomédico": CargoInfo("Biomédico", "Laboratório Clínico", "Assistencial", "coordenador"),
    "Biomédica": CargoInfo("Biomédica", "Laboratório Clínico", "Assistencial", "coordenador"),
    "Técnico de Refrigeração": CargoInfo("Técnico de Refrigeração", "Engenharia Clínica", "Administrativa", "coordenador"),
    "Assistente de Compras": CargoInfo("Assistente de Compras", "Suprimentos e Compras", "Administrativa", "coordenador"),
    "Analista de Recrutamento": CargoInfo("Analista de Recrutamento", "Recursos Humanos", "RH e Qualidade", "coordenador"),
    "Enfermeiro Assistencial": CargoInfo("Enfermeiro Assistencial", "Enfermagem", "Assistencial", "coordenador"),
    "Enfermeira Assistencial": CargoInfo("Enfermeira Assistencial", "Enfermagem", "Assistencial", "coordenador"),
}


def get_cargo_info(label: str) -> Optional[CargoInfo]:
    """Retorna as informações de um cargo pelo label exato."""
    return CARGOS_MAP.get(label)


def list_cargos() -> list[str]:
    """Retorna lista ordenada de labels de cargo."""
    return sorted(CARGOS_MAP.keys(), key=lambda x: x.lower())
