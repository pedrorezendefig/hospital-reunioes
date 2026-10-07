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
from datetime import UTC, datetime

import httpx
import pytest
from postgrest.exceptions import APIError

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from test_tecnologia_anexos import BUCKET, PNG, _anexar, _anexos, _cenario  # noqa: E402
from test_tecnologia_vinculo import BASE, DIRETOR, _demanda, _GithubFalso, _issue  # noqa: E402

from app.config import settings  # noqa: E402
from app.limiter import limiter  # noqa: E402
from app.services import assistente_tecnologia, tecnologia_anexos, tecnologia_email  # noqa: E402
from app.services.tecnologia_vinculo import bloco_para_o_diretor  # noqa: E402

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
            f'{self.CORPO}\n\n---\n\nAnexos: 3 imagens na Demanda\n\n<!-- demanda-vitta id="d-1" -->'
        )

    def test_a_frase_nao_entra_no_texto_do_diretor(self, monkeypatch):
        """O corpo que termina no bloco "Para o diretor" e o formato que o
        `bloco_para_o_diretor` le ate o fim: a frase colada ali voltaria para o
        card do diretor e para o "Copiar para IA"."""
        gh = _GithubFalso({501: _issue(501, corpo=self.CORPO)})
        client, _, _ = _cenario(demandas=[_demanda("d-1")], github=gh, monkeypatch=monkeypatch)
        assert _anexar(client).status_code == 201

        assert client.post(f"{BASE}/demandas/d-1/vincular", json={"numero": 501}).status_code == 200

        assert "Anexos: 1 imagem na Demanda" in gh.issues[501]["body"]
        assert bloco_para_o_diretor(gh.issues[501]["body"]) == "O selo passa a aparecer no card."

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
            "## Para o diretor\n\nO selo passa a aparecer no card.\n\n---\n\n"
            'Anexos: 2 imagens na Demanda\n\n<!-- demanda-vitta id="d-1" -->'
        )
        assert bloco_para_o_diretor(gh.issues[501]["body"]) == "O selo passa a aparecer no card."

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


# ─── 2. O print do Assistente vira Anexo no clique ───────────────────────────


DESCREVER = f"{BASE}/assistente/descrever-imagem"


@pytest.fixture
def _visao_dublada(monkeypatch):
    """O provedor de visao fica de fora: o que se prova aqui e o que o app
    guarda, e nao o que o modelo enxerga."""
    monkeypatch.setattr(
        assistente_tecnologia, "descrever_imagem", lambda **kw: "Tela de login com erro vermelho no topo."
    )
    tecnologia_anexos.esquecer_prints()
    yield
    tecnologia_anexos.esquecer_prints()


def _descrever(client, nome: str = "Captura de tela.png", conteudo: bytes = PNG):
    return client.post(DESCREVER, files={"imagem": (nome, conteudo, "image/png")})


def _criar(client, **extra):
    return client.post(
        f"{BASE}/demandas",
        json={"titulo": "Erro no login", "tipo": "defeito", "produto_id": "prod-1", **extra},
    )


@pytest.mark.usefixtures("_visao_dublada")
class TestPrintDoAssistente:
    def test_criar_demanda_grava_o_print_descrito_como_anexo(self, monkeypatch):
        client, sb, _ = _cenario(monkeypatch=monkeypatch)
        descrito = _descrever(client).json()
        assert descrito["texto"] == "Tela de login com erro vermelho no topo."

        criada = _criar(client, prints=[descrito["print_id"]])

        assert criada.status_code == 201
        assert criada.json()["aviso_dos_anexos"] is None
        anexos = _anexos(sb)
        assert len(anexos) == 1
        assert anexos[0]["demanda_id"] == criada.json()["id"]
        assert anexos[0]["nome_original"] == "Captura de tela.png"
        assert sb.storage.arquivos == {f"{BUCKET}/{anexos[0]['storage_path']}": PNG}

    def test_sem_o_clique_nenhum_registro_nem_binario_fica(self, monkeypatch):
        client, sb, _ = _cenario(monkeypatch=monkeypatch)

        assert _descrever(client).status_code == 200
        assert _descrever(client, nome="outro.png").status_code == 200

        assert _anexos(sb) == []
        assert sb.storage.arquivos == {}
        assert sb.tabelas["tecnologia_demandas"] == []

    def test_o_print_entra_uma_vez_so(self, monkeypatch):
        client, sb, _ = _cenario(monkeypatch=monkeypatch)
        print_id = _descrever(client).json()["print_id"]
        assert _criar(client, prints=[print_id]).status_code == 201

        segunda = _criar(client, prints=[print_id])

        assert segunda.status_code == 201
        assert len(_anexos(sb)) == 1
        assert segunda.json()["aviso_dos_anexos"]

    def test_print_que_se_perdeu_nao_impede_a_demanda_e_vira_aviso(self, monkeypatch):
        client, sb, _ = _cenario(monkeypatch=monkeypatch)

        criada = _criar(client, prints=["sumiu-com-o-reinicio"])

        assert criada.status_code == 201
        assert criada.json()["aviso_dos_anexos"] == tecnologia_anexos.aviso_dos_prints(1)
        assert _anexos(sb) == []

    def test_o_print_de_outra_pessoa_nao_entra(self, monkeypatch):
        client_pedro, sb, _ = _cenario(monkeypatch=monkeypatch)
        print_id = _descrever(client_pedro).json()["print_id"]
        client_diretor, _, _ = _cenario(logado=DIRETOR, supabase=sb, monkeypatch=monkeypatch)

        criada = _criar(client_diretor, prints=[print_id])

        assert criada.status_code == 201
        assert _anexos(sb) == []
        assert criada.json()["aviso_dos_anexos"] == tecnologia_anexos.aviso_dos_prints(1)

    @pytest.mark.parametrize("falha", (APIError({"message": "fora do ar"}), httpx.ReadTimeout("timeout")))
    def test_falha_do_banco_ao_ler_os_anexos_vira_aviso_e_a_demanda_responde_201(self, monkeypatch, falha):
        """A Demanda ja nasceu quando os prints entram: um 500 aqui mandaria a
        pessoa criar de novo, e a Demanda sairia duplicada."""
        client, sb, _ = _cenario(monkeypatch=monkeypatch)
        print_id = _descrever(client).json()["print_id"]
        original = sb.table

        def _table(nome):
            consulta = original(nome)
            if nome == "tecnologia_anexos":

                def execute():
                    raise falha

                consulta.execute = execute
            return consulta

        sb.table = _table

        criada = _criar(client, prints=[print_id])

        assert criada.status_code == 201
        assert criada.json()["aviso_dos_anexos"] == tecnologia_anexos.aviso_dos_prints(1)
        assert len(sb.tabelas["tecnologia_demandas"]) == 1


