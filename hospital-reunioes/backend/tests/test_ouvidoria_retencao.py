"""Retenção com anonimização após 5 anos (issue #343, PRD #319, ADR 0034).

A política de retenção da Ouvidoria: manifestação encerrada há mais de cinco
anos perde o Dossiê (relato, identificação de quem manifestou, anexos) e
mantém os campos que os relatórios contam (tipo, área, gravidade, canal,
datas, marcos e desfecho). O ato entra na trilha imutável e o carimbo garante
que rodar de novo não mexe em nada.

Cobre os critérios de aceite da issue pelo seam do service (a função que o
scheduler chama), mais o registro do job no scheduler e a migration. Nenhum
email sai daqui: a retenção não notifica ninguém.
"""

from __future__ import annotations

import datetime as dt
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services import ouvidoria_retencao  # noqa: E402

# Relógio congelado: 26 de agosto de 2026.
AGORA = dt.datetime(2026, 8, 26, 12, 0, tzinfo=dt.UTC)

# Encerrada em 2020: passou dos cinco anos com folga.
ENCERRADA_HA_SEIS_ANOS = "2020-08-26T12:00:00+00:00"
# Encerrada em 2024: dentro dos cinco anos.
ENCERRADA_HA_DOIS_ANOS = "2024-08-26T12:00:00+00:00"


def _manifestacao(numero: int = 7, **overrides) -> dict:
    """Caso encerrado há seis anos, com o Dossiê inteiro preenchido."""
    row = {
        "id": f"uuid-{numero}",
        "numero": numero,
        "protocolo": f"2020-{numero:04d}",
        "status": "encerrado",
        "data_abertura": "2020-08-01",
        "contato_em": "2020-08-01T10:00:00+00:00",
        "validada_em": "2020-08-02T10:00:00+00:00",
        "respondida_em": "2020-08-10T10:00:00+00:00",
        "encerrada_em": ENCERRADA_HA_SEIS_ANOS,
        "prazo_area_em": "2020-08-09T20:00:00+00:00",
        "tipo_manifestacao": "reclamacao",
        "categoria": "Demora no atendimento",
        "setor": "Recepcao",
        "gravidade": "medio",
        "canal": "telefone",
        "desfecho": "procedente",
        "minutos_pausados": 120,
        "reincidencia": False,
        "anonimo": False,
        "sigilo_reforcado": False,
        # O Dossiê que a retenção apaga.
        "relato_integral": "Joana da Silva, RG 12.345.678, esperou tres horas na recepcao do dia 1.",
        "manifestante_nome": "Joana da Silva",
        "manifestante_contato": "joana@exemplo.com / 11 99999-0000",
        "manifestante_vinculo": "paciente",
        "resumo": "Paciente Joana relata espera acima de tres horas na recepcao.",
        "extrato_para_o_setor": "Espera de tres horas relatada por Joana da Silva. Apurar e responder.",
        "desfecho_descricao": "Confirmada a espera de Joana; a recepcao reforcou a escala.",
        "resposta_da_area": "Falamos com a paciente Joana da Silva e pedimos desculpas.",
        "classificacao_ia": {"tipo": "reclamacao", "trecho": "Joana esperou tres horas"},
        "conversa_id": "chatwoot-4821",
        "anonimizada_em": None,
    }
    row.update(overrides)
    return row


def _anexo(numero: int = 1, manifestacao_id: str = "uuid-7", **overrides) -> dict:
    row = {
        "id": f"anexo-{numero}",
        "manifestacao_id": manifestacao_id,
        "filename": "foto-joana.jpg",
        "content_type": "image/jpeg",
        "tamanho_bytes": 1024,
        "storage_path": f"2020/anexo-{numero}.jpg",
        "enviado_por": "P10",
        "enviado_por_nome": "Marta Ouvidora",
        "created_at": "2020-08-02T10:00:00+00:00",
    }
    row.update(overrides)
    return row


