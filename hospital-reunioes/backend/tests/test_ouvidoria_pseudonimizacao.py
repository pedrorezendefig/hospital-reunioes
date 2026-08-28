"""Pseudonimização antes da IA externa (issue #342, PRD #319, ADR 0034).

A rotina é função pura: recebe texto livre da Manifestação e devolve o mesmo
texto com nome completo, CPF, telefone, email e Protocolo de ouvidoria trocados
por marcadores. Não lê banco, não olha o relógio, não fala com rede. É o seam
que a fatia I5 usa antes de qualquer envio ao OpenRouter, e estes testes
exercitam esse seam direto, como pede a seção "Decisões de teste" do PRD #319.

As entradas aqui não são inventadas em Title Case de uma linha só: são as
grafias em que a manifestação chega de verdade (caixa alta do balcão, tudo
minúsculo do celular, relato multilinha colado do Word), porque foi exatamente
fora do Title Case que a primeira versão desta rotina vazou nome.
"""

from __future__ import annotations

import re
import time

import pytest


class TestEmail:
    def test_email_do_manifestante_vira_marcador(self):
        from app.services.ouvidoria_pseudonimizacao import pseudonimizar

        saida = pseudonimizar("Pede retorno em maria.silva+ouvidoria@gmail.com.br, por favor.")

        assert saida == "Pede retorno em [EMAIL], por favor."

    @pytest.mark.parametrize(
        "entrada",
        [
            "a" * 50_000,
            "A" * 20_000,
            "1" * 20_000,
            "a@" * 10_000,
            "ab " * 20_000,
            "ab" + " " * 50_000 + "cd",
            "maria silva " * 10_000,
            ("a" * 45 + " \t\xa0\n") * 5_000,
        ],
        ids=[
            "minúsculas",
            "maiúsculas",
            "dígitos",
            "arrobas",
            "palavras curtas",
            "espaço entre duas palavras",
            "nomes da base repetidos",
            "palavra longa com separador variado",
        ],
    )
    def test_texto_longo_nao_trava_a_rotina(self, entrada):
        """A fatia I5 concatena relato, despachos e respostas do Dossiê: o
        texto passa fácil do teto de 10 mil do formulário. Sem teto no local
        part do email, 50 mil caracteres sem arroba levavam 7 segundos; sem
        teto no tamanho da palavra, 20 mil maiúsculas seguidas levavam 3,7.

        Os quatro últimos casos são a camada da base (issue #412): ela varre
        sequências de palavra separadas por espaço, e é onde um quantificador
        aninhado poderia virar backtracking caro. Medido: nenhum passa de
        0,15s."""
        from app.services.ouvidoria_pseudonimizacao import pseudonimizar

        comeco = time.monotonic()
        pseudonimizar(entrada)

        assert time.monotonic() - comeco < 2.0


class TestCPF:
    @pytest.mark.parametrize(
        "escrito",
        [
            "529.982.247-25",
            "52998224725",
            "529 982 247 25",
            "529-982-247-25",
            "529.982.247/25",
        ],
    )
    def test_cpf_vira_marcador(self, escrito):
        from app.services.ouvidoria_pseudonimizacao import pseudonimizar

        saida = pseudonimizar(f"Informou o CPF {escrito} no balcão.")

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


class TestDataDeNascimento:
    """Data de nascimento (issue #398), e SÓ ela.

    Nascimento e atendimento têm o mesmo desenho (`12/08/1975` e `12/08/2026`),
    então quem separa os dois é a pista. Apagar toda data completa fecharia o
    vazamento inteiro, mas levaria junto a data do atendimento, que é o
    contexto de que a sugestão de ação corretiva vive."""

    @pytest.mark.parametrize(
        "escrito, esperado",
        [
            ("Nasci em 12/08/1975.", "Nasci em [DATA_NASCIMENTO]."),
            ("Data de nascimento: 12/08/1975.", "Data de nascimento: [DATA_NASCIMENTO]."),
            ("nascida em 12-08-1975.", "nascida em [DATA_NASCIMENTO]."),
            ("DN 12.08.1975.", "DN [DATA_NASCIMENTO]."),
        ],
    )
    def test_data_atras_de_pista_de_nascimento_vira_marcador(self, escrito, esperado):
        from app.services.ouvidoria_pseudonimizacao import pseudonimizar

        assert pseudonimizar(escrito) == esperado

    @pytest.mark.parametrize(
        "texto",
        [
            "Estive no Pronto Socorro em 12/08/2026 e esperei quatro horas.",
            "A cirurgia foi remarcada de 03/09/2026 para 17/09/2026 sem aviso.",
        ],
    )
    def test_data_do_atendimento_atravessa_intacta(self, texto):
        """Não sobre-apagamento, e este é o teste que sustenta a decisão: sem
        pista, a data fica. Quando o dia do fato some, some com ele a chance de
        a sugestão dizer o que corrigir."""
        from app.services.ouvidoria_pseudonimizacao import pseudonimizar

        assert pseudonimizar(texto) == texto


class TestHandleDeRedeSocial:
    """Perfil de rede social citado no relato (issue #398). É identificador
    direto: leva a uma pessoa em um clique."""

    @pytest.mark.parametrize("escrito", ["@maria.silva88", "@joao_silva", "@Ana"])
    def test_handle_vira_marcador(self, escrito):
        from app.services.ouvidoria_pseudonimizacao import pseudonimizar

        saida = pseudonimizar(f"Ja reclamei no perfil {escrito} e ninguem respondeu.")

        assert saida == "Ja reclamei no perfil [REDE_SOCIAL] e ninguem respondeu."

    def test_email_continua_saindo_como_email(self):
        """Não sobre-apagamento: o handle não pode roubar o email, que tem
        rótulo próprio desde a #342 e também carrega uma arroba."""
        from app.services.ouvidoria_pseudonimizacao import pseudonimizar

        saida = pseudonimizar("Meu email e joana.pereira@gmail.com para retorno.")

        assert saida == "Meu email e [EMAIL] para retorno."

    def test_arroba_colada_em_palavra_nao_vira_meio_marcador(self):
        """A guarda de borda existe para o endereço que a regra de email NÃO
        reconhece, como o interno sem ponto no domínio. Sem ela, a arroba
        levaria só o domínio e deixaria "maria" no texto: o mesmo defeito de
        sair pela metade que o CNS tinha, agora com cara de anonimizado."""
        from app.services.ouvidoria_pseudonimizacao import pseudonimizar

        texto = "Mandei para maria@intranet e ninguem respondeu."

        assert pseudonimizar(texto) == texto


