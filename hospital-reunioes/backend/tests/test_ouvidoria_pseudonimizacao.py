"""Pseudonimização antes da IA externa (issue #342, PRD #319, ADR 0034).

A rotina é função pura: recebe texto livre da Manifestação e devolve o mesmo
texto com nome completo, CPF, telefone, email e Protocolo de ouvidoria trocados
por marcadores. Não lê banco, não olha o relógio, não fala com rede. É o seam
que a fatia I5 usa antes de qualquer envio ao OpenRouter, e estes testes
exercitam esse seam direto, como pede a seção "Decisões de teste" do PRD #319.
"""

from __future__ import annotations

import re

import pytest


class TestEmail:
    def test_email_do_manifestante_vira_marcador(self):
        from app.services.ouvidoria_pseudonimizacao import pseudonimizar

        saida = pseudonimizar("Pede retorno em maria.silva+ouvidoria@gmail.com.br, por favor.")

        assert saida == "Pede retorno em [EMAIL], por favor."


class TestCPF:
    def test_cpf_com_pontuacao_vira_marcador(self):
        from app.services.ouvidoria_pseudonimizacao import pseudonimizar

        saida = pseudonimizar("Informou o CPF 529.982.247-25 no balcão.")

        assert saida == "Informou o CPF [CPF] no balcão."

    def test_cpf_sem_pontuacao_vira_marcador(self):
        from app.services.ouvidoria_pseudonimizacao import pseudonimizar

        saida = pseudonimizar("Informou o CPF 52998224725 no balcão.")

        assert saida == "Informou o CPF [CPF] no balcão."


class TestTelefone:
    """Critério de aceite: telefone com DDD, nos desenhos que aparecem no
    relato de quem digita à mão."""

    @pytest.mark.parametrize(
        "escrito",
        [
            "(21) 98765-4321",
            "(21)98765-4321",
            "21 98765-4321",
            "21987654321",
            "+55 21 98765-4321",
            "(21) 3456-7890",
            "98765-4321",
        ],
    )
    def test_telefone_vira_marcador(self, escrito):
        from app.services.ouvidoria_pseudonimizacao import pseudonimizar

        saida = pseudonimizar(f"Pede que liguem no {escrito} depois das 18h.")

        assert saida == "Pede que liguem no [TELEFONE] depois das 18h."


class TestProtocolo:
    """O número de atendimento do critério de aceite é o Protocolo de
    ouvidoria, `ANO-NNNN` (CONTEXT.md)."""

    @pytest.mark.parametrize("escrito", ["2026-0007", "2026-10345"])
    def test_protocolo_vira_marcador(self, escrito):
        from app.services.ouvidoria_pseudonimizacao import pseudonimizar

        saida = pseudonimizar(f"Cobra resposta do {escrito} aberto na semana passada.")

        assert saida == "Cobra resposta do [PROTOCOLO] aberto na semana passada."


class TestNomeCompleto:
    def test_nome_completo_vira_marcador(self):
        from app.services.ouvidoria_pseudonimizacao import pseudonimizar

        saida = pseudonimizar("A paciente Maria da Silva Souza reclamou da espera.")

        assert saida == "A paciente [NOME] reclamou da espera."

    def test_primeiro_nome_atras_de_tratamento_tambem_some(self):
        """Sozinho, "Carlos" é palavra qualquer; atrás de "Dr." é a pessoa de
        quem o relato fala, e o tratamento é a pista que o desenho de nome e
        sobrenome não dá."""
        from app.services.ouvidoria_pseudonimizacao import pseudonimizar

        saida = pseudonimizar("O Dr. Carlos foi grosseiro e a Sra. Rita confirmou.")

        assert saida == "O Dr. [NOME] foi grosseiro e a Sra. [NOME] confirmou."

    def test_tratamento_seguido_de_nome_completo_some_de_uma_vez_so(self):
        from app.services.ouvidoria_pseudonimizacao import pseudonimizar

        assert pseudonimizar("Falei com a Dra. Beatriz Antunes Rocha.") == "Falei com a Dra. [NOME]."

    def test_nome_ao_lado_da_area_some_sem_levar_a_area_junto(self):
        """A sugestão de ação corretiva do PRD #319 precisa saber QUAL área
        falhou: apagar o nome não pode apagar o setor colado nele."""
        from app.services.ouvidoria_pseudonimizacao import pseudonimizar

        saida = pseudonimizar("A enfermeira Ana Paula Ribeiro do Centro Cirúrgico não respondeu.")

        assert saida == "A enfermeira [NOME] do Centro Cirúrgico não respondeu."