class _TabelaFake:
    """Fake do PostgREST fiel no que importa: o select projeta só o que foi
    pedido, update e delete filtram antes de agir (inclusive IS NULL) e o
    insert devolve a linha com o id que o banco geraria."""

    def __init__(self, nome: str, rows: list[dict]):
        self.nome = nome
        self.rows = rows
        self._filters: dict = {}
        self._nulos: list[str] = []
        self._ate: dict = {}
        self._insert: dict | list | None = None
        self._update: dict | None = None
        self._delete = False
        self._colunas: tuple[str, ...] | None = None
        self._limite: int | None = None

    def select(self, colunas: str = "*", *_a, **_kw):
        if colunas.strip() != "*":
            self._colunas = tuple(c.strip() for c in colunas.split(","))
        return self

    def insert(self, payload):
        self._insert = payload
        return self

    def update(self, payload: dict):
        self._update = payload
        return self

    def delete(self):
        self._delete = True
        return self

    def eq(self, col, value):
        self._filters[col] = value
        return self

    def is_(self, col, value):
        assert value in ("null", None)
        self._nulos.append(col)
        return self

    def lte(self, col, value):
        self._ate[col] = value
        return self

    def order(self, col, desc=False):
        self.rows = sorted(self.rows, key=lambda r: str(r.get(col) or ""), reverse=desc)
        return self

    def limit(self, n):
        self._limite = n
        return self

    def _projetar(self, row: dict) -> dict:
        if self._colunas is None:
            return dict(row)
        return {c: row.get(c) for c in self._colunas}

    def execute(self):
        if self._insert is not None:
            novos = self._insert if isinstance(self._insert, list) else [self._insert]
            gravados = []
            for n in novos:
                linha = dict(n)
                linha.setdefault("id", f"{self.nome}-{len(self.rows) + 1}")
                self.rows.append(linha)
                gravados.append(dict(linha))
            return type("R", (), {"data": gravados})()
        casadas = [
            r
            for r in self.rows
            if all(r.get(c) == v for c, v in self._filters.items())
            and all(r.get(c) is None for c in self._nulos)
            and all(r.get(c) is not None and str(r.get(c)) <= v for c, v in self._ate.items())
        ]
        if self._limite is not None:
            casadas = casadas[: self._limite]
        if self._update is not None:
            for r in casadas:
                r.update(self._update)
        if self._delete:
            apagadas = [dict(r) for r in casadas]
            for r in casadas:
                self.rows.remove(r)
            return type("R", (), {"data": apagadas})()
        return type("R", (), {"data": [self._projetar(r) for r in casadas]})()


class _StorageFake:
    def __init__(self):
        self.removidos: list[tuple[str, str]] = []
        self._bucket = ""

    def from_(self, bucket: str):
        self._bucket = bucket
        return self

    def remove(self, paths: list[str]):
        for p in paths:
            self.removidos.append((self._bucket, p))
        return {"data": []}


class _SupabaseFake:
    def __init__(self, manifestacoes: list[dict] | None = None, anexos: list[dict] | None = None):
        self.storage = _StorageFake()
        self.tabelas: dict[str, list[dict]] = {
            "ouvidoria_protocolos": manifestacoes if manifestacoes is not None else [_manifestacao()],
            "ouvidoria_anexos": anexos if anexos is not None else [],
            "ouvidoria_movimentos": [],
        }

    def table(self, nome: str):
        return _TabelaFake(nome, self.tabelas.setdefault(nome, []))


class TestDossieApagado:
    def test_caso_encerrado_ha_mais_de_cinco_anos_perde_o_dossie(self):
        supabase = _SupabaseFake()

        anonimizadas = ouvidoria_retencao.anonimizar_encerradas_antigas(supabase, AGORA)

        assert anonimizadas == 1
        caso = supabase.tabelas["ouvidoria_protocolos"][0]
        assert caso["relato_integral"] is None
        assert caso["manifestante_nome"] is None
        assert caso["manifestante_contato"] is None
        # O que sobrou de texto livre não pode carregar quem manifestou.
        sobrou = " ".join(str(v) for v in caso.values())
        assert "Joana" not in sobrou

    def test_campos_estatisticos_sobrevivem_inteiros_a_anonimizacao(self):
        """O que os relatórios contam não pode mudar: tipo, área, gravidade,
        canal, datas, marcos e desfecho seguem iguais ao que eram antes."""
        supabase = _SupabaseFake()
        antes = dict(supabase.tabelas["ouvidoria_protocolos"][0])

        ouvidoria_retencao.anonimizar_encerradas_antigas(supabase, AGORA)

        depois = supabase.tabelas["ouvidoria_protocolos"][0]
        for campo in ouvidoria_retencao.CAMPOS_ESTATISTICOS:
            assert campo in antes, f"a fixture não cobre o campo estatístico {campo}"
            assert depois[campo] == antes[campo], f"a anonimização mexeu em {campo}"