class TestPlaca:
    """Placa de veículo, nos dois desenhos que circulam hoje (issue #398): o
    antigo `ABC-1234` e o Mercosul `ABC1D23`."""

    @pytest.mark.parametrize("escrito", ["ABC-1234", "ABC1234", "ABC1D23", "abc-1234"])
    def test_placa_vira_marcador(self, escrito):
        from app.services.ouvidoria_pseudonimizacao import pseudonimizar

        saida = pseudonimizar(f"A ambulancia de placa {escrito} chegou atrasada.")

        assert saida == "A ambulancia de placa [PLACA] chegou atrasada."

    @pytest.mark.parametrize(
        "texto",
        [
            "Fiquei na UTI 2024 e ninguem apareceu.",
            "Cobraram R$ 12345678 de taxa.",
            "Fui para a sala 1234 do terceiro andar.",
        ],
    )
    def test_sigla_e_numero_soltos_nao_viram_placa(self, texto):
        """Não sobre-apagamento: o desenho da placa é colado ou com hífen. Uma
        sigla da casa separada do número por espaço continua no texto, senão a
        área sumiria da sugestão de ação corretiva."""
        from app.services.ouvidoria_pseudonimizacao import pseudonimizar

        assert "[PLACA]" not in pseudonimizar(texto)


class TestCEP:
    """CEP do endereço de quem manifesta (issue #398)."""

    def test_cep_vira_marcador(self):
        from app.services.ouvidoria_pseudonimizacao import pseudonimizar

        saida = pseudonimizar("Moro no CEP 20040-020 e ninguem me ligou de volta.")

        assert saida == "Moro no CEP [CEP] e ninguem me ligou de volta."

    @pytest.mark.parametrize(
        "texto, marcador_certo",
        [
            ("Pede que liguem no 98765-4321 depois.", "[TELEFONE]"),
            ("Cobra resposta do 2026-0007 aberto ontem.", "[PROTOCOLO]"),
        ],
    )
    def test_telefone_e_protocolo_nao_viram_cep(self, texto, marcador_certo):
        """Não sobre-apagamento: o desenho do CEP é cinco mais três dígitos, e
        ele não pode roubar o que já tem rótulo próprio."""
        from app.services.ouvidoria_pseudonimizacao import pseudonimizar

        saida = pseudonimizar(texto)

        assert "[CEP]" not in saida
        assert marcador_certo in saida


class TestRG:
    """RG, o documento que o manifestante apresenta no balcão (issue #398)."""

    @pytest.mark.parametrize("escrito", ["12.345.678-9", "12.345.678-X", "12345678-9"])
    def test_rg_vira_marcador(self, escrito):
        from app.services.ouvidoria_pseudonimizacao import pseudonimizar

        saida = pseudonimizar(f"Apresentei o RG {escrito} na recepcao.")

        assert saida == "Apresentei o RG [RG] na recepcao."

    def test_cpf_continua_saindo_como_cpf(self):
        """Não sobre-apagamento: o desenho do RG não pode roubar o CPF, que
        tem rótulo próprio e é o que a #342 entregou."""
        from app.services.ouvidoria_pseudonimizacao import pseudonimizar

        saida = pseudonimizar("Meu CPF e 529.982.247-25.")

        assert saida == "Meu CPF e [CPF]."

    def test_valor_em_reais_nao_vira_rg(self):
        from app.services.ouvidoria_pseudonimizacao import pseudonimizar

        assert "[RG]" not in pseudonimizar("Cobraram R$ 12345678 de taxa.")


class TestCNS:
    """Cartão Nacional de Saúde, 15 dígitos (issue #398).

    Era o mais urgente dos seis identificadores da issue: antes desta fatia ele
    saía PELA METADE (`[TELEFONE] 6586 452`), porque a regra de telefone mordia
    os oito primeiros dígitos e devolvia o resto ao texto. Meio identificador
    no texto é pior que o identificador inteiro: parece anonimizado e não é."""

    @pytest.mark.parametrize(
        "escrito",
        [
            "7005 0831 6586 452",
            "700 5083 1658 6452",
            "700508316586452",
            "7005-0831-6586-452",
        ],
    )
    def test_cartao_do_sus_vira_um_marcador_so(self, escrito):
        from app.services.ouvidoria_pseudonimizacao import pseudonimizar

        saida = pseudonimizar(f"Meu cartao do SUS {escrito} nao foi localizado.")

        assert saida == "Meu cartao do SUS [CNS] nao foi localizado."

    @pytest.mark.parametrize(
        "texto",
        [
            "Cobraram R$ 12345678 de taxa sem explicar.",
            "Pede que liguem no 21987654321 depois das 18h.",
        ],
    )
    def test_numero_que_nao_e_cns_nao_vira_cns(self, texto):
        """Não sobre-apagamento: valor em reais e telefone continuam com o
        rótulo que já tinham. O CNS não pode alargar para pegar qualquer
        número comprido."""
        from app.services.ouvidoria_pseudonimizacao import pseudonimizar

        assert "[CNS]" not in pseudonimizar(texto)


