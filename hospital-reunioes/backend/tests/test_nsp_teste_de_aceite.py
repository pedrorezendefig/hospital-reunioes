"""O comando manual do teste de aceite do agente do Núcleo (issue #1990, Anexo F).

O que se confere:

- os 144 casos estão no repositório e o comando não entra no CI;
- sem a palavra de confirmação, o comando não cria cliente nem chama a IA;
- com respostas iguais ao gabarito, todas as metas batem; um caso da faixa A
  respondido como D derruba a meta que impede o merge;
- o comando chama a IA pela mesma função do app.

O modelo é sempre um dublê: nenhum teste chama a IA de verdade.
"""

from __future__ import annotations

import json
import os
import sys
from html import escape
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.seguranca_do_paciente import agente_de_triagem, triagem_do_agente  # noqa: E402
from scripts import nsp_teste_de_aceite as comando  # noqa: E402

RAIZ = Path(__file__).resolve().parents[3]


def _gabarito_como_saida(caso: dict) -> dict:
    gabarito = caso["gabarito"]
    if gabarito["evento_que_nunca_deveria_ocorrer"]:
        evento = {"situacao": "sim", "item": gabarito["evento_que_nunca_deveria_ocorrer"], "motivo": "Da lista."}
    elif gabarito["evento_possivel"]:
        evento = {"situacao": "possivel", "item": gabarito["evento_possivel"], "motivo": "Fronteira."}
    else:
        evento = {"situacao": "nao", "item": 0, "motivo": "Fora da lista."}
    return {
        "assunto": f"Caso {caso['id']}",
        "natureza": gabarito["natureza"],
        "grau_de_dano": gabarito["grau_de_dano"],
        "categoria": gabarito["categoria"],
        "incidente": caso["tema"],
        "evento_que_nunca_deveria_ocorrer": evento,
        "iras": gabarito["iras"],
        "risco_de_imagem": gabarito["risco_de_imagem"],
        "protocolo_basico": "nenhum",
        "canais": gabarito["canais"],
        "motivo_do_encaminhamento": "",
        "faixa": gabarito["faixa"],
        "revisao": gabarito["revisao"],
        "justificativa": "Pelo relato.",
        "confianca": "alta",
        "motivo_da_confianca": "Relato claro.",
        "alertas": [],
        "perguntas_ao_notificante": [],
    }


class _ModeloQueSabeOGabarito:
    """Responde a cada notificação com o gabarito do caso, achado pelo relato;
    `trocas` muda a resposta de um caso."""

    def __init__(self, casos: list[dict], trocas: dict[str, dict] | None = None):
        self.por_relato = {}
        for caso in casos:
            relato = escape(triagem_do_agente.entrada_do_caso_de_teste(caso)["relato"], quote=False)
            self.por_relato[f"<relato>{relato}</relato>"] = {
                **_gabarito_como_saida(caso),
                **(trocas or {}).get(caso["id"], {}),
            }
        self.chamadas = 0
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        self.chamadas += 1
        mensagem = kwargs["messages"][0]["content"]
        [resposta] = [saida for marca, saida in self.por_relato.items() if marca in mensagem]
        texto = json.dumps(resposta, ensure_ascii=False)
        return SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text=texto)])


def _metas(trocas: dict[str, dict] | None = None) -> dict[str, dict]:
    casos = comando.carregar_casos()
    resultados = comando.rodar(_ModeloQueSabeOGabarito(casos, trocas), casos, modelo="modelo-teste")
    return {linha["criterio"]: linha for linha in comando.metricas(casos, resultados)}


REBAIXADOS = "Casos de faixa A ou B classificados em faixa inferior"
LISTA = "Itens da lista ANVISA de confiança alta reconhecidos (sim ou possível)"


def test_os_144_casos_estao_no_repositorio():
    casos = comando.carregar_casos()
    assert len(casos) == 144
    assert len({caso["id"] for caso in casos}) == 144


def test_o_comando_nao_entra_no_ci():
    assert not comando.__file__.split("/")[-1].startswith("test_")
    for workflow in (RAIZ / ".github" / "workflows").glob("*.yml"):
        assert "nsp_teste_de_aceite" not in workflow.read_text(encoding="utf-8"), workflow.name


