"""Rate limit por IP atrás do proxy da casa (issue #349).

O backend roda atrás do Traefik (e do rewrite do Next). Sem `--proxy-headers`,
`request.client.host` é o IP do container do proxy para todo visitante, e todo
limite por IP vira um balde único do hospital inteiro.

O contrato aqui é duplo:

- o Dockerfile liga `--proxy-headers` e confia SOMENTE nas faixas privadas da
  rede do Docker (nunca `*`: com curinga, qualquer cliente da internet escolhe
  o próprio IP e o limite deixa de existir);
- as mesmas faixas, aplicadas ao middleware que o uvicorn usa de verdade,
  fazem o IP real do visitante chegar ao app quando quem conecta é o proxy, e
  ignoram o cabeçalho de quem chega direto da internet.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from slowapi.util import get_remote_address  # noqa: E402

# As faixas privadas (RFC 1918) onde vivem o Traefik e o container do Next.
# É a mesma decisão de confiança do PR #348, agora para o app inteiro.
FAIXAS_PRIVADAS = ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")

_DOCKERFILE = Path(__file__).resolve().parents[1] / "Dockerfile"


def _cmd_do_dockerfile() -> list[str]:
    # O `CMD [` da forma exec, não o `CMD curl` de dentro do HEALTHCHECK.
    for linha in _DOCKERFILE.read_text().splitlines():
        if linha.strip().startswith("CMD ["):
            return json.loads(linha.strip().removeprefix("CMD").strip())
    raise AssertionError("Dockerfile sem linha CMD em forma exec")


class TestMiddlewareComAsMesmasFaixas:
    """O que as flags do Dockerfile ligam é o ProxyHeadersMiddleware do
    uvicorn. Aqui ele roda com as MESMAS faixas do CMD, provando que a
    configuração entrega o comportamento prometido."""

    @staticmethod
    def _client_com_proxy_headers(cliente: tuple[str, int]) -> TestClient:
        from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

        app = FastAPI()

        @app.get("/quem-sou-eu")
        async def quem_sou_eu(request: Request):
            return {"ip": get_remote_address(request)}

        return TestClient(ProxyHeadersMiddleware(app, trusted_hosts=list(FAIXAS_PRIVADAS)), client=cliente)

    def test_ip_do_visitante_atravessa_o_proxy_da_casa(self):
        client = self._client_com_proxy_headers(("172.18.0.5", 51000))
        r = client.get("/quem-sou-eu", headers={"X-Forwarded-For": "189.40.12.7"})
        assert r.json() == {"ip": "189.40.12.7"}

    def test_cliente_direto_da_internet_nao_escolhe_o_proprio_ip(self):
        client = self._client_com_proxy_headers(("189.40.12.7", 51000))
        r = client.get("/quem-sou-eu", headers={"X-Forwarded-For": "198.51.100.9"})
        assert r.json() == {"ip": "189.40.12.7"}


class TestContratoDoDockerfile:
    def test_uvicorn_le_o_ip_real_vindo_do_proxy_da_casa(self):
        cmd = _cmd_do_dockerfile()
        assert "--proxy-headers" in cmd
        assert f"--forwarded-allow-ips={','.join(FAIXAS_PRIVADAS)}" in cmd

    def test_confianca_no_cabecalho_nao_e_curinga(self):
        """`--forwarded-allow-ips=*` faria o limite deixar de existir."""
        cmd = _cmd_do_dockerfile()
        assert not any("*" in parte for parte in cmd)

    def test_stack_local_roda_com_as_mesmas_flags(self):
        """O `command:` do compose sobrescreve o CMD do Dockerfile (por causa do
        --reload): sem repetir as flags ali, o dev local volta a ter um balde
        único para todo visitante e o defeito reaparece só fora de produção."""
        compose = (_DOCKERFILE.parents[1] / "docker-compose.yml").read_text()
        linha = next(ln for ln in compose.splitlines() if "uvicorn app.main:app" in ln)

        assert "--proxy-headers" in linha
        assert f"--forwarded-allow-ips={','.join(FAIXAS_PRIVADAS)}" in linha
