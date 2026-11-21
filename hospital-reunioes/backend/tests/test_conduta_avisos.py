"""Os avisos por e-mail do Canal de Conduta (issue #1840, PRD #1786).

Uma classe por critério de aceite da issue:

1. tarefa nova gera e-mail ao membro responsável, com o texto fixo e o link
   para MINHA VEZ;
2. o e-mail e o link não contêm protocolo, nome, rito nem trecho de relato;
3. caso do rito Completo ou da Rota Especial avisa na hora;
4. os lembretes saem a cinco dias e a um dia do prazo;
5. nenhum e-mail é enviado a quem relatou;
6. o job não chama IA;
7. o texto do Produto no kit de conhecimento diz o comportamento novo.

O banco é o dublê de `conduta_apoio`, o Comitê é o de `test_conduta_triagem`
e o e-mail é sempre dublado. As pessoas são de teste.
"""

from __future__ import annotations

import ast
import base64
import inspect
import os
import secrets
import sys
from datetime import timedelta

import pytest
from test_conduta_triagem import (
    COORDENACAO,
    DE_FORA,
    DENTRO_COMPLETO,
    DENTRO_RAPIDO,
    FORA_DP,
    HOJE,
    MEMBRO,
    RELATO,
    SEGUNDO_LEITOR,
    Comite,
)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.config import settings  # noqa: E402
from app.services.conduta import avisos  # noqa: E402

FRASE = "Há uma tarefa no Canal de Conduta."


@pytest.fixture(autouse=True)
def _chave(monkeypatch):
    monkeypatch.setattr(settings, "conduta_chave_cifra", base64.b64encode(secrets.token_bytes(32)).decode())
    monkeypatch.setattr(settings, "frontend_url", "https://app.hsm.test")


@pytest.fixture
def emails(monkeypatch) -> list[dict]:
    enviados: list[dict] = []

    def _enviar(destinatario, assunto, html, texto, **kw):
        enviados.append({"para": destinatario, "assunto": assunto, "html": html, "texto": texto, **kw})
        return True

    monkeypatch.setattr(avisos, "_enviar_email", _enviar)
    return enviados


@pytest.fixture
def comite() -> Comite:
    return Comite()


def _para(emails: list[dict]) -> list[str]:
    return sorted(e["para"] for e in emails)


def _email(pid: str) -> str:
    return f"{pid.lower()}@hsm.test"


# ═══════════════════════════════════════════════════════════════════════════
# 1. Tarefa nova gera e-mail ao membro responsável
# ═══════════════════════════════════════════════════════════════════════════


