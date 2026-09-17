"""Testes do sanitizador de travessão (issue #136, ADR 0013).

A saída da IA (Ata, Ata Guiada, POP, email) não pode conter travessão (em dash)
nem meia-risca (en dash). A função pura troca esses sinais por vírgula no texto
corrido e por hífen quando estão entre dígitos (faixa numérica), sem nunca tocar
no hífen comum de palavra composta. Os literais com os tracinhos longos abaixo
são entradas de teste deliberadas.
"""

from app.utils.text_sanitizer import sanitizar_estrutura, sanitizar_travessao, texto_ou_nulo


class TestSanitizarTravessao:
    def test_travessao_entre_palavras_vira_virgula(self):
        assert sanitizar_travessao("o prazo — que era curto — venceu") == ("o prazo, que era curto, venceu")

    def test_meia_risca_entre_palavras_vira_virgula(self):
        assert sanitizar_travessao("reunião – decisão tomada") == "reunião, decisão tomada"

    def test_faixa_entre_digitos_vira_hifen(self):
        assert sanitizar_travessao("entre 10–15 leitos") == "entre 10-15 leitos"

    def test_faixa_de_anos_entre_digitos_vira_hifen(self):
        assert sanitizar_travessao("vigência 2024–2026") == "vigência 2024-2026"

    def test_faixa_com_travessao_longo_entre_digitos_vira_hifen(self):
        assert sanitizar_travessao("das 8—12 horas") == "das 8-12 horas"

    def test_multiplas_ocorrencias(self):
        assert sanitizar_travessao("a — b – c — d") == "a, b, c, d"

    def test_hifen_comum_nao_e_alterado(self):
        assert sanitizar_travessao("anti-inflamatório bem-estar pós-operatório") == (
            "anti-inflamatório bem-estar pós-operatório"
        )

    def test_hifen_entre_digitos_nao_e_alterado(self):
        # hífen comum em data/código não vira nada; só os tracinhos longos é que mudam
        assert sanitizar_travessao("2024-01-15 e o código A-12") == "2024-01-15 e o código A-12"

    def test_texto_sem_dash_passa_intacto(self):
        assert sanitizar_travessao("ata sem nenhum sinal especial") == "ata sem nenhum sinal especial"

    def test_dash_colado_em_palavra_vira_virgula(self):
        # sem espaços ao redor, entre letras, ainda é travessão de texto
        assert sanitizar_travessao("palavra—outra") == "palavra, outra"

    def test_entrada_vazia(self):
        assert sanitizar_travessao("") == ""

    def test_nao_string_passa_intacto(self):
        assert sanitizar_travessao(None) is None
        assert sanitizar_travessao(5) == 5


class TestSanitizarEstrutura:
    """A saída da IA é JSON estruturado (dict/list); o sanitizador percorre a
    estrutura e limpa só as folhas de texto, preservando o shape."""

    def test_percorre_dict_aninhado(self):
        entrada = {
            "objetivo": "discutir — e decidir",
            "quadro_atribuicoes": [
                {"acao": "comprar 10–15 itens", "responsavel": "Ana Silva"},
                {"acao": "rever bem-estar", "prazo": None},
            ],
        }
        esperado = {
            "objetivo": "discutir, e decidir",
            "quadro_atribuicoes": [
                {"acao": "comprar 10-15 itens", "responsavel": "Ana Silva"},
                {"acao": "rever bem-estar", "prazo": None},
            ],
        }
        assert sanitizar_estrutura(entrada) == esperado

    def test_preserva_tipos_nao_texto(self):
        entrada = {"presente": True, "n": 3, "prazo": None, "lista": [1, 2]}
        assert sanitizar_estrutura(entrada) == entrada

    def test_string_simples(self):
        assert sanitizar_estrutura("a — b") == "a, b"


class TestTextoOuNulo:
    """A régua do campo opcional de texto (issue #663).

    Era a `_limpar` privada do canal público e virou utilitário da casa quando o
    registro manual do ouvidor passou a gravar os mesmos campos: as duas portas
    escrevem `paciente_nome` e `paciente_referencia`, e quem lê é um leitor só.
    Promete três coisas, e cada teste aqui cobre uma delas.
    """

    def test_apara_as_pontas(self):
        assert texto_ou_nulo("  Maria Souza  ") == "Maria Souza"

    def test_espaco_em_branco_e_ausencia(self):
        assert texto_ou_nulo("   ") is None

    def test_pontuacao_sozinha_e_ausencia(self):
        """O hífen que alguém digita para dizer "não perguntei" não é conteúdo.

        Gravado, ele faria o Dossiê parar de mostrar "Não informado" e apagaria
        o aviso de relato em nome de outra pessoa sem o nome do paciente."""
        assert texto_ou_nulo("-") is None
        assert texto_ou_nulo("...") is None

    def test_travessao_no_meio_do_texto_e_sanitizado(self):
        """Tipografia da casa (ADR 0013) antes de o valor virar coluna: o campo
        aparece no Dossiê e no email ao setor. O travessão sozinho já cairia
        pela régua da pontuação, então quem distingue as duas versões desta
        função é o travessão ENTRE palavras."""
        assert texto_ou_nulo("Maria — leito 12") == "Maria, leito 12"
