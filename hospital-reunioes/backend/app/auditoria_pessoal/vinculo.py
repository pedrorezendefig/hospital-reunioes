"""Vínculo: casamento Funcionário ↔ matrículas (RH iD × Domínio).

Cascata: CPF válido → nome exato normalizado → fuzzy (difflib).
176/460 cadastros do RH iD têm o PIS no campo CPF (medição 05/2026), por isso
CPF igual ao PIS é descartado como chave. Fuzzy entra em fila de revisão.
"""

from __future__ import annotations

import unicodedata
from difflib import SequenceMatcher

from .modelos import EspelhoFuncionario, FolhaRegistro, Vinculo
from .parametros import Parametros


def normalizar_nome(nome: str) -> str:
    s = unicodedata.normalize("NFD", nome)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return " ".join(s.upper().split())


def cpf_valido(cpf: str) -> bool:
    cpf = "".join(filter(str.isdigit, cpf)).zfill(11) if cpf else ""
    if len(cpf) != 11 or cpf == cpf[0] * 11:
        return False
    for n in (9, 10):
        soma = sum(int(cpf[i]) * ((n + 1) - i) for i in range(n))
        digito = (soma * 10) % 11 % 10
        if digito != int(cpf[n]):
            return False
    return True


def _cpf11(cpf: str) -> str:
    dig = "".join(filter(str.isdigit, cpf or ""))
    return dig.zfill(11) if dig else ""


def vincular(
    espelhos: list[EspelhoFuncionario],
    folhas: list[FolhaRegistro],
    params: Parametros,
) -> tuple[list[Vinculo], dict[str, int], list[str]]:
    """Retorna (vínculos incl. órfãos, stats por método, fila de revisão)."""
    vinculos: list[Vinculo] = []
    fila_revisao: list[str] = []
    stats = {"cpf": 0, "nome": 0, "fuzzy": 0, "so_espelho": 0, "so_folha": 0}

    folhas_livres = list(folhas)
    espelhos_livres = list(espelhos)

    # 1) CPF — somente CPFs válidos e que não sejam o PIS recopiado
    cpf_folha: dict[str, list[FolhaRegistro]] = {}
    for f in folhas_livres:
        c = _cpf11(f.cpf)
        if c and cpf_valido(c):
            cpf_folha.setdefault(c, []).append(f)
    restantes_esp: list[EspelhoFuncionario] = []
    for e in espelhos_livres:
        c = _cpf11(e.cpf)
        candidatos = cpf_folha.get(c, [])
        if c and c != _cpf11(e.pis) and cpf_valido(c) and len(candidatos) == 1:
            f = candidatos[0]
            if f in folhas_livres:
                vinculos.append(Vinculo(espelho=e, folha=f, metodo="cpf", score=1.0))
                folhas_livres.remove(f)
                stats["cpf"] += 1
                continue
        restantes_esp.append(e)
    espelhos_livres = restantes_esp

    # 2) nome exato normalizado — só quando único dos dois lados
    nomes_folha: dict[str, list[FolhaRegistro]] = {}
    for f in folhas_livres:
        nomes_folha.setdefault(normalizar_nome(f.nome), []).append(f)
    nomes_espelho: dict[str, list[EspelhoFuncionario]] = {}
    for e in espelhos_livres:
        nomes_espelho.setdefault(normalizar_nome(e.nome), []).append(e)
    restantes_esp = []
    for e in espelhos_livres:
        n = normalizar_nome(e.nome)
        if len(nomes_espelho.get(n, [])) == 1 and len(nomes_folha.get(n, [])) == 1:
            f = nomes_folha[n][0]
            if f in folhas_livres:
                vinculos.append(Vinculo(espelho=e, folha=f, metodo="nome", score=1.0))
                folhas_livres.remove(f)
                stats["nome"] += 1
                continue
        if n in nomes_folha and len(nomes_folha.get(n, [])) > 1:
            fila_revisao.append(f"homônimo: {e.nome} (ponto {e.matricula}) casa com mais de um registro da folha")
        restantes_esp.append(e)
    espelhos_livres = restantes_esp

    # 3) fuzzy — melhor candidato com folga sobre o segundo.
    # Nome de casada costuma só ACRESCENTAR sobrenome: prefixo exato ganha bônus.
    def _score(a: str, b: str) -> float:
        ratio = SequenceMatcher(None, a, b).ratio()
        menor, maior = (a, b) if len(a) <= len(b) else (b, a)
        if len(menor.split()) >= 3 and maior.startswith(menor + " "):
            return max(ratio, 0.93)
        return ratio

    restantes_esp = []
    for e in espelhos_livres:
        alvo = normalizar_nome(e.nome)
        scores = sorted(
            ((_score(alvo, normalizar_nome(f.nome)), f) for f in folhas_livres),
            key=lambda par: par[0],
            reverse=True,
        )
        if (
            scores
            and scores[0][0] >= params.fuzzy_score_min
            and (len(scores) == 1 or scores[0][0] - scores[1][0] >= params.fuzzy_gap_min)
        ):
            score, f = scores[0]
            vinculos.append(Vinculo(espelho=e, folha=f, metodo="fuzzy", score=score))
            folhas_livres.remove(f)
            stats["fuzzy"] += 1
            fila_revisao.append(
                f"fuzzy {score:.2f}: {e.nome} (ponto {e.matricula}) ↔ {f.nome} (folha {f.empr}) — confirmar"
            )
        else:
            restantes_esp.append(e)

    for e in restantes_esp:
        vinculos.append(Vinculo(espelho=e, folha=None))
        stats["so_espelho"] += 1
    for f in folhas_livres:
        vinculos.append(Vinculo(espelho=None, folha=f))
        stats["so_folha"] += 1
    return vinculos, stats, fila_revisao
