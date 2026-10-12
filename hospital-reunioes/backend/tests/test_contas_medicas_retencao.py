"""Retenção de 7 dias dos PDFs de Contas médicas (issue #1125, PRD #1113).

O PDF enviado (conta ou prontuário) e o texto extraído guardado ao lado dele
saem do bucket privado `contas-medicas` quando `apagar_em` vence, e a linha de
`cm_arquivo` fica, com `apagado_em` carimbado. O que o módulo estruturou
(`cm_eventos`, `cm_conta_item`, `cm_guia_linha`) não é tocado.

Cobre os critérios pelo seam do serviço (a função que o scheduler chama) e
pelo job registrado no scheduler.
"""

from __future__ import annotations

import datetime as dt
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services import contas_medicas_retencao as retencao  # noqa: E402

# Relógio congelado: 12 de outubro de 2026, meio-dia em UTC.
AGORA = dt.datetime(2026, 10, 12, 12, 0, tzinfo=dt.UTC)
ONTEM = "2026-10-11T12:00:00+00:00"
AMANHA = "2026-10-13T12:00:00+00:00"
CARIMBO_ANTIGO = "2026-10-05T04:30:00+00:00"


def _arquivo(numero: int, apagar_em: str | None, apagado_em: str | None = None, **overrides) -> dict:
    linha = {
        "id": f"arq-{numero}",
        "envio_id": "envio-1",
        "tipo": "PRONTUARIO",
        "numero_atendimento": f"77{numero:04d}",
        "chave_bucket": f"envio-1/arq-{numero}.pdf",
        "apagar_em": apagar_em,
        "apagado_em": apagado_em,
    }
    linha.update(overrides)
    return linha


class _TabelaFake:
    """Fake do PostgREST no que a retenção usa: select com projeção, update
    filtrado (eq, IS NULL e `lte`), limit. Registra cada UPDATE executado no
    dono, para o teste afirmar que o job NÃO propôs escrita."""

    def __init__(self, nome: str, rows: list[dict], dono: _SupabaseFake):
        self.nome = nome
        self.rows = rows
        self.dono = dono
        self._iguais: dict = {}
        self._nulos: list[str] = []
        self._ate: dict = {}
        self._update: dict | None = None
        self._colunas: tuple[str, ...] | None = None
        self._limite: int | None = None

    def select(self, colunas: str = "*", *_a, **_kw):
        if colunas.strip() != "*":
            self._colunas = tuple(c.strip() for c in colunas.split(","))
        return self

    def update(self, payload: dict):
        self._update = payload
        return self

    def eq(self, col, value):
        self._iguais[col] = value
        return self

    def is_(self, col, value):
        assert value in ("null", None)
        self._nulos.append(col)
        return self

    def lte(self, col, value):
        self._ate[col] = value
        return self

    def order(self, col, desc=False):
        return self

    def limit(self, n):
        self._limite = n
        return self

    def execute(self):
        if self._update is not None:
            self.dono.escritas.append((self.nome, "update", dict(self._iguais)))
        casadas = [
            r
            for r in self.rows
            if all(r.get(c) == v for c, v in self._iguais.items())
            and all(r.get(c) is None for c in self._nulos)
            and all(r.get(c) is not None and str(r.get(c)) <= v for c, v in self._ate.items())
        ]
        if self._limite is not None:
            casadas = casadas[: self._limite]
        if self._update is not None:
            for r in casadas:
                r.update(self._update)
            return type("R", (), {"data": [dict(r) for r in casadas]})()
        if self._colunas is None:
            return type("R", (), {"data": [dict(r) for r in casadas]})()
        return type("R", (), {"data": [{c: r.get(c) for c in self._colunas} for r in casadas]})()


class _StorageFake:
    """O Storage relata o resultado arquivo a arquivo: o que saiu vem na
    lista; o que não existia não vem (200 com lista vazia quando nada casou);
    o que foi recusado vem com `error`. `fora_do_ar` faz a chamada levantar."""

    def __init__(self):
        self.arquivos: dict[str, set[str]] = {}
        self.recusar: set[str] = set()
        self.fora_do_ar = False
        self.pedidos: list[tuple[str, list[str]]] = []
        self._bucket = ""

    def from_(self, bucket: str):
        self._bucket = bucket
        return self

    def remove(self, paths: list[str]):
        self.pedidos.append((self._bucket, list(paths)))
        if self.fora_do_ar:
            raise RuntimeError("storage fora do ar (simulado)")
        no_bucket = self.arquivos.setdefault(self._bucket, set())
        corpo = []
        for p in paths:
            if p in self.recusar:
                corpo.append({"name": p, "error": "recusado (simulado)"})
                continue
            if p not in no_bucket:
                continue
            no_bucket.discard(p)
            corpo.append({"name": p, "bucket_id": self._bucket})
        return corpo

    def tem(self, bucket: str, path: str) -> bool:
        return path in self.arquivos.get(bucket, set())


