"""O e-mail de segunda (issue #1876; Refino 19 e decisões 20, 21, 23, 27, 64 e
68 do diretor no PRD #1757).

Toda segunda, de hora em hora das 8h às 12h, o job manda um e-mail por pessoa:
ao Facilitador, o que foi concluído, atualizado e repactuado na semana nas
Reuniões dele, mais o que segue atrasado; ao responsável, só as Pendências
dele em aberto; a quem é as duas coisas, um e-mail com as duas partes. Quem não
tem nada para ver não recebe. A guarda por pessoa e por semana fica no banco,
e o modo de teste do e-mail (sem transporte) não marca como enviado.
"""

from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass, field
from datetime import date

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.cron import scheduler as cron  # noqa: E402
from app.services import email_de_segunda  # noqa: E402

# Segunda, 23/11/2026: a semana que passou vai de 16/11 a 22/11.
SEGUNDA = date(2026, 11, 23)
PROXIMA_SEGUNDA = date(2026, 11, 30)
ATRASADA = "2026-11-20"
NO_PRAZO = "2026-12-10"


# ─── O banco de mentira ──────────────────────────────────────────────────────


@dataclass
class _Result:
    data: list


class _Negacao:
    def __init__(self, consulta):
        self._consulta = consulta

    def is_(self, coluna, valor):
        assert valor == "null"
        self._consulta._filtros.append(lambda linha: linha.get(coluna) is not None)
        return self._consulta


class _Consulta:
    def __init__(self, linhas: list[dict]):
        self._linhas = linhas
        self._filtros: list = []
        self._recorte: tuple[int, int] | None = None
        self._upsert = None
        self._apagar = False
        self._colunas: list[str] | None = None

    @property
    def not_(self):
        return _Negacao(self)

    def select(self, colunas="*", **_kw):
        # Só as colunas pedidas voltam, como no PostgREST: coluna esquecida no
        # select some do dict, e a regra que a lê decide sem ela.
        if colunas != "*":
            self._colunas = [c.strip() for c in colunas.split(",")]
        return self

    def eq(self, coluna, valor):
        self._filtros.append(lambda linha: str(linha.get(coluna)) == str(valor))
        return self

    def in_(self, coluna, valores):
        valores = set(valores)
        self._filtros.append(lambda linha: linha.get(coluna) in valores)
        return self

    def is_(self, coluna, valor):
        assert valor == "null"
        self._filtros.append(lambda linha: linha.get(coluna) is None)
        return self

    def gte(self, coluna, valor):
        self._filtros.append(lambda linha: str(linha.get(coluna)) >= str(valor))
        return self

    def lt(self, coluna, valor):
        self._filtros.append(lambda linha: str(linha.get(coluna)) < str(valor))
        return self

    def order(self, *_a, **_kw):
        return self

    def range(self, inicio, fim):
        self._recorte = (inicio, fim)
        return self

    def upsert(self, linhas, *, on_conflict, ignore_duplicates=False):
        assert ignore_duplicates
        self._upsert = (linhas, on_conflict.split(","))
        return self

    def delete(self):
        self._apagar = True
        return self

    def execute(self):
        if self._upsert is not None:
            novas, chave = self._upsert
            gravadas = []
            for nova in novas:
                if not any(all(str(v.get(c)) == str(nova.get(c)) for c in chave) for v in self._linhas):
                    self._linhas.append(dict(nova))
                    gravadas.append(dict(nova))
            return _Result(gravadas)
        achadas = [linha for linha in self._linhas if all(f(linha) for f in self._filtros)]
        if self._apagar:
            for linha in achadas:
                self._linhas.remove(linha)
            return _Result([dict(linha) for linha in achadas])
        linhas = [{c: linha.get(c) for c in self._colunas} if self._colunas else dict(linha) for linha in achadas]
        if self._recorte is not None:
            inicio, fim = self._recorte
            linhas = linhas[inicio : fim + 1]
        return _Result(linhas)


