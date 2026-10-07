"""As outras duas portas do Anexo da Demanda e a frase para o GitHub (issue
#1062, PRD #1056, ADR 0069, decisao 1).

- **Assistente**: o print descrito ganha um identificador efemero; "Criar
  Demanda" leva os identificadores e o backend grava os bytes como Anexo na
  mesma chamada. Sem o clique, nada fica: nem linha, nem binario.
- **Conversa**: a resposta leva uma imagem, ligada a ela; o comentario
  espelhado sai com o texto e "(1 imagem na Demanda)".
- **Issue**: "Anexos: N imagens na Demanda", sem URL e sem nome de arquivo, na
  issue criada por "Levar para desenvolvimento", na vinculada por numero e na
  ja vinculada quando a contagem muda.

Tudo pela ROTA, com o Supabase, o storage e o GitHub dublados no molde do
`test_tecnologia_anexos.py`.
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from test_tecnologia_anexos import BUCKET, PNG, _anexar, _anexos, _cenario  # noqa: E402
from test_tecnologia_vinculo import BASE, _demanda, _GithubFalso, _issue  # noqa: E402

from app.config import settings  # noqa: E402
from app.limiter import limiter  # noqa: E402
from app.services import tecnologia_email  # noqa: E402

LEVAR = f"{BASE}/demandas/d-1/levar-para-desenvolvimento"


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    limiter._storage.reset()
    yield
    limiter._storage.reset()


@pytest.fixture(autouse=True)
def _sem_email_de_verdade(monkeypatch):
    monkeypatch.setattr(tecnologia_email, "_enviar_email", lambda *a, **kw: True)
    monkeypatch.setattr(tecnologia_email, "transporte_configurado", lambda: True)


@pytest.fixture(autouse=True)
def _integracao_configurada(monkeypatch):
    monkeypatch.setattr(settings, "github_integracao_token", "token-de-teste")
    monkeypatch.setattr(settings, "github_integracao_repo", "pedrorezendefig/hospital-reunioes")


# ─── 1. A issue diz quantas imagens ha ───────────────────────────────────────


class TestIssueNovaDizQuantasImagens:
    def test_com_anexos_o_corpo_diz_quantas_imagens_ha_na_demanda(self, monkeypatch):
        client, _, gh = _cenario(demandas=[_demanda("d-1")], monkeypatch=monkeypatch)
        assert _anexar(client, nome="um.png").status_code == 201
        assert _anexar(client, nome="dois.png").status_code == 201

        assert client.post(LEVAR).status_code == 200

        assert "Anexos: 2 imagens na Demanda" in gh.criadas[0]["corpo"]

    def test_sem_anexo_o_corpo_nao_fala_de_anexo(self, monkeypatch):
        client, _, gh = _cenario(demandas=[_demanda("d-1")], monkeypatch=monkeypatch)

        assert client.post(LEVAR).status_code == 200

        assert "Anexos:" not in gh.criadas[0]["corpo"]


class TestVincularEscreveAFrase:
    CORPO = "## Para o diretor\n\nO selo passa a aparecer no card."

    def test_vincular_demanda_com_anexos_escreve_a_frase_na_issue_existente(self, monkeypatch):
        gh = _GithubFalso({501: _issue(501, corpo=self.CORPO)})
        client, _, _ = _cenario(demandas=[_demanda("d-1")], github=gh, monkeypatch=monkeypatch)
        for nome in ("um.png", "dois.png", "tres.png"):
            assert _anexar(client, nome=nome).status_code == 201

        assert client.post(f"{BASE}/demandas/d-1/vincular", json={"numero": 501}).status_code == 200

        assert gh.issues[501]["body"] == (
            f'{self.CORPO}\n\nAnexos: 3 imagens na Demanda\n\n<!-- demanda-vitta id="d-1" -->'
        )

    def test_vincular_de_novo_com_a_mesma_contagem_nao_escreve(self, monkeypatch):
        gh = _GithubFalso({501: _issue(501, corpo=self.CORPO)})
        client, _, _ = _cenario(demandas=[_demanda("d-1")], github=gh, monkeypatch=monkeypatch)
        assert _anexar(client).status_code == 201
        assert client.post(f"{BASE}/demandas/d-1/vincular", json={"numero": 501}).status_code == 200

        assert client.post(f"{BASE}/demandas/d-1/vincular", json={"numero": 501}).status_code == 200

        assert len(gh.corpos_escritos) == 1
        assert gh.issues[501]["body"].count("Anexos:") == 1
        assert "Anexos: 1 imagem na Demanda" in gh.issues[501]["body"]


class TestAContagemMudaNaIssueVinculada:
    CORPO = '## Para o diretor\n\nO selo passa a aparecer no card.\n\n<!-- demanda-vitta id="d-1" -->'

    def _vinculada(self, monkeypatch):
        gh = _GithubFalso({501: _issue(501, corpo=self.CORPO)})
        client, sb, _ = _cenario(
            demandas=[_demanda("d-1", estado="em_andamento", github_issue_numero=501)],
            github=gh,
            monkeypatch=monkeypatch,
        )
        return client, sb, gh

    def test_imagem_nova_atualiza_a_contagem_na_issue(self, monkeypatch):
        client, _, gh = self._vinculada(monkeypatch)

        assert _anexar(client, nome="um.png").status_code == 201
        assert "Anexos: 1 imagem na Demanda" in gh.issues[501]["body"]
        assert _anexar(client, nome="dois.png").status_code == 201

        assert gh.issues[501]["body"] == (
            '## Para o diretor\n\nO selo passa a aparecer no card.\n\n'
            'Anexos: 2 imagens na Demanda\n\n<!-- demanda-vitta id="d-1" -->'
        )

    def test_concluir_tira_a_frase_porque_as_imagens_sairam(self, monkeypatch):
        client, _, gh = self._vinculada(monkeypatch)
        assert _anexar(client).status_code == 201

        assert client.post(f"{BASE}/demandas/d-1/mover", json={"estado": "concluida"}).status_code == 200

        assert gh.issues[501]["body"] == self.CORPO

    def test_github_fora_do_ar_nao_derruba_o_anexo(self, monkeypatch):
        client, sb, gh = self._vinculada(monkeypatch)
        gh.erro = RuntimeError("GitHub fora do ar")

        assert _anexar(client).status_code == 201
        assert len(_anexos(sb)) == 1