class _SupabaseFake:
    def __init__(self, arquivos: list[dict], no_bucket: list[str] | None = None):
        self.storage = _StorageFake()
        self.escritas: list[tuple[str, str, dict]] = []
        self.tabelas: dict[str, list[dict]] = {"cm_arquivo": arquivos}
        if no_bucket is None:
            no_bucket = []
            for a in arquivos:
                if a.get("chave_bucket"):
                    no_bucket += [a["chave_bucket"], retencao.chave_do_texto(a["chave_bucket"])]
        self.storage.arquivos[retencao.BUCKET] = set(no_bucket)

    def table(self, nome: str):
        return _TabelaFake(nome, self.tabelas.setdefault(nome, []), self)

    def linha(self, arquivo_id: str) -> dict:
        return next(r for r in self.tabelas["cm_arquivo"] if r["id"] == arquivo_id)


class TestArquivoVencido:
    def test_vencido_some_do_bucket_e_ganha_carimbo_e_os_outros_ficam(self):
        vencido = _arquivo(1, apagar_em=ONTEM)
        no_prazo = _arquivo(2, apagar_em=AMANHA)
        carimbado = _arquivo(3, apagar_em=ONTEM, apagado_em=CARIMBO_ANTIGO)
        sb = _SupabaseFake([vencido, no_prazo, carimbado])
        # O carimbado já saiu do bucket de verdade; o resto está lá.
        sb.storage.arquivos[retencao.BUCKET] = {
            "envio-1/arq-1.pdf",
            "envio-1/arq-1.pdf.txt",
            "envio-1/arq-2.pdf",
            "envio-1/arq-2.pdf.txt",
        }

        retencao.apagar_arquivos_vencidos(sb, AGORA)

        assert not sb.storage.tem("contas-medicas", "envio-1/arq-1.pdf")
        assert sb.linha("arq-1")["apagado_em"] == AGORA.isoformat()

        assert sb.storage.tem("contas-medicas", "envio-1/arq-2.pdf")
        assert sb.storage.tem("contas-medicas", "envio-1/arq-2.pdf.txt")
        assert sb.linha("arq-2")["apagado_em"] is None

        assert sb.linha("arq-3")["apagado_em"] == CARIMBO_ANTIGO
        assert all(e[2].get("id") != "arq-3" for e in sb.escritas)
        assert all("arq-3" not in p for _, paths in sb.storage.pedidos for p in paths)

    def test_o_texto_extraido_ao_lado_do_pdf_sai_junto(self):
        sb = _SupabaseFake([_arquivo(1, apagar_em=ONTEM)])

        retencao.apagar_arquivos_vencidos(sb, AGORA)

        assert not sb.storage.tem("contas-medicas", "envio-1/arq-1.pdf.txt")

    def test_os_dados_estruturados_nao_sao_tocados(self):
        sb = _SupabaseFake([_arquivo(1, apagar_em=ONTEM)])
        sb.tabelas["cm_eventos"] = [{"id": "ev-1", "atendimento_id": "at-1", "eventos_json": {"dias": 3}}]
        sb.tabelas["cm_conta_item"] = [{"id": "it-1", "conta_id": "c-1", "codigo": "123"}]
        sb.tabelas["cm_guia_linha"] = [{"id": "gl-1", "conta_id": "c-1", "evidencia_trecho": "dipirona 1g"}]

        retencao.apagar_arquivos_vencidos(sb, AGORA)

        assert {t for t, _, _ in sb.escritas} == {"cm_arquivo"}
        assert sb.tabelas["cm_eventos"] == [{"id": "ev-1", "atendimento_id": "at-1", "eventos_json": {"dias": 3}}]
        assert sb.tabelas["cm_conta_item"] == [{"id": "it-1", "conta_id": "c-1", "codigo": "123"}]
        assert sb.tabelas["cm_guia_linha"] == [{"id": "gl-1", "conta_id": "c-1", "evidencia_trecho": "dipirona 1g"}]


