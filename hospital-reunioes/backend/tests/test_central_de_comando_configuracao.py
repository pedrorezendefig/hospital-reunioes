"""As variáveis de ambiente da Central de Comando inteira (issue #814, ADR 0058).

Todas nascem nesta fatia, nos três lugares, de uma vez: o `Settings` do
backend, os dois `.env.example` (o do backend, espelho 1:1 do `Settings`
conferido pelo gate `env_example_sync` do `/deploy`, e o de
`hospital-reunioes/`, que é o molde do `.env` que o backend lê de verdade) e a
lista `runtime_optional` do contrato de deploy. Assim as fatias do Instagram e
do conector MCP, que rodam em paralelo, não disputam esses arquivos.

A Central nasce DORMENTE (ADR 0058, decisão 8): nenhuma variável é
obrigatória, todas nascem vazias, e vazia quer dizer funcionalidade desligada
com erro honesto de configuração (503), nunca número zero. As duas exceções são
os nomes dos eventos de contato no GA4, que têm valor padrão.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.config import Settings  # noqa: E402

BACKEND = Path(__file__).resolve().parents[1]
APP_DIR = BACKEND.parent
REPO = APP_DIR.parent

# Google Analytics (Visitantes, Dados do Google, Ao vivo), Instagram e o
# conector MCP com o WorkOS AuthKit. `MCP_ALLOWED_EMAILS` do app antigo NÃO
# existe aqui de propósito: quem conecta é quem é Super admin (ADR 0058,
# decisão 4), e uma segunda lista de acesso divergiria da primeira em silêncio.
CHAVES_SEM_PADRAO = (
    "GA4_PROPERTY_ID",
    "GOOGLE_APPLICATION_CREDENTIALS_JSON",
    "INSTAGRAM_ACCESS_TOKEN",
    "INSTAGRAM_BUSINESS_ACCOUNT_ID",
    "MCP_AUTH_ISSUER",
    "MCP_AUTH_JWKS_URI",
    "MCP_RESOURCE_URL",
)

# Os eventos que o Site dispara quando alguém clica para falar com o hospital.
# Os padrões são os que o Site publica hoje (os mesmos da Central antiga).
EVENTOS_DE_CONTATO = {
    "GA4_EVENTO_WHATSAPP": "wa_click",
    "GA4_EVENTO_FALE_CONOSCO": "generate_lead",
}

TODAS = CHAVES_SEM_PADRAO + tuple(EVENTOS_DE_CONTATO)

# As que são segredo. Variável de build vira ARG no Dockerfile e fica gravada no
# histórico da imagem: o contrato diz a quem cola no Coolify que estas são só
# de Runtime.
SEGREDOS = ("GOOGLE_APPLICATION_CREDENTIALS_JSON", "INSTAGRAM_ACCESS_TOKEN")

# Os ambientes em que a seção dormente da Central aparecia no menu, até a issue
# #827 ligar a Central em produção. Nenhum deles vale em produção, e a asserção
# do contrato segue travando isso por higiene.
AMBIENTES_QUE_MOSTRAM_A_CENTRAL = ("development", "ci", "staging")


def _settings(**valores) -> Settings:
    """Um `Settings` que não lê o `.env` da máquina: o teste diz o que existe."""
    return Settings(
        _env_file=None,
        supabase_url="http://localhost:54321",
        supabase_service_role_key="chave-de-teste",
        environment="ci",
        **valores,
    )


def _chaves_do_env_example(caminho: Path) -> dict[str, str]:
    """`CHAVE=valor` de cada linha que não é comentário."""
    chaves: dict[str, str] = {}
    for linha in caminho.read_text(encoding="utf-8").splitlines():
        casou = re.match(r"^([A-Z0-9_]+)=(.*)$", linha)
        if casou:
            chaves[casou.group(1)] = casou.group(2)
    return chaves


def _servico(sid: str) -> dict:
    contrato = json.loads((REPO / "docs" / "spec" / "deploy" / "project.json").read_text(encoding="utf-8"))
    (servico,) = [s for s in contrato["services"] if s["id"] == sid]
    return servico


def _env_keys_do_backend() -> dict:
    return _servico("backend")["env_keys"]


class TestNoSettings:
    @pytest.mark.parametrize("chave", TODAS)
    def test_a_chave_existe_no_settings(self, chave):
        assert chave.lower() in Settings.model_fields

    @pytest.mark.parametrize("chave", CHAVES_SEM_PADRAO)
    def test_nasce_vazia(self, chave):
        """Vazia é o estado dormente: a Central sobe sem nenhuma delas."""
        assert getattr(_settings(), chave.lower()) == ""

    @pytest.mark.parametrize(("chave", "padrao"), EVENTOS_DE_CONTATO.items())
    def test_evento_de_contato_tem_padrao(self, chave, padrao):
        assert getattr(_settings(), chave.lower()) == padrao

    @pytest.mark.parametrize(("chave", "padrao"), EVENTOS_DE_CONTATO.items())
    def test_evento_de_contato_vazio_no_env_usa_o_padrao(self, chave, padrao):
        """Quem copia o `.env.example` leva a linha vazia junto. Um nome de
        evento vazio contaria zero clique em silêncio, e o canal apareceria
        medido com 0 sem ser verdade."""
        assert getattr(_settings(**{chave.lower(): ""}), chave.lower()) == padrao
        assert getattr(_settings(**{chave.lower(): "   "}), chave.lower()) == padrao

    @pytest.mark.parametrize("chave", EVENTOS_DE_CONTATO)
    def test_evento_de_contato_configurado_vale(self, chave):
        assert getattr(_settings(**{chave.lower(): "clique_whatsapp"}), chave.lower()) == "clique_whatsapp"


class TestNosEnvExample:
    """Os dois moldes levam a chave, e só o placeholder vazio: credencial de
    verdade nunca entra em arquivo do repositório."""

    @pytest.mark.parametrize("caminho", [BACKEND / ".env.example", APP_DIR / ".env.example"], ids=["backend", "local"])
    @pytest.mark.parametrize("chave", TODAS)
    def test_a_chave_esta_no_molde_com_placeholder_vazio(self, caminho, chave):
        chaves = _chaves_do_env_example(caminho)

        assert chave in chaves, f"{chave} falta em {caminho.relative_to(REPO)}"
        assert chaves[chave] == "", f"{chave} tem valor em {caminho.relative_to(REPO)}: só placeholder vazio"


class TestNoContratoDeDeploy:
    @pytest.mark.parametrize("chave", TODAS)
    def test_a_chave_e_runtime_optional_do_backend(self, chave):
        env_keys = _env_keys_do_backend()
        opcionais = {item["name"] for item in env_keys["runtime_optional"]}
        obrigatorias = {item["name"] for item in env_keys["runtime_required"]}

        assert chave in opcionais
        # Obrigatória derrubaria o `/deploy` em produção antes da última fatia,
        # que é a única que cola as credenciais no Coolify (ADR 0058, decisão 8).
        assert chave not in obrigatorias

    @pytest.mark.parametrize("chave", TODAS)
    def test_o_contrato_diz_para_que_serve(self, chave):
        env_keys = _env_keys_do_backend()
        (item,) = [i for i in env_keys["runtime_optional"] if i["name"] == chave]

        assert item["purpose"].strip()

    @pytest.mark.parametrize("chave", SEGREDOS)
    def test_segredo_da_central_e_so_de_runtime(self, chave):
        env_keys = _env_keys_do_backend()
        (item,) = [i for i in env_keys["runtime_optional"] if i["name"] == chave]

        assert "só Runtime, nunca Build Variable" in item["purpose"]
        assert chave not in {i["name"] for i in env_keys["build_time"]}


class TestDormenciaNaProducao:
    """A Central dormente dependia de a `NEXT_PUBLIC_ENVIRONMENT` de produção
    não ser um dos ambientes que mostravam a seção. A issue #827 ligou a Central
    e o menu não lê mais a variável, mas a asserção de produção do `/deploy`
    (gate 2.6) continua no contrato por higiene, e aceita o valor de hoje em
    produção, que é vazio."""

    @staticmethod
    def _assercao() -> dict:
        (item,) = [a for a in _servico("frontend")["prod_only_assertions"] if a["key"] == "NEXT_PUBLIC_ENVIRONMENT"]
        return item

    def test_e_uma_assercao_por_regex(self):
        assert self._assercao()["comparison"] == "regex"

    @pytest.mark.parametrize("valor", ["", "production"])
    def test_producao_vazia_ou_production_passa(self, valor):
        assert re.search(self._assercao()["value"], valor)

    @pytest.mark.parametrize("valor", AMBIENTES_QUE_MOSTRAM_A_CENTRAL)
    def test_ambiente_que_mostra_a_central_reprova_em_producao(self, valor):
        assert not re.search(self._assercao()["value"], valor)

    def test_o_contrato_diz_que_ela_controla_a_dormencia(self):
        (item,) = [i for i in _servico("frontend")["env_keys"]["build_time"] if i["name"] == "NEXT_PUBLIC_ENVIRONMENT"]

        assert "dormência" in item["purpose"]
        assert "ADR 0058" in item["purpose"]
