"""Registro manual do ouvidor, com anexos (issue #321, PRD #317, ADR 0034).

O que chega por telefone, balcão ou email entra pelo mesmo registro único: o
ouvidor digita, informa a data e hora REAIS do contato (o T0 é quando chegou ao
hospital, não quando foi digitado) e anexa a evidência.

Cobre os critérios de aceite da issue #321, todos pelo seam HTTP (o mesmo dos
testes de ouvidoria já existentes), mais a regra de anexo como função pura.
"""

from __future__ import annotations

import os
import sys

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from postgrest.exceptions import APIError
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.dependencies import get_current_user, get_supabase_client  # noqa: E402
from app.limiter import limiter  # noqa: E402
from app.middleware.request_context import RequestContextMiddleware  # noqa: E402
from app.routers import ouvidoria as ouvidoria_router  # noqa: E402
from app.services.ouvidoria_anexos import (  # noqa: E402
    LIMITE_BYTES,
    AnexoGrandeDemaisError,
    TipoNaoPermitidoError,
    validar_anexo,
)

OUVIDOR = {"id": "P10", "nome_completo": "Marta Ouvidora", "access_profile": None, "perfil_ouvidoria": "ouvidor"}
DIRETORIA = {
    "id": "P11",
    "nome_completo": "Dr. Diretor",
    "access_profile": "regular",
    "perfil_ouvidoria": "diretoria_executiva",
}
SECRETARIA = {"id": "P02", "nome_completo": "Sofia Secretaria", "access_profile": "secretaria"}
SUPER_ADMIN = {"id": "P03", "nome_completo": "Pedro Admin", "access_profile": "super_admin"}

REGISTRO = {
    "canal": "telefone",
    "contato_em": "2026-08-14T16:50:00",
    # Lista fechada desde a issue #372: o rótulo em `categoria` é a palavra do
    # ouvidor, e quem decide o sigilo é o tipo.
    "tipo_manifestacao": "reclamacao",
    "categoria": "Demora no atendimento",
    "setor": "Recepcao",
    "resumo": "Paciente relata espera acima de duas horas na recepcao.",
    "relato_integral": "Cheguei as 8h com minha mae e so fomos atendidos as 10h30.",
    "manifestante_nome": "Joana da Silva",
    "manifestante_contato": "(31) 99999-0000",
    "manifestante_vinculo": "acompanhante",
}


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    limiter._storage.reset()
    yield
    limiter._storage.reset()


class _TabelaFake:
    """Fake do PostgREST fiel no que importa: o insert devolve as colunas
    geradas pelo banco (numero, protocolo ANO-NNNN, prazo_resposta) e o select
    projeta só o que foi pedido."""

    def __init__(self, nome: str, rows: list[dict], falhar_insert: bool = False, recusar_filtro: bool = False):
        self.nome = nome
        self.rows = rows
        self.falhar_insert = falhar_insert
        self.recusar_filtro = recusar_filtro
        self._filters: dict = {}
        self._insert: dict | list | None = None
        self._colunas: tuple[str, ...] | None = None

    def select(self, colunas: str = "*", *_a, **_kw):
        if colunas.strip() != "*":
            self._colunas = tuple(c.strip() for c in colunas.split(","))
        return self

    def insert(self, payload):
        self._insert = payload
        return self

    def eq(self, col, value):
        self._filters[col] = value
        return self

    def order(self, col, desc=False):
        self.rows = sorted(self.rows, key=lambda r: r.get(col) or "", reverse=desc)
        return self

    def _gerar_colunas_do_banco(self, row: dict) -> dict:
        if self.nome != "ouvidoria_protocolos":
            row.setdefault("id", f"{self.nome}-{len(self.rows) + 1}")
            return row
        numero = len(self.rows) + 7
        abertura = row.get("data_abertura") or "2026-08-24"
        row.setdefault("id", f"uuid-{numero}")
        row["numero"] = numero
        row["data_abertura"] = abertura
        row["protocolo"] = f"{abertura[:4]}-{numero:04d}"
        row["prazo_resposta"] = "2026-08-21"
        row.setdefault("status", "em_classificacao")
        return row

    def _projetar(self, row: dict) -> dict:
        if self._colunas is None:
            return dict(row)
        return {c: row.get(c) for c in self._colunas}

    def execute(self):
        if self._insert is not None:
            if self.falhar_insert:
                raise APIError({"code": "23503", "message": "insert recusado"})
            novos = self._insert if isinstance(self._insert, list) else [self._insert]
            gravados = [self._gerar_colunas_do_banco(dict(n)) for n in novos]
            self.rows.extend(gravados)
            return type("R", (), {"data": [dict(g) for g in gravados]})()
        if self.recusar_filtro and any(v == "nao-e-uuid" for v in self._filters.values()):
            # Fiel ao PostgREST: id que não é UUID não vira "zero linhas", vira
            # erro de sintaxe de entrada (22P02).
            raise APIError({"code": "22P02", "message": "invalid input syntax for type uuid"})
        casadas = [r for r in self.rows if all(r.get(c) == v for c, v in self._filters.items())]
        return type("R", (), {"data": [self._projetar(r) for r in casadas]})()


