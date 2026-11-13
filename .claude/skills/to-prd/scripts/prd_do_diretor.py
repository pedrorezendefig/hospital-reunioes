"""O Refino da Demanda do diretor no terminal (PRD #240 do PedroOS).

O "Criar o card" da aba Tecnologia cria a issue da Demanda (ADR 0077): a
melhoria já nasce com o PRD inteiro, "Decisões de implementação" inclusive, em
`needs-triage`; o bug nasce com o Roteiro do bug, em `ready-for-agent`. O
Refino (`/grill-with-docs #N`, aberto pelo botão Refinar do PedroOS) lê a
issue, diz se o pedido é viável e grava o resultado na mesma issue.

Uso:
  python3 prd_do_diretor.py ler <N>                                  roteiro do Refino
  python3 prd_do_diretor.py completar <N> <arquivo> [--painel <url>]  grava o Refino na issue

`ler` só lê. `completar` lê o arquivo do Refino (`## Refino`, `## O que muda`
e, quando há, `## Perguntas para o diretor`), escreve a seção do Refino e a
lista de perguntas antes da Origem, troca a linha "O que muda" do bloco do
diretor pelo Veredito, grava a marca de Refino (com o link do painel) e mexe
nas labels: com pergunta aberta a issue fica em Triagem (`needs-triage`); sem
pergunta ela vai para `ready-for-agent`. Refinar de novo troca o Refino
anterior. O resto do corpo fica byte a byte.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

MARCADOR_DA_DEMANDA = re.compile(r'<!--\s*demanda-vitta id="[^"]*"\s*-->')
# a marca que o coletor do PedroOS lê (coletor/collect.py, MARCADOR_REFINO): a Demanda refinada e o link do painel
MARCA_DE_REFINO = re.compile(r"<!-- refino(?:: (\S+))? -->")
LINK_HTTPS = re.compile(r"https://[^\s<>\"']+")
# o cabeçalho do bloco que o app mostra ao diretor ("## 👔 Para o diretor"); a seção das perguntas não é ele
CABECALHO_DO_DIRETOR = re.compile(r"^#{1,6}(?![^\n]*Perguntas)[^\n]*para o diretor[^\n]*$", re.IGNORECASE | re.MULTILINE)
LINHA_O_QUE_MUDA = re.compile(r"^\*\*O que muda:\*\*.*$", re.MULTILINE)

TITULO_TOMADAS = "Já decidido pelo diretor (não pergunte de novo):"
TITULO_EM_ABERTO = "Ficou em aberto (a Leitura começa por aqui):"
NAO_E_DEMANDA = "Não é Demanda do diretor (sem o marcador da Demanda): siga o /grill-with-docs normal."
SECOES_OBRIGATORIAS = ("Decisões de implementação", "Decisões de teste")
SECOES_TECNICAS = (*SECOES_OBRIGATORIAS, "Fora de escopo", "Notas adicionais")
SECAO_DO_REFINO = "Refino"
SECAO_DAS_PERGUNTAS = "Perguntas para o diretor"


def _achar(corpo: str, titulo: str) -> tuple[int, int, int] | None:
    """(início do cabeçalho, fim do cabeçalho, fim da seção) de `## titulo`; a seção vai até o próximo `## ` ou marcador."""
    m = re.search(rf"^## {re.escape(titulo)}[ \t]*$", corpo, re.MULTILINE)
    if not m:
        return None
    fim = re.search(r"^## |^<!--", corpo[m.end() :], re.MULTILINE)
    return m.start(), m.end(), m.end() + (fim.start() if fim else len(corpo) - m.end())


def _secao(corpo: str, titulo: str) -> str | None:
    achado = _achar(corpo, titulo)
    return corpo[achado[1] : achado[2]].strip() if achado else None


def _sem_secao(corpo: str, titulo: str) -> str:
    achado = _achar(corpo, titulo)
    return corpo[: achado[0]] + corpo[achado[2] :] if achado else corpo


def _itens(texto: str | None) -> list[str]:
    return [linha[2:].strip() for linha in (texto or "").splitlines() if linha.startswith("- ") and linha[2:].strip()]


def ler(corpo: str) -> dict:
    em_aberto = _secao(corpo, "Ficou em aberto")
    marca = MARCA_DE_REFINO.search(corpo)
    return {
        "demanda": bool(MARCADOR_DA_DEMANDA.search(corpo)),
        "tipo": "melhoria" if em_aberto is not None else "bug" if _secao(corpo, "O bug") is not None else None,
        "decisoes": _secao(corpo, "Decisões de negócio") or "",
        "em_aberto": _itens(em_aberto),
        "bug": _secao(corpo, "O bug") or "",
        "completo": _secao(corpo, "Decisões de implementação") is not None,
        "refinada": bool(marca),
        "painel": marca.group(1) if marca and marca.group(1) and LINK_HTTPS.fullmatch(marca.group(1)) else None,
        "perguntas": _itens(_secao(corpo, SECAO_DAS_PERGUNTAS)),
    }


def mensagem_ao_diretor(titulo: str, perguntas: list[str]) -> str:
    """A mensagem que o Pedro cola no WhatsApp do diretor com as perguntas abertas."""
    pedido = f' "{titulo.strip()}"' if titulo.strip() else ""
    pedir = "uma coisa" if len(perguntas) == 1 else "umas coisas"
    linhas = [f"E aí, tudo bem? Olhei o seu pedido{pedido} e, antes de começar, preciso que você me responda {pedir}:", ""]
    linhas += [f"{n}. {p}" for n, p in enumerate(perguntas, start=1)]
    linhas += ["", "Me responde por aqui quando puder, tá? Qualquer coisa me chama."]
    return "\n".join(linhas)


def roteiro_do_grill(corpo: str, titulo: str = "") -> str:
    """O que o /grill-with-docs #N mostra antes da Leitura."""
    lido = ler(corpo)
    if not lido["demanda"]:
        return NAO_E_DEMANDA
    if lido["tipo"] == "bug":
        linhas = [
            "Refino curto do bug do diretor: Leitura e Veredito (dá para repetir? onde está a causa provável?). "
            "Pergunte só quando houver dúvida.",
            "",
            "O bug, nas palavras do diretor:",
            "",
            lido["bug"],
        ]
    elif lido["tipo"] == "melhoria":
        linhas = ["Refino da melhoria do diretor: Leitura, Veredito e Escolhas.", "", TITULO_TOMADAS, ""]
        linhas += [lido["decisoes"] or "(nenhuma)", "", TITULO_EM_ABERTO, ""]
        linhas += [f"- {item}" for item in lido["em_aberto"]] or ["(nada; vá direto à Leitura)"]
        if not lido["completo"]:
            linhas += ["", "Atenção: card antigo, sem Decisões de implementação: o arquivo do Refino traz também "
                       "## Decisões de implementação e ## Decisões de teste."]
    else:
        linhas = ["Demanda do diretor fora do formato do card novo: leia a issue inteira e faça o Refino completo."]
    if lido["refinada"]:
        linhas += ["", "Atenção: esta Demanda já foi refinada. Refinar de novo troca a seção do Refino."]
        if lido["perguntas"]:
            linhas += ["Perguntas abertas para o diretor:", *[f"- {p}" for p in lido["perguntas"]], ""]
            linhas += ["Mensagem para colar no WhatsApp:", "", mensagem_ao_diretor(titulo, lido["perguntas"])]
        else:
            linhas += ["Nenhuma pergunta aberta para o diretor."]
    return "\n".join(linhas)