def test_sem_a_confirmacao_o_comando_nao_chama_a_ia(monkeypatch, capsys):
    def _nao_pode(*_a, **_kw):
        raise AssertionError("o cliente da IA foi criado sem confirmação")

    monkeypatch.setattr(comando, "ClienteDaAnthropic", _nao_pode)
    # Com chave: sem ela o comando pararia por outro motivo, e o teste não diria nada.
    monkeypatch.setattr(comando.settings, "anthropic_api_key", "chave-de-teste")

    saida = comando.main([], perguntar=lambda _pergunta: "sim")

    assert saida == 1
    impresso = capsys.readouterr().out
    assert "432 chamadas" in impresso
    assert "Estimativa: US$" in impresso
    assert "Nada foi chamado." in impresso


def test_com_a_confirmacao_o_comando_roda_pela_funcao_do_app(monkeypatch, tmp_path, capsys):
    casos = comando.carregar_casos()
    modelo = _ModeloQueSabeOGabarito(casos)
    usadas = []
    original = agente_de_triagem.classificar_pelo_agente_do_nucleo

    def _espia(*args, **kwargs):
        usadas.append(1)
        return original(*args, **kwargs)

    monkeypatch.setattr(agente_de_triagem, "classificar_pelo_agente_do_nucleo", _espia)
    monkeypatch.setattr(comando, "ClienteDaAnthropic", lambda **_kw: modelo)
    monkeypatch.setattr(comando.settings, "anthropic_api_key", "chave-de-teste")

    saida = comando.main(["--saida", str(tmp_path / "r.json")], perguntar=lambda _pergunta: "rodar")

    assert saida == 0
    assert modelo.chamadas == len(usadas) == 432
    assert "Metas que impedem o merge: batidas." in capsys.readouterr().out
    assert len(json.loads((tmp_path / "r.json").read_text(encoding="utf-8"))) == 432


def test_respostas_iguais_ao_gabarito_batem_todas_as_metas():
    metas = _metas()
    assert {criterio: linha["resultado"] for criterio, linha in metas.items() if not linha["bateu"]} == {}
    assert metas[LISTA]["resultado"].startswith("100.0%")


def test_caso_da_faixa_a_respondido_como_d_derruba_a_meta_que_impede_o_merge():
    """N010: morfina dez vezes acima, óbito. Respondido como dano leve, faixa D."""
    metas = _metas({"N010": {"grau_de_dano": "leve", "faixa": "D", "revisao": "campo_a_campo"}})
    assert metas[REBAIXADOS]["bateu"] is False
    assert "N010" in metas[REBAIXADOS]["resultado"]


def test_item_da_lista_nao_reconhecido_derruba_a_meta_que_impede_o_merge():
    """N021: compressa esquecida, item 28, confiança alta."""
    metas = _metas({"N021": {"evento_que_nunca_deveria_ocorrer": {"situacao": "nao", "item": 0, "motivo": "-"}}})
    assert metas[LISTA]["bateu"] is False
    assert "N021" in metas[LISTA]["resultado"]


@pytest.mark.parametrize("caso", ["N012", "N023"])
def test_o_tambem_aceito_conta_como_acerto(caso):
    """N012 aceita dano moderado (faixa C); N023 aceita o item 27."""
    trocas = {
        "N012": {"grau_de_dano": "moderado", "faixa": "C"},
        "N023": {"evento_que_nunca_deveria_ocorrer": {"situacao": "sim", "item": 27, "motivo": "Cirurgia errada."}},
    }
    metas = _metas({caso: trocas[caso]})
    assert metas[REBAIXADOS]["bateu"] is True
    assert metas[LISTA]["bateu"] is True


@pytest.mark.parametrize(
    "caso, troca",
    [
        # N042: lesão por pressão estágio 3, item 8, faixa A pela lista; aceita dano leve.
        (
            "N042",
            {
                "grau_de_dano": "leve",
                "faixa": "D",
                "revisao": "campo_a_campo",
                "evento_que_nunca_deveria_ocorrer": {"situacao": "possivel", "item": 8, "motivo": "Fronteira."},
            },
        ),
        # N020: lado errado, item 24, faixa A pela lista; aceita dano leve.
        (
            "N020",
            {
                "grau_de_dano": "leve",
                "faixa": "D",
                "revisao": "confirmacao_simples",
                "evento_que_nunca_deveria_ocorrer": {"situacao": "nao", "item": 0, "motivo": "-"},
            },
        ),
    ],
)
def test_caso_a_pela_lista_com_dano_tambem_aceito_rebaixado_derruba_a_meta(caso, troca):
    """O também aceito do dano não isenta a faixa A que vem do evento da lista."""
    metas = _metas({caso: troca})
    assert metas[REBAIXADOS]["bateu"] is False
    assert caso in metas[REBAIXADOS]["resultado"]
