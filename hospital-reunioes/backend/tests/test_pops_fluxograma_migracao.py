"""Migração one-shot do Fluxograma legado (issue #224, ADR 0024).

Converte o subset Mermaid das convenções do prompt antigo (ADR 0017) para o
objeto da gramática restrita; o inconversível é sinalizado e o conteúdo fica
como está (cai no fallback existente). Cobre também a função de migração do
rascunho (preserva o SVG persistido byte a byte) e o script idempotente com
dry-run sobre pops_versoes.
"""

import pytest

from app.models.pops_fluxograma import fluxograma_valido
from app.services.pops_fluxograma_migracao import (
    MermaidInconversivelError,
    converter_mermaid_para_fluxograma,
    migrar_rascunho_fluxogramas,
)
from scripts.oneshot.migrar_fluxogramas_mermaid import executar

# Fixture real: o exemplo literal do prompt antigo (convenções do ADR 0017).
MERMAID_PROMPT_ANTIGO = (
    "flowchart TD\n"
    "  A([Início]) --> B[Higienizar as mãos]\n"
    "  B --> C{Material completo?}\n"
    "  C -->|Sim| D[Executar o procedimento]\n"
    "  C -->|Não| E[Providenciar a reposição]\n"
    "  E --> B\n"
    "  D --> F([Fim])"
)

# Fixture real dos testes de documento (test_pops_documento.py): decisão cujos
# dois ramos seguem caminhos independentes até o Fim (diamante), fora do layout
# de coluna única da gramática desta fatia (sinalizado, não convertido).
MERMAID_DIAMANTE = (
    "flowchart TD\n"
    "  A([Início]) --> B[Retirar adornos]\n"
    "  B --> C{Mãos visivelmente sujas?}\n"
    "  C -->|Sim| D[Lavar com água e sabonete]\n"
    "  C -->|Não| E[Friccionar preparação alcoólica]\n"
    "  D --> F([Fim])\n"
    "  E --> F"
)

# Fixture real dos testes de seções/elaboração: passos encadeados numa linha.
MERMAID_CADEIA = "flowchart TD\n  A[Início] --> C[Conferir] --> B[Fim]"


