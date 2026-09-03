"""A enumeração de rotas do /snapshot, testada contra o app real (issue #542).

O `introspect_routes.py` alimenta o `ROTAS.md`. Ele lia `app.routes`, e desde o
FastAPI 0.141 o `include_router` guarda o router incluído em vez de copiar as
rotas para cima: a lista volta sem rota nenhuma de router. Isso não dá erro, dá
varredura vazia, e o snapshot carimba documentação errada em silêncio a cada
deploy. Os testes aqui são o controle que faz esse vazio ficar vermelho.
"""

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
HELPER = REPO_ROOT / ".claude" / "skills" / "snapshot" / "scripts" / "introspect_routes.py"


def _carregar_helper():
    """O helper vive fora do pacote do backend (é script de skill), então entra
    por caminho em vez de import normal."""
    spec = importlib.util.spec_from_file_location("introspect_routes", HELPER)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


introspect = _carregar_helper()


class TestEnumeracaoDoAppReal:
    """O app montado de verdade, do jeito que o snapshot o vê no deploy."""

    @staticmethod
    def _rotas():
        from app.main import app

        return introspect.enumerar_rotas(app)

    def test_a_enumeracao_enxerga_o_app_inteiro(self):
        """Controle, antes de qualquer asserção sobre o conteúdo: uma lista
        vazia satisfaz "toda rota enumerada está correta" sem olhar rota
        nenhuma. Foi exatamente o que `app.routes` passou a devolver no 0.141."""
        rotas = self._rotas()

        assert len(rotas) >= introspect.PISO_ROTAS, (
            f"a enumeração só enxergou {len(rotas)} rotas, abaixo do piso {introspect.PISO_ROTAS}: {rotas[:3]}"
        )

    def test_a_enumeracao_bate_com_o_schema_publico(self):
        """O schema OpenAPI é o contrato público e vale nas duas versões do
        FastAPI. Se a enumeração divergir dele, alguma rota sumiu do ROTAS.md."""
        from app.main import app

        operacoes = {
            (metodo.upper(), caminho)
            for caminho, item in app.openapi()["paths"].items()
            for metodo in item
            if metodo.lower() in {"get", "post", "put", "patch", "delete"}
        }
        enumeradas = {(r["method"], r["path"]) for r in self._rotas()}

        assert operacoes - enumeradas == set(), f"rotas do schema que sumiram: {sorted(operacoes - enumeradas)}"

    def test_nenhuma_rota_esta_escondida_do_schema(self):
        """A enumeração passou a sair só do schema, então rota criada com
        `include_in_schema=False` sumiria do ROTAS.md sem dar erro. Hoje não
        existe nenhuma; quem criar a primeira fica vermelho aqui e decide se o
        mapa da app pode mesmo perder essa rota."""
        from app.main import app

        no_app = len(introspect._indice_por_operacao(app))
        no_schema = len(self._rotas())

        assert no_app == no_schema, f"o app tem {no_app} operações e o schema só documenta {no_schema}"

    def test_toda_rota_enumerada_sabe_de_que_router_veio(self):
        """Contar rota certo e perder o resto é meio conserto: o ROTAS.md agrupa
        por arquivo de router, então rota sem `module` cai num balde órfão. Uma
        enumeração que acerta o número e zera os metadados passaria nos dois
        testes acima sem que nada disso apareça."""
        sem_modulo = [(r["method"], r["path"]) for r in self._rotas() if not r["module"]]

        assert sem_modulo == [], f"{len(sem_modulo)} rotas sem router de origem: {sem_modulo[:3]}"

    def test_os_gates_de_permissao_continuam_visiveis(self):
        """A coluna de auth do ROTAS.md sai das dependencies reais da rota. Se a
        enumeração parar de casar a rota com o objeto do FastAPI, some todo
        `require_*` de uma vez e o mapa passa a dizer que a app é aberta."""
        com_gate = [r for r in self._rotas() if any(d.startswith("require_") for d in r["dependencies"])]

        assert len(com_gate) >= 100, f"só {len(com_gate)} rotas com gate require_*: as dependencies sumiram"