@dataclass
class _Banco:
    participantes: list = field(default_factory=list)
    reunioes: list = field(default_factory=list)
    pendencias: list = field(default_factory=list)
    pendencia_historico: list = field(default_factory=list)
    email_de_segunda: list = field(default_factory=list)

    def table(self, nome):
        return _Consulta(getattr(self, nome))


def _pessoa(pid, nome, *, perfil="regular", email=True, ativo=True, perfil_nsp=None) -> dict:
    return {
        "id": pid,
        "nome_completo": nome,
        "email": f"{pid.lower()}@hsm.test" if email else None,
        "access_profile": perfil,
        "ativo": ativo,
        "perfil_nsp": perfil_nsp,
    }


def _reuniao(id_reuniao, facilitador_id, titulo) -> dict:
    return {"id_reuniao": id_reuniao, "titulo": titulo, "facilitador_id": facilitador_id, "deleted_at": None}


def _pendencia(id_acao, descricao, responsavel_id, *, id_reuniao, status="PENDENTE", prazo=NO_PRAZO, co=None):
    return {
        "id_acao": id_acao,
        "id_reuniao": id_reuniao,
        "descricao_acao": descricao,
        "responsavel_id": responsavel_id,
        "co_responsavel_id": co,
        "responsavel_nome": f"Nome {responsavel_id}",
        "status": status,
        "prazo": prazo,
        "deleted_at": None,
    }


def _evento(id_acao, comando, criado_em, anotacao="Anotado.", *, prazo_depois=None) -> dict:
    return {
        "id_acao": id_acao,
        "comando": comando,
        "anotacao": anotacao,
        "criado_em": criado_em,
        "prazo_depois": prazo_depois,
    }


@pytest.fixture
def job(monkeypatch):
    """O job de segunda, com o banco de mentira e o e-mail capturado."""
    estado: dict = {"banco": _Banco(), "hoje": SEGUNDA, "enviados": [], "falhar": False, "transporte": True}

    def _enviar(destinatario, assunto, html_content, texto_fallback, *a, **kw):
        estado["enviados"].append(
            {"para": destinatario, "assunto": assunto, "html": html_content, "texto": texto_fallback}
        )
        return not estado["falhar"]

    monkeypatch.setattr(cron, "_supabase", lambda: estado["banco"])
    monkeypatch.setattr(cron, "_hoje", lambda: estado["hoje"])
    monkeypatch.setattr(email_de_segunda, "_enviar_email", _enviar)
    monkeypatch.setattr(email_de_segunda, "transporte_configurado", lambda: estado["transporte"])
    monkeypatch.setattr(email_de_segunda, "reunioes_do_nucleo", lambda _sb: [])

    def rodar():
        cron.enviar_email_de_segunda()

    return rodar, estado


def _so_responsavel(banco: _Banco) -> _Banco:
    """Bruno é responsável por uma Pendência aberta de uma Reunião que Fábio facilita."""
    banco.participantes = [_pessoa("P_FABIO", "Fábio Lima"), _pessoa("P_BRUNO", "Bruno Reis")]
    banco.reunioes = [_reuniao("R1", "P_FABIO", "Reunião da UTI")]
    banco.pendencias = [_pendencia("A1", "Trocar o monitor do leito 4", "P_BRUNO", id_reuniao="R1")]
    return banco


def _para(estado, pid) -> list[dict]:
    return [e for e in estado["enviados"] if e["para"] == f"{pid.lower()}@hsm.test"]


# ─── 1. Um e-mail só por pessoa e por semana ─────────────────────────────────


def test_rodar_o_job_varias_vezes_na_mesma_segunda_manda_um_email_so_por_pessoa(job):
    rodar, estado = job
    _so_responsavel(estado["banco"])

    for _ in range(5):
        rodar()

    assert len(_para(estado, "P_BRUNO")) == 1
    # A segunda seguinte é outra semana, e ganha o e-mail dela.
    estado["hoje"] = PROXIMA_SEGUNDA
    rodar()
    rodar()
    assert len(_para(estado, "P_BRUNO")) == 2