class TestConverterMermaid:
    def test_converte_o_exemplo_do_prompt_antigo(self):
        """CA: terminais, passos, decisão binária Sim/Não e retorno convertem
        para o JSON novo (o exemplo literal do prompt do ADR 0017)."""
        obj = converter_mermaid_para_fluxograma(MERMAID_PROMPT_ANTIGO)

        assert fluxograma_valido(obj)
        assert obj == {
            "nos": [
                {"id": "B", "tipo": "passo", "texto": "Higienizar as mãos"},
                {
                    "id": "C",
                    "tipo": "decisao",
                    "texto": "Material completo?",
                    "ramos": [
                        {"rotulo": "Sim"},
                        {
                            "rotulo": "Não",
                            "desvio": {"texto": "Providenciar a reposição", "retorna_para": "B"},
                        },
                    ],
                },
                {"id": "D", "tipo": "passo", "texto": "Executar o procedimento"},
            ]
        }

    def test_desvio_que_reencontra_o_fluxo_converte_sem_retorna_para(self):
        """Ramo cujo card reentra exatamente no próximo passo da coluna vira
        desvio sem `retorna_para` (segue o fluxo), sem mudar a semântica."""
        codigo = (
            "flowchart TD\n"
            "  A([Início]) --> B[Reunir o material]\n"
            "  B --> C{Material completo?}\n"
            "  C -->|Não| E[Solicitar reposição]\n"
            "  C -->|Sim| D[Realizar o procedimento]\n"
            "  E --> D\n"
            "  D --> F([Fim])"
        )
        obj = converter_mermaid_para_fluxograma(codigo)
        assert fluxograma_valido(obj)
        decisao = obj["nos"][1]
        assert decisao["ramos"] == [
            {"rotulo": "Não", "desvio": {"texto": "Solicitar reposição"}},
            {"rotulo": "Sim"},
        ]
        assert obj["nos"][2]["id"] == "D"

    def test_converte_cadeia_de_passos_na_mesma_linha(self):
        """Fixture real dos testes de seções: `A --> B --> C` numa linha só."""
        obj = converter_mermaid_para_fluxograma(MERMAID_CADEIA)
        assert fluxograma_valido(obj)
        assert [no["texto"] for no in obj["nos"]] == ["Início", "Conferir", "Fim"]
        assert all(no["tipo"] == "passo" for no in obj["nos"])

    def test_decisao_com_ramos_para_o_mesmo_no_converte_sem_desvio(self):
        codigo = (
            "flowchart TD\n"
            "  A([Início]) --> C{Confirmado?}\n"
            "  C -->|Sim| D[Registrar]\n"
            "  C -->|Não| D\n"
            "  D --> F([Fim])"
        )
        obj = converter_mermaid_para_fluxograma(codigo)
        assert fluxograma_valido(obj)
        assert obj["nos"][0]["ramos"] == [{"rotulo": "Sim"}, {"rotulo": "Não"}]

    def test_ramo_para_o_fim_converte_com_a_decisao_no_final_da_coluna(self):
        """Decisão cujo ramo reto vai direto ao Fim: a decisão fecha a coluna e
        o desvio retorna ao passo anterior."""
        codigo = (
            "flowchart TD\n"
            "  A([Início]) --> B[Executar]\n"
            "  B --> C{Deu certo?}\n"
            "  C -->|Sim| F([Fim])\n"
            "  C -->|Não| E[Corrigir e repetir]\n"
            "  E --> B"
        )
        obj = converter_mermaid_para_fluxograma(codigo)
        assert fluxograma_valido(obj)
        assert obj["nos"][-1]["tipo"] == "decisao"
        assert obj["nos"][-1]["ramos"][1]["desvio"] == {"texto": "Corrigir e repetir", "retorna_para": "B"}

    def test_limpa_aspas_e_quebras_html_do_texto(self):
        codigo = 'flowchart TD\n  A([Início]) --> B["Higienizar<br/>as mãos"]\n  B --> F([Fim])'
        obj = converter_mermaid_para_fluxograma(codigo)
        assert obj["nos"][0]["texto"] == "Higienizar as mãos"

    def test_ignora_comentarios_e_ponto_e_virgula(self):
        codigo = "flowchart TD\n  %% comentário\n  A([Início]) --> B[Conferir];\n  B --> F([Fim])"
        obj = converter_mermaid_para_fluxograma(codigo)
        assert [no["texto"] for no in obj["nos"]] == ["Conferir"]

    # ── Inconversíveis: sinalizados com motivo, sem converter ────────────────

    def test_diamante_ate_o_fim_e_sinalizado_como_inconversivel(self):
        """CA: o inconversível é sinalizado. Dois ramos com caminhos
        independentes até o Fim não cabem na coluna única desta fatia
        (candidato à gramática N-ária da #222)."""
        with pytest.raises(MermaidInconversivelError, match="ramos"):
            converter_mermaid_para_fluxograma(MERMAID_DIAMANTE)

    def test_sem_cabecalho_flowchart_e_inconversivel(self):
        with pytest.raises(MermaidInconversivelError, match="flowchart"):
            converter_mermaid_para_fluxograma("graph LR\n  A --> B")

    def test_linha_fora_do_subset_e_inconversivel(self):
        with pytest.raises(MermaidInconversivelError):
            converter_mermaid_para_fluxograma("flowchart TD\n  classDef destaque fill:#f00\n  A([Início]) --> F([Fim])")

    def test_no_sem_definicao_de_forma_e_inconversivel(self):
        with pytest.raises(MermaidInconversivelError, match="defini"):
            converter_mermaid_para_fluxograma("flowchart TD\n  A --> B")

    def test_decisao_com_tres_ramos_e_inconversivel(self):
        codigo = (
            "flowchart TD\n"
            "  A([Início]) --> C{Qual via?}\n"
            "  C -->|Oral| D[Via oral]\n"
            "  C -->|Venosa| E[Via venosa]\n"
            "  C -->|Tópica| G[Via tópica]\n"
            "  D --> F([Fim])"
        )
        with pytest.raises(MermaidInconversivelError, match="decis"):
            converter_mermaid_para_fluxograma(codigo)

    def test_ramo_de_decisao_sem_rotulo_e_inconversivel(self):
        codigo = "flowchart TD\n  A([Início]) --> C{Ok?}\n  C --> D[Seguir]\n  C -->|Não| E[Parar]\n  D --> F([Fim])"
        with pytest.raises(MermaidInconversivelError, match="rótulo"):
            converter_mermaid_para_fluxograma(codigo)

    def test_retorno_direto_sem_card_e_inconversivel(self):
        """Ramo que volta direto a um passo anterior sem card intermediário não
        tem texto de desvio na gramática nova."""
        codigo = (
            "flowchart TD\n"
            "  A([Início]) --> B[Conferir]\n"
            "  B --> C{Completo?}\n"
            "  C -->|Sim| D[Executar]\n"
            "  C -->|Não| B\n"
            "  D --> F([Fim])"
        )
        with pytest.raises(MermaidInconversivelError):
            converter_mermaid_para_fluxograma(codigo)

    def test_passo_com_duas_saidas_e_inconversivel(self):
        codigo = (
            "flowchart TD\n"
            "  A([Início]) --> B[Conferir]\n"
            "  B --> C[Executar]\n"
            "  B --> D[Registrar]\n"
            "  C --> F([Fim])\n"
            "  D --> F"
        )
        with pytest.raises(MermaidInconversivelError):
            converter_mermaid_para_fluxograma(codigo)

    def test_no_inalcancavel_e_inconversivel(self):
        """Conteúdo fora do caminho principal não some em silêncio."""
        codigo = "flowchart TD\n  A([Início]) --> B[Conferir]\n  B --> F([Fim])\n  X[Solto]"
        with pytest.raises(MermaidInconversivelError):
            converter_mermaid_para_fluxograma(codigo)

    def test_vazio_e_inconversivel(self):
        with pytest.raises(MermaidInconversivelError):
            converter_mermaid_para_fluxograma("   ")