APP_MINIMO = """
from fastapi import FastAPI

app = FastAPI()


@app.get("/ping")
def ping():
    return {}


@app.get("/pong")
def pong():
    return {}
"""


class TestPisoDeSanidade:
    """O piso é o que impede o dano silencioso: sem ele, uma enumeração que não
    acha nada gera um ROTAS.md vazio e o deploy segue como se estivesse tudo bem."""

    def test_o_helper_recusa_gerar_listagem_abaixo_do_piso(self, tmp_path):
        """App de duas rotas no lugar do de verdade: a enumeração está "certa",
        só é pequena demais para ser a aplicação. O helper tem que sair com
        erro e sem imprimir JSON, em vez de entregar a listagem mutilada."""
        (tmp_path / "app_minimo.py").write_text(APP_MINIMO, encoding="utf-8")

        proc = subprocess.run(
            [sys.executable, str(HELPER), "app_minimo:app"],
            cwd=str(tmp_path),
            capture_output=True,
            text=True,
            timeout=120,
        )

        assert proc.returncode != 0, f"o helper entregou a listagem curta calado: {proc.stdout[:200]}"
        assert proc.stdout.strip() == "", "não pode sair JSON junto com a recusa"
        assert str(introspect.PISO_ROTAS) in proc.stderr, f"a recusa precisa dizer o piso: {proc.stderr}"

    def test_o_app_de_verdade_passa_do_piso(self, tmp_path):
        """O outro lado do controle: o piso não pode estar tão alto que recuse a
        própria aplicação. Sem esta asserção, PISO_ROTAS = 10**9 passaria."""
        from app.main import app

        assert len(introspect.enumerar_rotas(app)) >= introspect.PISO_ROTAS


# App no formato do FastAPI 0.141 com o casamento de metadados quebrado: o
# schema está cheio (o `openapi()` é contrato público e continua respondendo) e
# o `routes` não entrega objeto de rota nenhum. É o que acontece de verdade se
# o `iter_route_contexts` for renomeado (o `getattr` cai no ramo legado, que no
# 0.141 varre `routes` e não acha APIRoute), ou se o
# `_get_api_route_for_openapi` mantiver o nome e passar a devolver None.
APP_SEM_OBJETO_DE_ROTA = """
CAMINHOS = {
    f"/rota-{i}": {"get": {"operationId": f"op{i}", "summary": "rota qualquer"}}
    for i in range(200)
}


class _AppComSchemaCheioESemRotas:
    routes: list = []

    def openapi(self):
        return {"paths": CAMINHOS}


app = _AppComSchemaCheioESemRotas()
"""


class TestPisoCobreMetadados:
    """A contagem certa com os metadados zerados é o estado mais perigoso: o
    `ROTAS.md` sai com 192 endpoints, "1 routers" e "0% exigem auth", sem
    carimbo de parcial, e o `snapshot.py` commita isso sozinho a cada deploy.
    É documentação afirmando que a aplicação inteira é aberta. Um piso que olha
    só `len(rotas)` não pega, porque as 192 rotas são de verdade."""

    def test_schema_cheio_sem_objeto_de_rota_e_recusado(self, tmp_path):
        """Ponta a ponta pelo `main()` de verdade, sem mock nenhum: 200 rotas no
        schema, zero casadas com objeto de rota. Passa folgado no piso de
        contagem e mesmo assim não pode virar documentação."""
        (tmp_path / "app_sem_rotas.py").write_text(APP_SEM_OBJETO_DE_ROTA, encoding="utf-8")

        proc = subprocess.run(
            [sys.executable, str(HELPER), "app_sem_rotas:app"],
            cwd=str(tmp_path),
            capture_output=True,
            text=True,
            timeout=120,
        )

        assert proc.returncode != 0, f"o helper entregou 200 rotas sem router nem auth calado: {proc.stdout[:200]}"
        assert proc.stdout.strip() == "", "não pode sair JSON junto com a recusa"
        assert "módulo" in proc.stderr, f"a recusa precisa dizer que faltou metadado: {proc.stderr}"

    def test_a_validacao_reprova_lista_cheia_sem_modulo(self):
        """O invariante isolado, sem depender da versão do FastAPI instalada:
        contagem acima do piso não basta, os metadados também têm piso."""
        rotas = [
            {"method": "GET", "path": f"/rota-{i}", "module": "", "dependencies": []}
            for i in range(introspect.PISO_ROTAS + 50)
        ]

        assert introspect.validar_enumeracao(rotas) is not None

    def test_a_validacao_aprova_o_app_de_verdade(self):
        """A outra metade: "reprovar sempre" passaria no teste acima e quebraria
        todo snapshot."""
        from app.main import app

        assert introspect.validar_enumeracao(introspect.enumerar_rotas(app)) is None