class TestOQueDeveSobreviver:
    @pytest.mark.parametrize(
        "texto",
        [
            "Reclamação sobre o Pronto Socorro do Hospital São Matheus.",
            "O caso foi aberto em 2026-08-12 e segue sem resposta.",
            "Esperou das 08h às 17h na Unidade de Terapia Intensiva.",
            "Avaliou o atendimento com nota 8 e citou o Reclame Aqui.",
        ],
    )
    def test_texto_sem_dado_pessoal_atravessa_intacto(self, texto):
        from app.services.ouvidoria_pseudonimizacao import pseudonimizar

        assert pseudonimizar(texto) == texto


class TestFuncaoPura:
    """Critério de aceite: mesma entrada, mesma saída, sem tocar banco ou
    rede."""

    def test_mesma_entrada_devolve_mesma_saida(self):
        from app.services.ouvidoria_pseudonimizacao import pseudonimizar

        entrada = "Maria da Silva, CPF 529.982.247-25, ligou do (21) 98765-4321."

        assert pseudonimizar(entrada) == pseudonimizar(entrada)

    def test_passar_a_saida_de_volta_nao_muda_mais_nada(self):
        from app.services.ouvidoria_pseudonimizacao import pseudonimizar

        uma_vez = pseudonimizar("Maria da Silva reclamou do protocolo 2026-0007 por maria@teste.com.")

        assert pseudonimizar(uma_vez) == uma_vez

    def test_modulo_nao_importa_banco_rede_nem_relogio(self):
        """Pureza que o olho não vê: se um dia alguém pendurar uma consulta ao
        Supabase ou uma chamada HTTP aqui dentro, este teste cai."""
        import ast
        import pathlib

        from app.services import ouvidoria_pseudonimizacao

        arvore = ast.parse(pathlib.Path(ouvidoria_pseudonimizacao.__file__).read_text(encoding="utf-8"))
        importados = set()
        for no in ast.walk(arvore):
            if isinstance(no, ast.Import):
                importados.update(alias.name.split(".")[0] for alias in no.names)
            elif isinstance(no, ast.ImportFrom) and no.module:
                importados.add(no.module.split(".")[0])

        proibidos = {"supabase", "httpx", "requests", "openai", "resend", "random", "time", "datetime", "os", "app"}

        assert importados & proibidos == set()

    @pytest.mark.parametrize("vazio", [None, ""])
    def test_texto_ausente_vira_texto_vazio(self, vazio):
        from app.services.ouvidoria_pseudonimizacao import pseudonimizar

        assert pseudonimizar(vazio) == ""


# Manifestações no formato em que elas chegam de verdade: formulário público,
# registro manual do ouvidor por telefone, denúncia de colaborador e elogio.
# Cada uma declara o que foi plantado nela e a âncora que PRECISA sobreviver,
# senão "apagar tudo" passaria por pseudonimização.
MANIFESTACOES = [
    (
        "formulario_publico",
        "Meu nome é Joana Maria Pereira, CPF 529.982.247-25. Estive no Pronto Socorro "
        "no dia 12/08 e esperei mais de três horas sem nenhuma informação sobre a fila. "
        "Meu telefone é (21) 98765-4321 e meu email é joana.pereira@gmail.com.",
        ["Joana Maria Pereira", "Joana", "Pereira", "529.982.247-25", "98765-4321", "joana.pereira@gmail.com"],
        "Pronto Socorro",
    ),
    (
        "registro_manual_telefone",
        "Ligou o senhor Carlos Eduardo Nunes, acompanhante da paciente Rita de Cassia Nunes, "
        "para reclamar da conduta do porteiro no plantão da noite. Contato 21987654321. "
        "Cita o protocolo 2026-0007, aberto no mês passado e sem resposta até agora.",
        ["Carlos Eduardo Nunes", "Rita de Cassia Nunes", "Nunes", "21987654321", "2026-0007"],
        "porteiro",
    ),
    (
        "denuncia_de_colaborador",
        "Sou colaboradora do Centro Cirúrgico e denuncio o coordenador Roberto Alves Pinto, "
        "que exige plantão extra sem registro. Meu contato é 11 3456-7890 e o email dele é "
        "roberto.alves@hsm.com.br.",
        ["Roberto Alves Pinto", "Roberto", "3456-7890", "roberto.alves@hsm.com.br"],
        "Centro Cirúrgico",
    ),
    (
        "elogio_sem_numero",
        "A equipe da Unidade de Terapia Intensiva foi excelente, em especial a enfermeira "
        "Ana Cristina Barbosa e o médico Paulo Sergio de Andrade Lima.",
        ["Ana Cristina Barbosa", "Barbosa", "Paulo Sergio de Andrade Lima", "Andrade"],
        "Unidade de Terapia Intensiva",
    ),
]