def _troca_o_que_muda(corpo: str, veredito: str) -> str:
    """A linha "O que muda" do bloco do diretor (até o primeiro `---`) passa a dizer o Veredito."""
    cabecalho = CABECALHO_DO_DIRETOR.search(corpo)
    if not cabecalho:
        raise ValueError('a issue não tem o bloco "Para o diretor"')
    fim = re.search(r"^-{3,}\s*$", corpo[cabecalho.end() :], re.MULTILINE)
    limite = cabecalho.end() + (fim.start() if fim else len(corpo) - cabecalho.end())
    linha = LINHA_O_QUE_MUDA.search(corpo, cabecalho.end(), limite)
    if not linha:
        raise ValueError('o bloco "Para o diretor" não tem a linha **O que muda:**')
    return corpo[: linha.start()] + f"**O que muda:** {veredito}" + corpo[linha.end() :]


def completar(corpo: str, refino: str, painel: str | None = None) -> tuple[str, list[str]]:
    """O corpo com o Refino gravado e as perguntas abertas para o diretor."""
    lido = ler(corpo)
    if not lido["demanda"]:
        raise ValueError("a issue não é Demanda do diretor; use o /to-prd normal")
    if CABECALHO_DO_DIRETOR.search(refino):
        raise ValueError('o bloco "Para o diretor" é do app; o Refino só troca a linha O que muda')
    texto = _secao(refino, SECAO_DO_REFINO)
    if not texto:
        raise ValueError("faltou a seção ## Refino (Leitura, Veredito e, na melhoria, Escolhas)")
    veredito = " ".join((_secao(refino, "O que muda") or "").split())
    if not veredito:
        raise ValueError("faltou a seção ## O que muda (o Veredito em palavras simples, para o diretor)")
    if painel is not None and not LINK_HTTPS.fullmatch(painel):
        raise ValueError("o link do painel precisa começar por https://")
    tecnicas = [(t, _secao(refino, t)) for t in SECOES_TECNICAS if _secao(refino, t) is not None]
    if lido["completo"] and tecnicas:
        raise ValueError("a issue já tem Decisões de implementação; as Escolhas vão na seção do Refino")
    if not lido["completo"] and lido["tipo"] == "melhoria":
        for titulo in SECOES_OBRIGATORIAS:
            if _secao(refino, titulo) is None:
                raise ValueError(f"faltou a seção ## {titulo} (o card antigo ainda não tem)")
    perguntas = _itens(_secao(refino, SECAO_DAS_PERGUNTAS))
    painel = painel or lido["painel"]

    novo = MARCA_DE_REFINO.sub("", _sem_secao(_sem_secao(corpo, SECAO_DO_REFINO), SECAO_DAS_PERGUNTAS)).rstrip()
    novo = _troca_o_que_muda(novo, veredito)
    bloco = "".join(f"## {t}\n\n{s}\n\n" for t, s in tecnicas)
    bloco += f"## {SECAO_DO_REFINO}\n\n{texto}\n\n" + (f"Painel do Refino: {painel}\n\n" if painel else "")
    if perguntas:
        bloco += f"## {SECAO_DAS_PERGUNTAS}\n\n" + "\n".join(f"- {p}" for p in perguntas) + "\n\n"
    origem = re.search(r"^## Origem\s*$", novo, re.MULTILINE) or MARCADOR_DA_DEMANDA.search(novo)
    novo = novo[: origem.start()] + bloco + novo[origem.start() :]
    marca = f"<!-- refino: {painel} -->" if painel else "<!-- refino -->"
    return f"{novo.rstrip()}\n{marca}", perguntas