def test_o_job_roda_na_segunda_de_hora_em_hora_das_8h_as_12h():
    from apscheduler.triggers.cron import CronTrigger

    try:
        cron.start_scheduler()
        job = cron.scheduler.get_job("email_de_segunda_reunioes")
        assert job.func is cron.enviar_email_de_segunda
        assert isinstance(job.trigger, CronTrigger)
        campos = {c.name: str(c) for c in job.trigger.fields}
        assert (campos["day_of_week"], campos["hour"], campos["minute"]) == ("mon", "8-12", "0")
        assert str(job.trigger.timezone) == "America/Sao_Paulo"
    finally:
        cron.stop_scheduler()


def test_falha_no_envio_nao_marca_e_a_hora_seguinte_manda(job):
    rodar, estado = job
    _so_responsavel(estado["banco"])

    estado["falhar"] = True
    rodar()
    assert estado["banco"].email_de_segunda == []

    estado["falhar"] = False
    rodar()
    rodar()
    assert len(_para(estado, "P_BRUNO")) == 2  # a que falhou e a que saiu
    assert [linha["participante_id"] for linha in estado["banco"].email_de_segunda] == ["P_BRUNO"]


def test_modo_de_teste_do_email_nao_marca_como_enviado(job):
    rodar, estado = job
    _so_responsavel(estado["banco"])
    estado["transporte"] = False

    rodar()
    rodar()

    # O e-mail vai para o log nas duas passadas, e nada fica marcado.
    assert len(_para(estado, "P_BRUNO")) == 2
    assert estado["banco"].email_de_segunda == []


# ─── 2. Sem nada para mostrar, sem e-mail ────────────────────────────────────


def test_pessoa_sem_nada_para_mostrar_nao_recebe_email(job):
    rodar, estado = job
    banco = _so_responsavel(estado["banco"])
    banco.participantes += [_pessoa("P_CARLA", "Carla Dias"), _pessoa("P_DANI", "Dani Souza")]
    # Carla facilita uma Reunião sem nada na semana e sem atrasada: a Pendência
    # concluída fechou há duas semanas e a outra foi cancelada.
    banco.reunioes.append(_reuniao("R2", "P_CARLA", "Reunião da Farmácia"))
    banco.pendencias += [
        _pendencia("A2", "Revisar o estoque", "P_DANI", id_reuniao="R2", status="CONCLUIDO", prazo=ATRASADA),
        _pendencia("A3", "Contar os frascos", "P_DANI", id_reuniao="R2", status="CANCELADO", prazo=ATRASADA),
    ]
    banco.pendencia_historico.append(_evento("A2", "concluir", "2026-11-12T14:00:00+00:00"))

    rodar()

    assert _para(estado, "P_CARLA") == []
    assert _para(estado, "P_DANI") == []
    # Fábio facilita a R1, que só tem Pendência no prazo e nada na semana.
    assert _para(estado, "P_FABIO") == []
    assert len(_para(estado, "P_BRUNO")) == 1
    assert {linha["participante_id"] for linha in banco.email_de_segunda} == {"P_BRUNO"}


# ─── 3. O e-mail do Facilitador ──────────────────────────────────────────────

_TITULOS = [
    "Das reuniões que você facilita",
    "Concluídas na semana",
    "Atualizadas na semana",
    "Repactuadas na semana",
    "Seguem atrasadas",
    "Suas pendências em aberto",
    "Abrir o aplicativo",
]


def _secoes(html: str) -> dict[str, str]:
    """O texto visível de cada parte do e-mail, do título até o próximo."""
    texto = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))
    posicoes = sorted((texto.find(t), t) for t in _TITULOS if t in texto)
    return {
        titulo: texto[inicio : (posicoes[i + 1][0] if i + 1 < len(posicoes) else len(texto))]
        for i, (inicio, titulo) in enumerate(posicoes)
    }