# Detectores escritos aqui, de propósito longe do módulo: se o teste usasse as
# expressões do próprio módulo, ele concordaria com qualquer bug delas.
_SOBROU_EMAIL = re.compile(r"\S+@\S+\.\S+")
_SOBROU_CPF = re.compile(r"\d{3}\.?\d{3}\.?\d{3}-?\d{2}")
_SOBROU_SEQUENCIA_LONGA = re.compile(r"\d{8,}")
_SOBROU_TELEFONE = re.compile(r"\d{4,5}[\s.-]\d{4}")
_SOBROU_PROTOCOLO = re.compile(r"\d{4}-\d{4,}")


class TestManifestacoesReais:
    @pytest.mark.parametrize(
        ("texto", "plantados", "ancora"),
        [caso[1:] for caso in MANIFESTACOES],
        ids=[caso[0] for caso in MANIFESTACOES],
    )
    def test_nenhum_dado_pessoal_sobrevive(self, texto, plantados, ancora):
        from app.services.ouvidoria_pseudonimizacao import pseudonimizar

        saida = pseudonimizar(texto)

        for plantado in plantados:
            assert plantado not in saida, f"sobreviveu no texto que iria para a IA: {plantado}"
        assert not _SOBROU_EMAIL.search(saida)
        assert not _SOBROU_CPF.search(saida)
        assert not _SOBROU_SEQUENCIA_LONGA.search(saida)
        assert not _SOBROU_TELEFONE.search(saida)
        assert not _SOBROU_PROTOCOLO.search(saida)

    @pytest.mark.parametrize(
        ("texto", "plantados", "ancora"),
        [caso[1:] for caso in MANIFESTACOES],
        ids=[caso[0] for caso in MANIFESTACOES],
    )
    def test_o_assunto_da_manifestacao_sobrevive(self, texto, plantados, ancora):
        """Pseudonimizar não é apagar: sem o assunto, a sugestão de ação
        corretiva do PRD #319 não teria sobre o que ser escrita."""
        from app.services.ouvidoria_pseudonimizacao import pseudonimizar

        assert ancora in pseudonimizar(texto)


class TestCasosDeBorda:
    def test_campo_que_e_so_o_nome_vira_so_o_marcador(self):
        """A fatia I5 passa pela mesma função o campo `manifestante_nome`, que
        chega sem frase em volta."""
        from app.services.ouvidoria_pseudonimizacao import pseudonimizar

        assert pseudonimizar("Joana Maria Pereira") == "[NOME]"

    def test_nome_colado_na_pontuacao_some_e_a_pontuacao_fica(self):
        from app.services.ouvidoria_pseudonimizacao import pseudonimizar

        assert pseudonimizar("Foi atendida por Ana Cristina Barbosa.") == "Foi atendida por [NOME]."

    def test_onze_digitos_que_nao_fecham_como_cpf_somem_do_mesmo_jeito(self):
        """Empate entre CPF cru e celular não pode virar vazamento: o número
        some, ainda que sob o outro marcador."""
        from app.services.ouvidoria_pseudonimizacao import pseudonimizar

        saida = pseudonimizar("Anotou 21988887777 como contato.")

        assert "21988887777" not in saida

    def test_marcador_nao_vira_isca_para_o_proximo_marcador(self):
        from app.services.ouvidoria_pseudonimizacao import pseudonimizar

        assert pseudonimizar("[NOME] [CPF] [TELEFONE] [EMAIL] [PROTOCOLO]") == (
            "[NOME] [CPF] [TELEFONE] [EMAIL] [PROTOCOLO]"
        )