class _BucketFake:
    def __init__(self, dono: _StorageFake, bucket: str):
        self.dono = dono
        self.bucket = bucket

    def upload(self, path, content, _opcoes=None):
        self.dono.arquivos[f"{self.bucket}/{path}"] = content

    def remove(self, paths):
        for path in paths:
            self.dono.arquivos.pop(f"{self.bucket}/{path}", None)

    def create_signed_url(self, path, expires_in):
        chave = f"{self.bucket}/{path}"
        if chave not in self.dono.arquivos:
            raise RuntimeError("Objeto inexistente no storage")
        self.dono.assinaturas.append({"path": chave, "expires_in": expires_in})
        return {"signedURL": f"https://storage.local/{chave}?token=assinado&exp={expires_in}"}


class _StorageFake:
    def __init__(self):
        self.arquivos: dict[str, bytes] = {}
        self.assinaturas: list[dict] = []

    def from_(self, bucket: str):
        return _BucketFake(self, bucket)


class _SupabaseFake:
    def __init__(self, manifestacoes: list[dict] | None = None):
        self.tabelas: dict[str, list[dict]] = {
            "ouvidoria_protocolos": manifestacoes if manifestacoes is not None else [],
            "ouvidoria_movimentos": [],
            "ouvidoria_acessos": [],
            "ouvidoria_anexos": [],
            # A taxonomia da casa: desde a issue #419 o setor da manifestação é
            # conferido contra ela nas portas que o gravam.
            "setores": [{"id": "s1", "nome": "Recepcao", "ativo": True}],
        }
        self.storage = _StorageFake()
        self.falhar_insert_em: str | None = None
        self.recusar_filtro_invalido = False

    def table(self, nome: str):
        return _TabelaFake(
            nome,
            self.tabelas.setdefault(nome, []),
            falhar_insert=self.falhar_insert_em == nome,
            recusar_filtro=self.recusar_filtro_invalido,
        )


def _client(monkeypatch, participante: dict | None, manifestacoes: list[dict] | None = None):
    app = FastAPI()
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(RequestContextMiddleware)
    app.include_router(ouvidoria_router.router, prefix="/api")

    supabase = _SupabaseFake(manifestacoes)

    async def _fake_participante(_user, _sb, fields=None):
        return participante

    monkeypatch.setattr(ouvidoria_router, "get_participante_for_user", _fake_participante)
    app.dependency_overrides[get_current_user] = lambda: {"id": "u1", "email": "u@hsm.br"}
    app.dependency_overrides[get_supabase_client] = lambda: supabase
    return TestClient(app), supabase