def _banco_do_facilitador(banco: _Banco) -> _Banco:
    banco.participantes = [
        _pessoa("P_FABIO", "Fábio Lima"),
        _pessoa("P_BRUNO", "Bruno Reis"),
        _pessoa("P_GIL", "Gil Rocha"),
    ]
    banco.reunioes = [_reuniao("R1", "P_FABIO", "Reunião da UTI"), _reuniao("R9", "P_GIL", "Reunião do RH")]
    banco.pendencias = [
        _pendencia("A1", "Trocar o monitor", "P_BRUNO", id_reuniao="R1", status="CONCLUIDO"),
        _pendencia("A2", "Treinar a equipe", "P_BRUNO", id_reuniao="R1", status="EM_PROGRESSO"),
        _pendencia("A3", "Comprar luvas", "P_BRUNO", id_reuniao="R1", prazo="2026-12-15"),
        _pendencia("A4", "Pintar a sala", "P_BRUNO", id_reuniao="R1", prazo=ATRASADA),
        _pendencia("A5", "Revisar a escala", "P_BRUNO", id_reuniao="R1"),
        _pendencia("A6", "Conferir o carrinho de parada", "P_BRUNO", id_reuniao="R1"),
        # De outra Reunião, de outro Facilitador.
        _pendencia("A9", "Contratar o técnico", "P_BRUNO", id_reuniao="R9", status="CONCLUIDO"),
    ]
    banco.pendencia_historico = [
        _evento("A1", "concluir", "2026-11-18T13:00:00+00:00", "Monitor trocado e testado."),
        _evento("A2", "iniciar", "2026-11-17T12:00:00+00:00", "Começamos pela noite."),
        _evento("A3", "repactuar", "2026-11-19T12:00:00+00:00", "O fornecedor atrasou.", prazo_depois="2026-12-15"),
        # Na semana anterior (domingo, 15/11, 23h em São Paulo): não entra.
        _evento("A5", "anotar", "2026-11-16T02:00:00+00:00", "Escala revista em parte."),
        _evento("A6", "anotar", "2026-11-20T15:00:00+00:00", "Falta repor a adrenalina."),
        _evento("A9", "concluir", "2026-11-18T13:00:00+00:00", "Técnico contratado."),
    ]
    return banco


def test_email_do_facilitador_traz_conclusoes_atualizacoes_repactuacoes_e_atrasadas_da_semana(job):
    rodar, estado = job
    _banco_do_facilitador(estado["banco"])

    rodar()

    (email,) = _para(estado, "P_FABIO")
    assert email["assunto"] == "Resumo de segunda: a semana das suas reuniões"
    secoes = _secoes(email["html"])
    assert "Trocar o monitor" in secoes["Concluídas na semana"]
    assert "Monitor trocado e testado." in secoes["Concluídas na semana"]
    assert "Treinar a equipe" in secoes["Atualizadas na semana"]
    assert "Conferir o carrinho de parada" in secoes["Atualizadas na semana"]
    assert "Falta repor a adrenalina." in secoes["Atualizadas na semana"]
    assert "Comprar luvas" in secoes["Repactuadas na semana"]
    assert "15/12/2026" in secoes["Repactuadas na semana"]
    assert "O fornecedor atrasou." in secoes["Repactuadas na semana"]
    assert "Pintar a sala" in secoes["Seguem atrasadas"]
    assert "20/11/2026" in secoes["Seguem atrasadas"]
    # A anotação da semana anterior e a Reunião de outro Facilitador ficam de fora.
    assert "Revisar a escala" not in email["html"]
    assert "Contratar o técnico" not in email["html"]
    # Fábio não é responsável por nada: o e-mail não tem a parte do responsável.
    assert "Suas pendências em aberto" not in secoes
    # Gil recebe só a conclusão da Reunião dele.
    (do_gil,) = _para(estado, "P_GIL")
    assert "Contratar o técnico" in _secoes(do_gil["html"])["Concluídas na semana"]
    assert "Trocar o monitor" not in do_gil["html"]


# ─── 4. O e-mail do responsável ──────────────────────────────────────────────