class TestProtocolo:
    """O número de atendimento do critério de aceite é o Protocolo de
    ouvidoria, `ANO-NNNN` (CONTEXT.md)."""

    @pytest.mark.parametrize("escrito", ["2026-0007", "2026-10345"])
    def test_protocolo_vira_marcador(self, escrito):
        from app.services.ouvidoria_pseudonimizacao import pseudonimizar

        saida = pseudonimizar(f"Cobra resposta do {escrito} aberto na semana passada.")

        assert saida == "Cobra resposta do [PROTOCOLO] aberto na semana passada."

    @pytest.mark.parametrize("escrito", ["2026/0007", "2026-007", "2026/007"])
    def test_protocolo_digitado_errado_a_mao_tambem_vira_marcador(self, escrito):
        """O Protocolo real é `ANO-NNNN` com quatro dígitos ou mais, mas quem
        digita à mão troca o hífen por barra e come um zero (issue #398). O
        número errado continua sendo o número de atendimento de alguém."""
        from app.services.ouvidoria_pseudonimizacao import pseudonimizar

        saida = pseudonimizar(f"Cobra resposta do {escrito} aberto na semana passada.")

        assert saida == "Cobra resposta do [PROTOCOLO] aberto na semana passada."

    def test_data_completa_nao_vira_protocolo(self):
        """Não sobre-apagamento: aceitar a barra não pode transformar a data do
        atendimento em Protocolo."""
        from app.services.ouvidoria_pseudonimizacao import pseudonimizar

        texto = "Estive no Pronto Socorro em 12/08/2026 e esperei quatro horas."

        assert pseudonimizar(texto) == texto


class TestNomePeloDesenho:
    """Caixa mista: duas ou mais palavras capitalizadas seguidas."""

    def test_nome_completo_vira_marcador(self):
        from app.services.ouvidoria_pseudonimizacao import pseudonimizar

        saida = pseudonimizar("A paciente Maria da Silva Souza reclamou da espera.")

        assert saida == "A paciente [NOME] reclamou da espera."

    def test_nome_com_inicial_do_meio_vira_marcador(self):
        from app.services.ouvidoria_pseudonimizacao import pseudonimizar

        assert pseudonimizar("Atendeu a Maria S. Souza ontem.") == "Atendeu a [NOME] ontem."

    def test_nome_com_apostrofo_vira_marcador(self):
        from app.services.ouvidoria_pseudonimizacao import pseudonimizar

        assert pseudonimizar("Atendeu a Maria D'Ávila ontem.") == "Atendeu a [NOME] ontem."

    def test_nome_em_caixa_alta_no_meio_do_relato_vira_marcador(self):
        """Quem escreve minúsculo e bate o nome em caixa alta é caso comum."""
        from app.services.ouvidoria_pseudonimizacao import pseudonimizar

        saida = pseudonimizar("fui atendida por JOANA PEREIRA e ninguém explicou nada.")

        assert saida == "fui atendida por [NOME] e ninguém explicou nada."

    @pytest.mark.parametrize(
        "separador",
        [" ", "  ", "\t", "\xa0", "\n"],
        ids=["espaço", "espaço duplo", "tab", "NBSP do Word", "quebra de linha"],
    )
    def test_separador_diferente_de_um_espaco_nao_salva_o_sobrenome(self, separador):
        from app.services.ouvidoria_pseudonimizacao import pseudonimizar

        saida = pseudonimizar(f"Atendeu a Maria{separador}Silva no balcão.")

        assert "Silva" not in saida
        assert "Maria" not in saida

    def test_relato_multilinha_com_o_nome_quebrado_em_duas_linhas(self):
        from app.services.ouvidoria_pseudonimizacao import pseudonimizar

        saida = pseudonimizar("Nome:\nJoana Maria\nPereira")

        assert "Pereira" not in saida
        assert "Joana" not in saida
        assert saida.startswith("Nome:\n")

    def test_palavra_do_vocabulario_no_meio_do_nome_nao_salva_o_nome(self):
        """ "Marco" é mês e é primeiro nome: enquanto o vocabulário partia o
        nome ao meio, "Maria Marco Silva" atravessava inteiro."""
        from app.services.ouvidoria_pseudonimizacao import pseudonimizar

        assert pseudonimizar("A paciente Maria Marco Silva reclamou.") == "A paciente [NOME] reclamou."
        assert pseudonimizar("Marco Antonio Ribeiro reclamou.") == "[NOME] reclamou."

    def test_dois_nomes_com_a_area_no_meio_viram_dois_marcadores(self):
        """Duas palavras da casa seguidas separam um nome do outro. Sem essa
        parede, o marcador engoliria a área que está entre os dois."""
        from app.services.ouvidoria_pseudonimizacao import pseudonimizar

        saida = pseudonimizar("Reclamou de Maria Silva do Centro Cirúrgico e Paulo Souza.")

        assert saida == "Reclamou de [NOME] do Centro Cirúrgico e [NOME]."