class TestRegistroManual:
    """O ouvidor registra o que chegou por telefone, balcão ou email."""

    def test_registro_manual_grava_o_t0_informado_e_nao_o_momento_do_clique(self, monkeypatch):
        """A manifestação chegou dia 14 às 16h50, mesmo que o ouvidor só tenha
        digitado depois: o T0 é o contato real, e a abertura acompanha ele."""
        client, supabase = _client(monkeypatch, OUVIDOR)

        r = client.post("/api/ouvidoria/manifestacoes", json=REGISTRO)

        assert r.status_code == 201, r.text
        gravado = supabase.tabelas["ouvidoria_protocolos"][0]
        assert gravado["contato_em"].startswith("2026-08-14T16:50")
        assert gravado["data_abertura"] == "2026-08-14"
        assert gravado["canal"] == "telefone"

    def test_protocolo_volta_na_resposta_e_o_caso_entra_na_fila_em_classificacao(self, monkeypatch):
        """O ouvidor precisa dizer o número a quem manifestou na hora, e o caso
        entra na mesma fila do painel: ninguém aciona setor sem validação."""
        client, _ = _client(monkeypatch, OUVIDOR)

        criada = client.post("/api/ouvidoria/manifestacoes", json=REGISTRO)

        assert criada.status_code == 201
        assert criada.json()["protocolo"] == "2026-0007"
        assert criada.json()["status"] == "em_classificacao"

        fila = client.get("/api/ouvidoria/protocolos")
        assert [m["protocolo"] for m in fila.json()["protocolos"]] == ["2026-0007"]

    def test_abertura_manual_abre_a_trilha_do_caso(self, monkeypatch):
        """História 17 do PRD: a trilha começa no nascimento do caso, para a
        reconstituição não ter buraco no primeiro passo."""
        client, supabase = _client(monkeypatch, OUVIDOR)

        client.post("/api/ouvidoria/manifestacoes", json=REGISTRO)

        movimento = supabase.tabelas["ouvidoria_movimentos"][0]
        assert movimento["estado_anterior"] is None
        assert movimento["estado_novo"] == "em_classificacao"
        assert movimento["autor_nome"] == "Marta Ouvidora"

    def test_data_de_contato_no_futuro_e_recusada(self, monkeypatch):
        """Retroativo é o caso normal; futuro é erro de digitação que empurraria
        o prazo do setor sem ninguém perceber."""
        client, supabase = _client(monkeypatch, OUVIDOR)

        r = client.post("/api/ouvidoria/manifestacoes", json={**REGISTRO, "contato_em": "2099-01-01T09:00:00"})

        assert r.status_code == 422
        assert supabase.tabelas["ouvidoria_protocolos"] == []


class TestAnonimato:
    """Quem não quer se identificar pode: acolher sem nome é função da
    ouvidoria (história 3 do PRD)."""

    def test_manifestacao_anonima_salva_sem_nome_e_sem_contato(self, monkeypatch):
        """Mesmo que o corpo traga identificação, marcar anônima apaga: a
        escolha de quem manifesta vale contra o que foi digitado."""
        client, supabase = _client(monkeypatch, OUVIDOR)

        r = client.post("/api/ouvidoria/manifestacoes", json={**REGISTRO, "anonimo": True})

        assert r.status_code == 201
        gravado = supabase.tabelas["ouvidoria_protocolos"][0]
        assert gravado["anonimo"] is True
        assert gravado["manifestante_nome"] is None
        assert gravado["manifestante_contato"] is None
        assert gravado["relato_integral"].startswith("Cheguei as 8h"), "O relato não se perde no anonimato"