class TestTarefaNova:
    def test_caso_recebido_avisa_a_coordenacao_que_confirma_a_triagem(self, comite, emails):
        comite.caso()

        avisos.rodada_do_dia(comite.banco, HOJE)

        assert _para(emails) == [_email(COORDENACAO)]
        assert emails[0]["assunto"] == FRASE
        assert FRASE in emails[0]["texto"]
        assert "https://app.hsm.test/comite-de-conduta\n" in emails[0]["texto"]
        assert 'href="https://app.hsm.test/comite-de-conduta"' in emails[0]["html"]

    def test_triagem_confirmada_avisa_o_segundo_leitor_e_so_ele(self, comite, emails):
        caso_id = comite.caso()
        avisos.rodada_do_dia(comite.banco, HOJE)
        emails.clear()

        comite.ok(COORDENACAO, caso_id, "triagem", DENTRO_RAPIDO)
        avisos.rodada_do_dia(comite.banco, HOJE)

        assert _para(emails) == [_email(SEGUNDO_LEITOR)]

    def test_contestacao_avisa_os_votantes_e_quem_ja_votou_nao_e_avisado(self, comite, emails):
        caso_id = comite.caso()
        comite.ok(COORDENACAO, caso_id, "triagem", DENTRO_RAPIDO)
        avisos.rodada_do_dia(comite.banco, HOJE)
        emails.clear()

        comite.ok(SEGUNDO_LEITOR, caso_id, "contestacao", {**DENTRO_COMPLETO, "motivo": "É grave."})
        comite.ok(COORDENACAO, caso_id, "contestacao/decisao", {"escolha": "manter"})
        avisos.rodada_do_dia(comite.banco, HOJE)

        assert _para(emails) == [_email(SEGUNDO_LEITOR), _email(MEMBRO)]

    def test_tarefa_que_ja_foi_feita_antes_da_rodada_nao_vira_email(self, comite, emails):
        caso_id = comite.caso()
        comite.ok(COORDENACAO, caso_id, "triagem", DENTRO_RAPIDO)

        avisos.rodada_do_dia(comite.banco, HOJE)

        assert _para(emails) == [_email(SEGUNDO_LEITOR)]
        situacoes = {(a["participante_id"], a["situacao"]) for a in comite.banco.tabelas["conduta_avisos"]}
        assert (COORDENACAO, "dispensado") in situacoes

    def test_duas_rodadas_no_mesmo_dia_nao_repetem_o_email(self, comite, emails):
        comite.caso()
        avisos.rodada_do_dia(comite.banco, HOJE)

        avisos.rodada_do_dia(comite.banco, HOJE)

        assert _para(emails) == [_email(COORDENACAO)]

    def test_quem_tem_varias_tarefas_recebe_um_email_so(self, comite, emails):
        comite.caso()
        comite.caso()

        avisos.rodada_do_dia(comite.banco, HOJE)

        assert _para(emails) == [_email(COORDENACAO)]
        assert {a["situacao"] for a in comite.banco.tabelas["conduta_avisos"]} == {"enviado"}

    def test_o_aviso_que_falha_fica_pendente_e_sai_na_rodada_seguinte(self, comite, emails, monkeypatch):
        comite.caso()
        monkeypatch.setattr(avisos, "_enviar_email", lambda *_a, **_kw: False)
        avisos.rodada_do_dia(comite.banco, HOJE)
        assert {a["situacao"] for a in comite.banco.tabelas["conduta_avisos"]} == {"pendente"}

        monkeypatch.setattr(avisos, "_enviar_email", lambda para, *_a, **_kw: emails.append({"para": para}) or True)
        avisos.rodada_do_dia(comite.banco, HOJE + timedelta(days=1))

        assert _para(emails) == [_email(COORDENACAO)]

    def test_a_acao_acontece_mesmo_com_o_aviso_fora_do_ar(self, comite, monkeypatch):
        caso_id = comite.caso()

        def _explode(*_a, **_kw):
            raise RuntimeError("banco dos avisos fora do ar")

        monkeypatch.setattr(avisos, "tarefas_do_caso", _explode)

        assert comite.ok(COORDENACAO, caso_id, "triagem", DENTRO_RAPIDO)["etapa"] == "apuracao"


# ═══════════════════════════════════════════════════════════════════════════
# 2. O e-mail e o link não contêm protocolo, nome, rito nem trecho de relato
# ═══════════════════════════════════════════════════════════════════════════


class TestSemConteudo:
    def test_o_email_leva_so_a_frase_fixa_e_o_link_da_minha_vez(self, comite, emails):
        caso_id = comite.caso()
        comite.ok(COORDENACAO, caso_id, "triagem", DENTRO_COMPLETO)
        protocolo = next(c for c in comite.banco.tabelas["conduta_casos"] if c["id"] == caso_id)["protocolo"]

        avisos.rodada_do_dia(comite.banco, HOJE)

        assert emails, "o aviso tinha de sair"
        for email in emails:
            assert email["assunto"] == FRASE
            assert email["texto"] == f"{FRASE}\n\nPara ver: https://app.hsm.test/comite-de-conduta\n"
            assert email["endereco_fora_do_log"] is True
            tudo = f"{email['assunto']}\n{email['texto']}\n{email['html']}"
            for proibido in (protocolo, caso_id, "Pessoa", "Fulano", "almoxarifado", "Completo", "completo"):
                assert proibido not in tudo, proibido


# ═══════════════════════════════════════════════════════════════════════════
# 3. Caso do rito Completo ou da Rota Especial avisa na hora
# ═══════════════════════════════════════════════════════════════════════════