# ─── 3. A resposta da Conversa leva uma imagem ───────────────────────────────


def _responder(client, texto: str = "Segue o print do erro.", **extra):
    return client.post(f"{BASE}/demandas/d-1/conversa", json={"texto": texto, **extra})


class TestRespostaComImagem:
    def test_a_imagem_fica_ligada_a_resposta_e_o_fio_a_mostra_junto(self, monkeypatch):
        client, sb, _ = _cenario(demandas=[_demanda("d-1")], monkeypatch=monkeypatch)
        anexo = _anexar(client, nome="tela.png").json()

        resposta = _responder(client, anexo_id=anexo["id"])

        assert resposta.status_code == 201
        linha_id = resposta.json()["id"]
        assert _anexos(sb)[0]["conversa_id"] == linha_id
        fio = client.get(f"{BASE}/demandas/d-1/conversa").json()
        da_resposta = next(linha for linha in fio if linha["id"] == linha_id)
        assert da_resposta["imagem"]["nome"] == "tela.png"
        assert da_resposta["imagem"]["url"].startswith(f"https://storage.local/{BUCKET}/")

    def test_resposta_sem_imagem_vem_sem_imagem_no_fio(self, monkeypatch):
        client, _, _ = _cenario(demandas=[_demanda("d-1")], monkeypatch=monkeypatch)
        assert _anexar(client).status_code == 201

        linha_id = _responder(client).json()["id"]

        fio = client.get(f"{BASE}/demandas/d-1/conversa").json()
        assert next(linha for linha in fio if linha["id"] == linha_id)["imagem"] is None

    def test_a_imagem_passa_pelos_mesmos_limites_do_anexo(self, monkeypatch):
        """A imagem da resposta sobe pela MESMA porta do anexo: formato, teto e
        o maximo de dez valem igual, com as mesmas frases."""
        client, sb, _ = _cenario(demandas=[_demanda("d-1")], monkeypatch=monkeypatch)

        assert _anexar(client, nome="planilha.xlsx").status_code == 422
        assert _anexar(client, conteudo=b"\x00" * (5 * 1024 * 1024 + 1)).status_code == 413
        assert _anexos(sb) == []

    @pytest.mark.parametrize("caso", ("de_outra_demanda", "ja_usada", "inexistente"))
    def test_imagem_que_nao_e_desta_resposta_e_recusada_sem_gravar_a_linha(self, monkeypatch, caso):
        client, sb, _ = _cenario(demandas=[_demanda("d-1"), _demanda("d-2")], monkeypatch=monkeypatch)
        if caso == "de_outra_demanda":
            anexo_id = _anexar(client, demanda_id="d-2").json()["id"]
        elif caso == "ja_usada":
            anexo_id = _anexar(client).json()["id"]
            assert _responder(client, anexo_id=anexo_id).status_code == 201
        else:
            anexo_id = "nao-existe"
        linhas_antes = len(sb.tabelas["tecnologia_conversas"])

        resposta = _responder(client, "Outra resposta.", anexo_id=anexo_id)

        assert resposta.status_code == 422
        assert len(sb.tabelas["tecnologia_conversas"]) == linhas_antes


