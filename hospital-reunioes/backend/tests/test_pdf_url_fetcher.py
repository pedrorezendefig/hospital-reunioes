"""A guarda compartilhada do `url_fetcher` dos PDFs (issue #633).

O PR #630 (issue #625) descobriu que a guarda do PDF do POP estava INERTE desde
a #152: o `url_fetcher` ia no `write_pdf()`, e quem busca os recursos é o objeto
`HTML`. O WeasyPrint descarta opção que não conhece só logando "Unknown
rendering option", então a guarda saía do ar em silêncio e o PDF continuava
saindo igual.

Ata, relatório da Ouvidoria e cartaz dos Pontos de escuta nunca tiveram guarda
nenhuma, nem inerte. Este arquivo cobre as duas coisas que a issue pede:

1. a guarda compartilhada em si, incluindo a recusa de multicast que faltava;
2. para cada um dos três geradores, que a guarda está LIGADA no render de
   verdade, o que só é verdade se o fetcher for para o construtor do `HTML`.

O detector é o espião: ele registra o que a guarda recusou DURANTE o render. É
por isso que a asserção é sobre as buscas, e não sobre a fábrica ter sido
chamada. Passar o fetcher só no `write_pdf()` chama a fábrica do mesmo jeito, e
um teste que olhasse só para isso ficaria verde sobre a guarda desligada, que é
exatamente o bug da #625.
"""

from __future__ import annotations

import base64
import os

import pytest


def _asset_uri(*partes: str) -> str:
    """URI `file://` de um asset estático do app, no formato que o template usa.

    `abspath` porque a allowlist é casamento exato e o WeasyPrint entrega a URL
    ao fetcher só com percent-encoding, sem normalizar o `..`: o teste tem que
    montar a URI pela mesma expressão que o gerador usa, senão compararia contra
    uma string que o render nunca produz.
    """
    caminho = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "app", "static", *partes))
    return f"file://{caminho}"


LOGO_URI = _asset_uri("images", "logo_hospital.png")
FONTE_URI = _asset_uri("fonts", "HPSimplified_Rg.ttf")

ARQUIVO_PROIBIDO = "file:///etc/passwd"
# Porta 9 (discard) de propósito: se a guarda caísse, não haveria servidor nem
# espera. Na prática a recusa acontece antes de qualquer socket, e o conftest
# proíbe rede no teste.
HOST_LOOPBACK = "http://127.0.0.1:9/segredo"


def _logo_data_uri() -> str:
    """O logo real do app como `data:` URI, os bytes do PNG de verdade.

    O cartaz dos Pontos de escuta não usa asset `file://` nenhum: logo e QR
    entram embutidos. É esse caminho que o teste do cartaz precisa exercitar.
    """
    with open(LOGO_URI.removeprefix("file://"), "rb") as arquivo:
        return "data:image/png;base64," + base64.b64encode(arquivo.read()).decode("ascii")


def _html_de_ataque(extras: str = "") -> str:
    """O HTML que o gerador entregaria ao WeasyPrint se alguém conseguisse
    plantar markup nele: um `file://` para fora dos assets e um host loopback."""
    return (
        "<html><body>"
        f'<img src="{ARQUIVO_PROIBIDO}" alt="a">'
        f'<img src="{HOST_LOOPBACK}" alt="b">'
        f"{extras}"
        "<p>Corpo do documento.</p>"
        "</body></html>"
    )


class _EspiaoDaGuarda:
    """Embrulha a fábrica real e anota o que o render pediu e o que a guarda
    recusou. A guarda em si roda inteira: o espião só observa."""

    def __init__(self) -> None:
        self.buscados: list[str] = []
        self.recusados: list[str] = []

    def instalar(self, monkeypatch, modulo) -> None:
        from app.services import pdf_url_fetcher

        real = pdf_url_fetcher.criar_pdf_url_fetcher

        def _fabrica(permitidos=frozenset()):
            fetcher = real(permitidos)
            fetch_original = fetcher.fetch

            def _fetch(url, headers=None):
                try:
                    resposta = fetch_original(url, headers)
                except ValueError:
                    self.recusados.append(url)
                    raise
                self.buscados.append(url)
                return resposta

            fetcher.fetch = _fetch
            return fetcher

        monkeypatch.setattr(modulo, "criar_pdf_url_fetcher", _fabrica)


