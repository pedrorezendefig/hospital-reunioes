"""Modelos do contexto Auditoria de Pessoal (ver docs/auditoria-pessoal/CONTEXT.md)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

# Minutos desde 00:00 do dia. Em fins de jornada normalizados, pode exceder
# 1440 (overnight: saída 07:13 do dia seguinte = 1873).
Minuto = int


@dataclass
class Tratamento:
    """Linha de 'TRATAMENTOS EFETUADOS SOBRE OS DADOS ORIGINAIS' do Espelho."""

    horario: Minuto | None
    ocorr: str  # I=Incluído, P=Pré-assinalado (Batida Automática), D=Desconsiderado
    motivo: str


@dataclass
class DiaPonto:
    data: date
    dow: str
    marcacoes: list[Minuto] = field(default_factory=list)
    # ENT.1, SAÍ.1, ENT.2, SAÍ.2, ENT.3, SAÍ.3 — como impressos (sem normalizar overnight)
    jornada: list[Minuto | None] = field(default_factory=lambda: [None] * 6)
    duracao: Minuto | None = None  # DURAÇÃO impressa (pode exceder 24h)
    ch: str | None = None
    tratamentos: list[Tratamento] = field(default_factory=list)

    def pares_jornada(self) -> list[tuple[Minuto, Minuto]]:
        """Pares (ent, saí) normalizados: saí <= ent vira overnight (+24h)."""
        pares: list[tuple[Minuto, Minuto]] = []
        for i in (0, 2, 4):
            ent, sai = self.jornada[i], self.jornada[i + 1]
            if ent is None or sai is None:
                continue
            if sai <= ent:
                sai += 1440
            pares.append((ent, sai))
        return pares

    def duracao_liquida(self) -> Minuto:
        """Horas trabalhadas no dia, em minutos — métrica usada pelas Regras.

        Via de regra é a soma dos pares de jornada (líquida, consistente com a
        grade contratual). Exceção: plantão overnight com batida dupla matinal
        (entrada 06:53, saída 07:12 do dia seguinte) — o par parece durar
        minutos, mas a DURAÇÃO impressa (>20h) revela o overnight; nesse caso
        vale a leitura overnight do par.
        """
        pares = self.pares_jornada()
        if not pares:
            return self.duracao or 0
        recalc = sum(s - e for e, s in pares)
        if self.duracao is not None and self.duracao >= 1200 and len(pares) == 1:
            ent, sai = pares[0]
            if sai <= 1440:
                overnight = (sai + 1440) - ent
                if abs(overnight - self.duracao) <= 70:
                    return overnight
        return recalc

    def presenca_bruta(self) -> Minuto | None:
        """Última saída − primeira entrada (sem descontar intervalos)."""
        pares = self.pares_jornada()
        if not pares:
            return None
        return max(s for _, s in pares) - min(e for e, _ in pares)

    @property
    def trabalhou(self) -> bool:
        return bool(self.marcacoes) or any(v is not None for v in self.jornada)

    @property
    def escala_prevista(self) -> bool:
        """Dia em que o Espelho imprime um CH (a escala previa trabalho)."""
        return self.ch is not None


@dataclass
class EspelhoFuncionario:
    pagina: int
    nome: str
    pis: str
    cpf: str
    matricula: str
    admissao: date | None
    centro_custo: str
    departamento: str
    cargo: str
    dias: list[DiaPonto] = field(default_factory=list)
    # CH -> pares (ent, saí) da grade contratual (saí < ent = overnight)
    grades: dict[str, list[tuple[Minuto, Minuto]]] = field(default_factory=dict)
    avisos_parse: list[str] = field(default_factory=list)


@dataclass
class Rubrica:
    codigo: int
    descricao: str
    referencia: float  # horas, dias ou % — conforme a rubrica
    valor: float
    tipo: str  # P=provento, D=desconto


@dataclass
class FolhaRegistro:
    empr: int
    nome: str
    situacao: str
    cpf: str
    admissao: date | None
    vinculo: str  # Celetista, Estagiário...
    cc: str
    depto: str
    horas_mes: float
    cargo: str
    cbo: str
    filial: str
    salario: float
    c_custo: str  # seção 'C.Custo: N - NOME' corrente
    demissao: date | None = None  # linha 'DEMITIDO EM dd/mm/aaaa' do registro
    # linhas informativas do registro: 'FERIAS DE ...', 'Doença período ...',
    # 'Licença maternidade: ...' — explicam ausências no Espelho
    observacoes: list[str] = field(default_factory=list)
    rubricas: list[Rubrica] = field(default_factory=list)
    nd: int = 0
    nf: int = 0
    proventos: float = 0.0
    descontos: float = 0.0
    informativa: float = 0.0
    liquido: float = 0.0
    base_inss: float = 0.0
    base_fgts: float = 0.0
    valor_fgts: float = 0.0
    base_irrf: float = 0.0
    avisos_parse: list[str] = field(default_factory=list)

    def rubricas_por_descricao(self, *trechos: str) -> list[Rubrica]:
        achadas = []
        for r in self.rubricas:
            desc = r.descricao.upper()
            if any(t in desc for t in trechos):
                achadas.append(r)
        return achadas

    @property
    def valor_hora(self) -> float:
        return self.salario / self.horas_mes if self.horas_mes else 0.0


@dataclass
class Vinculo:
    """Funcionário ↔ matrículas dos dois sistemas (ver CONTEXT.md)."""

    espelho: EspelhoFuncionario | None
    folha: FolhaRegistro | None
    metodo: str | None = None  # cpf | nome | fuzzy | None (órfão)
    score: float = 0.0

    @property
    def rotulo(self) -> str:
        if self.folha is not None:
            return f"{self.folha.nome} (folha {self.folha.empr})"
        if self.espelho is not None:
            return f"{self.espelho.nome} (ponto {self.espelho.matricula})"
        return "?"


@dataclass
class Achado:
    regra: str  # ex.: 'R2'
    regra_nome: str
    severidade: str  # CRITICA | ALTA | MEDIA | INFO
    pessoa: str
    descricao: str
    evidencia: str
    valor_estimado: float | None = None
