"""Cache do /api/data: o GitHub só é coletado por evento (?fresh=1) ou com o retrato velho.

O auto-refresh da página (60 s) e o curl do hr-ondas leem o cache; quem pede coleta nova é o
botão de recoletar e o hr-ondas quando um evento do workflow acontece.
"""

import sys
from pathlib import Path

DASH = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DASH))

import serve  # noqa: E402


def _montar(monkeypatch):
    relogio = {"t": 1_000.0}
    coletas = []
    monkeypatch.setattr(serve.time, "time", lambda: relogio["t"])
    monkeypatch.setattr(serve.collector, "collect", lambda root: coletas.append(relogio["t"]) or {"n": len(coletas)})
    monkeypatch.setattr(serve, "_cache", {"ts": 0.0, "data": None})
    return relogio, coletas


def test_auto_refresh_de_minuto_nao_recoleta(monkeypatch):
    relogio, coletas = _montar(monkeypatch)
    serve.get_data(False)
    for _ in range(4):  # quatro auto-refresh da página, um por minuto
        relogio["t"] += 60
        serve.get_data(False)
    assert len(coletas) == 1


def test_evento_recoleta_na_hora(monkeypatch):
    relogio, coletas = _montar(monkeypatch)
    serve.get_data(False)
    relogio["t"] += 5
    assert serve.get_data(True) == {"n": 2}


def test_sem_evento_recoleta_depois_de_cinco_minutos(monkeypatch):
    relogio, coletas = _montar(monkeypatch)
    serve.get_data(False)
    relogio["t"] += 301
    serve.get_data(False)
    assert len(coletas) == 2