class TestSigiloReforcado:
    """Denúncia e relato de conduta nascem sigilosos (ADR 0034, decisão 1) e
    seguem as regras de acesso da fatia de fundação. Quem diz o que o caso é
    passou a ser o tipo, em lista fechada (issue #372)."""

    @pytest.mark.parametrize("tipo", ["denuncia", "relato_de_conduta"])
    def test_denuncia_e_relato_de_conduta_nascem_sigilosos(self, monkeypatch, tipo):
        client, supabase = _client(monkeypatch, OUVIDOR)

        r = client.post("/api/ouvidoria/manifestacoes", json={**REGISTRO, "tipo_manifestacao": tipo})

        assert r.status_code == 201
        assert supabase.tabelas["ouvidoria_protocolos"][0]["sigilo_reforcado"] is True

    def test_rotulo_fora_do_padrao_nao_deixa_o_caso_desprotegido(self, monkeypatch):
        """O furo que a lista fechada tapa (issue #372): a regra antiga lia o
        texto digitado, e "Assédio moral" não casava com palavra nenhuma."""
        client, supabase = _client(monkeypatch, OUVIDOR)

        client.post(
            "/api/ouvidoria/manifestacoes",
            json={**REGISTRO, "tipo_manifestacao": "relato_de_conduta", "categoria": "Assedio moral"},
        )

        assert supabase.tabelas["ouvidoria_protocolos"][0]["sigilo_reforcado"] is True

    def test_tipo_fora_da_lista_e_recusado(self, monkeypatch):
        """Categoria escrita à mão não existe mais: o que não está na lista não
        entra, e o caso não é registrado."""
        client, supabase = _client(monkeypatch, OUVIDOR)

        r = client.post("/api/ouvidoria/manifestacoes", json={**REGISTRO, "tipo_manifestacao": "Denúncia"})

        assert r.status_code == 422
        assert supabase.tabelas["ouvidoria_protocolos"] == []

    def test_manifestacao_comum_nao_nasce_sigilosa(self, monkeypatch):
        client, supabase = _client(monkeypatch, OUVIDOR)

        client.post("/api/ouvidoria/manifestacoes", json=REGISTRO)

        assert supabase.tabelas["ouvidoria_protocolos"][0]["sigilo_reforcado"] is False

    @pytest.mark.parametrize(
        "rotulo",
        ["Elogio pela conduta da equipe", "Conduta do estacionamento terceirizado"],
    )
    def test_a_palavra_conduta_no_rotulo_nao_esconde_o_caso(self, monkeypatch, rotulo):
        """Sigiloso some do índice de todo mundo fora da Ouvidoria: transformar
        um elogio em caso invisível por causa de uma palavra seria pior do que
        não ter a regra. O rótulo não decide nada."""
        client, supabase = _client(monkeypatch, OUVIDOR)

        client.post(
            "/api/ouvidoria/manifestacoes",
            json={**REGISTRO, "tipo_manifestacao": "elogio", "categoria": rotulo},
        )

        assert supabase.tabelas["ouvidoria_protocolos"][0]["sigilo_reforcado"] is False

    def test_sigilosa_registrada_a_mao_nao_aparece_para_o_super_admin(self, monkeypatch):
        """A regra de acesso da fundação vale para o que nasce aqui: o super
        admin técnico fica de fora da denúncia (RN-40)."""
        client, supabase = _client(monkeypatch, OUVIDOR)
        client.post("/api/ouvidoria/manifestacoes", json={**REGISTRO, "tipo_manifestacao": "denuncia"})

        admin, _ = _client(monkeypatch, SUPER_ADMIN, supabase.tabelas["ouvidoria_protocolos"])

        indice = admin.get("/api/ouvidoria/protocolos")
        dossie = admin.get("/api/ouvidoria/manifestacoes/uuid-7")
        assert indice.json()["protocolos"] == []
        assert dossie.status_code == 403


