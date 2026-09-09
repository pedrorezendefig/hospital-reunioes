"""A guarda do `url_fetcher` dos PDFs: defesa em profundidade contra `file://`
e SSRF na geração de documento (issue #633).

Nasceu dentro do PDF do POP (issue #152) e saiu para cá porque Ata, relatório da
Ouvidoria e cartaz dos Pontos de escuta rodavam sem guarda nenhuma. Uma guarda
só, e todo gerador novo herda a mesma régua.

Como usar, e é a parte que morde: o fetcher vai no CONSTRUTOR do `HTML`, que é
quem busca os recursos. O `write_pdf` do WeasyPrint 70 descarta opção que não
conhece (só loga "Unknown rendering option"), então passá-lo ali desliga a
guarda em silêncio, com o PDF saindo igual. Foi assim que a guarda do POP viveu
inerte da #152 até o PR #630.

    HTML(string=html, url_fetcher=criar_pdf_url_fetcher(assets)).write_pdf(...)

A allowlist de `file://` é casamento EXATO da URI, e por isso as URIs dos assets
precisam ser montadas com `os.path.abspath`: o WeasyPrint normaliza o `..` da
URL antes de entregá-la ao fetcher, e uma allowlist com `..` no meio nunca
casaria, deixando o gerador sem o próprio logo.
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlsplit


def host_e_privado(host: str) -> bool:
    """True se o host resolve para um endereço que o PDF não deve buscar:
    privado, loopback, link-local, reservado, unspecified ou multicast
    (10/8, 127/8, 172.16/12, 192.168/16, 169.254/16, 224.0.0.0/4, ::1, fc00::/7,
    ff00::/8...). Resolve nomes (localhost e DNS apontando para rede interna)
    antes de julgar.

    Multicast entrou junto com a mudança de casa (issue #633): ele não cai em
    nenhum dos outros cinco predicados, então `239.255.255.250` (SSDP) passava
    reto e um PDF podia fazer descoberta de dispositivo na rede do hospital.
    """
    if not host:
        return True
    host = host.strip("[]")
    candidatos: list[str] = []
    try:
        candidatos.append(str(ipaddress.ip_address(host)))
    except ValueError:
        try:
            infos = socket.getaddrinfo(host, None)
            candidatos.extend(info[4][0] for info in infos)
        except (OSError, UnicodeError):
            # Não resolveu: trata como não confiável (fail-closed).
            return True
    for endereco in candidatos:
        try:
            ip = ipaddress.ip_address(endereco.split("%")[0])
        except ValueError:
            return True
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_unspecified
            or ip.is_multicast
        ):
            return True
    return False


def criar_pdf_url_fetcher(allowed_file_uris: frozenset[str] = frozenset()):
    """O `url_fetcher` do WeasyPrint que recusa todo `file://` que não seja um
    asset legítimo do template (logo/fonte do próprio app) e todo host
    privado/loopback/link-local/reservado/multicast, fechando o vetor de leitura
    de arquivo local e de SSRF. Levanta `ValueError` no que recusa; delega o
    resto ao fetcher padrão do WeasyPrint.

    `allowed_file_uris` vazio é o caso do gerador cujo template não usa asset
    `file://` nenhum (o cartaz dos Pontos de escuta embute logo e QR como
    `data:`): ali todo `file://` é recusado.

    A partir do WeasyPrint 70 o fetcher é uma classe (`weasyprint.urls.URLFetcher`),
    não mais a função `default_url_fetcher`: quem recusa precisa herdar dela, porque
    o `weasyprint.urls.fetch` lê `url_fetcher._fail_on_errors` ao tratar a exceção.
    Herdar faz a guarda valer também no redirect, que o WeasyPrint reentrega ao
    próprio fetcher (um 302 para `127.0.0.1` volta a passar pela recusa de host).
    Isso não sai de graça: o fetcher herdado tem estado, e a recusa precisa
    limpá-lo. Ver a invariante no `fetch`.

    A classe nasce aqui dentro porque o import do WeasyPrint é lazy: ele exige
    libs nativas (glib/pango) que não existem em todo ambiente de teste.
    """
    from weasyprint.urls import URLFetcher

    class _PdfUrlFetcher(URLFetcher):
        def fetch(self, url, headers=None):
            # INVARIANTE: toda recusa limpa `self._request` antes de levantar.
            # Do WeasyPrint 69 em diante o `URLFetcher` guarda o `Request` do
            # redirect nesse campo e só o limpa dentro do `fetch` do pai, depois
            # do ponto onde a guarda recusa. Sem limpar, a requisição recusada
            # fica pendurada e a busca SEGUINTE do mesmo PDF a reexecuta,
            # devolvendo aqueles bytes como se fossem o recurso legítimo: pedir
            # o logo passava a devolver o alvo recusado. Recusa nova entra com
            # a limpeza junto.
            partes = urlsplit(url)
            esquema = partes.scheme.lower()

            if esquema == "file":
                if url in allowed_file_uris:
                    return super().fetch(url, headers)
                self._request = None
                raise ValueError(f"file:// não permitido no PDF: {url}")

            if esquema in ("http", "https"):
                if host_e_privado(partes.hostname or ""):
                    self._request = None
                    raise ValueError(f"host privado/loopback recusado no PDF: {url}")
                return super().fetch(url, headers)

            if esquema == "data":
                return super().fetch(url, headers)

            self._request = None
            raise ValueError(f"esquema de URL não permitido no PDF: {esquema or url}")

    return _PdfUrlFetcher()