class TestNomePelaPista:
    """Sem caixa que ajude, quem entrega a pessoa é a pista: "meu nome é",
    "Dr.", "Sra.". É como chega o relato digitado no celular pelo QR."""

    def test_nome_todo_em_minusculas_atras_da_apresentacao(self):
        from app.services.ouvidoria_pseudonimizacao import pseudonimizar

        saida = pseudonimizar("meu nome e joana maria pereira, sou paciente da dra ana claudia")

        assert "joana maria pereira" not in saida
        assert "ana claudia" not in saida
        assert saida.count("[NOME]") == 2

    def test_relato_todo_em_caixa_alta(self):
        from app.services.ouvidoria_pseudonimizacao import pseudonimizar

        saida = pseudonimizar("MEU NOME E JOANA MARIA PEREIRA, CPF 529.982.247-25. ESTIVE NO PRONTO SOCORRO.")

        assert "JOANA" not in saida
        assert "PEREIRA" not in saida
        assert "[CPF]" in saida
        assert "ESTIVE NO PRONTO SOCORRO" in saida

    def test_relato_em_caixa_alta_nao_e_moido_inteiro(self):
        """Num texto todo em caixa alta a caixa não distingue nada: se ela
        contasse como desenho de nome, o relato viraria fila de marcador."""
        from app.services.ouvidoria_pseudonimizacao import pseudonimizar

        texto = "ESTIVE NO PRONTO SOCORRO E FUI MAL ATENDIDA. ESPEREI QUATRO HORAS."

        assert pseudonimizar(texto) == texto

    def test_primeiro_nome_atras_de_tratamento_tambem_some(self):
        from app.services.ouvidoria_pseudonimizacao import pseudonimizar

        saida = pseudonimizar("O Dr. Carlos foi grosseiro e a Sra. Rita confirmou.")

        assert saida == "O Dr. [NOME] foi grosseiro e a Sra. [NOME] confirmou."

    def test_tratamento_seguido_de_nome_completo_some_de_uma_vez_so(self):
        from app.services.ouvidoria_pseudonimizacao import pseudonimizar

        assert pseudonimizar("Falei com a Dra. Beatriz Antunes Rocha.") == "Falei com a Dra. [NOME]."

    @pytest.mark.parametrize(
        "texto",
        [
            "Dr. Pronto Socorro nao atendeu.",
            "A Sra. Enfermagem reclamou.",
            "Dra. Recepção falhou.",
        ],
    )
    def test_pista_seguida_de_area_nao_come_a_area(self, texto):
        """A pista também consulta o vocabulário da casa: o que vem depois de
        "Dr." só é pessoa se não for palavra da casa."""
        from app.services.ouvidoria_pseudonimizacao import pseudonimizar

        assert pseudonimizar(texto) == texto


class TestAreaSobrevive:
    """Pseudonimizar não é apagar: sem a área, a sugestão de ação corretiva do
    PRD #319 não sabe quem falhou."""

    @pytest.mark.parametrize(
        "texto",
        [
            "Reclamação sobre o Pronto Socorro do Hospital São Matheus.",
            "O caso foi aberto em 2026-08-12 e segue sem resposta.",
            "Esperou das 08h às 17h na Unidade de Terapia Intensiva.",
            "Avaliou o atendimento com nota 8 e citou o Reclame Aqui.",
            "A Central de Marcação de Consultas não atende.",
            "Fiz TC de CRÂNIO e RX de TÓRAX no Pronto Socorro.",
        ],
    )
    def test_texto_sem_dado_pessoal_atravessa_intacto(self, texto):
        from app.services.ouvidoria_pseudonimizacao import pseudonimizar

        assert pseudonimizar(texto) == texto

    @pytest.mark.parametrize(
        ("texto", "esperado"),
        [
            (
                "A enfermeira Ana Paula Ribeiro do Centro Cirúrgico não respondeu.",
                "A enfermeira [NOME] do Centro Cirúrgico não respondeu.",
            ),
            (
                "O Dr. João Silva da Hemodinâmica errou.",
                "O Dr. [NOME] da Hemodinâmica errou.",
            ),
            (
                "Falei com Maria Silva e depois com Paulo Souza.",
                "Falei com [NOME] e depois com [NOME].",
            ),
        ],
    )
    def test_nome_colado_na_area_some_sem_levar_a_area_junto(self, texto, esperado):
        from app.services.ouvidoria_pseudonimizacao import pseudonimizar

        assert pseudonimizar(texto) == esperado


class TestFuncaoPura:
    """Critério de aceite: mesma entrada, mesma saída, sem tocar banco ou
    rede."""

    def test_relato_com_os_cinco_dados_sai_exatamente_assim(self):
        """Saída literal, escrita à mão a partir do critério de aceite. É o
        teste que uma rotina que não fizesse nada (ou que apagasse tudo) não
        consegue passar."""
        from app.services.ouvidoria_pseudonimizacao import pseudonimizar

        saida = pseudonimizar(
            "Joana Maria Pereira, CPF 529.982.247-25, telefone (21) 98765-4321, "
            "email joana@gmail.com, sobre o protocolo 2026-0007 do Pronto Socorro."
        )

        assert saida == (
            "[NOME], CPF [CPF], telefone [TELEFONE], email [EMAIL], sobre o protocolo [PROTOCOLO] do Pronto Socorro."
        )

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

        # `socket`, `urllib` e `subprocess` são as portas de rede e de processo
        # que faltavam; `secrets` e `uuid` são as duas fontes de acaso que o
        # `random` sozinho não cobria, e acaso quebra a função pura do mesmo
        # jeito que o relógio (issue #398).
        #
        # `pathlib` fica DE FORA de propósito, e não por esquecimento: desde a
        # #412 o módulo lê a base de nomes do disco com ele, uma vez, no
        # import. Proibir aqui obrigaria a reescrever aquela leitura sem ganho
        # nenhum de pureza.
        proibidos = {
            "supabase",
            "httpx",
            "requests",
            "openai",
            "resend",
            "random",
            "secrets",
            "uuid",
            "time",
            "datetime",
            "os",
            "socket",
            "urllib",
            "subprocess",
            "app",
        }

        assert importados & proibidos == set()

    @pytest.mark.parametrize("vazio", [None, ""])
    def test_texto_ausente_vira_texto_vazio(self, vazio):
        from app.services.ouvidoria_pseudonimizacao import pseudonimizar

        assert pseudonimizar(vazio) == ""