class TestComentarioEspelhadoDaRespostaComImagem:
    def _vinculada(self, monkeypatch):
        gh = _GithubFalso({501: _issue(501)})
        client, sb, _ = _cenario(
            demandas=[_demanda("d-1", github_issue_numero=501)], github=gh, monkeypatch=monkeypatch
        )
        return client, sb, gh

    def test_o_comentario_sai_com_o_texto_e_a_contagem_sem_url(self, monkeypatch):
        client, _, gh = self._vinculada(monkeypatch)
        anexo = _anexar(client, nome="prontuario.png").json()

        assert _responder(client, "Segue o print do erro.", anexo_id=anexo["id"]).status_code == 201

        corpo = gh.comentarios_criados[0]["corpo"]
        assert corpo.endswith("Segue o print do erro.\n\n(1 imagem na Demanda)")

    def test_resposta_sem_imagem_nao_fala_de_imagem(self, monkeypatch):
        client, _, gh = self._vinculada(monkeypatch)

        assert _responder(client).status_code == 201

        assert "imagem" not in gh.comentarios_criados[0]["corpo"]

    def test_a_correcao_mantem_a_contagem_no_comentario(self, monkeypatch):
        client, sb, gh = self._vinculada(monkeypatch)
        anexo = _anexar(client).json()
        linha_id = _responder(client, anexo_id=anexo["id"]).json()["id"]
        # O duble carimba `criado_em` numa data fixa; a janela de correcao e de
        # 10 minutos a partir de agora.
        sb.tabelas["tecnologia_conversas"][-1]["criado_em"] = datetime.now(UTC).isoformat()

        corrigida = client.patch(f"{BASE}/demandas/d-1/conversa/{linha_id}", json={"texto": "Segue o print."})

        assert corrigida.status_code == 200
        assert gh.comentarios_editados[0]["corpo"].endswith("Segue o print.\n\n(1 imagem na Demanda)")


# ─── 4. Nada do anexo sai para o repositorio publico ─────────────────────────


class TestNenhumaUrlNemBinarioSaiParaAIssue:
    """O detector: tudo o que o app escreve no GitHub (corpo da issue nova, corpo
    reescrito pelo vincular e pela contagem, comentario espelhado e a correcao
    dele) e varrido atras de qualquer pedaco da URL assinada, do caminho no
    bucket, do nome do arquivo e dos bytes da imagem."""

    NOME = "prontuario do paciente.png"

    def _vazamentos(self, texto: str, sb) -> list[str]:
        caminhos = [linha["storage_path"] for linha in _anexos(sb)]
        assinadas = [a["path"] for a in sb.storage.assinaturas]
        suspeitos = [
            self.NOME,
            "prontuario",
            BUCKET,
            "storage.local",
            "token=",
            "\x89PNG",
            "iVBORw0KGgo",  # o PNG em base64
            *caminhos,
            *assinadas,
        ]
        return [pedaco for pedaco in suspeitos if pedaco and pedaco in texto]

    def test_corpo_e_comentario_levam_so_a_contagem(self, monkeypatch):
        gh = _GithubFalso({501: _issue(501)})
        client, sb, _ = _cenario(demandas=[_demanda("d-1"), _demanda("d-2")], github=gh, monkeypatch=monkeypatch)
        _anexar(client, nome=self.NOME)
        _anexar(client, demanda_id="d-2", nome=self.NOME)
        # A lista do card e o fio assinam URL: se algo delas vazasse, vazaria daqui.
        assert client.get(f"{BASE}/demandas/d-1/anexos").json()[0]["url"]
        assert client.post(LEVAR).status_code == 200
        assert client.post(f"{BASE}/demandas/d-2/vincular", json={"numero": 501}).status_code == 200
        anexo = _anexar(client, nome=self.NOME).json()
        linha_id = _responder(client, "Segue o print.", anexo_id=anexo["id"]).json()["id"]
        assert client.get(f"{BASE}/demandas/d-1/conversa").json()
        sb.tabelas["tecnologia_conversas"][-1]["criado_em"] = datetime.now(UTC).isoformat()
        assert client.patch(f"{BASE}/demandas/d-1/conversa/{linha_id}", json={"texto": "Segue."}).status_code == 200

        publicados = (
            [c["corpo"] for c in gh.criadas]
            + [corpo for _, corpo in gh.corpos_escritos]
            + [c["corpo"] for c in gh.comentarios_criados]
            + [c["corpo"] for c in gh.comentarios_editados]
        )

        assert len(publicados) >= 5
        assert sb.storage.assinaturas, "nada foi assinado: a varredura procuraria URL que nunca existiu"
        assert [self._vazamentos(texto, sb) for texto in publicados] == [[] for _ in publicados]
        assert "Anexos: 2 imagens na Demanda" in gh.issues[900]["body"]
        assert "Anexos: 1 imagem na Demanda" in gh.issues[501]["body"]
        assert gh.comentarios_criados[0]["corpo"].endswith("(1 imagem na Demanda)")