class TestQuemNaoEhTocado:
    """As duas recusas, cada uma com as outras portas escancaradas: o caso
    recusado só difere do anonimizável no motivo da recusa."""

    def test_caso_encerrado_ha_menos_de_cinco_anos_fica_intacto(self):
        supabase = _SupabaseFake(manifestacoes=[_manifestacao(encerrada_em=ENCERRADA_HA_DOIS_ANOS)])
        antes = dict(supabase.tabelas["ouvidoria_protocolos"][0])

        anonimizadas = ouvidoria_retencao.anonimizar_encerradas_antigas(supabase, AGORA)

        assert anonimizadas == 0
        assert supabase.tabelas["ouvidoria_protocolos"][0] == antes
        assert supabase.tabelas["ouvidoria_movimentos"] == []

    def test_caso_antigo_que_nao_esta_encerrado_fica_intacto(self):
        """Manifestação reaberta por reincidência guarda o `encerrada_em` do
        ciclo anterior. Sem a porta do estado, ela seria anonimizada em pleno
        andamento."""
        supabase = _SupabaseFake(
            manifestacoes=[_manifestacao(status="aguardando_area", reincidencia=True, reaberta_em=None)]
        )
        antes = dict(supabase.tabelas["ouvidoria_protocolos"][0])

        anonimizadas = ouvidoria_retencao.anonimizar_encerradas_antigas(supabase, AGORA)

        assert anonimizadas == 0
        assert supabase.tabelas["ouvidoria_protocolos"][0] == antes
        assert supabase.tabelas["ouvidoria_movimentos"] == []

    def test_caso_encerrado_sem_o_marco_do_encerramento_fica_intacto(self):
        """Sem `encerrada_em` não há como afirmar que os cinco anos passaram:
        o caso espera decisão humana em vez de perder o Dossiê por chute."""
        supabase = _SupabaseFake(manifestacoes=[_manifestacao(encerrada_em=None)])
        antes = dict(supabase.tabelas["ouvidoria_protocolos"][0])

        anonimizadas = ouvidoria_retencao.anonimizar_encerradas_antigas(supabase, AGORA)

        assert anonimizadas == 0
        assert supabase.tabelas["ouvidoria_protocolos"][0] == antes


class TestTrilha:
    def test_anonimizacao_entra_na_trilha_do_caso(self):
        supabase = _SupabaseFake()

        ouvidoria_retencao.anonimizar_encerradas_antigas(supabase, AGORA)

        movimentos = supabase.tabelas["ouvidoria_movimentos"]
        assert len(movimentos) == 1
        movimento = movimentos[0]
        assert movimento["manifestacao_id"] == "uuid-7"
        # Anonimizar não muda o estado: o caso segue encerrado.
        assert movimento["estado_anterior"] == "encerrado"
        assert movimento["estado_novo"] == "encerrado"
        assert movimento["autor_id"] is None
        assert "anonimiza" in (movimento["observacao"] or "").lower()

    def test_a_observacao_da_trilha_nao_reintroduz_o_dossie(self):
        """A trilha é imutável: um nome escrito ali seria dado pessoal que a
        retenção nunca mais conseguiria apagar."""
        supabase = _SupabaseFake()

        ouvidoria_retencao.anonimizar_encerradas_antigas(supabase, AGORA)

        movimento = supabase.tabelas["ouvidoria_movimentos"][0]
        assert "Joana" not in " ".join(str(v) for v in movimento.values())


