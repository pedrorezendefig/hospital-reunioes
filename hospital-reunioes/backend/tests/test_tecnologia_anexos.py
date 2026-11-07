"""O Anexo da Demanda (issue #1061, PRD #1056, ADR 0069; ADR 0077, decisao 8).

O print de tela que o diretor manda no chat vive SO no app: bucket privado
`anexos-tecnologia`, caminho sorteado, leitura por URL assinada de vida curta
(pela rota de automacao, em `test_tecnologia_automacao_anexos.py`). O cron
apaga o binario 30 dias depois de Em producao e na rodada em que a Etapa e Nao
sera feita (#1382), e deixa o registro (nome, quem, quando) marcado apagado; a
sincronizacao da Etapa nunca apaga.

A regra do anexo (formatos, teto, dez por Demanda) e testada no servico, que e
a porta por onde o print do chat entra (`anexar_prints`); a porta pelo chat
mora em `test_tecnologia_chat.py`. O formulario, a lista do card e o apagar ao
Concluir sairam na issue #1386. O Supabase e o storage sao dublados no molde
dos anexos da Ouvidoria (`test_ouvidoria_registro_manual.py`).
"""

from __future__ import annotations

import os
import sys
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from postgrest.exceptions import APIError

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from test_tecnologia_vinculo import PEDRO, _demanda, _GithubFalso, _issue, _montar  # noqa: E402

from app.cron import scheduler  # noqa: E402
from app.limiter import limiter  # noqa: E402
from app.services import tecnologia_anexos, tecnologia_sincronizacao  # noqa: E402
from app.services.assistente_tecnologia import (  # noqa: E402
    LIMITE_DA_IMAGEM,
    MOTIVO_IMAGEM_FORA_DA_LISTA,
    MOTIVO_IMAGEM_GRANDE,
)
from app.services.tecnologia_anexos import (  # noqa: E402
    MOTIVO_ANEXOS_DEMAIS,
    MOTIVO_ARQUIVO_VAZIO,
    MOTIVO_DEMANDA_ENCERRADA,
    MOTIVO_NAO_GUARDOU,
    AnexoRecusadoError,
)

BUCKET = "anexos-tecnologia"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


# ─── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    limiter._storage.reset()
    yield
    limiter._storage.reset()


# ─── Storage dublado ─────────────────────────────────────────────────────────


class _BucketFake:
    def __init__(self, dono: _StorageFake, bucket: str):
        self.dono = dono
        self.bucket = bucket

    def upload(self, path, content, _opcoes=None):
        self.dono.arquivos[f"{self.bucket}/{path}"] = content

    def remove(self, paths):
        """Como o Storage de verdade: devolve so o que saiu, item a item."""
        saiu = []
        for path in paths:
            if self.dono.arquivos.pop(f"{self.bucket}/{path}", None) is not None:
                saiu.append({"name": path})
        return saiu

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


class _BucketQueNaoApaga(_BucketFake):
    def remove(self, paths):
        return []


def _cenario(**kw):
    client, sb, gh = _montar(**kw)
    sb.storage = _StorageFake()
    return client, sb, gh


def _anexar(sb, demanda_id: str = "d-1", nome: str = "print.png", conteudo: bytes = PNG) -> dict:
    """O anexo pelo servico, a porta por onde o print do chat entra."""
    demanda = next(d for d in sb.tabelas["tecnologia_demandas"] if d["id"] == demanda_id)
    return tecnologia_anexos.anexar(sb, demanda=demanda, nome=nome, conteudo=conteudo, quem_id=PEDRO["id"])


def _recusa(sb, **kw) -> AnexoRecusadoError:
    with pytest.raises(AnexoRecusadoError) as erro:
        _anexar(sb, **kw)
    return erro.value


def _anexos(sb) -> list[dict]:
    return sb.tabelas.setdefault("tecnologia_anexos", [])


# ─── 1. Anexar ───────────────────────────────────────────────────────────────