# ═══════════════════════════════════════════════════════════════════════════
# A guarda compartilhada
# ═══════════════════════════════════════════════════════════════════════════


class TestGuardaCompartilhada:
    def _fetcher(self, permitidos: frozenset[str] = frozenset()):
        from app.services.pdf_url_fetcher import criar_pdf_url_fetcher

        return criar_pdf_url_fetcher(permitidos)

    def test_recusa_multicast(self):
        """O buraco que o PR #630 avistou: multicast não cai em NENHUM dos cinco
        predicados que a guarda usava (`is_private`, `is_loopback`,
        `is_link_local`, `is_reserved`, `is_unspecified`). Os cinco endereços
        abaixo são falsos nos cinco e só `is_multicast` os pega, então este
        teste morre se a parcela de multicast sair da guarda.

        `239.255.255.250:1900` é o SSDP, o alvo real: um PDF que buscasse esse
        endereço faria descoberta de dispositivo na rede do hospital.
        """
        for url in (
            "http://224.0.0.1/",
            "http://239.255.255.250:1900/",
            "https://232.1.1.1/",
            "http://[ff02::1]/",
            "http://[ff05::c]/",
        ):
            with pytest.raises(ValueError, match="host privado/loopback recusado"):
                self._fetcher().fetch(url)

    def test_recusa_cgnat(self):
        """O mesmo buraco do multicast, uma faixa depois: `100.64.0.0/10` (NAT de
        operadora, RFC 6598) é falso em `is_private`, `is_loopback`,
        `is_link_local`, `is_reserved`, `is_unspecified` E `is_multicast`. Só a
        checagem explícita de faixa o pega, então este teste morre se ela sair.

        Morde de verdade: é a faixa que operadora usa para NAT, comum em rede de
        hospital e em VPN, e um PDF que a alcançasse falaria com equipamento
        interno como se fosse endereço público.
        """
        for url in (
            "http://100.64.0.1/",
            "http://100.100.100.100/",
            "https://100.127.255.255/admin",
        ):
            with pytest.raises(ValueError, match="host privado/loopback recusado"):
                self._fetcher().fetch(url)

    def test_bordas_das_faixas_novas_seguem_publicas(self):
        """A guarda das faixas não pode virar recusa de tudo. `host_e_privado`
        direto, sem passar pelo `fetch`, porque o ponto aqui é o julgamento do
        endereço e não a busca (que a trava de rede do conftest barraria antes).

        Os três ladeiam as faixas novas por fora: `100.63.255.255` e
        `100.128.0.0` são os vizinhos imediatos do CGNAT, e `223.255.255.255` é
        o vizinho de baixo do multicast. Um mutante que alargasse a faixa (um
        `/8` no lugar do `/10`, por exemplo) morre aqui.
        """
        from app.services.pdf_url_fetcher import host_e_privado

        for host in ("100.63.255.255", "100.128.0.0", "223.255.255.255"):
            assert host_e_privado(host) is False

    def test_recusa_file_uri_fora_da_allowlist(self):
        with pytest.raises(ValueError, match="file:// não permitido"):
            self._fetcher().fetch(ARQUIVO_PROIBIDO)

    def test_recusa_host_loopback(self):
        with pytest.raises(ValueError, match="host privado/loopback recusado"):
            self._fetcher().fetch(HOST_LOOPBACK)

    def test_asset_da_allowlist_carrega_de_verdade(self):
        """Contraste positivo: o que está na allowlist volta com os bytes do
        arquivo (assinatura PNG e TTF), senão a guarda seria só um `raise`."""
        fetcher = self._fetcher(frozenset({LOGO_URI, FONTE_URI}))

        assert fetcher.fetch(LOGO_URI).read().startswith(b"\x89PNG")
        assert fetcher.fetch(FONTE_URI).read().startswith(b"\x00\x01\x00\x00")


