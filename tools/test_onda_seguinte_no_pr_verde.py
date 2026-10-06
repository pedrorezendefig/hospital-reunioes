"""A onda seguinte começa no PR verde, com o deploy em paralelo (issue #999).

ADR 0064, decisão 6a: a sessão da `/onda-enxuta` lança a sessão da onda
seguinte assim que os PRs ficam verdes e limpos, e só depois roda o rabo, em
paralelo com os implementadores novos. A passagem sai com "em deploy" e a
versão esperada; fatia bloqueada por issue da onda em deploy espera a
bloqueadora fechar; a sessão encerra só depois de comentar o resultado do rabo
na onda. Skill é instrução que um agente segue: estes testes leem os textos.

Emenda do grilling de 06/10/2026 (segunda tentativa; a primeira, PR #1019, caiu
por must-fix): a onda seguinte não lê nada da anterior depois do lançamento. A
passagem é escrita uma vez só, nenhuma sessão espera outra, e o fracasso do
rabo fica com o próprio rabo (`tools/test_rabo_assume_o_fracasso.py`).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
SKILLS = RAIZ / ".claude" / "skills"
ONDA = SKILLS / "onda-enxuta" / "SKILL.md"
PROMPTS = SKILLS / "onda-enxuta" / "references" / "prompts.md"
MONTAR = SKILLS / "montar-ondas-enxutas" / "SKILL.md"


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
    assert re.search(r"[Ee]ncerre só depois", resultado), resultado
    # o resultado vai para o comentário, não para a passagem já lançada
    assert "<nome>-onda<N+1>.md" not in resultado, resultado


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
    assert "só é disparado quando a bloqueadora fecha" in bloqueada, bloqueada


def test_as_decisoes_da_onda_registram_a_emenda_da_ordem():
    emenda = next(li for li in ler(SKILLS / "onda-enxuta" / "references" / "decisoes.md").splitlines()
                  if "decisão 6a" in li)
    assert "issue #999" in emenda and "decisão 2" in emenda, emenda




# ------------------------------------------- a onda seguinte não lê nada da anterior
# (emenda de 06/10/2026: a passagem é escrita uma vez só, e só o semáforo e o
# GitHub ligam duas sessões; a caixa de correio do PR #1019 caiu por must-fix)

TEXTOS_DA_ONDA = [ONDA, PROMPTS, MONTAR]

CAIXA_DE_CORREIO = [
    r"Rabo da onda",  # a linha que a sessão anterior acrescentava
    r"acrescent\w*[^.\n]*passagem",
    r"passagem[^.\n]*acrescent",
    r"(sessão|onda) (seguinte|anterior)[^.\n]*\besper",
    r"\besper\w*[^.\n]*(sessão|onda) anterior",
]


@pytest.mark.parametrize("caminho", TEXTOS_DA_ONDA, ids=lambda p: str(p.relative_to(SKILLS)))
def test_nenhum_texto_acrescenta_linha_a_passagem_nem_manda_sessao_esperar_outra(caminho):
    texto = ler(caminho)
    achados = [(padrao, li) for li in texto.splitlines() for padrao in CAIXA_DE_CORREIO if re.search(padrao, li)]
    assert achados == [], achados


def test_a_passagem_e_escrita_uma_vez_so_antes_do_rabo():
    escrever = next(li for li in passo(5).splitlines() if li.lstrip().startswith("2. Escreva a **passagem**"))
    assert "uma vez só" in escrever and "a linha `Em deploy`" in escrever, escrever
    assert re.search(r"[Dd]epois do lançamento ela não muda", escrever), escrever


def test_nenhum_texto_da_onda_manda_forcar_a_trava():
    for caminho in (ONDA, PROMPTS):
        assert "--forcar" not in ler(caminho), caminho


# ------------------------------------------- o que sobra na sessão, por saída do rabo


def item_da_saida(codigo: str) -> str:
    itens = [li for li in passo(6).splitlines() if f"Saída `{codigo}`" in li]
    assert len(itens) == 1, (codigo, itens)
    return itens[0]


def test_saida_2_com_pr_bloqueado_poe_a_issue_em_blocked_sem_contar_tentativa():
    item = item_da_saida("2")
    regra = re.search(r"Linha `de fora: #<PR> bloqueada por #<X>`[^.]*\.[^.]*\.", item)
    assert regra, item
    assert "--add-label blocked" in regra.group(0) and "sem contar tentativa" in regra.group(0), regra.group(0)


def test_saida_8_deixa_os_prs_abertos_notifica_e_registra_a_parada():
    item = item_da_saida("8")
    assert "PRs verdes ficam abertos" in item and "PushNotification" in item, item
    assert "comentário da onda" in item and "Sinal final" in item, item
    assert "Não conta tentativa" in item, item


def test_a_adr_0064_registra_a_emenda_sob_a_decisao_6a():
    adr = ler(RAIZ / "docs" / "adr" / "0064-revisao-so-must-fix-e-merge-pr-a-pr-sem-em-dia-com-a-base.md")
    decisao_6 = re.search(r"^6\. \*\*Deploy fora do caminho crítico\.\*\*.*?(?=^## )", adr, re.S | re.M).group(0)
    emenda = next(li for li in decisao_6.splitlines() if "Emenda de 06/10/2026 (grilling da #999)" in li)
    for trecho in ("a onda seguinte não lê nada da anterior", "marca a trava como parada",
                   "sai na hora com 8", "caixa de correio", "PR #1019"):
        assert trecho in emenda, (trecho, emenda)
    emenda_das_decisoes = next(li for li in ler(SKILLS / "onda-enxuta" / "references" / "decisoes.md").splitlines()
                               if "decisão 6a" in li)
    assert "não lê nada da anterior" in emenda_das_decisoes, emenda_das_decisoes


def test_saida_6_segue_para_a_medicao_sem_voltar_aos_passos_4_e_5():
    # com as issues reabertas e os PRs já mergeados, voltar ao `### 4.` deixa o lote
    # "verde ou baixado" e o `### 5.` relançaria `<nome>-onda<N+1>` uma segunda vez
    item = item_da_saida("6")
    assert "segue para o passo 4" not in item, item
    assert "item 4 deste passo (medição)" in item, item
    assert "sem voltar aos passos 4 e 5" in item, item
    assert "nem lançar a onda seguinte de novo" in item, item


def test_tabela_de_scripts_lista_a_parada():
    tabela = next(li for li in ler(ONDA).splitlines() if li.startswith("| `scripts/fechar_onda.py"))
    assert "8 parada" in tabela, tabela