class TestAnexar:
    def test_a_imagem_vai_ao_bucket_privado_e_o_registro_ao_banco(self):
        _, sb, _ = _cenario(demandas=[_demanda("d-1")])

        _anexar(sb, nome="Captura de tela.png")

        assert len(_anexos(sb)) == 1
        linha = _anexos(sb)[0]
        assert linha["demanda_id"] == "d-1"
        assert linha["nome_original"] == "Captura de tela.png"
        assert linha["anexado_por"] == PEDRO["id"]
        assert linha["ordem"] == 1
        assert linha["content_type"] == "image/png"
        assert linha["apagado_em"] is None
        # Caminho sorteado: o nome original pode carregar dado pessoal e nao
        # vira caminho no storage.
        assert "Captura" not in linha["storage_path"]
        assert sb.storage.arquivos == {f"{BUCKET}/{linha['storage_path']}": PNG}

    def test_dez_imagens_entram_e_a_decima_primeira_e_recusada(self):
        """A decima primeira volta com a frase do teto, e nao deixa binario nem
        linha."""
        _, sb, _ = _cenario(demandas=[_demanda("d-1")])

        for i in range(10):
            _anexar(sb, nome=f"tela-{i}.png")

        recusa = _recusa(sb, nome="tela-11.png")

        assert recusa.status_code == 422
        assert str(recusa) == MOTIVO_ANEXOS_DEMAIS
        assert "10" in str(recusa)
        assert sorted(linha["ordem"] for linha in _anexos(sb)) == list(range(1, 11))
        assert len(sb.storage.arquivos) == 10

    @pytest.mark.parametrize("nome", ["relatorio.pdf", "foto.heic", "tela.gif", "sem-extensao"])
    def test_formato_fora_da_lista_volta_com_a_frase_do_print(self, nome):
        _, sb, _ = _cenario(demandas=[_demanda("d-1")])

        recusa = _recusa(sb, nome=nome)

        assert recusa.status_code == 422
        assert str(recusa) == MOTIVO_IMAGEM_FORA_DA_LISTA
        assert _anexos(sb) == []
        assert sb.storage.arquivos == {}

    @pytest.mark.parametrize("nome", ["a.png", "b.jpg", "c.JPEG", "d.webp"])
    def test_os_quatro_formatos_do_print_entram(self, nome):
        _, sb, _ = _cenario(demandas=[_demanda("d-1")])

        _anexar(sb, nome=nome)

        assert len(sb.storage.arquivos) == 1

    def test_acima_do_teto_volta_com_a_frase_do_print(self):
        _, sb, _ = _cenario(demandas=[_demanda("d-1")])

        recusa = _recusa(sb, conteudo=b"x" * (LIMITE_DA_IMAGEM + 1))

        assert recusa.status_code == 413
        assert str(recusa) == MOTIVO_IMAGEM_GRANDE
        assert _anexos(sb) == []
        assert sb.storage.arquivos == {}

    def test_no_teto_cravado_ainda_entra(self):
        _, sb, _ = _cenario(demandas=[_demanda("d-1")])

        _anexar(sb, conteudo=b"x" * LIMITE_DA_IMAGEM)

        assert len(sb.storage.arquivos) == 1

    def test_arquivo_vazio_e_recusado_antes_do_bucket(self):
        """O CHECK da migration 115 recusaria a linha com tamanho zero, e o
        binario ja teria subido: a recusa tem que vir antes."""
        _, sb, _ = _cenario(demandas=[_demanda("d-1")])

        recusa = _recusa(sb, conteudo=b"")

        assert recusa.status_code == 422
        assert str(recusa) == MOTIVO_ARQUIVO_VAZIO
        assert sb.storage.arquivos == {}

    @pytest.mark.parametrize("estado", ["concluida", "cancelada"])
    def test_demanda_encerrada_nao_recebe_anexo(self, estado):
        """A Demanda encerrada no Quadro de antes da ADR 0077 nao volta a
        receber binario: seria dado pessoal parado no bucket."""
        _, sb, _ = _cenario(demandas=[_demanda("d-1", estado=estado)])

        recusa = _recusa(sb)

        assert str(recusa) == MOTIVO_DEMANDA_ENCERRADA
        assert sb.storage.arquivos == {}
        assert _anexos(sb) == []

    def test_falha_ao_gravar_a_linha_nao_deixa_binario_orfao(self):
        _, sb, _ = _cenario(demandas=[_demanda("d-1")])
        original = sb.table

        def _table(nome):
            consulta = original(nome)
            if nome == "tecnologia_anexos":
                executar = consulta.execute

                def execute():
                    if consulta._insert is not None:
                        raise RuntimeError("PostgREST fora do ar")
                    return executar()

                consulta.execute = execute
            return consulta

        sb.table = _table

        recusa = _recusa(sb)

        assert recusa.status_code == 503
        assert str(recusa) == MOTIVO_NAO_GUARDOU
        assert sb.storage.arquivos == {}


# ─── 2. O print do chat vira Anexo quando a fala entra (issue #1062) ─────────


@pytest.fixture
def _memoria_dos_prints():
    tecnologia_anexos.esquecer_prints()
    yield
    tecnologia_anexos.esquecer_prints()


def _guardar(quem_id: str = PEDRO["id"], nome: str = "Captura de tela.png") -> str:
    return tecnologia_anexos.guardar_print(quem_id=quem_id, nome=nome, conteudo=PNG)