class TestAnexos:
    def test_anexos_do_caso_saem_do_banco_e_do_storage(self):
        supabase = _SupabaseFake(anexos=[_anexo(1), _anexo(2)])

        ouvidoria_retencao.anonimizar_encerradas_antigas(supabase, AGORA)

        assert supabase.tabelas["ouvidoria_anexos"] == []
        caminhos = {caminho for _bucket, caminho in supabase.storage.removidos}
        assert caminhos == {"2020/anexo-1.jpg", "2020/anexo-2.jpg"}
        assert {bucket for bucket, _c in supabase.storage.removidos} == {"anexos-ouvidoria"}

    def test_anexo_de_outro_caso_nao_e_apagado(self):
        """O caso vizinho é recente: o binário dele não pode ir junto."""
        supabase = _SupabaseFake(
            manifestacoes=[_manifestacao(7), _manifestacao(8, encerrada_em=ENCERRADA_HA_DOIS_ANOS)],
            anexos=[_anexo(1, manifestacao_id="uuid-7"), _anexo(9, manifestacao_id="uuid-8")],
        )

        ouvidoria_retencao.anonimizar_encerradas_antigas(supabase, AGORA)

        restantes = supabase.tabelas["ouvidoria_anexos"]
        assert [a["id"] for a in restantes] == ["anexo-9"]
        assert supabase.storage.removidos == [("anexos-ouvidoria", "2020/anexo-1.jpg")]


class TestIdempotencia:
    def test_segunda_execucao_nao_muda_nada_nem_gera_movimento_novo(self):
        supabase = _SupabaseFake(anexos=[_anexo(1)])

        primeira = ouvidoria_retencao.anonimizar_encerradas_antigas(supabase, AGORA)
        depois_da_primeira = dict(supabase.tabelas["ouvidoria_protocolos"][0])
        removidos_na_primeira = list(supabase.storage.removidos)

        segunda = ouvidoria_retencao.anonimizar_encerradas_antigas(supabase, AGORA + dt.timedelta(days=1))

        assert primeira == 1
        assert segunda == 0
        assert supabase.tabelas["ouvidoria_protocolos"][0] == depois_da_primeira
        assert len(supabase.tabelas["ouvidoria_movimentos"]) == 1
        assert supabase.storage.removidos == removidos_na_primeira


class TestDataDeCorte:
    def test_corte_recua_cinco_anos_no_mesmo_dia(self):
        assert ouvidoria_retencao.data_de_corte(AGORA) == dt.datetime(2021, 8, 26, 12, 0, tzinfo=dt.UTC)

    def test_vinte_e_nove_de_fevereiro_recua_para_o_dia_28(self):
        """2024 é bissexto, 2019 não: sem tratar isso o job quebraria no dia."""
        bissexto = dt.datetime(2024, 2, 29, 12, 0, tzinfo=dt.UTC)

        assert ouvidoria_retencao.data_de_corte(bissexto) == dt.datetime(2019, 2, 28, 12, 0, tzinfo=dt.UTC)


class TestMigration:
    """A 079 dá ao caso o carimbo de idempotência da retenção e o índice da
    varredura. Reaplicável sem quebrar (padrão da casa)."""

    def _ddl(self) -> str:
        caminho = os.path.join(
            os.path.dirname(__file__),
            "..",
            "..",
            "supabase",
            "migrations",
            "079_ouvidoria_retencao_anonimizacao.sql",
        )
        with open(caminho, encoding="utf-8") as f:
            return f.read().lower()

    def test_caso_ganha_o_carimbo_de_anonimizacao(self):
        assert "add column if not exists anonimizada_em" in self._ddl()

    def test_migration_e_idempotente(self):
        ddl = self._ddl()
        assert "add column if not exists" in ddl
        assert "create index if not exists" in ddl

    def test_indice_cobre_exatamente_a_varredura_do_job(self):
        """O job lê por status encerrado, sem carimbo, ordenando por
        `encerrada_em`."""
        ddl = self._ddl()
        assert "idx_ouvidoria_protocolos_retencao" in ddl
        assert "encerrada_em" in ddl
        assert "anonimizada_em is null" in ddl
        assert "'encerrado'" in ddl


class TestJobNoScheduler:
    """A retenção roda sozinha, sem ninguém pedir."""

    def test_job_de_retencao_esta_registrado(self):
        from app.cron import scheduler as cron

        try:
            cron.start_scheduler()
            assert cron.scheduler.get_job("retencao_ouvidoria") is not None
        finally:
            cron.stop_scheduler()