class TestGateDePerfil:
    """Papéis sem perfil de ouvidoria não acessam o endpoint (critério da
    issue): registrar manifestação é ato da Ouvidoria."""

    @pytest.mark.parametrize("papel", [SECRETARIA, SUPER_ADMIN, None])
    def test_papel_sem_perfil_de_ouvidoria_nao_registra_manifestacao(self, monkeypatch, papel):
        client, supabase = _client(monkeypatch, papel)

        r = client.post("/api/ouvidoria/manifestacoes", json=REGISTRO)

        assert r.status_code == 403
        assert supabase.tabelas["ouvidoria_protocolos"] == []

    def test_diretoria_executiva_tambem_registra(self, monkeypatch):
        client, _ = _client(monkeypatch, DIRETORIA)

        r = client.post("/api/ouvidoria/manifestacoes", json=REGISTRO)

        assert r.status_code == 201

    @pytest.mark.parametrize("papel", [SECRETARIA, SUPER_ADMIN, None])
    def test_papel_sem_perfil_de_ouvidoria_nao_mexe_em_anexo(self, monkeypatch, papel):
        client, supabase = _client(monkeypatch, papel, [_MANIFESTACAO])

        envio = client.post(
            "/api/ouvidoria/manifestacoes/uuid-7/anexos",
            files={"file": ("foto.jpg", b"binario", "image/jpeg")},
        )
        listagem = client.get("/api/ouvidoria/manifestacoes/uuid-7/anexos")

        assert envio.status_code == 403
        assert listagem.status_code == 403
        assert supabase.tabelas["ouvidoria_anexos"] == []


_MANIFESTACAO = {
    "id": "uuid-7",
    "numero": 7,
    "protocolo": "2026-0007",
    "data_abertura": "2026-08-14",
    "prazo_resposta": "2026-08-21",
    "status": "em_classificacao",
    "categoria": "Demora no atendimento",
    "setor": "Recepcao",
    "resumo": "Paciente relata espera acima de duas horas na recepcao.",
    "conversa_id": "",
    "sigilo_reforcado": False,
}