class TestMigrarRascunhoFluxogramas:
    def _rascunho(self, conteudo, svg="<svg>persistido</svg>"):
        secao = {"id": "id-flux", "titulo": "Fluxograma", "conteudo": conteudo, "tipo": "fluxograma"}
        if svg is not None:
            secao["svg"] = svg
        return {
            "secoes": [
                {"id": "id-obj", "titulo": "Objetivo", "conteudo": "Padronizar.", "tipo": "texto"},
                secao,
            ]
        }

    def test_converte_a_secao_mermaid_e_preserva_o_svg_byte_a_byte(self):
        """CA: a conversão troca só o `conteudo`; o SVG persistido (fonte do PDF
        assinado, ADR 0017) não muda um byte, e id/título/demais seções ficam."""
        rascunho = self._rascunho(MERMAID_PROMPT_ANTIGO)
        novo, relatorios = migrar_rascunho_fluxogramas(rascunho)

        secao = novo["secoes"][1]
        assert isinstance(secao["conteudo"], dict)
        assert fluxograma_valido(secao["conteudo"])
        assert secao["svg"] == "<svg>persistido</svg>"
        assert secao["id"] == "id-flux"
        assert novo["secoes"][0] == rascunho["secoes"][0]
        assert [r["status"] for r in relatorios] == ["convertida"]

    def test_nao_muta_o_rascunho_original(self):
        rascunho = self._rascunho(MERMAID_PROMPT_ANTIGO)
        migrar_rascunho_fluxogramas(rascunho)
        assert rascunho["secoes"][1]["conteudo"] == MERMAID_PROMPT_ANTIGO

    def test_e_idempotente(self):
        """CA: rodar de novo não muda nada (objeto já convertido é pulado)."""
        novo, _ = migrar_rascunho_fluxogramas(self._rascunho(MERMAID_PROMPT_ANTIGO))
        de_novo, relatorios = migrar_rascunho_fluxogramas(novo)
        assert de_novo == novo
        assert [r["status"] for r in relatorios] == ["pulada"]

    def test_inconversivel_permanece_como_estava(self):
        """CA: o que não parsear permanece intacto e cai no fallback existente."""
        rascunho = self._rascunho(MERMAID_DIAMANTE)
        novo, relatorios = migrar_rascunho_fluxogramas(rascunho)
        assert novo == rascunho
        assert relatorios[0]["status"] == "inconversivel"
        assert relatorios[0]["motivo"]

    def test_string_json_e_secao_vazia_sao_puladas(self):
        rascunho = {
            "secoes": [
                {"id": "s1", "titulo": "Fluxograma", "conteudo": '{"nos": []}', "tipo": "fluxograma"},
                {"id": "s2", "titulo": "Fluxo B", "conteudo": "", "tipo": "fluxograma"},
            ]
        }
        novo, relatorios = migrar_rascunho_fluxogramas(rascunho)
        assert novo == rascunho
        assert [r["status"] for r in relatorios] == ["pulada", "pulada"]

    def test_rascunho_legado_de_chaves_fixas_migra_o_shape_e_converte(self):
        """Rascunho anterior ao ADR 0016 (chaves fixas) primeiro vira lista de
        seções (função existente) e então o fluxograma converte."""
        legado = {"objetivo": "Padronizar.", "fluxograma": MERMAID_PROMPT_ANTIGO}
        novo, relatorios = migrar_rascunho_fluxogramas(legado)
        secoes_flux = [s for s in novo["secoes"] if s["tipo"] == "fluxograma"]
        assert len(secoes_flux) == 1
        assert isinstance(secoes_flux[0]["conteudo"], dict)
        assert [r["status"] for r in relatorios] == ["convertida"]