# ═══════════════════════════════════════════════════════════════════════════
# A guarda ligada no render de cada gerador
# ═══════════════════════════════════════════════════════════════════════════


class TestGuardaLigadaNaAta:
    def test_render_recusa_file_uri_e_loopback_e_carrega_o_logo(self, monkeypatch):
        from app.services import pdf_generator

        espiao = _EspiaoDaGuarda()
        espiao.instalar(monkeypatch, pdf_generator)

        html = _html_de_ataque(f'<img src="{LOGO_URI}" alt="logo">')
        monkeypatch.setattr(pdf_generator.env, "get_template", lambda _nome: _TemplateFalso(html))

        pdf = pdf_generator.gerar_pdf_ata({"id_reuniao": "r-1"}, {})

        assert pdf.startswith(b"%PDF")
        assert ARQUIVO_PROIBIDO in espiao.recusados
        assert HOST_LOOPBACK in espiao.recusados
        # O logo do próprio template segue entrando: a allowlist casa a URI que
        # o gerador de fato produz, e a Ata não fica sem a marca do hospital.
        assert LOGO_URI in espiao.buscados


class TestGuardaLigadaNoRelatorio:
    def test_render_recusa_file_uri_e_loopback_e_carrega_o_logo(self, monkeypatch):
        from app.services import ouvidoria_relatorio

        espiao = _EspiaoDaGuarda()
        espiao.instalar(monkeypatch, ouvidoria_relatorio)

        html = _html_de_ataque(f'<img src="{LOGO_URI}" alt="logo">')
        monkeypatch.setattr(ouvidoria_relatorio, "montar_html", lambda _registro: html)

        pdf = ouvidoria_relatorio.renderizar_pdf({})

        assert pdf.startswith(b"%PDF")
        assert ARQUIVO_PROIBIDO in espiao.recusados
        assert HOST_LOOPBACK in espiao.recusados
        assert LOGO_URI in espiao.buscados


class TestGuardaLigadaNoCartaz:
    def test_render_recusa_file_uri_e_loopback_e_carrega_o_logo_embutido(self, monkeypatch):
        """A allowlist de `file://` do cartaz é VAZIA: o template não usa asset
        `file://` nenhum (logo e QR entram como `data:`). O contraste positivo
        aqui é o `data:`, que a guarda deixa passar."""
        from app.services import ouvidoria_pontos

        espiao = _EspiaoDaGuarda()
        espiao.instalar(monkeypatch, ouvidoria_pontos)

        data_uri = _logo_data_uri()
        html = _html_de_ataque(f'<img src="{data_uri}" alt="logo">')
        monkeypatch.setattr(ouvidoria_pontos, "html_do_cartaz", lambda _ponto: html)

        pdf = ouvidoria_pontos.pdf_do_cartaz({"codigo": "AB2345"})

        assert pdf.startswith(b"%PDF")
        assert ARQUIVO_PROIBIDO in espiao.recusados
        assert HOST_LOOPBACK in espiao.recusados
        assert data_uri in espiao.buscados


class _TemplateFalso:
    """Um template Jinja de mentira, para plantar no render o HTML que os três
    templates de verdade não deixam entrar (todos são `autoescape=True` e nenhum
    usa `| safe`). A guarda é defesa em profundidade: o teste precisa simular o
    dia em que a primeira camada cair."""

    def __init__(self, html: str) -> None:
        self._html = html

    def render(self, **_kwargs) -> str:
        return self._html