class TestAnexos:
    """A evidência (foto do quarto, PDF da conta, áudio do telefonema) fica
    junto do caso, e o binário fora do banco (ADR 0034)."""

    def test_anexo_sobe_fica_listado_no_caso_e_o_binario_vai_para_o_storage(self, monkeypatch):
        client, supabase = _client(monkeypatch, OUVIDOR, [_MANIFESTACAO])

        envio = client.post(
            "/api/ouvidoria/manifestacoes/uuid-7/anexos",
            files={"file": ("conta-do-quarto.pdf", b"%PDF-1.4 conteudo", "application/pdf")},
        )

        assert envio.status_code == 201, envio.text
        assert envio.json()["filename"] == "conta-do-quarto.pdf"
        assert envio.json()["tamanho_bytes"] == len(b"%PDF-1.4 conteudo")

        listados = client.get("/api/ouvidoria/manifestacoes/uuid-7/anexos").json()["anexos"]
        assert [a["filename"] for a in listados] == ["conta-do-quarto.pdf"]
        assert len(supabase.storage.arquivos) == 1, "O binário precisa ir ao storage, não ao banco"

    def test_anexo_abre_por_url_assinada_com_expiracao(self, monkeypatch):
        """Evidência de ouvidoria não fica em bucket público: o link é assinado
        e morre sozinho."""
        client, supabase = _client(monkeypatch, OUVIDOR, [_MANIFESTACAO])
        anexo_id = client.post(
            "/api/ouvidoria/manifestacoes/uuid-7/anexos",
            files={"file": ("foto.jpg", b"binario da foto", "image/jpeg")},
        ).json()["id"]

        r = client.get(f"/api/ouvidoria/manifestacoes/uuid-7/anexos/{anexo_id}/url")

        assert r.status_code == 200, r.text
        assert r.json()["url"].startswith("https://storage.local/")
        assert r.json()["expira_em_segundos"] > 0
        assert supabase.storage.assinaturas[0]["expires_in"] == r.json()["expira_em_segundos"]

    def test_anexo_acima_de_20_mb_e_recusado_com_mensagem_clara(self, monkeypatch):
        client, supabase = _client(monkeypatch, OUVIDOR, [_MANIFESTACAO])
        grande = b"x" * (20 * 1024 * 1024 + 1)

        r = client.post(
            "/api/ouvidoria/manifestacoes/uuid-7/anexos",
            files={"file": ("video-do-corredor.mp3", grande, "audio/mpeg")},
        )

        assert r.status_code == 413
        assert "20 MB" in r.json()["detail"]
        assert supabase.tabelas["ouvidoria_anexos"] == []
        assert supabase.storage.arquivos == {}, "Arquivo recusado não pode ficar no storage"

    def test_tipo_de_arquivo_nao_permitido_e_recusado_com_mensagem_clara(self, monkeypatch):
        client, supabase = _client(monkeypatch, OUVIDOR, [_MANIFESTACAO])

        r = client.post(
            "/api/ouvidoria/manifestacoes/uuid-7/anexos",
            files={"file": ("planilha.exe", b"MZ binario", "application/octet-stream")},
        )

        assert r.status_code == 415
        assert ".exe" in r.json()["detail"]
        assert supabase.tabelas["ouvidoria_anexos"] == []
        assert supabase.storage.arquivos == {}

    def test_anexo_de_manifestacao_inexistente_nao_e_aceito(self, monkeypatch):
        client, supabase = _client(monkeypatch, OUVIDOR, [_MANIFESTACAO])

        r = client.post(
            "/api/ouvidoria/manifestacoes/uuid-404/anexos",
            files={"file": ("foto.jpg", b"binario", "image/jpeg")},
        )

        assert r.status_code == 404
        assert supabase.storage.arquivos == {}

    def test_anexo_de_outro_caso_nao_abre_pelo_id_desta_manifestacao(self, monkeypatch):
        """O id do anexo não basta: ele precisa ser deste caso, senão o link
        assinado vira caminho lateral para a evidência alheia."""
        outra = {**_MANIFESTACAO, "id": "uuid-8", "numero": 8, "protocolo": "2026-0008"}
        client, _ = _client(monkeypatch, OUVIDOR, [_MANIFESTACAO, outra])
        anexo_id = client.post(
            "/api/ouvidoria/manifestacoes/uuid-8/anexos",
            files={"file": ("foto.jpg", b"binario", "image/jpeg")},
        ).json()["id"]

        r = client.get(f"/api/ouvidoria/manifestacoes/uuid-7/anexos/{anexo_id}/url")

        assert r.status_code == 404

    def test_id_de_anexo_invalido_devolve_404_e_nao_erro_do_banco(self, monkeypatch):
        """Id que não é UUID faz o PostgREST recusar o filtro: por fora isso é
        anexo inexistente, não falha do servidor."""
        client, supabase = _client(monkeypatch, OUVIDOR, [_MANIFESTACAO])
        supabase.recusar_filtro_invalido = True

        r = client.get("/api/ouvidoria/manifestacoes/uuid-7/anexos/nao-e-uuid/url")

        assert r.status_code == 404

    def test_falha_ao_gravar_o_anexo_nao_deixa_binario_orfao_no_storage(self, monkeypatch):
        """O bucket não tem faxina: binário sem linha no banco é lixo que
        ninguém alcança e nada recolhe."""
        client, supabase = _client(monkeypatch, OUVIDOR, [_MANIFESTACAO])
        supabase.falhar_insert_em = "ouvidoria_anexos"

        r = client.post(
            "/api/ouvidoria/manifestacoes/uuid-7/anexos",
            files={"file": ("foto.jpg", b"binario", "image/jpeg")},
        )

        assert r.status_code == 500
        assert supabase.storage.arquivos == {}, "O binário ficou órfão no storage"

    def test_ler_a_lista_de_anexos_entra_na_trilha_de_acesso(self, monkeypatch):
        """O nome do arquivo pode identificar quem manifestou: ler a lista já é
        acesso ao caso (invariante de LGPD do ADR 0034)."""
        client, supabase = _client(monkeypatch, OUVIDOR, [_MANIFESTACAO])

        client.get("/api/ouvidoria/manifestacoes/uuid-7/anexos")

        assert [a["acao"] for a in supabase.tabelas["ouvidoria_acessos"]] == ["listar_anexos"]


