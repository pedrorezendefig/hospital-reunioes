"""A onda seguinte começa no PR verde, com o deploy em paralelo (issue #999).

ADR 0064, decisão 6a: a sessão da `/onda-enxuta` lança a sessão da onda
seguinte assim que os PRs ficam verdes e limpos, e só depois roda o rabo, em
paralelo com os implementadores novos. A passagem sai com "em deploy" e a
versão esperada; fatia bloqueada por issue da onda em deploy espera a
bloqueadora fechar; a sessão encerra só depois de comentar o resultado do rabo
na onda. Skill é instrução que um agente segue: estes testes leem os textos.
"""

from __future__ import annotations

import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
SKILLS = RAIZ / ".claude" / "skills"
ONDA = SKILLS / "onda-enxuta" / "SKILL.md"
PROMPTS = SKILLS / "onda-enxuta" / "references" / "prompts.md"


def ler(caminho: Path) -> str:
    return caminho.read_text(encoding="utf-8")


def secao(md: str, titulo: str, nivel: str = "##") -> str:
    """De um `<nivel> <titulo>` até o próximo título do mesmo nível."""
    achado = re.search(rf"^{nivel} {re.escape(titulo)}.*?(?=^{nivel} |\Z)", md, re.S | re.M)
    assert achado, f"seção ausente: {titulo}"
    return achado.group(0)


def passo(numero: int) -> str:
    """O `### <numero>. ` do Fluxo, até o próximo título de nível 2 ou 3."""
    achado = re.search(rf"^### {numero}\. .*?(?=^#{{2,3}} |\Z)", ler(ONDA), re.S | re.M)
    assert achado, f"passo ausente: {numero}"
    return achado.group(0)


def bloco_da_passagem() -> str:
    # o bloco tem um `## Passagem` dentro: a seção vai do título até o fim do arquivo
    passagem = ler(PROMPTS).split("\n## Passagem (prompt da próxima sessão)\n", 1)[1]
    return re.search(r"```\n(.*?)```", passagem, re.S).group(1)


# ------------------------------------------- a onda seguinte sai no PR verde


def test_a_sessao_lanca_a_onda_seguinte_e_so_depois_roda_o_rabo():
    resumo = next(li for li in ler(ONDA).splitlines() if li.startswith("**Uma sessão de fundo = uma onda.**"))
    # a ordem antiga: o rabo (fecha a onda), depois a passagem, depois o lançamento
    assert not re.search(r"(fecha a onda|rabo).*escreve a passagem.*lança", resumo), resumo
    assert re.search(
        r"PRs ficam verdes e limpos.*escreve a passagem e lança a sessão da onda seguinte"
        r".*roda o rabo.*em paralelo.*comenta o resultado na onda",
        resumo,
    ), resumo

    # no fluxo, o lançamento vem no passo 5, e o rabo de verdade só no 6
    lote = passo(5)
    assert "lancar_sessao.sh <nome>-onda<N+1>" in lote, lote
    assert "a linha `Em deploy`" in lote, lote
    rabo = next(li for li in passo(6).splitlines() if "fechar_onda.py --prs" in li)
    assert "--dry-run" not in rabo, rabo


def test_a_passagem_sai_com_o_que_esta_em_deploy_e_a_versao_esperada():
    bloco = bloco_da_passagem()
    assert re.search(
        r"^Em deploy: PRs #a #b \(issues #x #y\), versão esperada v<antiga> -> v<nova>", bloco, re.M
    ), bloco
    # nada do que só é verdade depois do rabo
    for depois_do_rabo in ("fechada em", "build ok", "health ok", "Está solta"):
        assert depois_do_rabo not in bloco, depois_do_rabo


