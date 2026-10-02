#!/usr/bin/env python3
"""Roteiro de prints do módulo Reuniões e metas (ADR 0057, decisões 3 e 4).

Cada print do manual é tela real do app rodando em localhost, capturada por
este roteiro, e não recorte feito à mão: quando a tela muda, é este arquivo que
roda de novo e refaz as imagens. Os balões numerados do Print de passo são
desenhados aqui, por cima da tela, antes da captura.

Receita:

1. Supabase local no ar (`supabase start` em `hospital-reunioes/`).
2. Stack do app com o código que o print vai mostrar:
   `bash .claude/skills/atualizar-app/scripts/apply.sh`.
3. Dados de exemplo do módulo (as pessoas fictícias, a reunião de exemplo e as
   pendências nos seis estados): `python3 docs/manual/prints/reunioes.py
   --semear`. É idempotente e recusa rodar contra qualquer banco que não seja o
   local.
4. `python3 docs/manual/prints/reunioes.py`.

**Dado de gente de verdade.** O banco local tem participantes reais do
hospital, e as telas deste módulo são cheias de nome de pessoa: lista de
participantes, responsável da pendência, menção no comentário. Por isso o
roteiro nunca abre uma lista de pessoas inteira. Onde a tela oferece busca, ele
digita o que casa só com as pessoas de exemplo (todas em `@exemplo.local`); nas
telas de acompanhamento, as únicas pendências do banco local são as que este
roteiro semeia.

**Quem entra em cada print.** A Secretária não vê Pendências, Dashboard nem Ata
Guiada, então a tela dela sai logada como a Secretária de exemplo. O resto sai
logado como a Facilitadora de exemplo.

Uso: python3 docs/manual/prints/reunioes.py [--base http://localhost:3000]
     [--saida docs/manual/src/assets/reunioes] [--print <nome>] [--semear]
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import TYPE_CHECKING

# O Playwright só é preciso para capturar: `--semear` e a guarda que protege o
# banco rodam sem ele, e é isso que deixa o teste da guarda importar este
# arquivo numa máquina sem navegador instalado.
if TYPE_CHECKING:
    from playwright.sync_api import Page

# Tela de trabalho sentada: reunião se marca e ata se revisa no computador.
COMPUTADOR = {"width": 1440, "height": 900}
ESCALA = 2

ENV_LOCAL = Path(__file__).resolve().parents[3] / "hospital-reunioes" / ".env"

# A base do app em produção, a mesma do roteiro da Ouvidoria: é o domínio do
# frontend no contrato de deploy (`docs/spec/deploy/project.json`).
BASE_DO_APP_EM_PRODUCAO = "https://app.hospitalsaomatheus.cloud"

# O que não pode aparecer num print publicado: o endereço da máquina de quem
# capturou. Os padrões são os mesmos do roteiro da Ouvidoria, e valem pela
# mesma razão: o manual é público.
ENDERECOS_LOCAIS = (
    r"\blocalhost\b",
    r"\b127\.0\.0\.1\b",
    r"\b127\.1\b",
    r"\b0\.0\.0\.0\b",
    r"\[::1\]",
    r"\b192\.168\.\d{1,3}\.\d{1,3}\b",
    r"\b10\.\d{1,3}\.\d{1,3}\.\d{1,3}\b",
    r"\b172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}\b",
    r"\.local\b",
    r"\.internal\b",
    r"\.test\b",
)
RE_ENDERECO_LOCAL = re.compile("|".join(ENDERECOS_LOCAIS), re.IGNORECASE)

# As pessoas de exemplo. Ninguém aqui existe, e `exemplo.local` não é domínio
# de verdade: é o que permite estes prints num repositório público.
# O domínio de todo mundo que este roteiro inventa. Não existe, e é o que
# permite os prints deste módulo num repositório público.
DOMINIO_DE_EXEMPLO = "exemplo.local"

SENHA = "ManualReunioes2026!"
FACILITADORA = ("P920", "Renata Fontes", "renata.fontes@exemplo.local")
SECRETARIA = ("P921", "Beatriz Nunes", "beatriz.nunes@exemplo.local")

# (id, nome, email, cargo, setor, perfil de acesso, super admin)
PESSOAS = [
    (FACILITADORA[0], FACILITADORA[1], FACILITADORA[2], "Coordenação", "Centro de Material e Esterilização", "super_admin", True),
    (SECRETARIA[0], SECRETARIA[1], SECRETARIA[2], None, "Administração", "secretaria", False),
    ("P922", "Tiago Meireles", "tiago.meireles@exemplo.local", "Farmacêutico", "Farmácia", "regular", False),
    ("P923", "Luciana Braga", "luciana.braga@exemplo.local", "Enfermeira", "Unidade de Terapia Intensiva", "regular", False),
    ("P924", "Otávio Serra", "otavio.serra@exemplo.local", "Técnico de Esterilização", "Centro de Material e Esterilização", "regular", False),
]

# A reunião de exemplo que atravessa o manual inteiro: ela é marcada, recebe a
# transcrição, vira ata e solta as pendências. O roteiro ajusta o estado dela
# antes de cada print, porque é a mesma reunião em momentos diferentes.
REUNIAO = "MANREU01"
TITULO_REUNIAO = "Acompanhamento da CME"

# A reunião que já foi para a assinatura e caiu na coleta interna de aceites:
# é dela que nasce o link sem login da tela de Aceite.
REUNIAO_ACEITE = "MANREU02"
TITULO_ACEITE = "Comissão de Farmácia"
TOKEN_ACEITE = "manual-aceite-exemplo-2026"


class EnderecoLocalNoPrint(Exception):
    """O print ia para o manual com o endereço da máquina de quem capturou."""


def exigir_endereco_de_producao(texto_visivel: str, nome: str) -> None:
    """Recusa a captura quando o que a pessoa lê no print traz endereço local.

    Olha o texto visível, e não o HTML: os chunks do frontend citam localhost
    em desenvolvimento sem que nada disso apareça na imagem.

    O domínio das pessoas de exemplo sai da conta antes da conferência. Ele
    termina em `.local`, que é padrão de rede interna e é por isso que a guarda
    o persegue; mas `exemplo.local` não é máquina nenhuma, é o domínio
    inventado que este roteiro semeia justamente para o print não levar e-mail
    de gente de verdade. Casar com ele travaria toda tela deste módulo, que
    mostra o e-mail de quem está logado no canto de cima. Qualquer outro
    `.local` continua recusado.
    """
    sem_exemplo = re.sub(re.escape(DOMINIO_DE_EXEMPLO), "", texto_visivel, flags=re.IGNORECASE)
    achados = sorted({m.group(0) for m in RE_ENDERECO_LOCAL.finditer(sem_exemplo)})
    if achados:
        raise EnderecoLocalNoPrint(
            f"{nome}: o print mostra {', '.join(achados)}. O manual é público: "
            f"monte a tela com {BASE_DO_APP_EM_PRODUCAO} antes de capturar."
        )


def capturar(page, caminho: Path, nome: str, alvo=None, **kwargs) -> None:
    """Confere o texto visível e só então grava a imagem.

    A guarda vive aqui, no caminho por onde todo print passa, e não em cada
    função: print novo nasce protegido sem ninguém lembrar de chamar nada. Por
    isso `alvo` existe: o print de uma janela é a captura daquele elemento, e
    se ela tivesse caminho próprio seria o print que escapa da guarda.
    """
    exigir_endereco_de_producao(page.inner_text("body"), nome)
    (alvo or page).screenshot(path=str(caminho), **kwargs)


# --------------------------------------------------------------------------
# O balão numerado
# --------------------------------------------------------------------------

# O navy do app (`--color-primary` do `globals.css`), a mesma cor do cabeçalho
# das telas: o balão é marcação do manual, mas não é corpo estranho na tela.
NAVY = "#2B2E7E"
DIAMETRO = 28
FOLGA = 6


def balao(page: Page, alvo, numero: int) -> None:
    """Desenha o balão do passo `numero` no canto superior esquerdo do `alvo`.

    `alvo` é um `Locator` (o botão que o passo cita, achado pelo texto de tela)
    ou um seletor CSS. O balão é um `div` injetado no documento, por cima de
    tudo e sem receber clique, e some no recarregamento da página: nada disto
    fica no app, e a marcação regera junto com o print quando a tela muda.
    """
    elemento = page.locator(alvo) if isinstance(alvo, str) else alvo
    elemento.scroll_into_view_if_needed()
    caixa = elemento.bounding_box()
    if caixa is None:
        raise SystemExit(
            f"balão {numero}: o elemento não está na tela, então o balão sairia "
            "solto num canto. Confira o seletor."
        )
    page.evaluate(
        """([x, y, numero, diametro, cor]) => {
            const b = document.createElement('div');
            b.className = 'balao-do-manual';
            b.textContent = String(numero);
            Object.assign(b.style, {
                position: 'absolute',
                left: (x + window.scrollX) + 'px',
                top: (y + window.scrollY) + 'px',
                width: diametro + 'px',
                height: diametro + 'px',
                borderRadius: '9999px',
                background: cor,
                color: '#ffffff',
                font: '700 15px/' + diametro + 'px "HP Simplified", system-ui, sans-serif',
                textAlign: 'center',
                boxShadow: '0 2px 6px rgba(0,0,0,0.35)',
                pointerEvents: 'none',
                zIndex: '2147483647',
            });
            document.body.appendChild(b);
        }""",
        [
            caixa["x"] - DIAMETRO + FOLGA,
            caixa["y"] - DIAMETRO + FOLGA,
            numero,
            DIAMETRO,
            NAVY,
        ],
    )


def limpar_baloes(page: Page) -> None:
    """Tira os balões da tela: a mesma página serve a mais de um print."""
    page.evaluate(
        "document.querySelectorAll('.balao-do-manual').forEach(b => b.remove())"
    )


def tirar_o_foco(page: Page) -> None:
    """O anel de foco num campo vira instrução falsa ('clique aqui')."""
    page.evaluate("document.activeElement && document.activeElement.blur()")


# --------------------------------------------------------------------------
# Login
# --------------------------------------------------------------------------


_QUEM_ENTROU: str | None = None


def entrar(page: Page, base: str, email: str) -> None:
    """Login com uma das pessoas de exemplo, trocando de conta quando precisa.

    A espera é por sair de `/login`: seguir direto para a tela antes disso
    devolve o roteiro ao login e o print sai da tela errada. Quem já está
    logado é lembrado num módulo, e não na página, porque a página é recriada a
    cada navegação e o roteiro refaria o login entre dois prints seguidos.

    Trocar de conta (a tela da Secretaria sai logada como ela) exige apagar a
    sessão do navegador: com ela de pé, `/login` redireciona para dentro do app
    e o campo de e-mail nem chega a existir.
    """
    global _QUEM_ENTROU
    if _QUEM_ENTROU == email:
        return
    if _QUEM_ENTROU is not None:
        page.goto(f"{base}/login", wait_until="domcontentloaded")
        page.evaluate("() => { localStorage.clear(); sessionStorage.clear(); }")
        page.context.clear_cookies()
        _QUEM_ENTROU = None
    campo = page.get_by_placeholder("seu@email.com")
    for tentativa in range(3):
        page.goto(f"{base}/login", wait_until="networkidle")
        try:
            campo.wait_for(timeout=10000)
            break
        except Exception:
            if tentativa == 2:
                raise SystemExit(
                    "o login não abriu: a tela continua entrando com a sessão "
                    "anterior. Feche o navegador do roteiro e rode de novo."
                )
            page.evaluate("() => { localStorage.clear(); sessionStorage.clear(); }")
            page.context.clear_cookies()
    campo.fill(email)
    page.get_by_placeholder("••••••••").fill(SENHA)
    page.get_by_role("button", name="Entrar").click()
    page.wait_for_url(lambda url: "/login" not in url, timeout=30000)
    _QUEM_ENTROU = email


# --------------------------------------------------------------------------
# Dados de exemplo (`--semear`) e o estado da reunião
# --------------------------------------------------------------------------


def _credenciais_locais() -> tuple[str, str]:
    """URL e chave de serviço do `.env` local, nunca de produção."""
    env = {}
    for linha in ENV_LOCAL.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if linha and not linha.startswith("#") and "=" in linha:
            chave, valor = linha.split("=", 1)
            env[chave] = valor.strip().strip('"')
    url = env.get("SUPABASE_URL", "")
    chave = env.get("SUPABASE_SERVICE_KEY") or env.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if "127.0.0.1" not in url and "localhost" not in url:
        raise SystemExit(f"recusado: '{url}' não é o Supabase local.")
    return url, chave


def _rest(caminho: str, metodo="GET", corpo=None, prefer=None):
    url, chave = _credenciais_locais()
    dados = json.dumps(corpo).encode() if corpo is not None else None
    cabecalhos = {
        "apikey": chave,
        "Authorization": f"Bearer {chave}",
        "Content-Type": "application/json",
    }
    if prefer:
        cabecalhos["Prefer"] = prefer
    req = urllib.request.Request(
        f"{url}/rest/v1/{caminho}", data=dados, headers=cabecalhos, method=metodo
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resposta:
            texto = resposta.read().decode()
            return json.loads(texto) if texto.strip() else None
    except urllib.error.HTTPError as e:
        raise SystemExit(f"{metodo} {caminho}: {e.code} {e.read().decode()[:300]}")


def _login_de_exemplo(email: str, nome: str) -> str:
    """Cria (ou reaproveita) o login da pessoa de exemplo no Supabase local.

    O `nome` vai no perfil do login, e não só na tabela de participantes,
    porque é dele que sai o "Olá, Fulano" do Dashboard: sem isso a tela
    cumprimenta o começo do e-mail, e o print mostraria "Olá, renata.fontes".
    """
    url, chave = _credenciais_locais()
    cabecalhos = {
        "apikey": chave,
        "Authorization": f"Bearer {chave}",
        "Content-Type": "application/json",
    }
    corpo = json.dumps(
        {
            "email": email,
            "password": SENHA,
            "email_confirm": True,
            "user_metadata": {"nome": nome},
        }
    ).encode()
    req = urllib.request.Request(f"{url}/auth/v1/admin/users", data=corpo, headers=cabecalhos)
    try:
        with urllib.request.urlopen(req, timeout=20) as resposta:
            return json.load(resposta)["id"]
    except urllib.error.HTTPError as e:
        texto = e.read().decode()
        if e.code not in (400, 422) or "already" not in texto:
            raise SystemExit(f"login {email}: {e.code} {texto[:300]}")
    busca = urllib.request.Request(
        f"{url}/auth/v1/admin/users?page=1&per_page=200",
        headers={"apikey": chave, "Authorization": f"Bearer {chave}"},
    )
    with urllib.request.urlopen(busca, timeout=20) as resposta:
        for usuario in json.load(resposta)["users"]:
            if usuario["email"] != email:
                continue
            # Login de uma rodada anterior: o perfil é atualizado, senão o
            # nome que o Dashboard cumprimenta fica o da primeira vez.
            ajuste = urllib.request.Request(
                f"{url}/auth/v1/admin/users/{usuario['id']}",
                data=json.dumps({"user_metadata": {"nome": nome}}).encode(),
                headers=cabecalhos,
                method="PUT",
            )
            with urllib.request.urlopen(ajuste, timeout=20):
                pass
            return usuario["id"]
    raise SystemExit(f"login {email} não encontrado depois de criado.")


def _dia(delta: int) -> str:
    return (dt.date.today() + dt.timedelta(days=delta)).isoformat()


def _json_da_ata() -> dict:
    """A ata que o assistente escreveria a partir da transcrição de exemplo."""
    return {
        "objetivo": (
            "Acompanhar os indicadores do Centro de Material e Esterilização e "
            "combinar o que cada setor entrega até a próxima reunião."
        ),
        "hora_inicio": "09:00",
        "hora_fim": "10:00",
        "participantes": [
            {"nome": nome, "cargo": cargo or "", "setor": setor or "", "presente": True}
            for _, nome, _, cargo, setor, _, _ in PESSOAS
            if nome != SECRETARIA[1]
        ],
        "discussao": [
            {
                "titulo": "Tempo de giro das autoclaves",
                "descricao": (
                    "O setor apresentou o tempo médio de cada ciclo e mostrou "
                    "onde a fila de material cresce no fim da tarde."
                ),
                "decisao": (
                    "Antecipar o último ciclo do dia em uma hora durante o mês "
                    "de teste."
                ),
                "responsavel": "Otávio Serra",
                "contribuicoes": [
                    {
                        "nome": "Otávio Serra",
                        "funcao": "Técnico de Esterilização - Centro de Material e Esterilização",
                        "conteudo": "Mostrou a fila de material das 17h e o tempo de cada ciclo.",
                    },
                    {
                        "nome": "Luciana Braga",
                        "funcao": "Enfermeira - Unidade de Terapia Intensiva",
                        "conteudo": "Pediu prioridade para as caixas de via aérea difícil.",
                    },
                ],
                "divergencias": [],
            },
            {
                "titulo": "Reposição do material de consumo",
                "descricao": (
                    "A Farmácia apontou atraso na entrega de indicadores "
                    "biológicos e propôs um pedido programado."
                ),
                "decisao": "Passar a fazer o pedido no primeiro dia útil de cada mês.",
                "responsavel": "Tiago Meireles",
                "contribuicoes": [
                    {
                        "nome": "Tiago Meireles",
                        "funcao": "Farmacêutico - Farmácia",
                        "conteudo": "Propôs pedido programado para não faltar indicador biológico.",
                    }
                ],
                "divergencias": [],
            },
        ],
        "quadro_atribuicoes": [
            {
                "acao": "Revisar o fluxo de esterilização do instrumental cirúrgico",
                "responsavel": "Otávio Serra",
                "cargo": "Técnico de Esterilização",
                "prazo": _dia(9),
                "entregavel": "Fluxo revisado e afixado no setor",
                "objetivo_meta": "Reduzir a fila de material do fim da tarde",
                "status": "ABERTO",
            },
            {
                "acao": "Atualizar a escala de plantão da UTI",
                "responsavel": "Luciana Braga",
                "cargo": "Enfermeira",
                "prazo": _dia(5),
                "entregavel": "Escala publicada no mural",
                "objetivo_meta": "Garantir cobertura no turno da noite",
                "status": "ABERTO",
            },
        ],
    }


# (id, descrição, responsável, prazo, estado, entregável)
PENDENCIAS = [
    ("MANP01", "Revisar o fluxo de esterilização do instrumental cirúrgico", "P924", 9, "PENDENTE", "Fluxo revisado e afixado no setor"),
    ("MANP02", "Atualizar a escala de plantão da UTI", "P923", 5, "EM_PROGRESSO", "Escala publicada no mural"),
    ("MANP03", "Conferir o estoque de indicadores biológicos", "P922", -4, "CONCLUIDO", "Planilha de conferência assinada"),
    ("MANP04", "Publicar o relatório de indicadores do trimestre", "P920", -6, "ATRASADO", "Relatório no painel do setor"),
    ("MANP05", "Treinar a equipe no novo formulário de rastreabilidade", "P923", None, "REPACTUADA", "Lista de presença do treinamento"),
    ("MANP06", "Revisar o contrato de manutenção das autoclaves", "P924", 2, "PENDENTE", "Contrato revisado com o setor de compras"),
    ("MANP07", "Comprar carrinho de emergência para a Farmácia", "P922", 14, "CANCELADO", "Carrinho recebido e conferido"),
]

# O comentário de exemplo e a menção que ele gera. Ele mora numa pendência só
# (MANP06), e as duas telas que precisam do histórico vazio usam outra: sem
# isso, o print do passo que mostra "Sem rastros de atividade." envelheceria na
# primeira vez que este roteiro rodasse.
PENDENCIA_COM_COMENTARIO = "MANP06"
PENDENCIA_SEM_COMENTARIO = "MANP01"
AUTOR_DO_COMENTARIO = "P922"
MENCIONADO = FACILITADORA[0]
# As duas pendências que os prints da Lista citam pelo nome, e não pela ordem:
# a tabela ordena pelo prazo, e prender um balão à "primeira linha" faria o
# print apontar outra pendência assim que uma data virasse.
PENDENCIA_ATRASADA = "Publicar o relatório de indicadores do trimestre"
COMENTARIO_DE_EXEMPLO = (
    "@Renata Fontes o setor de compras pediu o parecer técnico antes de "
    "renovar. Consegue olhar esta semana?"
)


def semear() -> None:
    """As pessoas, as duas reuniões de exemplo e as pendências dos seis estados."""
    # A guarda do banco roda no primeiro passo, antes de montar qualquer linha:
    # o dano aqui é escrita, e criar login é a primeira coisa que aconteceria.
    _credenciais_locais()

    por_id = {}
    for pid, nome, email, cargo, setor, perfil, super_admin in PESSOAS:
        por_id[pid] = nome
        _rest(
            "participantes",
            "POST",
            [
                {
                    "id": pid,
                    "nome_completo": nome,
                    "email": email,
                    "cargo": cargo,
                    "setor": setor,
                    "ativo": True,
                    "access_profile": perfil,
                    "is_super_admin": super_admin,
                    "is_externo": False,
                    "auth_user_id": _login_de_exemplo(email, nome),
                }
            ],
            prefer="resolution=merge-duplicates",
        )

    roster = [pid for pid, *_ in PESSOAS if pid != SECRETARIA[0]]

    # Uma chamada por reunião: o PostgREST recusa um lote cujos objetos não
    # têm exatamente as mesmas chaves, e as duas reuniões estão em momentos
    # diferentes do caminho.
    _rest(
        "reunioes",
        "POST",
        [
            {
                "id_reuniao": REUNIAO,
                "titulo": TITULO_REUNIAO,
                "data": _dia(1),
                "hora_inicio": "09:00:00",
                "hora_fim": "10:00:00",
                "tipo": "Coordenação",
                "facilitador_id": FACILITADORA[0],
                "setor": "Centro de Material e Esterilização",
                "objetivo": "Acompanhar os indicadores do setor e as ações da última reunião.",
                "status_ata": "PROGRAMADA",
                "fonte": "MOCK",
            }
        ],
        prefer="resolution=merge-duplicates",
    )
    _rest(
        "reunioes",
        "POST",
        [
            {
                "id_reuniao": REUNIAO_ACEITE,
                "titulo": TITULO_ACEITE,
                "data": _dia(-7),
                "hora_inicio": "14:00:00",
                "hora_fim": "15:00:00",
                "tipo": "Gerencial",
                "facilitador_id": FACILITADORA[0],
                "setor": "Farmácia",
                "objetivo": "Revisar a padronização dos medicamentos de alta vigilância.",
                "status_ata": "AGUARDANDO_ASSINATURA",
                "json_ata": _json_da_ata(),
                "envelope_key_clicksign": "envelope-de-exemplo-do-manual",
                "modo_interno_desde": dt.datetime.now(dt.timezone.utc).isoformat(),
                "fonte": "MOCK",
            },
        ],
        prefer="resolution=merge-duplicates",
    )

    for id_reuniao in (REUNIAO, REUNIAO_ACEITE):
        existentes = {
            linha["participante_id"]
            for linha in _rest(
                f"reuniao_participantes?id_reuniao=eq.{id_reuniao}&select=participante_id"
            )
        }
        novos = [
            {"id_reuniao": id_reuniao, "participante_id": pid}
            for pid in roster
            if pid not in existentes
        ]
        if novos:
            _rest("reuniao_participantes", "POST", novos)

    _rest(
        "pendencias",
        "POST",
        [
            {
                "id_acao": pid,
                "id_reuniao": REUNIAO,
                "descricao_acao": descricao,
                "responsavel_id": responsavel,
                "responsavel_nome": por_id[responsavel],
                "cargo": dict((p[0], p[3]) for p in PESSOAS)[responsavel],
                "prazo": None if prazo is None else _dia(prazo),
                "meta_entregavel": entregavel,
                "status": estado,
            }
            for pid, descricao, responsavel, prazo, estado, entregavel in PENDENCIAS
        ],
        prefer="resolution=merge-duplicates",
    )

    token_hash = hashlib.sha256(TOKEN_ACEITE.encode()).hexdigest()
    ja_tem = _rest(
        f"reuniao_aceite_tokens?id_reuniao=eq.{REUNIAO_ACEITE}"
        f"&participante_id=eq.P923&select=id,token_hash"
    )
    if not ja_tem:
        _rest(
            "reuniao_aceite_tokens",
            "POST",
            [
                {
                    "id_reuniao": REUNIAO_ACEITE,
                    "participante_id": "P923",
                    "token_hash": token_hash,
                }
            ],
        )
    else:
        _rest(
            f"reuniao_aceite_tokens?id=eq.{ja_tem[0]['id']}",
            "PATCH",
            {"token_hash": token_hash, "usado_em": None},
        )

    # O comentário com menção e o aviso que ele acende no sino. Os dois são
    # apagados e refeitos a cada semeadura: sem isso o histórico cresceria uma
    # linha por rodada e o sino acumularia avisos, e os dois prints mudariam
    # sozinhos de uma captura para a outra.
    _rest(f"comentarios_pendencias?id_acao=eq.{PENDENCIA_COM_COMENTARIO}", "DELETE")
    _rest(
        f"notificacoes?referencia_id=eq.{PENDENCIA_COM_COMENTARIO}&tipo=eq.MENCAO",
        "DELETE",
    )
    descricao = {p[0]: p[1] for p in PENDENCIAS}[PENDENCIA_COM_COMENTARIO]
    _rest(
        "comentarios_pendencias",
        "POST",
        [
            {
                "id_acao": PENDENCIA_COM_COMENTARIO,
                "autor_id": AUTOR_DO_COMENTARIO,
                "autor_nome": por_id[AUTOR_DO_COMENTARIO],
                "conteudo": COMENTARIO_DE_EXEMPLO,
                "mencoes": [MENCIONADO],
            }
        ],
    )
    _rest(
        "notificacoes",
        "POST",
        [
            {
                "destinatario_id": MENCIONADO,
                "tipo": "MENCAO",
                "titulo": f"{por_id[AUTOR_DO_COMENTARIO]} mencionou você",
                "mensagem": f"Menção em: {descricao[:80]}",
                "referencia_id": PENDENCIA_COM_COMENTARIO,
                "lida": False,
            }
        ],
    )

    print("dados de exemplo do módulo Reuniões e metas prontos.")


def por_reuniao(**campos) -> None:
    """Põe a reunião de exemplo no momento que o próximo print precisa mostrar.

    A mesma reunião aparece Programada, em Processando IA e em Validação
    Necessária ao longo do manual, porque é uma reunião só atravessando o
    caminho inteiro. Mudar o estado aqui é o que deixa cada print ser a tela de
    verdade daquele momento, e não uma reunião diferente por passo.
    """
    _rest(f"reunioes?id_reuniao=eq.{REUNIAO}", "PATCH", campos)


# --------------------------------------------------------------------------
# Prints
# --------------------------------------------------------------------------


def _dia_livre() -> int:
    """Um dia do mês que está na tela e não tem reunião de exemplo.

    O print do passo "clique no dia da reunião" precisa de uma célula vazia, e
    o calendário abre no mês de hoje: por isso o dia sai de hoje, e não de uma
    data escrita à mão que sairia do mês na virada.
    """
    hoje = dt.date.today()
    return hoje.day + 4 if hoje.day <= 20 else hoje.day - 4


def _numero_do_dia(page: Page, dia: int):
    """O número do dia no calendário: é nele que o balão do passo se ancora.

    Ancorar na célula inteira jogaria o balão para o canto de cima dela, que na
    grade do mês é a linha da semana anterior, e o leitor leria o balão na
    semana errada.
    """
    return page.get_by_text(str(dia), exact=True).first


def _celula_do_dia(page: Page, dia: int):
    """A célula inteira do dia: é ela que abre a janela de agendar."""
    return _numero_do_dia(page, dia).locator("xpath=..")


def _menu(page: Page, rotulo: str):
    """O item do menu lateral, pelo texto que a pessoa lê nele."""
    return page.get_by_role("link", name=rotulo, exact=True).first


def calendario(page: Page, base: str, saida: Path) -> None:
    """A tela do Calendário: o item do menu e o dia que se clica para marcar."""
    entrar(page, base, FACILITADORA[2])
    page.set_viewport_size(COMPUTADOR)
    page.goto(f"{base}/reunioes/calendario", wait_until="networkidle")
    page.get_by_text("Calendário de Reuniões").wait_for()
    page.wait_for_timeout(1500)
    balao(page, _menu(page, "Calendário"), 1)
    balao(page, _numero_do_dia(page, _dia_livre()), 2)
    # A grade do mês é mais alta que a tela: sem a página inteira, o print sai
    # cortado no meio da semana, sem o menu que o passo 1 manda clicar.
    page.evaluate("window.scrollTo(0, 0)")
    capturar(page, saida / "calendario.png", "calendario", full_page=True)
    limpar_baloes(page)


def agendar_reuniao(page: Page, base: str, saida: Path) -> None:
    """A janela que o dia abre, preenchida como quem marca preencheria.

    O formulário é preenchido e NÃO é enviado: o banco local é compartilhado, e
    a reunião de exemplo já existe. A janela é alta, então a captura abre uma
    tela mais alta que o padrão para o print sair com a janela inteira em vez
    de cortada no meio do formulário.
    """
    entrar(page, base, FACILITADORA[2])
    page.set_viewport_size({"width": COMPUTADOR["width"], "height": 1400})
    page.goto(f"{base}/reunioes/calendario", wait_until="networkidle")
    page.get_by_text("Calendário de Reuniões").wait_for()
    page.wait_for_timeout(1500)
    _celula_do_dia(page, _dia_livre()).click()
    page.get_by_role("heading", name="Agendar Reunião").wait_for()
    page.wait_for_timeout(1000)

    # A janela inteira, e não a faixa do título: é o `max-w-2xl` que embrulha
    # cabeçalho, formulário e botões, e o `rounded` mais perto do título é só o
    # cabeçalho.
    modal = page.get_by_role("heading", name="Agendar Reunião").locator(
        "xpath=ancestor::div[contains(@class,'max-w-2xl')][1]"
    )
    page.get_by_placeholder("Ex: Reunião de Diretoria, Abril 2026").fill(TITULO_REUNIAO)
    modal.get_by_role("combobox").first.click()
    page.get_by_role("option", name="Coordenação").click()
    page.get_by_role("button", name="09:00", exact=True).click()
    page.get_by_placeholder("Descreva a pauta da reunião...").fill(
        "Indicadores do setor e as ações combinadas na última reunião."
    )
    # A busca por sobrenome casa só as pessoas de exemplo. Sem ela, a lista de
    # participantes disponíveis abre com nome e setor de gente de verdade do
    # hospital, e o manual é público.
    for nome, sobrenome in (("Otávio Serra", "Serra"), ("Luciana Braga", "Braga")):
        busca = page.get_by_placeholder("Buscar participante...")
        busca.fill(sobrenome)
        page.get_by_text(f'RESULTADOS PARA "{sobrenome.upper()}"').wait_for()
        page.get_by_text(nome, exact=True).first.click()
        page.wait_for_timeout(500)
    # A última pessoa fica no meio do caminho, com a busca escrita e o
    # resultado na tela: é o passo 5 acontecendo. Com a busca em branco a tela
    # lista o cadastro inteiro, que é nome e setor de gente de verdade, e a
    # lista não fecha (ela nasce aberta e fica).
    page.get_by_placeholder("Buscar participante...").fill("Meireles")
    page.get_by_text('RESULTADOS PARA "MEIRELES"').wait_for()
    tirar_o_foco(page)
    page.wait_for_timeout(800)

    # A janela tem rolagem própria: se ela tiver rolado, o balão (que se ancora
    # na posição da tela) sai longe do campo que o passo cita, e o print mente.
    page.evaluate(
        "el => el.scrollTop = 0",
        modal.element_handle(),
    )
    page.wait_for_timeout(300)
    balao(page, page.get_by_placeholder("Ex: Reunião de Diretoria, Abril 2026"), 3)
    balao(page, page.get_by_text("Horário da Reunião"), 4)
    balao(page, page.get_by_placeholder("Buscar participante..."), 5)
    balao(page, modal.get_by_role("button", name="Agendar Reunião"), 6)
    rolagem = page.evaluate("el => el.scrollTop", modal.element_handle())
    if rolagem:
        raise SystemExit(
            "agendar-reuniao: a janela rolou por dentro antes da captura "
            f"({rolagem}px), então os balões não estão sobre os campos. Abra a "
            "captura numa tela mais alta."
        )
    capturar_bloco(page, saida / "agendar-reuniao.png", "agendar-reuniao", modal)
    limpar_baloes(page)


def marcar_nova_reuniao(page: Page, base: str, saida: Path) -> None:
    """A tela da Secretaria, com o campo que a do Facilitador não tem.

    Sai logada como a Secretária de exemplo: é a tela dela, e o menu da
    Secretaria (Início, Nova reunião, Calendário) faz parte do que o passo 1
    manda clicar. O formulário é preenchido e NÃO é enviado.
    """
    entrar(page, base, SECRETARIA[2])
    page.set_viewport_size(COMPUTADOR)
    page.goto(f"{base}/secretaria/nova", wait_until="networkidle")
    page.get_by_role("heading", name="Marcar nova reunião").wait_for()
    page.wait_for_timeout(1500)

    page.get_by_placeholder("Ex: Reunião de Diretoria, junho 2026").fill(TITULO_REUNIAO)
    page.locator("input[type=date]").fill(_dia(4))
    page.locator("input[type=time]").first.fill("09:00")
    page.locator("input[type=time]").last.fill("10:00")
    page.get_by_role("combobox").first.click()
    page.get_by_role("option", name="Coordenação").click()

    # A lista de facilitadores é gente de verdade com o acesso mais alto: ela
    # abre, recebe o sobrenome da facilitadora de exemplo e fecha na escolha.
    page.get_by_role("button", name="Selecione um facilitador").click()
    page.get_by_placeholder("Buscar facilitador...").fill("Fontes")
    page.get_by_role("button", name=FACILITADORA[1], exact=False).first.click()

    # O campo de participantes perde o texto de convite assim que o facilitador
    # entra nele sozinho, então quem o acha é o papel, não o rótulo.
    participantes = page.locator("div[role=button][aria-haspopup=listbox]")
    participantes.click()
    for nome in ("Otávio Serra", "Luciana Braga"):
        page.get_by_role("main").get_by_placeholder("Buscar...").fill(nome.split()[-1])
        page.get_by_text(nome, exact=False).last.click()
    # Clicar fora fecha a lista, que de aberta mostraria o cadastro inteiro.
    page.get_by_role("heading", name="Marcar nova reunião").click()
    page.wait_for_timeout(500)

    page.get_by_placeholder(
        "Descreva o que será discutido, o que precisa ser decidido, etc."
    ).fill("Indicadores do setor e as ações combinadas na última reunião.")
    tirar_o_foco(page)
    page.evaluate("window.scrollTo(0, 0)")
    page.wait_for_timeout(600)

    balao(page, _menu(page, "Nova reunião"), 1)
    balao(page, page.get_by_placeholder("Ex: Reunião de Diretoria, junho 2026"), 2)
    balao(page, page.get_by_role("combobox").first, 3)
    balao(page, page.get_by_role("button", name=FACILITADORA[1], exact=False).first, 4)
    balao(page, participantes, 5)
    balao(page, page.get_by_role("button", name="Agendar reunião"), 6)
    capturar(page, saida / "marcar-nova-reuniao.png", "marcar-nova-reuniao")
    limpar_baloes(page)


# O PDF preliminar que a reunião ganha quando a ata fica pronta. O botão
# "Baixar PDF" da validação só existe quando o campo está preenchido.
PDF_PRELIMINAR = "pdfs/MANREU01/ata_preliminar.pdf"


def capturar_bloco(page, caminho: Path, nome: str, alvo, margem: int = 36) -> None:
    """Captura um bloco da tela com folga em volta, pelos balões.

    O balão fica 6 px para FORA do canto do elemento (é o desenho do Print de
    passo), então recortar o bloco na medida exata corta metade do balão do
    primeiro campo. A folga devolve essa faixa.
    """
    caixa = alvo.bounding_box()
    if caixa is None:
        raise SystemExit(f"{nome}: o bloco não está na tela para ser recortado.")
    # O recorte é da página inteira, e não da janela: bloco mais alto que a
    # tela sairia cortado no rodapé. A caixa vem em coordenadas da janela, daí
    # a soma da rolagem.
    rolagem_x = page.evaluate("window.scrollX")
    rolagem_y = page.evaluate("window.scrollY")
    x = max(0, caixa["x"] + rolagem_x - margem)
    y = max(0, caixa["y"] + rolagem_y - margem)
    capturar(
        page,
        caminho,
        nome,
        full_page=True,
        clip={
            "x": x,
            "y": y,
            "width": caixa["width"] + margem * 2,
            "height": caixa["height"] + margem * 2,
        },
    )


def _cartao(page: Page, titulo: str):
    """O cartão inteiro de um bloco da tela da reunião, pelo título dele."""
    return page.get_by_role("heading", name=titulo, exact=True).locator(
        "xpath=ancestor::div[contains(@class,'rounded-2xl')][1]"
    )


def _ata_pronta(base: str) -> None:
    """Põe a reunião de exemplo no momento em que a ata já está escrita."""
    por_reuniao(
        status_ata="AGUARDANDO_VALIDACAO",
        json_ata=_json_da_ata(),
        url_pdf_preliminar=f"{base}/{PDF_PRELIMINAR}",
    )


def _reuniao_programada() -> None:
    """Devolve a reunião de exemplo ao começo do caminho."""
    por_reuniao(status_ata="PROGRAMADA", json_ata=None, url_pdf_preliminar=None)


def calendario_cartao_da_reuniao(page: Page, base: str, saida: Path) -> None:
    """O cartão da reunião no Calendário: é por ele que se abre a reunião.

    Serve a duas tarefas, porque o primeiro passo das duas é o mesmo: anexar a
    transcrição e montar a ata conversando começam abrindo a reunião por aqui.
    """
    _reuniao_programada()
    entrar(page, base, FACILITADORA[2])
    page.set_viewport_size(COMPUTADOR)
    page.goto(f"{base}/reunioes/calendario", wait_until="networkidle")
    page.get_by_text("Calendário de Reuniões").wait_for()
    page.wait_for_timeout(1500)
    balao(page, page.locator(f'a[href^="/reunioes/{REUNIAO}"]').first, 1)
    page.evaluate("window.scrollTo(0, 0)")
    capturar(
        page,
        saida / "calendario-cartao-da-reuniao.png",
        "calendario-cartao-da-reuniao",
        full_page=True,
    )
    limpar_baloes(page)


def bloco_transcricao(page: Page, base: str, saida: Path) -> None:
    """O bloco Transcrição da reunião, com o botão que abre o arquivo."""
    _reuniao_programada()
    entrar(page, base, FACILITADORA[2])
    page.set_viewport_size(COMPUTADOR)
    page.goto(f"{base}/reunioes/{REUNIAO}", wait_until="networkidle")
    page.get_by_role("heading", name="Transcrição", exact=True).wait_for()
    page.wait_for_timeout(1500)
    cartao = _cartao(page, "Transcrição")
    balao(page, page.get_by_role("heading", name="Transcrição", exact=True), 2)
    balao(page, page.get_by_role("button", name="Anexar Transcrição e Processar com IA"), 3)
    capturar_bloco(page, saida / "bloco-transcricao.png", "bloco-transcricao", cartao)
    limpar_baloes(page)


def transcricao_processando(page: Page, base: str, saida: Path) -> None:
    """A tela enquanto o assistente lê a transcrição.

    O estado vem do banco, e não de um arquivo enviado de verdade: processar a
    transcrição aqui chamaria o serviço de fora, e o print é da tela, que é a
    mesma nos dois caminhos. No fim a reunião volta a Programada, para o
    roteiro poder rodar de novo.
    """
    entrar(page, base, FACILITADORA[2])
    page.set_viewport_size(COMPUTADOR)
    por_reuniao(status_ata="PROCESSANDO", json_ata=None, url_pdf_preliminar=None)
    try:
        page.goto(f"{base}/reunioes/{REUNIAO}", wait_until="networkidle")
        page.get_by_text("A IA está processando a transcrição").first.wait_for()
        page.wait_for_timeout(2000)
        # Aqui a tela inteira é o aviso: enquanto o assistente lê, a página
        # troca os blocos da reunião por este recado, então não há cartão de
        # Transcrição para recortar.
        balao(page, page.get_by_text("A IA está processando a transcrição").first, 4)
        page.evaluate("window.scrollTo(0, 0)")
        capturar(
            page,
            saida / "transcricao-processando.png",
            "transcricao-processando",
            full_page=True,
        )
        limpar_baloes(page)
    finally:
        _reuniao_programada()


def ata_escrita(page: Page, base: str, saida: Path) -> None:
    """A ata que o assistente escreveu, como ela aparece ao recarregar."""
    _ata_pronta(base)
    entrar(page, base, FACILITADORA[2])
    page.set_viewport_size(COMPUTADOR)
    page.goto(f"{base}/reunioes/{REUNIAO}", wait_until="networkidle")
    page.get_by_role("heading", name="Discussão dos Pontos (2)").wait_for()
    page.wait_for_timeout(2000)
    # O recorte é a discussão, e não a página inteira: o que o passo promete é
    # que o texto da ata está escrito, e a página inteira aqui é a mesma da
    # tarefa de revisar, com o balão em outro lugar.
    cartao = _cartao(page, "Discussão dos Pontos (2)")
    balao(page, page.get_by_role("heading", name="Discussão dos Pontos (2)"), 5)
    capturar_bloco(page, saida / "ata-escrita.png", "ata-escrita", cartao)
    limpar_baloes(page)


def bloco_ata_guiada(page: Page, base: str, saida: Path) -> None:
    """O bloco que abre a conversa com o assistente, na reunião Programada."""
    _reuniao_programada()
    entrar(page, base, FACILITADORA[2])
    page.set_viewport_size(COMPUTADOR)
    page.goto(f"{base}/reunioes/{REUNIAO}", wait_until="networkidle")
    page.get_by_role("heading", name="Ata Guiada", exact=True).wait_for()
    page.wait_for_timeout(1500)
    cartao = _cartao(page, "Ata Guiada")
    balao(page, page.get_by_role("button", name="Iniciar Ata Guiada"), 2)
    capturar_bloco(page, saida / "bloco-ata-guiada.png", "bloco-ata-guiada", cartao)
    limpar_baloes(page)


def ata_guiada(page: Page, base: str, saida: Path) -> None:
    """A tela da conversa: a ata de um lado, o assistente do outro.

    Nada é enviado ao assistente: o print é da tela como ela recebe quem
    chega, e cada mensagem trocada aqui chamaria o serviço de fora.
    """
    _reuniao_programada()
    entrar(page, base, FACILITADORA[2])
    page.set_viewport_size(COMPUTADOR)
    page.goto(f"{base}/reunioes/{REUNIAO}/ata-guiada", wait_until="networkidle")
    page.get_by_text("Assistente da Ata").wait_for()
    page.wait_for_timeout(2500)
    balao(page, page.get_by_placeholder("Conte o que foi tratado na reunião..."), 3)
    balao(page, page.get_by_text("Assistente da Ata"), 4)
    balao(page, page.get_by_role("button", name="Anexar documento de apoio"), 5)
    balao(page, page.get_by_role("button", name="Concluir e gerar pendências"), 6)
    # A coluna da conversa passa da altura da tela: sem a página inteira, a
    # caixa de escrever e o clipe do documento saem cortados no rodapé.
    page.evaluate("window.scrollTo(0, 0)")
    capturar(page, saida / "ata-guiada.png", "ata-guiada", full_page=True)
    limpar_baloes(page)


def validacao_necessaria(page: Page, base: str, saida: Path) -> None:
    """A reunião na validação: o bloco de decisão, os participantes e a ata."""
    _ata_pronta(base)
    entrar(page, base, FACILITADORA[2])
    page.set_viewport_size(COMPUTADOR)
    page.goto(f"{base}/reunioes/{REUNIAO}", wait_until="networkidle")
    page.get_by_role("heading", name="Validação Necessária").wait_for()
    page.wait_for_timeout(2000)
    balao(page, page.get_by_role("heading", name="Validação Necessária"), 1)
    balao(page, page.get_by_role("link", name="Baixar PDF"), 2)
    balao(page, page.get_by_role("heading", name="Participantes (4)"), 3)
    balao(page, page.get_by_role("button", name="Solicitar Correção"), 4)
    balao(page, page.get_by_role("button", name="Enviar para assinatura"), 5)
    page.evaluate("window.scrollTo(0, 0)")
    capturar(page, saida / "validacao-necessaria.png", "validacao-necessaria", full_page=True)
    limpar_baloes(page)


def finalizar_sem_assinatura(page: Page, base: str, saida: Path) -> None:
    """A janela de confirmação, com a conta das pendências que vão nascer.

    A janela é aberta e NÃO é confirmada: confirmar fecharia a ata de exemplo
    e o roteiro deixaria de poder rodar de novo.
    """
    _ata_pronta(base)
    entrar(page, base, FACILITADORA[2])
    page.set_viewport_size(COMPUTADOR)
    page.goto(f"{base}/reunioes/{REUNIAO}", wait_until="networkidle")
    page.get_by_role("heading", name="Validação Necessária").wait_for()
    page.wait_for_timeout(1500)
    page.get_by_role("button", name="Finalizar sem assinatura").first.click()
    page.get_by_role("heading", name="Finalizar sem assinatura?").wait_for()
    page.wait_for_timeout(1000)
    janela = page.get_by_role("dialog").locator("div.max-w-md").first
    balao(page, page.get_by_role("heading", name="Finalizar sem assinatura?"), 6)
    capturar_bloco(
        page, saida / "finalizar-sem-assinatura.png", "finalizar-sem-assinatura", janela
    )
    limpar_baloes(page)


def enviar_para_assinatura(page: Page, base: str, saida: Path) -> None:
    """O bloco onde a ata segue para a assinatura digital."""
    _ata_pronta(base)
    entrar(page, base, FACILITADORA[2])
    page.set_viewport_size(COMPUTADOR)
    page.goto(f"{base}/reunioes/{REUNIAO}", wait_until="networkidle")
    page.get_by_role("heading", name="Validação Necessária").wait_for()
    page.wait_for_timeout(2000)
    balao(page, page.get_by_role("link", name="Baixar PDF"), 1)
    balao(page, page.get_by_role("button", name="Enviar para assinatura"), 2)
    page.evaluate("window.scrollTo(0, 0)")
    capturar(
        page,
        saida / "enviar-para-assinatura.png",
        "enviar-para-assinatura",
        clip={"x": 0, "y": 0, "width": COMPUTADOR["width"], "height": 620},
    )
    limpar_baloes(page)


def dashboard(page: Page, base: str, saida: Path) -> None:
    """O painel de desempenho inteiro: os quatro números e os dois gráficos."""
    entrar(page, base, FACILITADORA[2])
    page.set_viewport_size(COMPUTADOR)
    page.goto(f"{base}/dashboard", wait_until="networkidle")
    page.get_by_text("Status das Pendências").wait_for()
    # Os gráficos entram com animação: capturar antes dela terminar sai com as
    # barras pela metade.
    page.wait_for_timeout(3000)
    balao(page, _menu(page, "Dashboard"), 1)
    balao(page, page.get_by_text("Conformidade"), 2)
    balao(page, page.get_by_text("Vencem em 3 dias"), 3)
    balao(page, page.get_by_text("Status das Pendências"), 4)
    balao(page, page.get_by_text("Pendências por Setor"), 5)
    balao(page, page.get_by_text("Filtros Dinâmicos de Desempenho"), 6)
    page.evaluate("window.scrollTo(0, 0)")
    capturar(page, saida / "dashboard.png", "dashboard", full_page=True)
    limpar_baloes(page)


# O quadro tem seis colunas e não cabe na largura de trabalho: em 1440 as três
# últimas ficam fora da tela, e o passo manda conferir as seis na ordem. A
# captura abre uma janela mais larga para o print mostrar o quadro inteiro.
COMPUTADOR_LARGO = {"width": 2160, "height": 900}


def kanban(page: Page, base: str, saida: Path) -> None:
    """O quadro parado, com as seis colunas e os cartões.

    O "Solte aqui" da coluna de destino só existe durante o arrasto, então o
    print é o quadro em repouso: o balão do passo que manda arrastar fica no
    cartão, e o do passo que manda soltar fica na coluna de destino.
    """
    entrar(page, base, FACILITADORA[2])
    page.set_viewport_size(COMPUTADOR_LARGO)
    page.goto(f"{base}/pendencias/kanban", wait_until="networkidle")
    page.get_by_text("Arraste os cards para alterar o status das pendências").wait_for()
    page.wait_for_timeout(2500)
    balao(page, _menu(page, "Kanban"), 1)
    balao(page, page.get_by_text("Pendente", exact=True).first, 2)
    balao(page, page.get_by_text("Filtros Dinâmicos"), 3)
    balao(page, page.get_by_text("Revisar o contrato de manutenção das autoclaves"), 4)
    balao(page, page.get_by_text("Em Progresso", exact=True).first, 5)
    balao(page, page.get_by_text("Revisar o fluxo de esterilização do instrumental cirúrgico"), 6)
    page.evaluate("window.scrollTo(0, 0)")
    capturar(page, saida / "kanban.png", "kanban", full_page=True)
    limpar_baloes(page)


def aceite_pelo_link(page: Page, base: str, saida: Path) -> None:
    """A tela sem login que o link do e-mail abre.

    Ela só existe porque a reunião de exemplo está na coleta interna de
    aceites, que é o estado em que a assinatura digital foi recusada ou
    cancelada. O aceite NÃO é registrado: clicar em "Li e aceito" gastaria o
    link, que é de uso único, e a próxima rodada do roteiro não teria tela.
    """
    page.set_viewport_size(COMPUTADOR)
    page.goto(f"{base}/aceite/{TOKEN_ACEITE}", wait_until="networkidle")
    page.get_by_text("Ata de reunião para aceite").wait_for()
    page.wait_for_timeout(2000)
    balao(page, page.get_by_text("Ata de reunião para aceite"), 1)
    balao(page, page.get_by_text("A coleta de assinaturas digitais").first, 2)
    balao(page, page.get_by_role("heading", name="Pauta da Reunião"), 3)
    balao(page, page.get_by_role("heading", name="Quadro de Atribuições (2 ações)"), 4)
    balao(page, page.locator("input[type=checkbox]").first, 5)
    balao(page, page.get_by_role("button", name="Li e aceito"), 6)
    page.evaluate("window.scrollTo(0, 0)")
    capturar(page, saida / "aceite-pelo-link.png", "aceite-pelo-link", full_page=True)
    limpar_baloes(page)


# A tabela da Lista é mais larga do que a área de trabalho de 1440: a coluna
# com a lupa que abre a pendência fica fora da tela e a pessoa só chega nela
# rolando de lado. O print abre uma janela mais larga, como o do quadro, para a
# linha aparecer inteira, com a lupa que o passo manda clicar.
COMPUTADOR_LISTA = {"width": 1680, "height": 900}


# A pendência que os prints da janela de detalhe abrem: é a que o semear
# mantém sem comentário nenhum, para o print do histórico vazio existir.
PENDENCIA_LIMPA = {p[0]: p[1] for p in PENDENCIAS}[PENDENCIA_SEM_COMENTARIO]


def _bloco_da_tabela(page: Page):
    """O cartão branco que envolve a tabela da Lista."""
    return page.locator("table").locator(
        "xpath=ancestor::div[contains(@class,'rounded-2xl')][1]"
    )


def capturar_faixa(page, caminho: Path, nome: str, de, ate, margem: int = 24) -> None:
    """Captura a faixa que vai do alto de um elemento ao pé de outro.

    O recorte de um bloco só não serve quando o balão do passo está fora dele:
    o selo que o Dashboard liga fica acima da tabela, e recortar a tabela
    deixaria o balão de fora do print que ele explica.
    """
    alto = de.bounding_box()
    baixo = ate.bounding_box()
    if alto is None or baixo is None:
        raise SystemExit(f"{nome}: a faixa não está na tela para ser recortada.")
    rolagem_x = page.evaluate("window.scrollX")
    rolagem_y = page.evaluate("window.scrollY")
    x = max(0, min(alto["x"], baixo["x"]) + rolagem_x - margem)
    y = max(0, alto["y"] + rolagem_y - margem)
    direita = max(alto["x"] + alto["width"], baixo["x"] + baixo["width"]) + rolagem_x
    capturar(
        page,
        caminho,
        nome,
        full_page=True,
        clip={
            "x": x,
            "y": y,
            "width": direita - x + margem,
            "height": baixo["y"] + baixo["height"] + rolagem_y - y + margem,
        },
    )


def _linha_da_pendencia(page: Page, descricao: str):
    """A linha da tabela da pendência, pelo texto da Ação / Tarefa."""
    return page.locator("tbody tr").filter(has_text=descricao).first


def _lupa_da_linha(page: Page, descricao: str):
    """A lupa no fim da linha: é ela que abre a pendência, e não a linha."""
    return _linha_da_pendencia(page, descricao).get_by_role(
        "button", name="Abrir detalhes da pendência"
    )


def _abrir_lista(page: Page, base: str, sufixo: str = "") -> None:
    entrar(page, base, FACILITADORA[2])
    page.set_viewport_size(COMPUTADOR_LISTA)
    page.goto(f"{base}/pendencias{sufixo}", wait_until="networkidle")
    page.get_by_role("heading", name="Pendências").first.wait_for()
    page.get_by_text("Ação / Tarefa").wait_for()
    page.wait_for_timeout(2000)


def pendencias_lista(page: Page, base: str, saida: Path) -> None:
    """A Lista inteira: o item do menu, os filtros, as colunas e a lupa."""
    _abrir_lista(page, base)
    balao(page, _menu(page, "Lista"), 1)
    balao(page, page.get_by_text("Filtros Dinâmicos"), 2)
    balao(page, page.get_by_text("Ação / Tarefa"), 4)
    balao(page, _lupa_da_linha(page, PENDENCIA_ATRASADA), 6)
    page.evaluate("window.scrollTo(0, 0)")
    capturar(page, saida / "pendencias-lista.png", "pendencias-lista", full_page=True)
    limpar_baloes(page)


def pendencias_criticas(page: Page, base: str, saida: Path) -> None:
    """A Lista como o Dashboard a abre: com o selo Críticas ligado.

    O selo não existe na tela vazia: ele nasce do recorte que o cartão
    "Vencem em 3 dias" passa no endereço, e é assim que a pessoa chega nele.
    """
    _abrir_lista(page, base, "?criticas=true")
    selo = page.get_by_role("button", name="Críticas")
    selo.wait_for()
    balao(page, selo, 3)
    page.evaluate("window.scrollTo(0, 0)")
    capturar_faixa(
        page,
        saida / "pendencias-criticas.png",
        "pendencias-criticas",
        selo,
        _bloco_da_tabela(page),
    )
    limpar_baloes(page)


def pendencias_status(page: Page, base: str, saida: Path) -> None:
    """A lista de estados que o selo da coluna Status abre.

    O roteiro abre o menu e não escolhe nada: escolher mudaria de verdade o
    estado da pendência de exemplo, e o próximo print sairia de outra tela.
    """
    _abrir_lista(page, base)
    linha = _linha_da_pendencia(page, PENDENCIA_ATRASADA)
    selo = linha.get_by_role("button", name="Alterar status")
    selo.click()
    page.get_by_role("button", name="Repactuada").first.wait_for()
    page.wait_for_timeout(500)
    balao(page, selo, 5)
    capturar_bloco(
        page, saida / "pendencias-status.png", "pendencias-status", _bloco_da_tabela(page), margem=0
    )
    limpar_baloes(page)


def abrir_a_pendencia(page: Page, base: str, saida: Path) -> None:
    """A lupa no fim da linha, que é por onde a pendência abre.

    A linha inteira não abre nada (o `<tr>` da tabela não tem clique), então o
    balão deste passo fica no botão, e não na linha.
    """
    _abrir_lista(page, base)
    balao(page, _lupa_da_linha(page, PENDENCIA_LIMPA), 1)
    capturar_bloco(
        page, saida / "abrir-a-pendencia.png", "abrir-a-pendencia", _bloco_da_tabela(page), margem=0
    )
    limpar_baloes(page)


def _abrir_detalhe(page: Page, base: str, descricao: str):
    """Abre a pendência e devolve a janela de detalhe."""
    _abrir_lista(page, base)
    _lupa_da_linha(page, descricao).click()
    janela = page.locator("div.bg-white.rounded-2xl.shadow-premium").last
    page.get_by_text("Mencione equipe com @").wait_for()
    page.wait_for_timeout(1200)
    return janela


def comentario_na_pendencia(page: Page, base: str, saida: Path) -> None:
    """A janela da pendência: o histórico ainda vazio e a caixa de escrever."""
    janela = _abrir_detalhe(page, base, PENDENCIA_LIMPA)
    balao(page, page.get_by_text("Sem rastros de atividade."), 2)
    balao(page, page.get_by_placeholder("Escreva algo... (@ para menção)"), 3)
    # A janela é recortada dois pixels para dentro: a captura do elemento em
    # escala 2 leva junto uma tira da tela de trás, e ela aparece no print como
    # um rabisco no rodapé.
    capturar_bloco(
        page,
        saida / "comentario-na-pendencia.png",
        "comentario-na-pendencia",
        janela,
        margem=-2,
    )
    limpar_baloes(page)


def _exigir_so_pessoas_de_exemplo(page: Page, nome: str) -> None:
    """Recusa a captura quando a lista da arroba mostra gente de verdade.

    Mencionável é todo super admin do banco, e o banco local tem as contas
    reais de quem trabalha no sistema. O filtro da arroba é que mantém a lista
    nas pessoas de exemplo, e esta guarda é quem percebe quando ele deixa de
    bastar, em vez de o nome de alguém sair no manual público.
    """
    lista = page.locator("div.absolute.bottom-full")
    if lista.count() == 0:
        raise SystemExit(f"{nome}: a lista da arroba não abriu.")
    # As iniciais do avatar saem no mesmo texto do nome e não identificam
    # ninguém: a guarda olha as linhas que são nome e setor.
    mostrados = [
        linha.strip()
        for linha in lista.first.inner_text().splitlines()
        if linha.strip() and not re.fullmatch(r"[A-ZÀ-Ý]{1,3}", linha.strip())
    ]
    de_exemplo = {n for _, n, *_ in PESSOAS} | {
        s for _, _, _, _, s, _, _ in PESSOAS if s
    } | {c for _, _, _, c, _, _, _ in PESSOAS if c}
    intrusos = sorted(set(mostrados) - de_exemplo)
    if intrusos:
        raise SystemExit(
            f"{nome}: a lista da arroba mostra {', '.join(intrusos)}, que não é "
            "gente de exemplo. O manual é público: aperte o filtro da arroba."
        )


def mencao_na_pendencia(page: Page, base: str, saida: Path) -> None:
    """A lista de nomes que a arroba abre, e o botão que envia.

    O comentário fica escrito e NÃO é enviado: enviar deixaria um rastro na
    pendência de exemplo, e o print do passo anterior, que mostra o histórico
    vazio, sairia errado na rodada seguinte.
    """
    janela = _abrir_detalhe(page, base, PENDENCIA_LIMPA)
    caixa = page.get_by_placeholder("Escreva algo... (@ para menção)")
    caixa.click()
    # O filtro vai até onde só as pessoas de exemplo casam: "@Lu" ainda pega
    # gente de verdade do banco local, que é super admin e por isso aparece em
    # toda pendência.
    caixa.type("Combinado na reunião. @Lucia", delay=40)
    page.get_by_role("button", name="Luciana Braga").first.wait_for()
    page.wait_for_timeout(500)
    _exigir_so_pessoas_de_exemplo(page, "mencao-na-pendencia")
    balao(page, page.get_by_role("button", name="Luciana Braga").first, 4)
    balao(page, janela.locator("button.bg-primary").last, 5)
    capturar_bloco(
        page, saida / "mencao-na-pendencia.png", "mencao-na-pendencia", janela, margem=-2
    )
    limpar_baloes(page)


def sino_da_mencao(page: Page, base: str, saida: Path) -> None:
    """O aviso da menção no sino de quem foi chamado pelo nome.

    Quem aparece logada é a pessoa mencionada: o comentário de exemplo é de
    outra pessoa, semeado com a menção, e é ele que acende este aviso.
    """
    _abrir_lista(page, base)
    sino = page.get_by_role("button", name="Notificações")
    sino.click()
    page.get_by_text("mencionou você").first.wait_for()
    page.wait_for_timeout(800)
    balao(page, sino, 6)
    # O aviso abre por cima da tela, fora da caixa do sino: recortar só o sino
    # devolveria um print do ícone, sem a frase que o passo manda ler.
    capturar_faixa(
        page,
        saida / "sino-da-mencao.png",
        "sino-da-mencao",
        sino,
        page.locator("div.absolute.right-0.mt-2").first,
    )
    limpar_baloes(page)


PRINTS: dict = {
    "calendario": calendario,
    "agendar-reuniao": agendar_reuniao,
    "marcar-nova-reuniao": marcar_nova_reuniao,
    "calendario-cartao-da-reuniao": calendario_cartao_da_reuniao,
    "bloco-transcricao": bloco_transcricao,
    "transcricao-processando": transcricao_processando,
    "ata-escrita": ata_escrita,
    "bloco-ata-guiada": bloco_ata_guiada,
    "ata-guiada": ata_guiada,
    "validacao-necessaria": validacao_necessaria,
    "finalizar-sem-assinatura": finalizar_sem_assinatura,
    "enviar-para-assinatura": enviar_para_assinatura,
    "dashboard": dashboard,
    "kanban": kanban,
    "aceite-pelo-link": aceite_pelo_link,
    "pendencias-lista": pendencias_lista,
    "pendencias-criticas": pendencias_criticas,
    "pendencias-status": pendencias_status,
    "abrir-a-pendencia": abrir_a_pendencia,
    "comentario-na-pendencia": comentario_na_pendencia,
    "mencao-na-pendencia": mencao_na_pendencia,
    "sino-da-mencao": sino_da_mencao,
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:3000")
    ap.add_argument("--saida", default="docs/manual/src/assets/reunioes")
    ap.add_argument(
        "--print",
        dest="escolhido",
        choices=sorted(PRINTS),
        help="captura só um print; sem isto, o roteiro inteiro roda.",
    )
    ap.add_argument(
        "--semear",
        action="store_true",
        help="cria os dados de exemplo no Supabase local e sai.",
    )
    args = ap.parse_args()

    if args.semear:
        semear()
        return 0

    saida = Path(args.saida)
    saida.mkdir(parents=True, exist_ok=True)
    escolhidos = [args.escolhido] if args.escolhido else sorted(PRINTS)

    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        navegador = p.chromium.launch()
        contexto = navegador.new_context(
            viewport=COMPUTADOR, device_scale_factor=ESCALA, locale="pt-BR"
        )
        page = contexto.new_page()
        for nome in escolhidos:
            PRINTS[nome](page, args.base.rstrip("/"), saida)
            print(f"print: {saida / (nome + '.png')}")
        navegador.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