class TestRegraDoAnexo:
    """A regra de tipo e tamanho como função pura: a borda exata do limite não
    precisa de 20 MB trafegando por HTTP para ser verificada."""

    def test_arquivo_exatamente_no_limite_e_aceito(self):
        extensao, content_type = validar_anexo("foto.jpg", LIMITE_BYTES)

        assert (extensao, content_type) == (".jpg", "image/jpeg")

    def test_um_byte_acima_do_limite_e_recusado(self):
        with pytest.raises(AnexoGrandeDemaisError):
            validar_anexo("foto.jpg", LIMITE_BYTES + 1)

    def test_arquivo_sem_extensao_e_recusado(self):
        with pytest.raises(TipoNaoPermitidoError):
            validar_anexo("documento", 1024)

    def test_extensao_em_caixa_alta_continua_valendo(self):
        """Foto de celular chega como IMG_0042.JPG: caixa não é tipo novo."""
        assert validar_anexo("IMG_0042.JPG", 1024)[0] == ".jpg"

    def test_content_type_sai_da_extensao_e_nao_do_que_o_cliente_declarou(self):
        """Quem envia pode mentir no header; o storage serve o que a gente
        gravou, então o tipo vem da extensão que passou na lista."""
        assert validar_anexo("relatorio.pdf", 2048)[1] == "application/pdf"


MIGRATIONS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "supabase", "migrations")
MIGRATION_REGISTRO_MANUAL = "066_ouvidoria_registro_manual_anexos.sql"


def _ddl(nome: str = MIGRATION_REGISTRO_MANUAL) -> str:
    with open(os.path.join(MIGRATIONS_DIR, nome), encoding="utf-8") as f:
        return f.read()


class TestSchemaDoRegistroManual:
    """Invariantes que precisam valer no banco, e não só na API: contornar a
    API não pode contornar a regra."""

    def test_anexo_tem_rls_default_deny(self):
        ddl = _ddl().lower()
        assert "alter table ouvidoria_anexos enable row level security" in ddl, (
            "Tabela nova sem RLS abre o anexo pela anon_key do bundle do frontend"
        )

    def test_bucket_do_anexo_e_privado_e_sem_leitura_para_qualquer_logado(self):
        ddl = _ddl().lower()
        assert "'anexos-ouvidoria', 'anexos-ouvidoria', false" in ddl, "Bucket de evidência não pode ser público"
        comandos = [linha for linha in ddl.splitlines() if not linha.strip().startswith("--")]
        assert not any("create policy" in linha for linha in comandos), (
            "Evidência de ouvidoria não se lê por estar logado no app: só por URL assinada pelo backend"
        )

    def test_banco_tambem_recusa_anexo_acima_de_20_mb(self):
        ddl = _ddl().lower()
        assert str(LIMITE_BYTES) in ddl, "O limite da API precisa estar no CHECK da tabela"

    def test_t0_e_o_canal_entram_na_manifestacao(self):
        ddl = _ddl().lower()
        assert "add column if not exists contato_em timestamptz" in ddl
        assert "add column if not exists canal text not null default 'ana'" in ddl, (
            "Sem default, a coluna nova quebraria as linhas que já existem"
        )

    def test_migration_e_idempotente(self):
        """Rodar duas vezes no Studio não pode explodir: é como a casa aplica."""
        ddl = _ddl().lower()
        assert "create table if not exists ouvidoria_anexos" in ddl
        assert "on conflict (id) do nothing" in ddl
        for constraint in ("ouvidoria_protocolos_canal_check",):
            assert f"drop constraint if exists {constraint}" in ddl