def test_a_sessao_so_encerra_depois_de_comentar_o_resultado_do_rabo_na_onda():
    resultado = passo(7)
    assert "<!-- automacao -->" in resultado and "## Onda <nome> <N>" in resultado, resultado
    # a passagem já lançada registra o resultado quando o rabo termina
    assert "Rabo da onda <N>:" in resultado and "<nome>-onda<N+1>.md" in resultado, resultado
    assert re.search(r"[Ee]ncerre só depois", resultado), resultado


# ------------------------------------------- fatia bloqueada pela onda em deploy


def test_fatia_bloqueada_pela_onda_em_deploy_fica_na_onda_em_vez_de_sair_da_fila():
    fila = passo(1)
    regra = next(li for li in fila.splitlines() if "dependencies/blocked_by" in li)
    assert re.search(r"bloqueio por issue da linha `Em deploy`.*fica na onda", regra), regra


def test_implementador_de_fatia_bloqueada_pela_onda_em_deploy_so_sai_depois_que_a_bloqueadora_fecha():
    lote = passo(3)
    espera = next(li for li in lote.splitlines() if li.startswith("Fatia bloqueada por issue em deploy"))
    assert "só é disparada depois que a bloqueadora fecha" in espera, espera
    # a espera é por evento, em segundo plano, lendo o bloqueio nativo, não o relatório
    assert "run_in_background: true" in espera and "dependencies/blocked_by" in espera, espera
    assert '.state == "open"' in espera, espera
    # o worktree dela nasce depois do squash da bloqueadora, e a espera tem teto
    assert "origin/main" in espera and "teto" in espera, espera
    # as outras não esperam por ela
    disparo = next(li for li in lote.splitlines() if li.startswith("Dispare os"))
    assert "sem bloqueio aberto" in disparo, disparo


# ------------------------------------------- o semáforo segue ordenando os deploys


def test_o_rabo_de_cada_onda_usa_chave_propria_no_semaforo():
    # duas ondas da mesma sessão se sobrepõem no deploy; com a chave da sessão, o
    # semáforo (reentrante pela chave) deixaria o rabo da seguinte entrar junto, e o
    # worktree `~/wt-<chave>` de um seria apagado pelo outro
    # (o PR avulso, como o da fatia de manual, não leva `--sessao`: a chave é `pr-<N>`)
    for numero in (5, 6):
        comandos = re.findall(r"fechar_onda\.py --prs[^`]*--sessao[^`]*`", passo(numero))
        assert comandos, numero
        assert all("--sessao <nome>-onda<N>" in c for c in comandos), comandos


# ------------------------------------------- o intervalo vai para o comentário da onda


def test_o_comentario_da_onda_registra_o_intervalo_dos_prs_verdes_ao_primeiro_implementador():
    # a hora dos PRs verdes viaja na passagem; a sessão seguinte mede contra ela
    assert re.search(r"^Sessão <nome>, onda <N> com os PRs verdes em <data hora ISO>\.$", bloco_da_passagem(), re.M)

    disparo = next(li for li in passo(3).splitlines() if li.startswith("Dispare os"))
    assert "date -u" in disparo and "primeiro implementador" in disparo, disparo

    relatorio = next(li for li in passo(7).splitlines() if li.startswith("Relatório de até"))
    assert re.search(r"intervalo entre os PRs verdes da onda anterior .* e o primeiro implementador desta", relatorio), (
        relatorio
    )


# ------------------------------------------- o planejador e o registro das decisões contam a ordem nova


def test_o_montar_ondas_diz_que_a_onda_seguinte_sai_no_pr_verde():
    passo_a_passo = secao(ler(SKILLS / "montar-ondas-enxutas" / "SKILL.md"), "6. Relatório e ordem de comando", "###")
    linha = next(li for li in passo_a_passo.splitlines() if li.lstrip().startswith("3. Com os PRs verdes"))
    assert not re.search(r"fecha a onda.*lança", linha), linha
    assert re.search(r"lança sozinha a sessão da onda seguinte.*em paralelo.*comenta o resultado", linha), linha

    bloqueada = next(li for li in ler(SKILLS / "montar-ondas-enxutas" / "SKILL.md").splitlines()
                     if li.startswith("| Bloqueada |"))
    assert "espera a bloqueadora fechar" in bloqueada, bloqueada