class TestNaHora:
    def test_tarefa_do_rito_completo_sai_no_job_de_minuto_em_minuto(self, comite, emails):
        caso_id = comite.caso()
        comite.ok(COORDENACAO, caso_id, "triagem", DENTRO_COMPLETO)

        avisos.despachar(comite.banco, HOJE, so_na_hora=True)

        assert _para(emails) == [_email(SEGUNDO_LEITOR)]

    def test_tarefa_do_rito_rapido_espera_a_rodada_do_dia(self, comite, emails):
        caso_id = comite.caso()
        comite.ok(COORDENACAO, caso_id, "triagem", DENTRO_RAPIDO)

        avisos.despachar(comite.banco, HOJE, so_na_hora=True)
        assert emails == []

        avisos.rodada_do_dia(comite.banco, HOJE)
        assert _para(emails) == [_email(SEGUNDO_LEITOR)]

    def test_caso_da_rota_especial_avisa_o_grupo_na_hora(self, comite, emails):
        from app.services.conduta import casos

        caso_id = casos.registrar_caso(comite.banco, relato=RELATO, categoria=None, rota="especial")["id"]
        comite.banco.tabelas.setdefault("conduta_atribuicoes", []).append(
            {"id": "atr-1", "caso_id": caso_id, "participante_id": COORDENACAO, "motivo": "grupo_especial"}
        )

        avisos.avisar_tarefas_novas(comite.banco, caso_id, {})
        avisos.despachar(comite.banco, HOJE, so_na_hora=True)

        assert _para(emails) == [_email(COORDENACAO)]


# ═══════════════════════════════════════════════════════════════════════════
# 4. Os lembretes saem a cinco dias e a um dia do prazo
# ═══════════════════════════════════════════════════════════════════════════


def _com_prazo(comite: Comite, faltam: int, triagem: dict = FORA_DP) -> str:
    """Um caso triado, com o prazo a `faltam` dias de HOJE."""
    caso_id = comite.caso()
    comite.ok(COORDENACAO, caso_id, "triagem", triagem)
    linha = next(c for c in comite.banco.tabelas["conduta_casos"] if c["id"] == caso_id)
    linha["prazo_em"] = (HOJE + timedelta(days=faltam)).isoformat()
    return caso_id


def _lembretes(comite: Comite) -> list[tuple[str, str]]:
    return sorted(
        (a["participante_id"], a["motivo"])
        for a in comite.banco.tabelas.get("conduta_avisos", [])
        if a["motivo"] != "tarefa"
    )


class TestLembretes:
    @pytest.mark.parametrize("faltam, marco", [(5, "lembrete_5"), (1, "lembrete_1")])
    def test_cinco_dias_e_um_dia_do_prazo_lembram_quem_tem_a_tarefa(self, comite, emails, faltam, marco):
        _com_prazo(comite, faltam)

        avisos.rodada_do_dia(comite.banco, HOJE)

        assert _lembretes(comite) == [(SEGUNDO_LEITOR, marco)]
        assert _email(SEGUNDO_LEITOR) in _para(emails)

    @pytest.mark.parametrize("faltam", [6, -1])
    def test_longe_do_prazo_ou_depois_dele_nao_ha_lembrete(self, comite, emails, faltam):
        _com_prazo(comite, faltam)

        avisos.rodada_do_dia(comite.banco, HOJE)

        assert _lembretes(comite) == []

    def test_cada_marco_lembra_uma_vez_so(self, comite, emails):
        _com_prazo(comite, 5)
        avisos.rodada_do_dia(comite.banco, HOJE)
        emails.clear()

        avisos.rodada_do_dia(comite.banco, HOJE)
        avisos.rodada_do_dia(comite.banco, HOJE + timedelta(days=1))
        assert emails == []

        avisos.rodada_do_dia(comite.banco, HOJE + timedelta(days=4))
        assert _lembretes(comite) == [(SEGUNDO_LEITOR, "lembrete_1"), (SEGUNDO_LEITOR, "lembrete_5")]
        assert _para(emails) == [_email(SEGUNDO_LEITOR)]

    def test_o_job_parado_uns_dias_manda_so_o_marco_mais_adiantado(self, comite, emails):
        _com_prazo(comite, 1)

        avisos.rodada_do_dia(comite.banco, HOJE)

        assert _lembretes(comite) == [(SEGUNDO_LEITOR, "lembrete_1")]

    def test_sem_ninguem_com_tarefa_o_lembrete_vai_a_coordenacao(self, comite, emails):
        caso_id = _com_prazo(comite, 5, DENTRO_RAPIDO)
        comite.ok(SEGUNDO_LEITOR, caso_id, "conferencia")

        avisos.rodada_do_dia(comite.banco, HOJE)

        assert _lembretes(comite) == [(COORDENACAO, "lembrete_5")]

    def test_caso_encerrado_nao_lembra(self, comite, emails):
        caso_id = _com_prazo(comite, 5)
        comite.ok(SEGUNDO_LEITOR, caso_id, "conferencia")
        comite.ok(COORDENACAO, caso_id, "encaminhamento")

        avisos.rodada_do_dia(comite.banco, HOJE)

        assert _lembretes(comite) == []