def test_email_do_responsavel_traz_so_as_pendencias_dele_em_aberto(job):
    rodar, estado = job
    banco = _banco_do_facilitador(estado["banco"])
    banco.participantes.append(_pessoa("P_HELO", "Heloísa Melo"))
    banco.pendencias += [
        _pendencia("B1", "Ligar para o fornecedor", "P_HELO", id_reuniao="R9"),
        _pendencia("B2", "Organizar o arquivo", "P_BRUNO", id_reuniao="R9", co="P_HELO", prazo=ATRASADA),
        _pendencia("B3", "Fechar o relatório", "P_HELO", id_reuniao="R9", status="CONCLUIDO"),
        _pendencia("B4", "Mandar o ofício", "P_HELO", id_reuniao="R9", status="CANCELADO"),
    ]

    rodar()

    (email,) = _para(estado, "P_HELO")
    assert email["assunto"] == "Resumo de segunda: suas pendências em aberto"
    secoes = _secoes(email["html"])
    assert set(secoes) == {"Suas pendências em aberto", "Abrir o aplicativo"}
    abertas = secoes["Suas pendências em aberto"]
    assert "Ligar para o fornecedor" in abertas
    assert "Organizar o arquivo" in abertas  # co-responsável
    assert "(atrasada)" in abertas
    assert "Fechar o relatório" not in email["html"]
    assert "Mandar o ofício" not in email["html"]
    # Nenhuma Pendência de Bruno em que ela não está.
    assert "Treinar a equipe" not in email["html"]


def test_pendencia_de_reuniao_do_nucleo_fica_fora_para_quem_o_nucleo_nao_libera(job, monkeypatch):
    rodar, estado = job
    banco = _so_responsavel(estado["banco"])
    banco.reunioes.append(_reuniao("R_NSP", "P_FABIO", "Reunião do Núcleo"))
    banco.pendencias.append(_pendencia("N1", "Notificar o evento adverso", "P_BRUNO", id_reuniao="R_NSP"))
    monkeypatch.setattr(email_de_segunda, "reunioes_do_nucleo", lambda _sb: ["R_NSP"])
    monkeypatch.setattr(email_de_segunda, "reunioes_ocultas", lambda _sb, _pessoa: ["R_NSP"])

    rodar()

    (email,) = _para(estado, "P_BRUNO")
    assert "Trocar o monitor do leito 4" in email["html"]
    assert "Notificar o evento adverso" not in email["html"]
    assert "Notificar o evento adverso" not in email["texto"]


def test_acesso_pleno_ve_a_reuniao_do_nucleo_que_facilita_e_quem_nao_tem_nao_ve(job, monkeypatch):
    """O caminho real do sigilo, com o dict da pessoa como o job o lê do banco."""
    from app import dependencies
    from app.services import colegiados

    rodar, estado = job
    banco = _so_responsavel(estado["banco"])
    banco.participantes.append(_pessoa("P_DIRETOR", "Diretor Executivo", perfil_nsp="acesso_pleno"))
    banco.reunioes.append(_reuniao("R_NSP", "P_DIRETOR", "Reunião do Núcleo"))
    banco.pendencias += [
        _pendencia("N1", "Analisar o evento adverso", "P_BRUNO", id_reuniao="R_NSP", prazo=ATRASADA),
        _pendencia("N2", "Revisar o protocolo de quedas", "P_DIRETOR", id_reuniao="R_NSP"),
    ]
    monkeypatch.setattr(email_de_segunda, "reunioes_do_nucleo", lambda _sb: ["R_NSP"])
    monkeypatch.setattr(dependencies, "reunioes_do_nucleo", lambda _sb: ["R_NSP"])
    # Ninguém tem Participação no Núcleo: só o Acesso pleno libera.
    monkeypatch.setattr(colegiados, "vinculo_vigente", lambda *_a, **_kw: (None, False))

    rodar()

    (do_diretor,) = _para(estado, "P_DIRETOR")
    secoes = _secoes(do_diretor["html"])
    assert "Analisar o evento adverso" in secoes["Seguem atrasadas"]
    assert "Revisar o protocolo de quedas" in secoes["Suas pendências em aberto"]
    (do_bruno,) = _para(estado, "P_BRUNO")
    assert "Trocar o monitor do leito 4" in do_bruno["html"]
    assert "Analisar o evento adverso" not in do_bruno["html"]