def test_as_decisoes_da_onda_registram_a_emenda_da_ordem():
    emenda = next(li for li in ler(SKILLS / "onda-enxuta" / "references" / "decisoes.md").splitlines()
                  if "decisão 6a" in li)
    assert "issue #999" in emenda and "decisão 2" in emenda, emenda


# ------------------------------------------- a sessão seguinte sabe da onda anterior antes do próprio rabo
# (revisão do PR #1019: com a onda seguinte já viva, rollback e parada da anterior precisam chegar a ela)


def _antes_do_rabo() -> str:
    fechamento = passo(6)
    achado = re.search(r"^Primeiro, a onda anterior.*?(?=^1\. )", fechamento, re.S | re.M)
    assert achado, fechamento
    return achado.group(0)


def test_a_sessao_seguinte_espera_a_linha_da_onda_anterior_antes_do_proprio_rabo():
    regra = _antes_do_rabo()
    assert "`Em deploy` diferente de `nenhum`" in regra, regra
    # espera por evento, no arquivo da própria passagem, com teto que cobre a espera de migration (24 h)
    assert "`Rabo da onda <N-1>:`" in regra and "<nome>-onda<N>.md" in regra, regra
    assert "run_in_background: true" in regra and "teto de 25 h" in regra, regra
    # a regra vem antes do comando do rabo, não depois
    fechamento = passo(6)
    assert fechamento.index("Primeiro, a onda anterior") < fechamento.index("fechar_onda.py --prs <a> <b>")


def test_rollback_da_onda_anterior_poe_o_revert_primeiro_no_rabo_da_seguinte():
    regra = _antes_do_rabo()
    revert = next(li for li in regra.splitlines() if li.startswith("- `saída 6"))
    assert "gh pr checks <R> --watch" in revert, revert
    assert "o revert entra primeiro e sem revisor no comando do item 3: `--prs <R> <a> <b>`" in revert, revert
    # a fatia desta onda que dependia da issue reaberta não sobe sem a bloqueadora
    assert "bloqueada por uma das issues da linha fica de fora" in revert, revert

    # e quem fez o rollback avisa pela passagem lançada, logo depois de abrir o revert
    saida6 = next(li for li in passo(6).splitlines() if li.lstrip().startswith("- Saída `6`"))
    assert "`Rabo da onda <N>: saída 6, revert no PR #<R>, issues <#x #y>`" in saida6, saida6
    assert "na frente do próximo `fechar_onda.py`" not in saida6, saida6


def test_onda_anterior_parada_segura_o_rabo_da_seguinte_e_ninguem_forca_a_trava():
    regra = _antes_do_rabo()
    parada = next(li for li in regra.splitlines() if li.startswith("- `parada`"))
    assert "Não rode o rabo" in parada and "teto estourado" in parada, parada
    # a parada se propaga para a onda depois desta
    assert "`Rabo da onda <N>: parada, a onda <N-1> não fechou`" in parada, parada
    # a trava velha de outra onda é prod quebrada esperando humano: nunca --forcar, mesmo que o script mande
    assert re.search(r"[Nn]unca rode `semaforo\.sh soltar .*--forcar`", regra), regra

    saida34 = next(li for li in passo(6).splitlines() if li.lstrip().startswith("- Saída `3` ou `4`"))
    assert "`Rabo da onda <N>: saída <3|4>, parada, semáforo preso na chave <nome>-onda<N>" in saida34, saida34

    # o registro vai para a passagem assim que o rabo termina, não no fim da sessão
    registro = next(li for li in passo(7).splitlines() if li.startswith("1. Com passagem lançada"))
    assert "assim que o rabo termina" in registro and "espera por ela antes do próprio rabo" in registro, registro