class _FakeQuery:
    def __init__(self, tabela):
        self._tabela = tabela

    def select(self, *_args, **_kwargs):
        return self

    def order(self, *_args, **_kwargs):
        return self

    def range(self, inicio, fim):
        self._inicio, self._fim = inicio, fim
        return self

    def update(self, payload):
        self._update = payload
        return self

    def eq(self, coluna, valor):
        self._eq = (coluna, valor)
        return self

    def execute(self):
        if hasattr(self, "_update"):
            self._tabela.updates.append((self._eq[1], self._update))

            class _R:
                data = []

            return _R()

        class _R:
            data = self._tabela.rows[self._inicio : self._fim + 1]

        return _R()


class _FakeTabela:
    def __init__(self, rows):
        self.rows = rows
        self.updates = []


class _FakeSupabase:
    def __init__(self, rows):
        self.tabela = _FakeTabela(rows)

    def table(self, nome):
        assert nome == "pops_versoes"
        return _FakeQuery(self.tabela)


class TestScriptMigracao:
    def _rows(self):
        return [
            {
                "id": "v1",
                "rascunho": {
                    "secoes": [
                        {
                            "id": "f1",
                            "titulo": "Fluxograma",
                            "conteudo": MERMAID_PROMPT_ANTIGO,
                            "tipo": "fluxograma",
                            "svg": "<svg>a</svg>",
                        }
                    ]
                },
            },
            {
                "id": "v2",
                "rascunho": {
                    "secoes": [{"id": "f2", "titulo": "Fluxograma", "conteudo": MERMAID_DIAMANTE, "tipo": "fluxograma"}]
                },
            },
            {"id": "v3", "rascunho": None},
        ]

    def test_dry_run_relata_e_nao_escreve(self):
        """CA: modo dry-run com relatório de convertidos/pulados/inconversíveis,
        sem tocar o banco."""
        fake = _FakeSupabase(self._rows())
        totais = executar(fake, aplicar=False)
        assert fake.tabela.updates == []
        assert totais["convertidas"] == 1
        assert totais["inconversiveis"] == 1
        assert totais["versoes"] == 3

    def test_aplicar_escreve_so_as_versoes_que_mudaram(self):
        fake = _FakeSupabase(self._rows())
        totais = executar(fake, aplicar=True)
        assert totais["versoes_atualizadas"] == 1
        assert len(fake.tabela.updates) == 1
        versao_id, payload = fake.tabela.updates[0]
        assert versao_id == "v1"
        secao = payload["rascunho"]["secoes"][0]
        assert isinstance(secao["conteudo"], dict)
        assert secao["svg"] == "<svg>a</svg>"

    def test_segunda_execucao_e_idempotente(self):
        """CA: script idempotente; depois de aplicar, nada mais a escrever."""
        fake = _FakeSupabase(self._rows())
        executar(fake, aplicar=True)
        rows2 = self._rows()
        rows2[0]["rascunho"] = fake.tabela.updates[0][1]["rascunho"]
        fake2 = _FakeSupabase(rows2)
        totais = executar(fake2, aplicar=True)
        assert fake2.tabela.updates == []
        assert totais["versoes_atualizadas"] == 0