def labels_do_refino(labels: list[str], perguntas: list[str]) -> dict[str, list[str]]:
    """Com pergunta aberta a issue fica (ou volta) em Triagem; sem pergunta ela vai para o agente."""
    fica, sai = ("needs-triage", "ready-for-agent") if perguntas else ("ready-for-agent", "needs-triage")
    return {"add": [fica] if fica not in labels else [], "remove": [sai] if sai in labels else []}


def _gh(*args: str) -> str:
    return subprocess.run(["gh", *args], capture_output=True, text=True, check=True).stdout


def _gravar(numero: str, corpo: str, mudar: dict[str, list[str]], gh) -> None:
    with tempfile.NamedTemporaryFile("w", suffix=".md", encoding="utf-8", delete=False) as f:
        f.write(corpo)
    args = ["issue", "edit", numero, "--body-file", f.name]
    args += [a for l in mudar["add"] for a in ("--add-label", l)]
    args += [a for l in mudar["remove"] for a in ("--remove-label", l)]
    try:
        gh(*args)
    finally:
        Path(f.name).unlink(missing_ok=True)


def main(argv: list[str], gh=_gh) -> int:
    if len(argv) == 2 and argv[0] == "ler" and argv[1].isdigit():
        dados = json.loads(gh("issue", "view", argv[1], "--json", "body,title"))
        print(roteiro_do_grill(dados.get("body") or "", dados.get("title") or ""))
        return 0
    painel_ok = len(argv) == 3 or (len(argv) == 5 and argv[3] == "--painel")
    if argv and argv[0] == "completar" and painel_ok and argv[1].isdigit():
        numero, arquivo = argv[1], argv[2]
        dados = json.loads(gh("issue", "view", numero, "--json", "body,labels,title"))
        try:
            novo, perguntas = completar(dados.get("body") or "", Path(arquivo).read_text(encoding="utf-8"),
                                        argv[4] if len(argv) == 5 else None)
        except ValueError as erro:
            print(f"não gravei o Refino na #{numero}: {erro}", file=sys.stderr)
            return 1
        labels = [l["name"] for l in dados.get("labels") or []]
        _gravar(numero, novo, labels_do_refino(labels, perguntas), gh)
        print(f"Refino gravado na #{numero}: a issue ganhou a marca Refinada.")
        if perguntas:
            print("A issue fica em Triagem até o diretor responder. Mensagem para colar no WhatsApp:\n")
            print(mensagem_ao_diretor(dados.get("title") or "", perguntas))
        else:
            print("Sem pergunta aberta para o diretor: a issue está em ready-for-agent.")
        return 0
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