def test_lembrete_da_agenda_regulatoria_nao_entra_no_email(job):
    """A Pendência sem Reunião é o lembrete do Núcleo (ADR 0095, decisão 4):
    nenhuma lista de Pendências o mostra, e o e-mail também não."""
    rodar, estado = job
    banco = _so_responsavel(estado["banco"])
    banco.participantes.append(_pessoa("P_EX", "Ex-Presidente do Núcleo"))
    banco.pendencias += [
        _pendencia("L1", "Enviar o relatório à Anvisa", "P_EX", id_reuniao=None, prazo=ATRASADA),
        _pendencia("L2", "Renovar o alvará sanitário", "P_BRUNO", id_reuniao=None),
    ]

    rodar()

    assert _para(estado, "P_EX") == []
    (do_bruno,) = _para(estado, "P_BRUNO")
    assert "Trocar o monitor do leito 4" in do_bruno["html"]
    assert "Renovar o alvará sanitário" not in do_bruno["html"]
    assert "Renovar o alvará sanitário" not in do_bruno["texto"]


# ─── 5. As duas coisas, um e-mail ────────────────────────────────────────────


def test_quem_e_facilitador_e_responsavel_recebe_um_email_com_as_duas_partes_separadas(job):
    rodar, estado = job
    banco = _banco_do_facilitador(estado["banco"])
    # Fábio também é responsável por uma Pendência da Reunião de Gil.
    banco.pendencias.append(_pendencia("C1", "Atualizar o protocolo", "P_FABIO", id_reuniao="R9"))

    rodar()

    (email,) = _para(estado, "P_FABIO")
    assert email["assunto"] == "Resumo de segunda: suas reuniões e suas pendências"
    secoes = _secoes(email["html"])
    assert "Atualizar o protocolo" in secoes["Suas pendências em aberto"]
    assert "Atualizar o protocolo" not in secoes["Seguem atrasadas"]
    assert "Pintar a sala" in secoes["Seguem atrasadas"]
    assert "Pintar a sala" not in secoes["Suas pendências em aberto"]
    # A parte do Facilitador vem antes da do responsável.
    html = email["html"]
    assert html.index("Das reuniões que você facilita") < html.index("Suas pendências em aberto")


# ─── 6. Sem travessão ────────────────────────────────────────────────────────

_TRACOS = re.compile("[—–]")


def test_template_e_email_de_segunda_sem_travessao_nem_meia_risca(job):
    from app.services.email_service import TEMPLATES_DIR

    rodar, estado = job
    banco = _banco_do_facilitador(estado["banco"])
    banco.pendencias.append(_pendencia("C1", "Atualizar o protocolo", "P_FABIO", id_reuniao="R9"))

    rodar()

    template = (TEMPLATES_DIR / email_de_segunda.TEMPLATE).read_text(encoding="utf-8")
    assert not _TRACOS.search(template)
    assert estado["enviados"]
    for email in estado["enviados"]:
        for parte in ("assunto", "html", "texto"):
            assert not _TRACOS.search(email[parte]), (email["para"], parte)


# ─── 7. O kit de conhecimento ────────────────────────────────────────────────


def test_o_texto_de_reunioes_no_kit_diz_o_email_de_segunda():
    from app.services.conhecimento import CONHECIMENTO_DIR

    texto = (CONHECIMENTO_DIR / "reunioes.md").read_text(encoding="utf-8")
    assert "Toda segunda-feira, a partir das 8h, cada pessoa recebe um e-mail" in texto
    assert "o que foi concluído, atualizado e repactuado na semana" in texto
    assert "só as pendências dele em aberto" in texto
    assert "um e-mail só, com as duas partes separadas" in texto
    assert "Quem não tem nada para ver não recebe e-mail" in texto