# Manifestações no formato em que elas chegam de verdade, nas quatro grafias
# que existem na porta de entrada: Title Case do registro manual, caixa alta do
# balcão, minúsculas do celular pelo QR e o relato multilinha colado do Word.
# Cada uma declara o que foi plantado nela e a âncora que PRECISA sobreviver,
# senão "apagar tudo" passaria por pseudonimização.
MANIFESTACOES = [
    (
        "formulario_publico_title_case",
        "Meu nome é Joana Maria Pereira, CPF 529.982.247-25. Estive no Pronto Socorro "
        "no dia 12/08 e esperei mais de três horas sem nenhuma informação sobre a fila. "
        "Meu telefone é (21) 98765-4321 e meu email é joana.pereira@gmail.com.",
        ["Joana Maria Pereira", "Joana", "Pereira", "529.982.247-25", "98765-4321", "joana.pereira@gmail.com"],
        "Pronto Socorro",
    ),
    (
        "balcao_em_caixa_alta",
        "MEU NOME E JOANA MARIA PEREIRA, CPF 529-982-247-25. ESTIVE NO PRONTO SOCORRO "
        "E FUI MAL ATENDIDA. MEU TELEFONE E 21987654321.",
        ["JOANA MARIA PEREIRA", "JOANA", "PEREIRA", "529-982-247-25", "21987654321"],
        "PRONTO SOCORRO",
    ),
    (
        "celular_pelo_qr_tudo_minusculo",
        "meu nome e joana maria pereira, sou paciente da dra ana claudia e esperei "
        "quatro horas na recepção. meu cpf e 529.982.247/25 e o telefone e 21 98765-4321.",
        ["joana maria pereira", "ana claudia", "529.982.247/25", "98765-4321"],
        "recepção",
    ),
    (
        "registro_manual_multilinha",
        "Manifestante:\nCarlos Eduardo Nunes\nAcompanhante de Rita de Cassia Nunes\n\n"
        "Reclama da conduta do porteiro no plantão da noite.\nContato: 21987654321\n"
        "Cita o protocolo 2026-0007, aberto no mês passado.",
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
_SOBROU_CPF = re.compile(r"\d{3}[.\s/-]?\d{3}[.\s/-]?\d{3}[.\s/-]?\d{2}")
_SOBROU_SEQUENCIA_LONGA = re.compile(r"\d{8,}")
_SOBROU_TELEFONE = re.compile(r"\d{4,5}[\s.-]\d{4}")
_SOBROU_PROTOCOLO = re.compile(r"\d{4}-\d{4,}")


class TestManifestacoesReais:
    @pytest.mark.parametrize(
        ("texto", "plantados"),
        [(caso[1], caso[2]) for caso in MANIFESTACOES],
        ids=[caso[0] for caso in MANIFESTACOES],
    )
    def test_nenhum_dado_pessoal_sobrevive(self, texto, plantados):
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
        ("texto", "ancora"),
        [(caso[1], caso[3]) for caso in MANIFESTACOES],
        ids=[caso[0] for caso in MANIFESTACOES],
    )
    def test_o_assunto_da_manifestacao_sobrevive(self, texto, ancora):
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

    def test_fixo_sem_ddd_e_sem_separador_tambem_some(self):
        """Oito dígitos corridos ainda são um telefone inteiro."""
        from app.services.ouvidoria_pseudonimizacao import pseudonimizar

        assert pseudonimizar("Deixou o fixo 34567890 para retorno.") == "Deixou o fixo [TELEFONE] para retorno."

    def test_cpf_com_digito_a_mais_por_erro_de_digitacao_nao_escapa(self):
        """Dígito sobrando não pode virar porta de saída: a sequência longa
        carrega o CPF inteiro dentro dela."""
        from app.services.ouvidoria_pseudonimizacao import pseudonimizar

        saida = pseudonimizar("Anotou 52998224725123 no formulário.")

        assert "52998224725" not in saida

    def test_marcador_nao_vira_isca_para_o_proximo_marcador(self):
        from app.services.ouvidoria_pseudonimizacao import pseudonimizar

        assert pseudonimizar("[NOME] [CPF] [TELEFONE] [EMAIL] [PROTOCOLO]") == (
            "[NOME] [CPF] [TELEFONE] [EMAIL] [PROTOCOLO]"
        )


# Os quatro vazamentos de NOME que a #342 deixou abertos e a #412 fechou. Esta
# classe nasceu como `TestLimitesConhecidosDoNome`, e cada teste aqui é o par
# reescrito de um teste que ANTES assertava o nome sobrevivendo. O docstring de
# cada um guarda o vazamento antigo, porque quem mexer na regra de nome precisa
# saber qual furo o caso fecha.
class TestNomePelaListaDeNomes:
    """A camada de lista (issue #412) não olha caixa nem pista: ela cruza as
    palavras do texto com a base de nomes próprios brasileiros do repositório.
    Duas palavras de nome seguidas (com conectivo no meio, se houver) viram um
    marcador só."""

    def test_minusculas_sem_pista_nao_vazam_mais_o_nome(self):
        """ANTES: vazava sempre, 20 de 20 casos.

        Canal do QR do cartaz (ADR 0036): a pessoa digita no celular sem
        maiúscula nenhuma e se apresenta com "sou o", que não é pista
        conhecida. Não havia evidência nenhuma para agarrar; agora as três
        palavras estão na base de nomes."""
        from app.services.ouvidoria_pseudonimizacao import pseudonimizar

        saida = pseudonimizar("meu cpf e 529.982.247-25, sou o joao carlos pereira, tel 21987654321")

        assert saida == "meu cpf e [CPF], sou o [NOME], tel [TELEFONE]"

    def test_conectivo_no_meio_nao_salva_mais_o_sobrenome(self):
        """ANTES: "meu nome e [NOME] ferreira".

        A pista come um número fixo de palavras e o conectivo ("da", "de",
        "dos") gastava uma delas. A camada de lista não tem teto: ela anda pelo
        grupo inteiro, e conectivo entre dois nomes não parte nada."""
        from app.services.ouvidoria_pseudonimizacao import pseudonimizar

        assert pseudonimizar("meu nome e maria da conceicao ferreira") == "meu nome e [NOME]"

    def test_marcador_dos_outros_dados_nao_desliga_mais_a_guarda_de_caixa_alta(self):
        """ANTES: "MARCIA GOMES" sobrevivia quando havia muito dado pessoal.

        `_predominantemente_em_caixa_alta` rodava DEPOIS das substituições, e
        os marcadores que elas deixam ([CPF], [TELEFONE]) são maiúsculos: cada
        um empurrava a contagem para cima até o desenho se desligar. Agora a
        guarda lê o texto ORIGINAL, e a camada de lista pega o nome mesmo se o
        desenho se desligar."""
        from app.services.ouvidoria_pseudonimizacao import pseudonimizar

        sem_numeros = pseudonimizar("MARCIA GOMES reclamou do atendimento")
        com_numeros = pseudonimizar(
            "MARCIA GOMES cpf 529.982.247-25 tel 21987654321 e 21999998888 "
            "email marcia@ex.com protocolos 2026-0007 e 2026-0008"
        )

        assert sem_numeros == "[NOME] reclamou do atendimento"
        # A mesma pessoa, cercada de dado pessoal, some do mesmo jeito.
        assert "MARCIA" not in com_numeros
        assert "GOMES" not in com_numeros
        assert com_numeros.startswith("[NOME] cpf [CPF]")

    def test_sobrenome_com_cara_de_verbo_nao_escapa_mais(self):
        """ANTES: "Clemente" passava por verbo e escapava pela pista E pelo
        desenho.

        A heurística de terminação ("ou", "eu", "ava", "ando", "mente") existe
        para a pista não comer o verbo da frase ("Sra. Rita confirmou") e não
        sabe distinguir verbo de sobrenome. A base de nomes sabe: quem está
        nela é nome, terminação nenhuma desfaz isso."""
        from app.services.ouvidoria_pseudonimizacao import pseudonimizar

        assert pseudonimizar("meu nome e joao clemente") == "meu nome e [NOME]"
        assert pseudonimizar("Reclamou de Joao Clemente no balcao") == "Reclamou de [NOME] no balcao"

    def test_verbo_que_nao_e_nome_continua_de_fora_da_base(self):
        """O contrapeso do teste acima: a base ganha da terminação, então ela
        não pode conter verbo. Se um dia entrar, este teste cai."""
        from app.services.ouvidoria_pseudonimizacao import pseudonimizar

        assert pseudonimizar("Reclamou Confirmou Informou no balcao") == "Reclamou Confirmou Informou no balcao"

    def test_um_nome_sozinho_nao_vira_marcador(self):
        """A base exige DUAS palavras de nome seguidas. Primeiro nome solto
        continua atrás de pista, senão "a Rosa do quarto 12" perderia a flor
        junto com a pessoa."""
        from app.services.ouvidoria_pseudonimizacao import pseudonimizar

        assert pseudonimizar("levou uma rosa para o leito") == "levou uma rosa para o leito"

    def test_nome_fora_da_base_cercado_de_marcador_ainda_some_pelo_desenho(self):
        """A guarda de caixa alta lê o texto ORIGINAL.

        Nome estrangeiro não está na base brasileira, então quem precisa pegá-lo
        é o desenho (Title Case). Antes da #412, os marcadores maiúsculos que as
        outras regras deixavam ([CPF], [TELEFONE], [EMAIL], [PROTOCOLO])
        empurravam a contagem de maiúsculas até o texto parecer todo em caixa
        alta, e o desenho se desligava justamente no relato mais recheado de
        dado pessoal."""
        from app.services.ouvidoria_pseudonimizacao import pseudonimizar

        saida = pseudonimizar(
            "WOJCIECH NOWAK cpf 529.982.247-25 e 111.444.777-35 email a@b.com e c@d.com "
            "prot 2026-0007 2026-0008 2026-0009"
        )

        assert saida == "[NOME] cpf [CPF] e [CPF] email [EMAIL] e [EMAIL] prot [PROTOCOLO] [PROTOCOLO] [PROTOCOLO]"

    def test_uma_palavra_fora_da_base_ja_separa_duas_pessoas(self):
        """O muro da base é de UMA palavra, não de duas como no desenho.

        O desenho tolera uma palavra do vocabulário no meio do nome porque para
        ele "Marco" é palavra da casa; para a base, "Marco" é nome e o grupo se
        forma sozinho. Com a tolerância do desenho aqui, o marcador engoliria a
        palavra que separa as duas pessoas."""
        from app.services.ouvidoria_pseudonimizacao import pseudonimizar

        saida = pseudonimizar("carlos eduardo nunes acompanhante de rita cassia nunes")

        assert saida == "[NOME] acompanhante de [NOME]"

    def test_palavra_da_casa_ganha_da_base_de_nomes(self):
        """ "Socorro" e "Matheus" são prenomes brasileiros E são o nome da casa.
        O vocabulário da casa ganha, senão "Pronto Socorro" e "Hospital São
        Matheus" virariam marcador."""
        from app.services.ouvidoria_pseudonimizacao import pseudonimizar

        texto = "Reclamação sobre o Pronto Socorro do Hospital São Matheus."

        assert pseudonimizar(texto) == texto


class TestBaseNaoAtrapalhaAsOutrasCamadas:
    """A base entrou como camada NOVA, então ela não pode piorar nada que o
    desenho e a pista já resolviam. A review do PR #423 pegou os três jeitos de
    piorar, e cada um virou teste aqui."""

    @pytest.mark.parametrize(
        ("texto", "esperado"),
        [
            ("a paciente Maria Silva Kowalski esteve aqui", "a paciente [NOME] esteve aqui"),
            ("o medico Andre Luiz Schmidt nao apareceu", "o medico [NOME] nao apareceu"),
            ("Sra. Maria Silva Nakagawa esteve aqui", "Sra. [NOME] esteve aqui"),
            ("meu nome e maria silva nakagawa", "meu nome e [NOME]"),
        ],
    )
    def test_sobrenome_fora_da_base_colado_num_nome_da_base_nao_sobra(self, texto, esperado):
        """Nome brasileiro com sobrenome estrangeiro é o caso comum aqui.

        A base é a ÚLTIMA camada por causa disto: se ela rodasse primeiro, o
        marcador que ela deixa cortaria a frase no meio, o desenho e a pista
        não conseguiriam atravessar o `[`, e o sobrenome que elas apagavam
        sozinhas ficaria órfão no texto. Rodando por último, ela só acrescenta:
        o que sobra de um marcador vizinho é absorvido por ele."""
        from app.services.ouvidoria_pseudonimizacao import pseudonimizar

        assert pseudonimizar(texto) == esperado

    @pytest.mark.parametrize(
        "texto",
        [
            "esperei dias e dias por uma resposta",
            "vitoria e gloria para a equipe",
        ],
    )
    def test_e_nao_faz_ponte_entre_duas_palavras_comuns(self, texto):
        """ "Dias", "Vitoria", "Gloria", "Santa", "Porto" e "Santos" são nomes
        de gente E são palavra de todo dia. Com o "e" valendo como conectivo, a
        base atravessava de uma à outra e comia a frase entre elas. O "e" vale
        para o desenho, onde a caixa já garante que os dois lados são nome; na
        base, não vale."""
        from app.services.ouvidoria_pseudonimizacao import pseudonimizar

        assert pseudonimizar(texto) == texto

    @pytest.mark.parametrize(
        ("texto", "esperado"),
        [
            ("a paciente maria do socorro silva reclamou", "a paciente [NOME] reclamou"),
            ("a paciente maria socorro reclamou", "a paciente [NOME] reclamou"),
            ("meu nome e matheus silva pereira", "meu nome e [NOME]"),
            ("matheus ferreira nao apareceu", "[NOME] nao apareceu"),
        ],
    )
    def test_palavra_que_e_nome_e_casa_vale_como_nome_na_base(self, texto, esperado):
        """ "Socorro", "Matheus" e "Domingo" são prenomes brasileiros E são
        palavra da casa. Na base eles valem como NOME. Tirá-los de lá era o que
        fazia "Maria do Socorro Silva" e "Matheus Ferreira", formas comuns
        demais no Brasil, vazarem inteiras."""
        from app.services.ouvidoria_pseudonimizacao import pseudonimizar

        assert pseudonimizar(texto) == esperado

    @pytest.mark.parametrize(
        ("texto", "esperado"),
        [
            ("meu nome e socorro kowalski", "meu nome e [NOME]"),
            ("Sra. Matheus Nakagawa reclamou", "Sra. [NOME] reclamou"),
            ("meu nome e domingo schmidt", "meu nome e [NOME]"),
        ],
    )
    def test_a_pista_nao_trava_num_nome_que_tambem_e_palavra_da_casa(self, texto, esperado):
        """Prenome da casa seguido de sobrenome FORA da base é o caso que só a
        pista resolve: a base vê um nome e um desconhecido, e um nome sozinho
        nunca vira marcador. A pista parava logo no prenome, porque ele é
        palavra da casa, e o nome inteiro ficava no texto mesmo com "meu nome
        é" na frente."""
        from app.services.ouvidoria_pseudonimizacao import pseudonimizar

        assert pseudonimizar(texto) == esperado

    @pytest.mark.parametrize(
        "texto",
        [
            "Reclamação sobre o Pronto Socorro do Hospital São Matheus.",
            "fui atendida no pronto socorro no domingo",
            "a consulta de domingo foi remarcada",
            "o pronto socorro do sao matheus estava cheio",
            "o socorro do hospital nao atendeu no domingo",
        ],
    )
    def test_o_nome_da_casa_sobrevive_sem_precisar_de_excecao(self, texto):
        """O contrapeso do teste acima: quem protege a casa não é uma exceção
        na base, é a parede comum. "Pronto" e "São" não são nome, e uma palavra
        fora da base já parte o grupo."""
        from app.services.ouvidoria_pseudonimizacao import pseudonimizar

        assert pseudonimizar(texto) == texto


class TestLimiteDaBaseDuasPalavrasAmbiguasColadas:
    """LIMITE ACEITO, com o dano escrito.

    "Santa", "Vitoria", "Porto", "Santos" e "Dias" são nome de gente E palavra
    de todo dia. Quando duas delas ficam coladas, a base não tem como saber
    qual das duas leituras é a certa, e ela resolve a dúvida para o mesmo lado
    que o resto do módulo: apagar. Perder "porto de santos" custa contexto;
    deixar "Porto Santos" custa dado pessoal, e o critério da issue #342 manda
    perder o contexto.

    Estes casos ficam aqui asserindo o apagamento porque ele é a escolha, não
    um acidente. Se um dia a decisão virar, é este teste que muda."""

    @pytest.mark.parametrize(
        ("texto", "esperado"),
        [
            ("a santa vitoria da nossa equipe", "a [NOME] da nossa equipe"),
            ("fui ao porto de santos", "fui ao [NOME]"),
        ],
    )
    def test_duas_palavras_ambiguas_coladas_viram_marcador(self, texto, esperado):
        from app.services.ouvidoria_pseudonimizacao import pseudonimizar

        assert pseudonimizar(texto) == esperado


class TestSobreApagamentoDaBaseDeNomes:
    """Medição do custo da camada nova: frases de ouvidoria SEM nenhum nome de
    pessoa precisam atravessar intactas. Se a base começar a comer contexto, é
    aqui que aparece primeiro."""

    @pytest.mark.parametrize(
        "texto",
        [
            "Esperei quatro horas na fila do Pronto Socorro sem nenhuma informação.",
            "A recepção não sabia informar o horário da consulta remarcada.",
            "O convênio negou o exame e ninguém explicou o motivo.",
            "Fui mal atendida no balcão da Central de Marcação de Consultas.",
            "O elevador do bloco B ficou parado a tarde inteira.",
            "Solicito revisão da conta hospitalar cobrada em duplicidade.",
            "A comida da internação chegou fria em três dias seguidos.",
            "O quarto 312 ficou sem limpeza durante todo o fim de semana.",
            "Reclamo da demora na entrega do laudo da tomografia.",
            "Ninguém atendeu o telefone da ouvidoria a semana inteira.",
            "A equipe da enfermagem trocou o horário da medicação sem avisar.",
            "Elogio o atendimento rápido e educado da triagem noturna.",
        ],
    )
    def test_relato_sem_nome_de_pessoa_atravessa_intacto(self, texto):
        from app.services.ouvidoria_pseudonimizacao import pseudonimizar

        assert pseudonimizar(texto) == texto


class TestBaseDeNomes:
    def test_a_base_esta_no_pacote_e_foi_carregada(self):
        """A base é um arquivo de dados dentro de `app/`, então ela viaja na
        imagem do Docker junto com o código (`COPY app/ app/`).

        Se alguém mover o arquivo, a leitura no import levanta
        `FileNotFoundError` e o backend não sobe: falha barulhenta, que é a
        certa. Este teste guarda o outro lado, o silencioso: base presente mas
        vazia ou truncada, que não quebra nada e desliga a camada inteira sem
        ninguém perceber. Não troque a leitura por um `try/except` que devolva
        conjunto vazio: seria exatamente essa falha silenciosa."""
        from app.services.ouvidoria_pseudonimizacao import _NOMES_PROPRIOS

        assert len(_NOMES_PROPRIOS) > 2_000
        for nome in ("maria", "joao", "silva", "clemente", "gomes", "ferreira"):
            assert nome in _NOMES_PROPRIOS

    def test_as_tres_palavras_que_sao_nome_e_casa_ao_mesmo_tempo(self):
        """ "Socorro", "Matheus" e "Domingo" estão nas duas listas, e a base
        NÃO as remove: o que protege "Pronto Socorro" é a parede comum, porque
        "Pronto" não é nome. Se a colisão crescer (vocabulário novo, corte de
        frequência menor), este teste avisa para reavaliar a parede em vez de
        alguém descobrir pelo relato apagado."""
        from app.services.ouvidoria_pseudonimizacao import _NEUTRAS, _NOMES_PROPRIOS

        assert _NOMES_PROPRIOS & _NEUTRAS == {"socorro", "matheus", "domingo"}

    def test_a_base_esta_normalizada(self):
        """Sem acento e em minúsculas: a comparação normaliza a palavra do
        texto do mesmo jeito, e uma linha com acento nunca casaria."""
        from app.services.ouvidoria_pseudonimizacao import _NOMES_PROPRIOS, _sem_acento

        for nome in _NOMES_PROPRIOS:
            assert nome == _sem_acento(nome.lower())


class TestOsSeisIdentificadoresNoMesmoRelato:
    """A ordem das regras é contrato (issue #398), e ela só se prova junta.

    Cada identificador tem seu teste isolado acima. Este aqui existe porque os
    desenhos se sobrepõem: o telefone morde a cabeça do CNS, do RG e da placa;
    a arroba do handle é a mesma do email; a barra do Protocolo é a mesma da
    data. Um relato com todos eles é onde a fila inteira precisa aguentar."""

    RELATO = (
        "Meu nome e Joana Maria Pereira, nasci em 12/08/1975. "
        "CPF 529.982.247-25, RG 12.345.678-9, cartao do SUS 7005 0831 6586 452. "
        "Moro no CEP 20040-020 e meu telefone e (21) 98765-4321. "
        "Email joana.pereira@gmail.com, perfil @maria.silva88. "
        "A ambulancia ABC-1234 chegou atrasada e abri o protocolo 2026/0007. "
        "Estive no Pronto Socorro em 12/08/2026 e esperei quatro horas."
    )

    def test_todo_identificador_vira_o_seu_proprio_marcador(self):
        from app.services.ouvidoria_pseudonimizacao import pseudonimizar

        saida = pseudonimizar(self.RELATO)

        for marcador in (
            "[NOME]",
            "[DATA_NASCIMENTO]",
            "[CPF]",
            "[RG]",
            "[CNS]",
            "[CEP]",
            "[TELEFONE]",
            "[EMAIL]",
            "[REDE_SOCIAL]",
            "[PLACA]",
            "[PROTOCOLO]",
        ):
            assert marcador in saida, f"{marcador} nao saiu no relato completo"

    def test_nenhum_pedaco_de_identificador_sobra_no_texto(self):
        """Nada de sair pela metade: nem o dado inteiro, nem um naco dele."""
        from app.services.ouvidoria_pseudonimizacao import pseudonimizar

        saida = pseudonimizar(self.RELATO)

        for pedaco in (
            "Joana",
            "Pereira",
            "1975",
            "529.982.247-25",
            "12.345.678-9",
            "7005",
            "6586",
            "452",
            "20040-020",
            "98765-4321",
            "gmail.com",
            "maria.silva88",
            "ABC-1234",
            "2026/0007",
        ):
            assert pedaco not in saida, f"{pedaco} atravessou"

    def test_a_ancora_do_relato_sobrevive(self):
        """Apagar tudo não é pseudonimizar: a área e o dia do fato ficam, senão
        a sugestão de ação corretiva não tem o que corrigir."""
        from app.services.ouvidoria_pseudonimizacao import pseudonimizar

        saida = pseudonimizar(self.RELATO)

        assert "Pronto Socorro" in saida
        assert "12/08/2026" in saida