@pytest.mark.skipif(
    not hasattr(importlib.import_module("fastapi.routing"), "iter_route_contexts"),
    reason="o achatamento por iter_route_contexts só existe do FastAPI 0.141 em diante",
)
class TestAchatamentoDevolvendoNada:
    """O segundo caminho, o que a nota do PR não cobria: o
    `_get_api_route_for_openapi` mantém nome e assinatura e passa a devolver
    None. Não levanta ImportError, não cai no fallback AST, não carimba nada."""

    def test_achatamento_mudo_e_recusado(self, monkeypatch):
        from app.main import app

        monkeypatch.setattr(
            importlib.import_module("fastapi.openapi.utils"),
            "_get_api_route_for_openapi",
            lambda _contexto: None,
        )

        rotas = introspect.enumerar_rotas(app)

        assert len(rotas) >= introspect.PISO_ROTAS, "o schema continua cheio, o defeito é só nos metadados"
        assert introspect.validar_enumeracao(rotas) is not None


SNAPSHOT_PY = REPO_ROOT / ".claude" / "skills" / "snapshot" / "scripts" / "snapshot.py"


def _carregar_snapshot():
    spec = importlib.util.spec_from_file_location("snapshot_script", SNAPSHOT_PY)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


class TestSnapshotNaoEngoleAEnumeracaoQuebrada:
    """O snapshot cai no parser AST quando a introspecção não consegue rodar
    (sem venv, sem .env). Esse fallback é legítimo e carimba "listagem parcial".
    O que não pode é usar o mesmo caminho quando a introspecção RODOU e voltou
    quebrada: aí o certo é parar, porque documentação errada não avisa ninguém."""

    def test_o_piso_estourado_interrompe_a_geracao(self, monkeypatch, tmp_path):
        snapshot = _carregar_snapshot()

        class ProcFalso:
            returncode = snapshot.CODIGO_ENUMERACAO_QUEBRADA
            stdout = ""
            stderr = "[introspect_routes] enumeração devolveu 0 rotas, abaixo do piso 150"

        monkeypatch.setattr(snapshot.shutil, "which", lambda _nome: "/usr/bin/true")
        monkeypatch.setattr(snapshot.subprocess, "run", lambda *a, **k: ProcFalso())

        routers = tmp_path / "app" / "routers"
        routers.mkdir(parents=True)

        with pytest.raises(snapshot.EnumeracaoDeRotasQuebrada):
            snapshot.parse_routers(routers)

    def test_introspeccao_impossivel_continua_caindo_no_parser_ast(self, monkeypatch, tmp_path):
        """A outra metade: sem esta, "levantar sempre" passaria no teste acima e
        quebraria todo snapshot rodado fora do venv."""
        snapshot = _carregar_snapshot()

        class ProcQuebrado:
            returncode = 1
            stdout = ""
            stderr = "ModuleNotFoundError: No module named 'app'"

        monkeypatch.setattr(snapshot.shutil, "which", lambda _nome: "/usr/bin/true")
        monkeypatch.setattr(snapshot.subprocess, "run", lambda *a, **k: ProcQuebrado())

        routers = tmp_path / "app" / "routers"
        routers.mkdir(parents=True)

        _rotas, fonte = snapshot.parse_routers(routers)

        assert fonte == "ast"