def _fala_com(sb, print_ids: list[str], quem_id: str = PEDRO["id"]) -> str | None:
    demanda = sb.tabelas["tecnologia_demandas"][0]
    return tecnologia_anexos.anexar_prints(sb, demanda=demanda, print_ids=print_ids, quem_id=quem_id)


@pytest.mark.usefixtures("_memoria_dos_prints")
class TestPrintDoChat:
    def test_a_fala_grava_o_print_descrito_como_anexo(self):
        _, sb, _ = _cenario(demandas=[_demanda("d-1")])

        aviso = _fala_com(sb, [_guardar()])

        assert aviso is None
        anexos = _anexos(sb)
        assert len(anexos) == 1
        assert anexos[0]["demanda_id"] == "d-1"
        assert anexos[0]["nome_original"] == "Captura de tela.png"
        assert sb.storage.arquivos == {f"{BUCKET}/{anexos[0]['storage_path']}": PNG}

    def test_sem_a_fala_nenhum_registro_nem_binario_fica(self):
        _, sb, _ = _cenario(demandas=[_demanda("d-1")])

        _guardar()
        _guardar(nome="outro.png")

        assert _anexos(sb) == []
        assert sb.storage.arquivos == {}

    def test_o_print_entra_uma_vez_so(self):
        _, sb, _ = _cenario(demandas=[_demanda("d-1")])
        print_id = _guardar()
        assert _fala_com(sb, [print_id]) is None

        segunda = _fala_com(sb, [print_id])

        assert len(_anexos(sb)) == 1
        assert segunda == tecnologia_anexos.aviso_dos_prints(1)

    def test_print_que_se_perdeu_vira_aviso(self):
        _, sb, _ = _cenario(demandas=[_demanda("d-1")])

        assert _fala_com(sb, ["sumiu-com-o-reinicio"]) == tecnologia_anexos.aviso_dos_prints(1)
        assert _anexos(sb) == []

    def test_o_print_de_outra_pessoa_nao_entra(self):
        _, sb, _ = _cenario(demandas=[_demanda("d-1")])
        print_id = _guardar(quem_id=PEDRO["id"])

        aviso = _fala_com(sb, [print_id], quem_id="P2")

        assert _anexos(sb) == []
        assert aviso == tecnologia_anexos.aviso_dos_prints(1)

    @pytest.mark.parametrize("falha", (APIError({"message": "fora do ar"}), httpx.ReadTimeout("timeout")))
    def test_falha_do_banco_vira_aviso_e_nao_derruba_a_fala(self, falha):
        """A fala ja entrou quando os prints entram: um 500 aqui mandaria o
        diretor mandar a fala de novo."""
        _, sb, _ = _cenario(demandas=[_demanda("d-1")])
        print_id = _guardar()
        original = sb.table

        def _table(nome):
            consulta = original(nome)
            if nome == "tecnologia_anexos":

                def execute():
                    raise falha

                consulta.execute = execute
            return consulta

        sb.table = _table

        assert _fala_com(sb, [print_id]) == tecnologia_anexos.aviso_dos_prints(1)

    def test_o_aviso_manda_mandar_o_print_de_novo_na_conversa(self):
        """O formulario e o card sairam: o caminho de volta e a propria
        conversa, e a frase nao manda abrir tela nenhuma."""
        assert tecnologia_anexos.aviso_dos_prints(1) == (
            "Um print da conversa não entrou como imagem. Mande o print de novo na conversa."
        )
        assert tecnologia_anexos.aviso_dos_prints(0) is None


# ─── 3. A Etapa nao apaga o print ────────────────────────────────────────────


class TestAEtapaNaoApaga:
    @pytest.mark.parametrize(
        "issue",
        [
            {"state": "closed", "state_reason": "completed", "labels": []},
            {"state": "open", "state_reason": None, "labels": [{"name": "in-progress"}]},
        ],
        ids=["entregue", "em-desenvolvimento"],
    )
    def test_mudanca_de_etapa_nao_apaga_nada(self, monkeypatch, issue):
        """A Etapa muda pela sincronizacao (webhook e reconciliacao), inclusive
        para Entregue: o diretor ainda confere com o print na mao (ADR 0069,
        decisao 3)."""
        gh = _GithubFalso({900: _issue(900, estado=issue["state"], motivo=issue["state_reason"])})
        gh.issues[900]["labels"] = issue["labels"]
        client, sb, _ = _cenario(
            demandas=[_demanda("d-1", estado="em_andamento", github_issue_numero=900, autor_id="P2")],
            github=gh,
            monkeypatch=monkeypatch,
        )
        _anexar(sb)
        demanda = dict(sb.tabelas["tecnologia_demandas"][0])

        assert tecnologia_sincronizacao.sincronizar_demanda(sb, demanda) is True

        assert sb.tabelas["tecnologia_demandas"][0]["etapa"] != demanda["etapa"], "a Etapa nao mudou"
        assert len(sb.storage.arquivos) == 1
        assert _anexos(sb)[0]["apagado_em"] is None


