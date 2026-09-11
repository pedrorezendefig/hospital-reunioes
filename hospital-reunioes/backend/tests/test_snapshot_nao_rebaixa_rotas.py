"""O /snapshot não pode rebaixar um ROTAS.md completo para listagem parcial.

O guarda da issue #542 (`EnumeracaoDeRotasQuebrada`) cobre "a introspecção
rodou e voltou menor que o piso". Este arquivo cobre o vizinho, que mordeu na
onda de 10/09/2026: a introspecção **não conseguiu rodar** (sem `.env` no
worktree), o fallback AST entrou, e o AST não enxerga as dependências dos
routers. O ROTAS.md foi reescrito com a coluna Auth virada de ✅ para ❌ em
dezenas de rotas autenticadas, e o snapshot commitou sozinho.

O banner de "listagem parcial" que o fallback carimba avisa sobre rota que
falta, não sobre auth que mente, e ninguém lê banner num commit automático.
"""

import importlib.util
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SNAPSHOT = REPO_ROOT / ".claude" / "skills" / "snapshot" / "scripts" / "snapshot.py"


def _carregar_snapshot():
    """O script vive fora do pacote do backend (é script de skill)."""
    spec = importlib.util.spec_from_file_location("snapshot_script", SNAPSHOT)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


snapshot = _carregar_snapshot()


ROTAS_COMPLETO = """# ROTAS.md
<!-- gerado automaticamente por /snapshot -->

Endpoints HTTP expostos pelo backend FastAPI do Projeto.

## auth (`app/routers/auth.py`)

| Método | Rota | O que faz | Auth |
|--------|------|-----------|------|
| GET | `/auth/me` | Dados do usuário. | ✅ |
"""

ROTAS_PARCIAL = ROTAS_COMPLETO.replace(
    "Endpoints HTTP expostos",
    "> ⚠️ **Listagem parcial.** Gerada pelo parser estático.\n\nEndpoints HTTP expostos",
)


class TestRebaixariaORotasMd:
    """A regra pura: quando reescrever seria perder informação."""

    def test_ast_por_cima_de_listagem_completa_rebaixa(self, tmp_path):
        """O caso que mordeu: o arquivo em disco veio da introspecção e esta
        passagem só tem o AST."""
        rotas = tmp_path / "ROTAS.md"
        rotas.write_text(ROTAS_COMPLETO, encoding="utf-8")

        assert snapshot._rebaixaria_o_rotas_md(rotas, "ast") is True

    def test_ast_por_cima_de_listagem_ja_parcial_nao_rebaixa(self, tmp_path):
        """Quem já estava parcial pode ser reescrito: não há o que perder."""
        rotas = tmp_path / "ROTAS.md"
        rotas.write_text(ROTAS_PARCIAL, encoding="utf-8")

        assert snapshot._rebaixaria_o_rotas_md(rotas, "ast") is False

    def test_runtime_nunca_rebaixa(self, tmp_path):
        """O caminho normal. Sem esta asserção, um guarda que devolvesse True
        sempre passaria nos outros casos e travaria todo snapshot legítimo."""
        rotas = tmp_path / "ROTAS.md"
        rotas.write_text(ROTAS_COMPLETO, encoding="utf-8")

        assert snapshot._rebaixaria_o_rotas_md(rotas, "runtime") is False

    def test_sem_arquivo_em_disco_nao_rebaixa(self, tmp_path):
        """Primeira geração num repo que ainda não tem ROTAS.md."""
        assert snapshot._rebaixaria_o_rotas_md(tmp_path / "ROTAS.md", "ast") is False


def _repo_minimo(tmp_path: Path, conteudo_rotas: str) -> Path:
    """Repo de mentira com o bastante para o snapshot rodar: project.json sem
    service fastapi (logo, sem routers para introspectar, logo fonte 'ast')."""
    (tmp_path / "docs" / "spec" / "deploy").mkdir(parents=True)
    (tmp_path / "docs" / "spec" / "snapshots").mkdir(parents=True)
    (tmp_path / "docs" / "spec" / "deploy" / "project.json").write_text(
        json.dumps({"project": {"name": "Projeto"}, "services": []}), encoding="utf-8"
    )
    (tmp_path / "docs" / "spec" / "snapshots" / "ROTAS.md").write_text(conteudo_rotas, encoding="utf-8")
    return tmp_path


class TestPelaLinhaDeComando:
    """A prova que importa: o arquivo EM DISCO não pode mudar.

    A função pura acima poderia estar certa e não estar ligada ao caminho de
    escrita, que foi exatamente o que aconteceu com a guarda do PDF na #152.
    """

    def test_o_arquivo_em_disco_nao_e_tocado(self, tmp_path, monkeypatch, capsys):
        repo = _repo_minimo(tmp_path, ROTAS_COMPLETO)
        antes = (repo / "docs" / "spec" / "snapshots" / "ROTAS.md").read_text(encoding="utf-8")

        monkeypatch.setattr("sys.argv", ["snapshot", "--root", str(repo)])
        codigo = snapshot.main()

        depois = (repo / "docs" / "spec" / "snapshots" / "ROTAS.md").read_text(encoding="utf-8")
        assert codigo == 4, "sair 0 faria o /deploy seguir como se nada tivesse acontecido"
        assert depois == antes, "o ROTAS.md completo foi reescrito pelo parser AST"
        assert "Listagem parcial" not in depois
        erro = capsys.readouterr().err
        assert "rebaixaria" in erro.lower(), "a recusa precisa dizer por que, não sair calada"

    def test_a_escotilha_deixa_passar_de_proposito(self, tmp_path, monkeypatch):
        """Quem clonou sem venv precisa conseguir gerar os outros arquivos.
        Sem esta saída o guarda vira indisponibilidade para o repo novo."""
        repo = _repo_minimo(tmp_path, ROTAS_COMPLETO)

        monkeypatch.setattr(
            "sys.argv",
            ["snapshot", "--root", str(repo), "--aceitar-listagem-parcial", "--no-commit"],
        )
        codigo = snapshot.main()

        depois = (repo / "docs" / "spec" / "snapshots" / "ROTAS.md").read_text(encoding="utf-8")
        assert codigo == 0
        assert "Listagem parcial" in depois, "com a escotilha, o rebaixamento é explícito"

    def test_com_ja_parcial_em_disco_segue_sem_escotilha(self, tmp_path, monkeypatch):
        """Controle do teste acima: se o guarda travasse todo caso 'ast', o
        teste da escotilha passaria por acaso."""
        repo = _repo_minimo(tmp_path, ROTAS_PARCIAL)

        monkeypatch.setattr("sys.argv", ["snapshot", "--root", str(repo), "--no-commit"])

        assert snapshot.main() == 0