class TestArquivoAusenteNoBucket:
    def test_arquivo_que_ja_saiu_do_bucket_e_carimbado_sem_erro(self):
        sb = _SupabaseFake([_arquivo(1, apagar_em=ONTEM)], no_bucket=[])

        rodada = retencao.apagar_arquivos_vencidos(sb, AGORA)

        assert sb.linha("arq-1")["apagado_em"] == AGORA.isoformat()
        assert rodada == retencao.Rodada(apagados=0, ausentes=1, falhas=0)

    def test_linha_sem_chave_no_bucket_e_carimbada_sem_pedir_nada_ao_storage(self):
        sb = _SupabaseFake([_arquivo(1, apagar_em=ONTEM, chave_bucket=None)])

        rodada = retencao.apagar_arquivos_vencidos(sb, AGORA)

        assert sb.linha("arq-1")["apagado_em"] == AGORA.isoformat()
        assert sb.storage.pedidos == []
        assert rodada.ausentes == 1


class TestFalhaDoStorage:
    def test_recusa_do_storage_deixa_a_linha_sem_carimbo_para_a_rodada_seguinte(self):
        sb = _SupabaseFake([_arquivo(1, apagar_em=ONTEM)])
        sb.storage.recusar = {"envio-1/arq-1.pdf"}

        rodada = retencao.apagar_arquivos_vencidos(sb, AGORA)

        assert sb.linha("arq-1")["apagado_em"] is None
        assert rodada == retencao.Rodada(apagados=0, ausentes=0, falhas=1)

    def test_storage_fora_do_ar_nao_carimba_e_nao_derruba_os_demais(self):
        sb = _SupabaseFake([_arquivo(1, apagar_em=ONTEM), _arquivo(2, apagar_em=ONTEM, chave_bucket=None)])
        sb.storage.fora_do_ar = True

        rodada = retencao.apagar_arquivos_vencidos(sb, AGORA)

        assert sb.linha("arq-1")["apagado_em"] is None
        assert sb.linha("arq-2")["apagado_em"] == AGORA.isoformat()
        assert rodada == retencao.Rodada(apagados=0, ausentes=1, falhas=1)


class TestJobNoScheduler:
    """A retenção roda sozinha, todo dia, no relógio do hospital."""

    def test_job_registrado_com_horario_diario_no_fuso_de_sao_paulo(self):
        from apscheduler.triggers.cron import CronTrigger

        from app.cron import scheduler as cron

        try:
            cron.start_scheduler()
            job = cron.scheduler.get_job("retencao_contas_medicas")
            assert job is not None
            assert job.func is cron.expurgar_arquivos_contas_medicas
            assert isinstance(job.trigger, CronTrigger)
            campos = {f.name: str(f) for f in job.trigger.fields}
            assert (campos["hour"], campos["minute"]) == ("4", "30")
            assert (campos["day"], campos["day_of_week"]) == ("*", "*")
            assert str(job.trigger.timezone) == "America/Sao_Paulo"
        finally:
            cron.stop_scheduler()


class TestLogDoJob:
    """O log do job traz só contagens: nem chave do bucket, nem número do
    atendimento, nem id da linha, nem mensagem de exceção."""

    def _rodar_job(self, monkeypatch, caplog, sb) -> str:
        from app.cron import scheduler as cron

        monkeypatch.setattr(cron, "_supabase", lambda: sb)
        with caplog.at_level("DEBUG"):
            cron.expurgar_arquivos_contas_medicas()
        return "\n".join(r.getMessage() for r in caplog.records)

    def test_log_traz_as_contagens_da_rodada(self, monkeypatch, caplog):
        sb = _SupabaseFake(
            [
                _arquivo(1, apagar_em=ONTEM),
                _arquivo(2, apagar_em=ONTEM),
                _arquivo(3, apagar_em=ONTEM, chave_bucket=None),
                _arquivo(4, apagar_em=ONTEM),
            ]
        )
        sb.storage.recusar = {"envio-1/arq-4.pdf"}

        log = self._rodar_job(monkeypatch, caplog, sb)

        assert "2 apagado(s), 1 já ausente(s), 1 falha(s)" in log
        for arquivo in sb.tabelas["cm_arquivo"]:
            assert arquivo["id"] not in log
            assert arquivo["numero_atendimento"] not in log
        assert "envio-1" not in log

    def test_falha_inesperada_loga_so_o_tipo_do_erro(self, monkeypatch, caplog):
        sb = _SupabaseFake([_arquivo(1, apagar_em=ONTEM)])

        def _quebra(_nome):
            raise RuntimeError("cm_arquivo envio-1/arq-1.pdf atendimento 770001")

        sb.table = _quebra

        log = self._rodar_job(monkeypatch, caplog, sb)

        assert "RuntimeError" in log
        assert "envio-1" not in log
        assert "770001" not in log
        assert all(r.exc_info is None for r in caplog.records)