# ═══════════════════════════════════════════════════════════════════════════
# 5. Nenhum e-mail é enviado a quem relatou
# ═══════════════════════════════════════════════════════════════════════════


class TestQuemRelatou:
    def test_o_caso_inteiro_nunca_escreve_para_quem_esta_fora_do_comite(self, comite, emails):
        """Quem relatou não está no Comitê do caso: a pessoa de fora faz o
        papel dela, com e-mail no cadastro, e não recebe nada em etapa alguma."""
        caso_id = _com_prazo(comite, 1, DENTRO_COMPLETO)
        comite.ok(SEGUNDO_LEITOR, caso_id, "contestacao", {**FORA_DP, "motivo": "Não é do canal."})
        for pid in (COORDENACAO, MEMBRO):
            comite.ok(pid, caso_id, "contestacao/decisao", {"escolha": "acatar"})
        comite.caso()

        for dias in range(7):
            avisos.despachar(comite.banco, HOJE + timedelta(days=dias), so_na_hora=True)
            avisos.rodada_do_dia(comite.banco, HOJE + timedelta(days=dias))

        assert emails, "o Comitê tinha de ser avisado"
        assert _email(DE_FORA) not in _para(emails)
        assert set(_para(emails)) <= {_email(p) for p in (COORDENACAO, SEGUNDO_LEITOR, MEMBRO)}

    def test_o_citado_nao_e_avisado_do_caso_em_que_e_citado(self, comite, emails):
        caso_id = comite.caso()
        comite.banco.tabelas.setdefault("conduta_citados", []).append(
            {"id": "cit-1", "caso_id": caso_id, "participante_id": COORDENACAO}
        )
        comite.banco.tabelas["conduta_avisos"] = []

        avisos.avisar_tarefas_novas(comite.banco, caso_id, {})
        avisos.rodada_do_dia(comite.banco, HOJE)

        assert _email(COORDENACAO) not in _para(emails)

    def test_os_avisos_nao_leem_o_relato_nem_o_codigo_de_quem_relatou(self):
        """O caso é lido só pelos metadados da lista, e nada aqui decifra."""
        arvore = ast.parse(inspect.getsource(avisos))
        importados = {a.name for n in ast.walk(arvore) if isinstance(n, ast.Import | ast.ImportFrom) for a in n.names}
        atributos = {n.attr for n in ast.walk(arvore) if isinstance(n, ast.Attribute)}
        textos = {n.value for n in ast.walk(arvore) if isinstance(n, ast.Constant) and isinstance(n.value, str)}
        assert "cifra" not in importados
        assert "decifrar_texto" not in atributos
        assert not {"relato_cifrado", "codigo_hash"} & textos
        assert "CAMPOS_DA_LISTA" in importados


# ═══════════════════════════════════════════════════════════════════════════
# 6. O job não chama IA
# ═══════════════════════════════════════════════════════════════════════════

# O que denuncia IA no código: os módulos do app que falam com provedor de
# modelo e os SDKs.
_MARCAS_DE_IA = ("ai_processor", "anthropic", "openai", "openrouter", "agente")


def _marcas(codigo: str) -> list[str]:
    return [marca for marca in _MARCAS_DE_IA if marca in codigo.lower()]