# ─── 4. O prazo depois de Em produção (issue #1382, ADR 0077) ──────────────


def _ha_dias(dias: int) -> str:
    return (datetime.now(UTC) - timedelta(days=dias)).isoformat()


def _rodada_do_cron(monkeypatch, sb) -> None:
    """A rodada de hora em hora da Tecnologia, pela porta do scheduler. As duas
    releituras do GitHub ficam de fora: este teste e sobre o que vem depois."""
    monkeypatch.setattr(scheduler, "_supabase", lambda: sb)
    monkeypatch.setattr(tecnologia_sincronizacao, "reconciliar_vinculos", lambda _sb: {})
    monkeypatch.setattr(tecnologia_sincronizacao, "reconciliar_em_producao", lambda _sb: {})
    scheduler.reconciliar_vinculos_tecnologia()


class TestOPrintVenceDepoisDeEmProducao:
    """Sem o Concluir humano, o binario sai 30 dias depois de a Etapa chegar a
    Em producao, e na rodada seguinte quando a Etapa e Nao sera feita. O
    registro fica, marcado apagado."""

    def test_em_producao_ha_mais_de_30_dias_apaga_o_binario_e_marca_o_registro(self, monkeypatch):
        _, sb, _ = _cenario(demandas=[_demanda("d-1")])
        _anexar(sb, nome="tela.png")
        sb.tabelas["tecnologia_demandas"][0].update(etapa="em_producao", entregue_em=_ha_dias(31))

        _rodada_do_cron(monkeypatch, sb)

        assert sb.storage.arquivos == {}, "o binario ficou no bucket 31 dias depois de Em producao"
        assert [linha["nome_original"] for linha in _anexos(sb)] == ["tela.png"]
        assert _anexos(sb)[0]["apagado_em"]

    @pytest.mark.parametrize(
        "etapa,dias",
        [("em_producao", 29), ("entregue", 60)],
        ids=["em-producao-ha-29-dias", "entregue-ha-60-dias"],
    )
    def test_antes_do_prazo_o_print_continua(self, monkeypatch, etapa, dias):
        """Em producao ha menos de 30 dias o diretor ainda confere com o print
        na mao. Entregue nao conta o prazo: a correcao ainda nem subiu."""
        _, sb, _ = _cenario(demandas=[_demanda("d-1")])
        _anexar(sb, nome="tela.png")
        sb.tabelas["tecnologia_demandas"][0].update(etapa=etapa, entregue_em=_ha_dias(dias))

        _rodada_do_cron(monkeypatch, sb)

        assert len(sb.storage.arquivos) == 1
        assert _anexos(sb)[0]["apagado_em"] is None

    def test_nao_sera_feita_apaga_na_rodada_seguinte(self, monkeypatch):
        _, sb, _ = _cenario(demandas=[_demanda("d-1"), _demanda("d-2")])
        _anexar(sb, demanda_id="d-1", nome="recusada.png")
        _anexar(sb, demanda_id="d-2", nome="aberta.png")
        sb.tabelas["tecnologia_demandas"][0].update(etapa="nao_sera_feita")

        _rodada_do_cron(monkeypatch, sb)

        apagados = {linha["nome_original"]: bool(linha["apagado_em"]) for linha in _anexos(sb)}
        assert apagados == {"recusada.png": True, "aberta.png": False}
        restante = next(linha for linha in _anexos(sb) if linha["nome_original"] == "aberta.png")
        assert list(sb.storage.arquivos) == [f"{BUCKET}/{restante['storage_path']}"]

    def test_binario_que_o_storage_nao_confirmou_fica_sem_a_marca(self, monkeypatch, caplog):
        """O Storage pode recusar sem levantar. O anexo que nao saiu NAO ganha
        a marca de apagado e o caminho fica no log, para alguem achar; a
        rodada seguinte tenta de novo."""
        _, sb, _ = _cenario(demandas=[_demanda("d-1")])
        _anexar(sb, nome="teimoso.png")
        sb.tabelas["tecnologia_demandas"][0].update(etapa="nao_sera_feita")
        sb.storage.from_ = lambda bucket: _BucketQueNaoApaga(sb.storage, bucket)

        with caplog.at_level("ERROR"):
            _rodada_do_cron(monkeypatch, sb)

        linha = _anexos(sb)[0]
        assert linha["apagado_em"] is None
        assert linha["storage_path"] in caplog.text