class TestSemIa:
    def test_o_detector_reconhece_um_modulo_que_chama_ia(self):
        """Piso do detector: o módulo de IA do app tem marca."""
        from app.services import ai_processor

        assert _marcas(inspect.getsource(ai_processor))

    def test_o_servico_dos_avisos_nao_fala_com_ia(self):
        assert _marcas(inspect.getsource(avisos)) == []

    def test_os_jobs_do_scheduler_so_chamam_o_servico(self):
        from app.cron import scheduler

        for job, chamada in (
            (scheduler.avisar_na_hora_conduta, "avisos.despachar("),
            (scheduler.rodada_de_avisos_conduta, "avisos.rodada_do_dia("),
        ):
            codigo = inspect.getsource(job)
            assert _marcas(codigo) == []
            assert chamada in codigo

    def test_os_jobs_estao_registrados_de_minuto_em_minuto_e_uma_vez_por_dia(self):
        from app.cron import scheduler

        codigo = inspect.getsource(scheduler.start_scheduler)
        assert 'avisar_na_hora_conduta,\n        "interval",\n        minutes=1,' in codigo
        assert 'rodada_de_avisos_conduta,\n        "cron",\n        hour=8,' in codigo

    def test_os_avisos_saem_com_o_provedor_de_ia_fora_do_ar(self, comite, emails, monkeypatch):
        import anthropic

        def _explode(*_a, **_kw):
            raise AssertionError("o job dos avisos chamou IA")

        monkeypatch.setattr(anthropic, "Anthropic", _explode)
        monkeypatch.setattr(anthropic, "AsyncAnthropic", _explode)
        _com_prazo(comite, 5)

        assert avisos.rodada_do_dia(comite.banco, HOJE) == {"enviados": 1, "falhas": 0}

    def test_os_jobs_leem_o_dia_em_sao_paulo_e_chamam_o_servico(self, monkeypatch):
        from app.cron import scheduler

        dia = HOJE + timedelta(days=3)
        chamadas: list = []
        monkeypatch.setattr(scheduler, "_supabase", lambda: "banco")
        monkeypatch.setattr(scheduler, "_hoje_em_sao_paulo", lambda: dia)
        monkeypatch.setattr(avisos, "despachar", lambda b, h, **kw: chamadas.append(("na_hora", b, h, kw)) or {})
        monkeypatch.setattr(avisos, "rodada_do_dia", lambda b, h: chamadas.append(("dia", b, h, {})) or {})

        scheduler.avisar_na_hora_conduta()
        scheduler.rodada_de_avisos_conduta()

        assert chamadas == [("na_hora", "banco", dia, {"so_na_hora": True}), ("dia", "banco", dia, {})]

    def test_o_job_que_falha_nao_derruba_o_scheduler(self, monkeypatch):
        from app.cron import scheduler

        monkeypatch.setattr(scheduler, "_supabase", lambda: "banco")

        def _explode(*_a, **_kw):
            raise RuntimeError("banco fora do ar")

        monkeypatch.setattr(avisos, "despachar", _explode)
        monkeypatch.setattr(avisos, "rodada_do_dia", _explode)

        scheduler.avisar_na_hora_conduta()
        scheduler.rodada_de_avisos_conduta()


# ═══════════════════════════════════════════════════════════════════════════
# 7. O texto do Produto no kit de conhecimento diz o comportamento novo
# ═══════════════════════════════════════════════════════════════════════════


def _secao_do_kit(titulo: str) -> str:
    from app.services.conhecimento import CONHECIMENTO_DIR

    texto = (CONHECIMENTO_DIR / "canal-de-conduta.md").read_text(encoding="utf-8")
    partes = texto.split(f"## {titulo}\n", 1)
    assert len(partes) == 2, f"a seção {titulo!r} sumiu do kit"
    return partes[1].split("\n## ", 1)[0]


class TestKitDeConhecimento:
    def test_os_avisos_estao_no_que_ja_esta_no_ar(self):
        secao = _secao_do_kit("O que já está no ar")
        assert FRASE in secao
        assert "MINHA VEZ" in secao
        assert "cinco dias e a um dia do prazo" in secao
        assert "rito Completo e a Rota Especial avisam na hora" in secao
        assert "quem relatou não recebe aviso por nenhum meio" in secao
