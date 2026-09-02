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
            # As três formas que travaram de verdade na issue #398. Elas não
            # são inventadas: cada uma foi medida em segundos antes do fix.
            "12-08-2026-" * 10_000,
            "1." * 20_000,
            "529.982.247-25 " * 20_000,
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
            "datas com hífen coladas",
            "dígito e ponto alternados",
            "CPF repetido",
        ],
    )
    def test_texto_longo_nao_trava_a_rotina(self, entrada):
        """A fatia I5 concatena relato, despachos e respostas do Dossiê: o
        texto passa fácil do teto de 10 mil do formulário. Sem teto no local
        part do email, 50 mil caracteres sem arroba levavam 7 segundos; sem
        teto no tamanho da palavra, 20 mil maiúsculas seguidas levavam 3,7.

        Os quatro casos do meio são a camada da base (issue #412): ela varre
        sequências de palavra separadas por espaço, e é onde um quantificador
        aninhado poderia virar backtracking caro. Medido: nenhum passa de
        0,15s.

        Os três últimos são da issue #398, e nenhuma review os pegou: só a
        medição. A exigência de letra antes da arroba, escrita DENTRO do
        desenho do email, varria o mesmo trecho de novo a cada posição, e
        "12-08-2026-" repetido dez mil vezes levava 17,8 segundos. A checagem
        virou uma pergunta em `_mascarar_email`, feita uma vez sobre o que já
        casou, e o mesmo texto passou a levar 0,04s."""
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
            # As grafias que o revisor do PR achou vazando (issue #398).
            ("Data de nascimento - 12/08/1975.", "Data de nascimento - [DATA_NASCIMENTO]."),
            ("Data de nascimento (12/08/1975).", "Data de nascimento ([DATA_NASCIMENTO])."),
            ("Nasc. 12/08/1975.", "Nasc. [DATA_NASCIMENTO]."),
            ("O paciente nasceu em 12/08/1975.", "O paciente nasceu em [DATA_NASCIMENTO]."),
            ("Nascimento em 12/08/1975.", "Nascimento em [DATA_NASCIMENTO]."),
            ("DN: 1975-08-12.", "DN: [DATA_NASCIMENTO]."),
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

    @pytest.mark.parametrize(
        "escrito",
        [
            "@maria.silva88",
            "@joao_silva",
            "@Ana",
            "@a",
            # Handle comprido: a primeira versão tinha teto de trinta e o que
            # passasse dele vazava INTEIRO, em vez de sair cortado.
            "@maria_da_silva_pereira_oficial_2026",
        ],
    )
    def test_handle_vira_marcador(self, escrito):
        from app.services.ouvidoria_pseudonimizacao import pseudonimizar

        saida = pseudonimizar(f"Ja reclamei no perfil {escrito} e ninguem respondeu.")

        assert saida == "Ja reclamei no perfil [REDE_SOCIAL] e ninguem respondeu."

    def test_handle_no_fim_da_frase_nao_come_o_ponto(self):
        """O ponto faz parte do handle no meio ("maria.silva88") e não faz no
        fim. Comendo o ponto final, o marcador cola duas frases numa só e o
        texto que a IA lê muda de sentido."""
        from app.services.ouvidoria_pseudonimizacao import pseudonimizar

        saida = pseudonimizar("Perfil @maria.silva88. A ambulancia chegou.")

        assert saida == "Perfil [REDE_SOCIAL]. A ambulancia chegou."

    def test_email_continua_saindo_como_email(self):
        """Não sobre-apagamento: o handle não pode roubar o email, que tem
        rótulo próprio desde a #342 e também carrega uma arroba."""
        from app.services.ouvidoria_pseudonimizacao import pseudonimizar

        saida = pseudonimizar("Meu email e joana.pereira@gmail.com para retorno.")

        assert saida == "Meu email e [EMAIL] para retorno."

    def test_endereco_interno_sem_ponto_no_dominio_sai_como_email(self):
        """O endereço da intranet ("maria@intranet") não tem ponto no domínio,
        e por isso atravessava inteiro: a regra de email exigia o ponto e a do
        handle recusava a arroba colada em palavra. É identificador direto
        saindo do hospital. Agora ele sai como `[EMAIL]`, inteiro: nem vaza,
        nem sai pela metade."""
        from app.services.ouvidoria_pseudonimizacao import pseudonimizar

        saida = pseudonimizar("Mandei para maria@intranet e ninguem respondeu.")

        assert saida == "Mandei para [EMAIL] e ninguem respondeu."


class TestPlaca:
    """Placa de veículo, nos dois desenhos que circulam hoje (issue #398): o
    antigo `ABC-1234` e o Mercosul `ABC1D23`."""

    @pytest.mark.parametrize("escrito", ["ABC-1234", "ABC1234", "ABC1D23"])
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

    @pytest.mark.parametrize(
        "escrito",
        [
            "12.345.678-9",
            "12.345.678-X",
            "12345678-9",
            # Sem o dígito verificador: é assim que a maioria escreve o RG.
            "12.345.678",
            # Sete dígitos, que é o tamanho do RG em vários estados.
            "1234567-8",
        ],
    )
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

    def test_rg_com_letra_colada_no_verificador_nao_deixa_o_numero_no_texto(self):
        """Grafia esquisita não pode devolver o documento inteiro ao texto. O
        que pode sobrar é o verificador, que sozinho não identifica ninguém."""
        from app.services.ouvidoria_pseudonimizacao import pseudonimizar

        saida = pseudonimizar("Apresentei o RG 12.345.678-9X na recepcao.")

        assert "12.345.678" not in saida
        assert "[RG]" in saida

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
            # Agrupamento torto, de quem copiou do cartão sem contar os grupos.
            # Estas são as que ainda saíam pela metade quando a regra exigia o
            # agrupamento certo, e meia metade é o defeito que esta fatia veio
            # fechar: quinze dígitos são quinze dígitos, agrupados como forem.
            "7005 0831 6586452",
            "700508316586 452",
            "7005 083165864 52",
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

    @pytest.mark.parametrize(
        "escrito",
        [
            "7005  0831 6586 452",  # espaço duplo, de quem colou do PDF
            "7005/0831/6586/452",  # barra, de quem copiou do cartão
        ],
    )
    def test_cartao_do_sus_com_separador_torto_tambem_vira_marcador(self, escrito):
        from app.services.ouvidoria_pseudonimizacao import pseudonimizar

        saida = pseudonimizar(f"Meu cartao do SUS {escrito} nao foi localizado.")

        assert saida == "Meu cartao do SUS [CNS] nao foi localizado."

    @pytest.mark.parametrize(
        "escrito",
        [
            "cns 7005 0831 6586 452 3 vezes",
            "cns 7005 0831 6586 452 33 vezes",
        ],
    )
    def test_numero_vizinho_nao_devolve_a_metade_do_cns_ao_texto(self, escrito):
        """O caso que matou a primeira versão desta regra. Um dígito solto ao
        lado empurra o bloco para dezesseis, e a contagem exata deixava o bloco
        inteiro passar: o telefone então mordia a cabeça e devolvia a cauda ao
        texto. Bloco numérico grande demais some inteiro, custe o contexto que
        custar."""
        from app.services.ouvidoria_pseudonimizacao import pseudonimizar

        saida = pseudonimizar(escrito)

        for pedaco in ("7005", "0831", "6586", "452"):
            assert pedaco not in saida, f"{pedaco} sobreviveu em {saida!r}"

    def test_dois_telefones_colados_saem_os_dois_e_nao_viram_cns(self):
        """A fronteira entre dois números, e ela ficou barata.

        Dois telefones separados só por espaço são um bloco de vinte e dois
        dígitos. Ele passa da conta do cartão, mas nenhum trecho dele soma
        quinze, então a varredura do bloco grande não age e cada telefone sai
        pela regra que é dele. Antes os dois viravam um marcador só, e a
        contagem de quantos números eram se perdia."""
        from app.services.ouvidoria_pseudonimizacao import pseudonimizar

        saida = pseudonimizar("Deixei dois numeros: 21987654321 21987654322.")

        assert saida == "Deixei dois numeros: [TELEFONE] [TELEFONE]."


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


class TestAchadosDaSegundaReview:
    """As oito grafias que a segunda review independente achou (issue #398).

    Todas reproduzidas antes de qualquer mudança. A primeira delas é a mais
    séria: era regressão contra a `main`, criada pela correção da PRIMEIRA
    review. A regra que apagava todo bloco numérico maior que quinze dígitos
    engolia DUAS DATAS DE ATENDIMENTO seguidas, que é justamente o contexto
    que a decisão de não apagar data existe para proteger."""

    @pytest.mark.parametrize(
        "texto",
        [
            "A cirurgia de 12.08.2026 foi remarcada para 13.08.2026 sem aviso.",
            "As datas 12-08-2026 13-09-2026 estavam erradas no papel.",
            "Estive la em 12/08/2026 13/09/2026 e nao fui atendida.",
        ],
    )
    def test_duas_datas_de_atendimento_seguidas_atravessam_intactas(self, texto):
        """O dia do fato some se ele vier ao lado de outro dia do fato? Não.
        Esta é a garantia que a decisão de domínio da issue #398 comprou."""
        from app.services.ouvidoria_pseudonimizacao import pseudonimizar

        assert pseudonimizar(texto) == texto

    @pytest.mark.parametrize(
        "escrito",
        [
            "7005 0831, 6586 452",  # vírgula de quem separa em grupos
            "7005\n0831 6586 452",  # quebra de linha do PDF colado
            "7005 0831 6586/452",  # barra misturada com espaço
        ],
    )
    def test_cns_com_separador_misturado_nao_sai_pela_metade(self, escrito):
        from app.services.ouvidoria_pseudonimizacao import pseudonimizar

        saida = pseudonimizar(f"cartao {escrito} fim")

        for pedaco in ("7005", "0831", "6586", "452"):
            assert pedaco not in saida, f"{pedaco} sobreviveu em {saida!r}"

    def test_telefone_colado_em_outro_numero_sai_inteiro_com_o_ddd(self):
        """O DDD entre parênteses sobrava enquanto a varredura do bloco grande
        agia por tamanho: ela engolia a cauda e deixava "(21)" para trás.
        Agindo só quando cabe um CNS dentro do bloco, ela sai do caminho e cada
        telefone é tratado pela regra dele, com DDD e tudo."""
        from app.services.ouvidoria_pseudonimizacao import pseudonimizar

        saida = pseudonimizar("tel (21) 98765-4321 12345678 fim")

        assert saida == "tel [TELEFONE] [TELEFONE] fim"

    @pytest.mark.parametrize("escrito", ["20.040-020", "20040.020", "20040-020"])
    def test_cep_nas_tres_grafias_vira_marcador(self, escrito):
        """O ponto entre os dois primeiros grupos é tipografia normal de CEP no
        Brasil, e nessa grafia ele atravessava inteiro, nem como `[TELEFONE]`."""
        from app.services.ouvidoria_pseudonimizacao import pseudonimizar

        saida = pseudonimizar(f"Moro no CEP {escrito} e ninguem me ligou.")

        assert saida == "Moro no CEP [CEP] e ninguem me ligou."

    def test_dois_protocolos_separados_por_barra_saem_como_protocolo(self):
        from app.services.ouvidoria_pseudonimizacao import pseudonimizar

        saida = pseudonimizar("Abri os protocolos 2026-0007/2026-0008 e nada.")

        assert saida == "Abri os protocolos [PROTOCOLO]/[PROTOCOLO] e nada."

    def test_handle_com_hifen_nao_deixa_a_cauda_no_texto(self):
        """`[REDE_SOCIAL]-silva` é meia identificação, que este módulo trata
        como pior que nenhuma."""
        from app.services.ouvidoria_pseudonimizacao import pseudonimizar

        saida = pseudonimizar("Reclamei no perfil @maria-silva e nada.")

        assert saida == "Reclamei no perfil [REDE_SOCIAL] e nada."

    def test_rg_nao_come_o_comeco_de_um_numero_mais_longo(self):
        """`[RG].901` some com parte de um valor e ainda deixa um caco."""
        from app.services.ouvidoria_pseudonimizacao import pseudonimizar

        texto = "Cobraram o valor de 12.345.678.901 reais no boleto."

        assert pseudonimizar(texto) == texto

    @pytest.mark.parametrize("escrito", ["D.N. 12/08/1975", "Nascto 12/08/1975"])
    def test_pistas_de_nascimento_de_formulario_tambem_contam(self, escrito):
        """A regra da data é toda governada por pista, então pista que falta é
        a única forma de ela vazar. `D.N.` é tão comum num formulário quanto
        `DN`."""
        from app.services.ouvidoria_pseudonimizacao import pseudonimizar

        saida = pseudonimizar(f"{escrito}, moradora do centro.")

        assert "1975" not in saida
        assert "[DATA_NASCIMENTO]" in saida


class TestAchadosDaTerceiraReview:
    """A terceira review achou o remendo da segunda (issue #398).

    A exceção "fila de datas não vira marcador por tamanho" cobria só o caminho
    de quem tinha MAIS de quinze dígitos, e só quando as datas vinham separadas
    por espaço ou vírgula. Fora desses dois recortes, o dia do fato voltava a
    sumir. A correção não é mais uma exceção: as datas saem do caminho ANTES de
    qualquer regra numérica e voltam no fim."""

    @pytest.mark.parametrize(
        "texto",
        [
            # Quinze dígitos exatos: caía no ramo do CNS, que não olhava a exceção.
            "Estive la em 1/08/2026 13/09/2026 e nao fui atendida.",
            "Fui em 12/8/2026 13/09/2026 e nada.",
            # Lista vertical, que é como se escreve um relato de verdade.
            "Datas em que estive no Pronto Socorro:\n12/08/2026\n13/09/2026\n14/10/2026",
            # Intervalo com hífen: separador que a exceção não previa.
            "Periodo de 12/08/2026-13/09/2026 sem atendimento.",
            "Entre 12.08.2026, 13.09.2026 e 14.10.2026 ninguem ligou.",
        ],
    )
    def test_qualquer_fila_de_datas_atravessa_intacta(self, texto):
        from app.services.ouvidoria_pseudonimizacao import pseudonimizar

        assert pseudonimizar(texto) == texto

    @pytest.mark.parametrize(
        "escrito",
        [
            "7005 - 0831 - 6586 - 452",  # separador de tres caracteres
            "7005   0831 6586 452",  # tres espacos do PDF colado
            "7005 . 0831 . 6586 . 452",
        ],
    )
    def test_cns_com_separador_largo_nao_escapa_nem_sai_pela_metade(self, escrito):
        """O teto de dois caracteres no separador deixava o cartão inteiro
        atravessar, ou pior, sair pela metade. Quinze dígitos são quinze
        dígitos, agrupados como forem e espaçados como forem."""
        from app.services.ouvidoria_pseudonimizacao import pseudonimizar

        saida = pseudonimizar(f"cartao {escrito} fim")

        for pedaco in ("7005", "0831", "6586", "452"):
            assert pedaco not in saida, f"{pedaco} sobreviveu em {saida!r}"

    def test_numero_com_arroba_no_meio_nao_vira_email(self):
        """Aceitar domínio sem ponto abriu a porta para `20@30` virar email. O
        domínio precisa ter pelo menos uma letra para ser um domínio."""
        from app.services.ouvidoria_pseudonimizacao import pseudonimizar

        texto = "O valor foi 20@30 reais."

        assert pseudonimizar(texto) == texto

    def test_mes_abreviado_colado_no_ano_nao_vira_placa(self):
        """`Nov2024` tem o desenho de três letras e quatro dígitos, mas não é
        placa. A placa exige caixa alta ou o hífen, e é assim que ela para de
        comer abreviação de mês."""
        from app.services.ouvidoria_pseudonimizacao import pseudonimizar

        texto = "Fui atendido no Nov2024 pela equipe."

        assert pseudonimizar(texto) == texto

    def test_valor_em_reais_nao_vira_cep(self):
        """`R$ 12.345 678` tem cinco mais três dígitos, e o espaço no separador
        do CEP transformava dinheiro em endereço."""
        from app.services.ouvidoria_pseudonimizacao import pseudonimizar

        texto = "Cobraram R$ 12.345 678 sem explicar."

        assert pseudonimizar(texto) == texto


class TestAchadosDaQuartaReview:
    """O esconderijo de datas abriu uma classe de vazamento (issue #398).

    `_DATA` era frouxo demais para servir de peneira: a cabeça de um telefone
    pontuado tem o desenho de uma data ("55.21.9876" dentro de
    "+55.21.98765432"), então ela era arrancada do texto, escapava de TODAS as
    regras numéricas e voltava intacta no fim. O que peneira o texto inteiro
    precisa ser estreito."""

    @pytest.mark.parametrize(
        "texto",
        [
            "+55.21.98765432",
            "contato 55.21.98765-4321",
            "liguem 21.9.9999-8888",
            "cns 70.05.0831 6586452",
        ],
    )
    def test_numero_com_cara_de_data_na_cabeca_nao_escapa_pelo_esconderijo(self, texto):
        """O critério é "nenhum naco de quatro dígitos ou mais", e não um
        pedaço escolhido a dedo: com o pedaço, o teste passava vazio, porque
        uma peneira frouxa arranca um naco diferente e deixa outro para trás.

        Quatro é o corte porque abaixo dele o que sobra é DDD ou prefixo, que
        é região e não pessoa. É o mesmo limite que a fila de números vizinhos
        já tem escrito nos limites conhecidos."""
        from app.services.ouvidoria_pseudonimizacao import pseudonimizar

        saida = pseudonimizar(texto)

        nacos = re.findall(r"\d{4,}", saida)
        assert not nacos, f"{nacos} atravessaram em {saida!r}"

    @pytest.mark.parametrize(
        "texto, esperado",
        [
            # Data de verdade sai do caminho.
            ("de 12/08/2026 a 13/09/2026", ["12/08/2026", "13/09/2026"]),
            ("DN 1975-08-12 e alta 2026-01-05", ["1975-08-12", "2026-01-05"]),
            ("em 12.08.26 nada", ["12.08.26"]),
            # Desenho de data com campo impossível NÃO é data, e não pode ser
            # arrancado: o que sai daqui escapa de todas as regras numéricas e
            # volta ao texto intacto no fim.
            # Cada linha erra UM campo só, senão o teste não diz qual guarda
            # o pegou: com dois campos errados, tirar uma das duas validações
            # continua verde e o mutante passeia.
            ("ramal 45.12.2026 ocupado", []),  # só o dia é impossível
            ("nota 12.34.2026 emitida", []),  # só o mês é impossível
            ("ref 31.12.9999 vencida", []),  # só o ano é impossível
            ("cod 9.12.08.2026 usado", []),  # data atrás de dígito e ponto
            ("tel +55.21.98765432 agora", []),  # cauda de dígitos colada
        ],
    )
    def test_o_esconderijo_so_arranca_data_de_verdade(self, texto, esperado):
        """A peneira, direto, e não a fiação.

        Ela é o único ponto do módulo que RETIRA texto do caminho de todas as
        regras, então um desenho frouxo aqui não erra o rótulo: vaza. Testar
        pela saída de `pseudonimizar` não prova nada, porque um número que
        escapa pela peneira sai igual a um número que nenhuma regra reconhece,
        e o teste passa vazio nos dois casos."""
        from app.services.ouvidoria_pseudonimizacao import _guardar_datas

        limpo, guardadas = _guardar_datas(texto)

        assert guardadas == esperado
        assert limpo.count("\x00") == len(esperado)

    @pytest.mark.parametrize(
        "texto",
        [
            "O caso aconteceu em nov-2024 e ninguem resolveu.",
            "Refere-se a jan-2026, mes passado.",
        ],
    )
    def test_mes_abreviado_com_hifen_nao_vira_placa(self, texto):
        """A placa exige CAIXA ALTA. Sem isso ela comia o mês do fato, que é o
        contexto de que a sugestão de ação corretiva vive.

        Este teste nasceu vácuo e a mutação provou: ele era um `or` com
        `"[PLACA]" in saida` no fim, e para os casos em caixa alta essa era a
        ÚNICA parte que podia passar. Ou seja, ele afirmava o contrário do
        próprio nome, e tirar a guarda de caixa alta o deixava verde."""
        from app.services.ouvidoria_pseudonimizacao import pseudonimizar

        assert "[PLACA]" not in pseudonimizar(texto)

    @pytest.mark.parametrize("texto", ["O paciente da UTI-2024 nao foi atendido.", "Abri o SAC-2024 e nada."])
    def test_sigla_da_casa_em_caixa_alta_ainda_vira_placa(self, texto):
        """O preço que ficou, escrito como teste em vez de como nota de rodapé:
        três maiúsculas coladas em quatro dígitos são o desenho da placa, e a
        sigla da casa cabe nele. Está nos limites conhecidos."""
        from app.services.ouvidoria_pseudonimizacao import pseudonimizar

        assert "[PLACA]" in pseudonimizar(texto)

    def test_texto_com_caractere_nulo_nao_derruba_a_funcao(self):
        """`pseudonimizar` é documentada como total: entra texto qualquer, sai
        texto. O lugar guardado da data é o NUL, e um NUL vindo de fora
        desalinhava a reposição e estourava `StopIteration`."""
        from app.services.ouvidoria_pseudonimizacao import pseudonimizar

        saida = pseudonimizar("relato\x00 em 12/08/2026 no Pronto Socorro")

        # O texto inteiro, e não só "a data está em algum lugar": um NUL de
        # fora empurra cada data uma posição adiante, e o assert frouxo passava
        # com a data reposta no meio da palavra errada.
        assert saida == "relato em 12/08/2026 no Pronto Socorro"

    def test_reposicao_com_mais_lugares_que_datas_nao_estoura(self):
        """A função interna, direto, e não a fiação: com a limpeza do NUL de
        pé, `pseudonimizar` nunca chega aqui com sobra, então só a chamada
        direta prova o cinto de segurança."""
        from app.services.ouvidoria_pseudonimizacao import _LUGAR_DA_DATA, _repor_datas

        assert _repor_datas(f"a{_LUGAR_DA_DATA}b{_LUGAR_DA_DATA}c", ["12/08/2026"]) == "a12/08/2026bc"

    @pytest.mark.parametrize(
        "texto",
        [
            "Cheguei@8h e ninguem atendeu.",
            "10@20reais cobrados",
        ],
    )
    def test_arroba_entre_numeros_nao_vira_email(self, texto):
        """Aceitar domínio sem ponto foi o que fechou "maria@intranet", e abriu
        a porta para hora e valor virarem email. O endereço precisa de letra
        antes da arroba, e de um domínio que seja ou pontuado ou todo de
        letras."""
        from app.services.ouvidoria_pseudonimizacao import pseudonimizar

        assert "[EMAIL]" not in pseudonimizar(texto)


class TestAchadosDaQuintaReview:
    """A exigência de letra antes da arroba abriu um vazamento (issue #398).

    Ela entrou para barrar "20@30" e "100,00@farmacia", e passou a valer para
    TODO endereço: um email cujo local part é só número ("1234567@uol.com.br")
    atravessava inteiro. Guarda desenhada para o caso raro não pode julgar o
    caso comum."""

    @pytest.mark.parametrize(
        "escrito",
        [
            "1234567@uol.com.br",
            "123@vivo.com.br",
            "998877665@hotmail.com",
        ],
    )
    def test_email_com_local_part_so_de_numero_vira_marcador(self, escrito):
        from app.services.ouvidoria_pseudonimizacao import pseudonimizar

        saida = pseudonimizar(f"Meu email e {escrito} para retorno.")

        assert saida == "Meu email e [EMAIL] para retorno."

    @pytest.mark.parametrize("escrito", ["maria@hsm2026", "maria@intra-net", "contato@rede_local"])
    def test_dominio_interno_sai_inteiro_e_nao_deixa_naco(self, escrito):
        """`[EMAIL]2026` é meia identificação e ainda deixa um naco de quatro
        dígitos, que é exatamente o que a quarta review mandou não deixar."""
        from app.services.ouvidoria_pseudonimizacao import pseudonimizar

        saida = pseudonimizar(f"Mandei para {escrito} e nada.")

        assert saida == "Mandei para [EMAIL] e nada."

    @pytest.mark.parametrize(
        "texto",
        [
            "O valor foi 20@30 reais.",
            "Cheguei@8h e ninguem atendeu.",
        ],
    )
    def test_o_que_a_guarda_veio_barrar_continua_barrado(self, texto):
        """Controle: sem isto, devolver o email ao caso comum passaria verde
        mesmo derrubando a guarda inteira."""
        from app.services.ouvidoria_pseudonimizacao import pseudonimizar

        assert "[EMAIL]" not in pseudonimizar(texto)


class TestAchadosDaSextaReview:
    """Sete grafias, dois vazamentos e dois exageros (issue #398)."""

    @pytest.mark.parametrize(
        "escrito",
        ["Nasci no dia 12/08/1975", "Nascido no dia 12/08/1975", "nasceu no dia 12/08/1975", "Nasci aos 12/08/1975"],
    )
    def test_pista_de_nascimento_com_conector_comum(self, escrito):
        """A regra é toda governada por pista, então conector que falta é a
        única forma de a data vazar. "no dia" é pelo menos tão comum quanto
        "em" num relato escrito."""
        from app.services.ouvidoria_pseudonimizacao import pseudonimizar

        assert "1975" not in pseudonimizar(f"{escrito}, moradora do centro.")

    @pytest.mark.parametrize("escrito", ["MG-12.345.678", "SP-12.345.678-9"])
    def test_rg_com_prefixo_de_estado_vira_marcador(self, escrito):
        """`MG-12.345.678` é a forma corrente do documento em Minas. A guarda
        que impede o RG de casar no meio de um número maior recusava o hífen
        mesmo quando ele vem depois de LETRA, e o documento inteiro passava."""
        from app.services.ouvidoria_pseudonimizacao import pseudonimizar

        saida = pseudonimizar(f"Apresentei o RG {escrito} na recepcao.")

        assert "12.345.678" not in saida
        assert "[RG]" in saida

    @pytest.mark.parametrize("texto", ["Sou do exercicio 2025/2026.", "Gestao 1999/2000 do convenio."])
    def test_intervalo_de_anos_nao_vira_protocolo(self, texto):
        """Aceitar a barra no Protocolo fez `2025/2026` virar número de
        atendimento. Exercício e gestão são escritos assim o tempo todo, e
        perder isso é perder o período de que a análise fala."""
        from app.services.ouvidoria_pseudonimizacao import pseudonimizar

        assert pseudonimizar(texto) == texto

    @pytest.mark.parametrize("texto", ["Cheguei @8h e ninguem atendeu.", "Foram 3 unidades @2,50 cobradas."])
    def test_arroba_seguida_de_numero_nao_vira_perfil(self, texto):
        """Perfil não começa com dígito. Com espaço antes da arroba, a guarda
        de borda não protegia, e hora e preço unitário viravam rede social."""
        from app.services.ouvidoria_pseudonimizacao import pseudonimizar

        assert "[REDE_SOCIAL]" not in pseudonimizar(texto)

    def test_matricula_em_dominio_interno_sai_como_email(self):
        """O buraco entre a quarta review e a quinta: local part só de número
        (fechado quando o domínio tem ponto) com domínio sem ponto (aberto para
        a intranet). Login de matrícula caía exatamente no meio."""
        from app.services.ouvidoria_pseudonimizacao import pseudonimizar

        saida = pseudonimizar("Meu login 12345@intranet nao funciona.")

        assert saida == "Meu login [EMAIL] nao funciona."

    @pytest.mark.parametrize(
        "texto",
        [
            "Leitos 12, 14, 15, 18, 20, 22, 24, 26 do bloco B.",
            "Recebi as guias 1234, 5678, 9012, 3456 no balcao.",
        ],
    )
    def test_lista_longa_de_numeros_nao_vira_um_marcador_so(self, texto):
        """A varredura do bloco maior que quinze dígitos existe para o cartão
        com um vizinho colado, não para uma enumeração. Um número escrito por
        gente tem poucos grupos; uma lista tem muitos, e é isso que separa os
        dois sem reabrir o buraco do CNS pela metade."""
        from app.services.ouvidoria_pseudonimizacao import pseudonimizar

        assert pseudonimizar(texto) == texto


class TestAchadosDoFuzzDiferencial:
    """O que o fuzz diferencial da issue #441 achou, e a leitura não.

    Cada caso aqui saiu de uma entrada gerada, foi reproduzido ANTES da
    correção e está na grafia em que o gerador o produziu.
    """

    @pytest.mark.parametrize(
        "escrito",
        [
            "nascimento no dia - 21/07/1992",
            "nasci em (04/06/2002",
            "nasci em: 24-7-1979",
            "nasceu em: 01.02.1956",
            "nascido em - 12.4.1965",
            "Data de nascimento - em 17/03/1960",
        ],
    )
    def test_separador_entre_o_conector_e_a_data_de_nascimento(self, escrito):
        """A pista aceitava separador antes do conector, mas não DEPOIS dele:
        "nasci em: 24-7-1979" e "nascimento no dia - 21/07/1992" atravessavam
        inteiros. Foi o achado mais numeroso do fuzz, 71 de 4 mil entradas."""
        from app.services.ouvidoria_pseudonimizacao import pseudonimizar

        saida = pseudonimizar(f"{escrito}, moradora do centro.")

        assert "[DATA_NASCIMENTO]" in saida
        assert not re.search(r"\d{4}", saida)

    @pytest.mark.parametrize("escrito", ["2026/1916", "2026-2001", "2025-1999"])
    def test_protocolo_com_sequencial_que_parece_ano_vira_marcador(self, escrito):
        """A guarda que salvou "exercicio 2025/2026" recusava QUALQUER
        sequencial de quatro dígitos começando em 19 ou 20, então o Protocolo
        real "2026/1916" atravessava inteiro. Quem separa os dois é a
        distância: intervalo anda para a frente, e anda pouco."""
        from app.services.ouvidoria_pseudonimizacao import pseudonimizar

        saida = pseudonimizar(f"O atendimento {escrito} nao teve retorno.")

        assert saida == "O atendimento [PROTOCOLO] nao teve retorno."

    @pytest.mark.parametrize(
        "texto", ["Sou do exercicio 2025/2026.", "Gestao 1999/2000 do convenio.", "Contrato 2026/2026 renovado."]
    )
    def test_intervalo_de_anos_continua_atravessando(self, texto):
        """O outro lado da mesma guarda: exercício e gestão continuam inteiros,
        e é isso que a correção não pode reabrir."""
        from app.services.ouvidoria_pseudonimizacao import pseudonimizar

        assert pseudonimizar(texto) == texto

    @pytest.mark.parametrize("escrito", ["445-3494-2018-2675", "700 5083 2019 4523", "123.4567.2026.4523"])
    def test_protocolo_nao_morde_o_meio_do_cartao_do_sus(self, escrito):
        """Um cartão do SUS cujo miolo tem cara de ano saía pela metade:
        "445-3494-[PROTOCOLO]" devolvia sete dígitos do cartão ao texto. É o
        mesmo defeito que o telefone tinha, e a cura é a mesma: contar os
        quinze dígitos ANTES de qualquer desenho menor mordê-los."""
        from app.services.ouvidoria_pseudonimizacao import pseudonimizar

        saida = pseudonimizar(f"O cartao do SUS {escrito} foi apresentado na recepcao.")

        assert saida == "O cartao do SUS [CNS] foi apresentado na recepcao."

    @pytest.mark.parametrize(
        "escrito",
        ["529.982.247 - 25", "529 982 247  25", "529.982.247\t25", "529.982.247 -25"],
    )
    def test_cpf_com_separador_de_mais_de_um_caractere(self, escrito):
        """O desenho do CPF aceitava UM caractere de separador, e quem digita
        no balcão põe espaço antes do hífen. É a mesma raiz que o CNS já tinha
        curado no separador dele, e o fuzz mostrou que o CPF continuava com
        ela."""
        from app.services.ouvidoria_pseudonimizacao import pseudonimizar

        saida = pseudonimizar(f"Segue o CPF {escrito} para contato.")

        assert saida == "Segue o CPF [CPF] para contato."

    @pytest.mark.parametrize("escrito", ["529982.247-25", "5299.822.47-25", "111444777-35"])
    def test_cpf_com_pontuacao_fora_do_lugar_mas_verificador_valido(self, escrito):
        """Ponto no lugar errado tirava o CPF de todos os desenhos: onze
        dígitos com separador que não seja 3.3.3-2 não são telefone corrido
        nem CPF pontuado, e o documento atravessava inteiro. Quem prova o
        documento aqui não é a pontuação, é o dígito verificador."""
        from app.services.ouvidoria_pseudonimizacao import pseudonimizar

        saida = pseudonimizar(f"Segue o CPF {escrito} para contato.")

        assert saida == "Segue o CPF [CPF] para contato."

    @pytest.mark.parametrize(
        "texto, esperado",
        [
            ("Anotei o CPF 111444.777-35 2 vezes.", "Anotei o CPF [CPF] 2 vezes."),
            ("Liguei 3 529982.247-25 vezes.", "Liguei 3 [CPF] vezes."),
        ],
    )
    def test_cpf_torto_com_numero_vizinho_colado(self, texto, esperado):
        """O vizinho empurra a conta para doze dígitos e o documento voltava
        inteiro ao texto, o mesmo defeito que o CNS teve com o cartão. A cura é
        a mesma: procurar o TRECHO de onze dígitos dentro do bloco, dos dois
        lados, porque o vizinho tanto vem depois quanto vem antes."""
        from app.services.ouvidoria_pseudonimizacao import pseudonimizar

        assert pseudonimizar(texto) == esperado

    def test_a_rede_do_cpf_nao_morde_o_meio_do_cartao_do_sus(self):
        """A regressão que o próprio fuzz pegou, na rodada seguinte ao conserto
        do CPF torto: dentro de "22480 03924 46707 2" existe um trecho de onze
        dígitos que fecha o verificador por acaso, e a rede do CPF, rodando
        antes da contagem do cartão, partia o CNS ao meio e devolvia "22480" ao
        texto. Rede larga vai DEPOIS de desenho específico, sempre."""
        from app.services.ouvidoria_pseudonimizacao import pseudonimizar

        saida = pseudonimizar("Cartao nacional de saude: 22480 03924 46707 2 vezes.")

        assert saida == "Cartao nacional de saude: [TELEFONE] vezes."

    @pytest.mark.parametrize(
        "escrito",
        ["21  99843  3002", "21 - 99843 - 3002", "(21)  99843  3002", "99843  3002"],
    )
    def test_telefone_com_separador_de_mais_de_um_caractere(self, escrito):
        """Texto colado de PDF chega com espaço duplo entre os grupos, e o
        telefone exigia separador de um caractere só: o número inteiro
        atravessava. Foi o segundo achado mais numeroso do fuzz."""
        from app.services.ouvidoria_pseudonimizacao import pseudonimizar

        saida = pseudonimizar(f"Meu contato {escrito} para retorno.")

        assert saida == "Meu contato [TELEFONE] para retorno."

    @pytest.mark.parametrize("escrito", ["(21) 9 8765-4321", "21 9 8765 4321", "+55 21 9 8765-4321"])
    def test_celular_com_o_nono_digito_destacado(self, escrito):
        """O nono dígito escrito à parte é grafia corrente de formulário. O
        desenho não a previa, e o que sobrava no texto era o corpo do número
        pela metade."""
        from app.services.ouvidoria_pseudonimizacao import pseudonimizar

        saida = pseudonimizar(f"Meu contato {escrito} para retorno.")

        assert saida == "Meu contato [TELEFONE] para retorno."

    @pytest.mark.parametrize(
        "texto",
        [
            "Esperei 98765\n\n4321 pessoas na fila.",
            "Aguardei 21\n\n98765\n\n4321 minutos.",
        ],
    )
    def test_numero_de_paragrafos_diferentes_nao_vira_um_telefone_so(self, texto):
        """O separador que ficou repetível não pode atravessar parágrafo: dois
        números de linhas diferentes não são um telefone. É a mesma regra que o
        separador do CNS já seguia, e sem ela o preço aparece justamente no
        relato colado em blocos, que é o formato em que ele chega."""
        from app.services.ouvidoria_pseudonimizacao import pseudonimizar

        assert pseudonimizar(texto) == texto

    def test_enumeracao_de_digitos_soltos_nao_vira_cpf(self):
        """Os onze dígitos desta lista são os de um CPF válido, na ordem, e a
        rede acharia o trecho e fecharia o verificador. Documento não é escrito
        em onze pedaços: quatro grupos são o teto do desenho ("123 456 789
        09"), e é isso que separa o documento de uma enumeração de leitos.

        A guarda também é o que segura o custo: sem ela, um relato de 250 mil
        caracteres de números soltos faz a conta do verificador rodar uma vez
        por posição."""
        from app.services.ouvidoria_pseudonimizacao import pseudonimizar

        texto = "Os leitos 5, 2, 9, 9, 8, 2, 2, 4, 7, 2, 5 estavam vazios."

        assert pseudonimizar(texto) == texto

    def test_onze_digitos_iguais_nao_sao_documento(self):
        """Onze dígitos iguais FECHAM o módulo 11, e é por isso que a conta os
        recusa à parte. A recusa foi movida para o fim da função quando a rede
        do CPF passou a chamá-la dezenas de milhares de vezes por relato, e o
        veredito tem que ser o mesmo: "11111.111111" não é documento de
        ninguém.

        O outro lado deste caso é um limite conhecido: nessa grafia quem prova
        o documento é o verificador, então CPF digitado errado atravessa."""
        from app.services.ouvidoria_pseudonimizacao import pseudonimizar

        texto = "Digitaram 11111.111111 no cadastro."

        assert pseudonimizar(texto) == texto

    def test_cpf_invalido_com_separador_duplo_ainda_sai_pelo_desenho(self):
        """O desenho 3.3.3-2 não confere verificador, e é por isso que ele
        existe ao lado da rede: CPF digitado errado continua sendo o documento
        de alguém. Com o separador de um caractere só, esta grafia caía entre
        as duas defesas e atravessava inteira."""
        from app.services.ouvidoria_pseudonimizacao import pseudonimizar

        saida = pseudonimizar("Anotaram meu CPF 123.456.789 - 00 errado.")

        assert saida == "Anotaram meu CPF [CPF] errado."

    def test_protocolo_com_sequencial_gigante_nao_derruba_a_rotina(self):
        """A conta que separa Protocolo de intervalo de anos só roda sobre
        sequencial de QUATRO dígitos, e isso não é enfeite: `int()` de uma
        string com mais de 4.300 dígitos levanta erro no Python, e a função é
        documentada como total. Um relato com um número absurdo colado derruba
        a chamada da IA inteira, não só a linha dele.

        O sequencial começa em "20" de propósito: é o que faz a conta ser
        tentada, e é ali que ela estoura sem o teto."""
        from app.services.ouvidoria_pseudonimizacao import pseudonimizar

        saida = pseudonimizar("O atendimento 2026-20" + "1" * 5_000 + " nao teve retorno.")

        assert saida == "O atendimento [PROTOCOLO] nao teve retorno."


TETO_DE_SEGUNDOS_POR_DESENHO = 0.2
CARACTERES_DA_MEDICAO = 250_000
REPETICOES_DA_MEDICAO = 3


def _repetir_ate(pedaco: str, tamanho: int = CARACTERES_DA_MEDICAO) -> str:
    return (pedaco * (tamanho // len(pedaco) + 1))[:tamanho]


def _melhor_tempo(trabalho) -> float:
    """O melhor de três, e não uma tomada só.

    O runner do CI é máquina compartilhada: uma execução isolada mede o
    escalonador tanto quanto mede o código, e um gate que reprova por isso
    ensina o time a ignorar o gate. O menor de três é a medida mais honesta da
    capacidade real, e continua reprovando código lento, que é lento nas
    três."""
    tempos = []
    for _ in range(REPETICOES_DA_MEDICAO):
        comeco = time.monotonic()
        trabalho()
        tempos.append(time.monotonic() - comeco)
    return min(tempos)


class TestTempoDosDesenhosDaIssue441:
    """Regex novo entra medido (issue #441, critério de aceite).

    O pior defeito do PR da #398 não foi achado por review nenhuma, e sim pela
    medição: uma checagem escrita dentro do regex do email levava 17,8 segundos
    num relato de datas repetidas. Aqui cada desenho que a #441 mexeu é medido
    SOZINHO, em 250 mil caracteres do texto que mais o faz sofrer, porque o
    tempo da rotina inteira esconde qual das passadas custou.
    """

    @pytest.mark.parametrize(
        "desenho, entrada",
        [
            ("_CPF_SEPARADO", _repetir_ate("123  456  789  09 ")),
            ("_CPF_SEPARADO", _repetir_ate("1 - 2 - 3 - 4 - ")),
            ("_TELEFONE", _repetir_ate("21  99843  3002 ")),
            ("_TELEFONE", _repetir_ate("(21) 9 8765 - 4321 ")),
            ("_TELEFONE", _repetir_ate("12 - 34 . 56  78 ")),
            ("_DATA_DE_NASCIMENTO", _repetir_ate("nasci em - no dia : ")),
            ("_DATA_DE_NASCIMENTO", _repetir_ate("nasc" + ":.-() " * 40)),
            ("_PROTOCOLO", _repetir_ate("2026-2026-2026 ")),
            ("_PROTOCOLO", _repetir_ate("2026/0007 ")),
        ],
        ids=[
            "CPF com separador duplo",
            "CPF com hífen entre espaços",
            "telefone com separador duplo",
            "celular com nono dígito solto",
            "grupos curtos com separador variado",
            "pista de nascimento sem data",
            "pista com pontuação repetida",
            "ano colado em ano",
            "protocolo repetido",
        ],
    )
    def test_desenho_novo_nao_passa_de_dois_decimos_de_segundo(self, desenho, entrada):
        from app.services import ouvidoria_pseudonimizacao as modulo

        padrao = getattr(modulo, desenho)

        gasto = _melhor_tempo(lambda: padrao.sub("", entrada))

        assert gasto < TETO_DE_SEGUNDOS_POR_DESENHO, f"{desenho} levou {gasto:.3f}s"

    @pytest.mark.parametrize(
        "entrada",
        [
            _repetir_ate("111444.777-35 2 "),
            _repetir_ate("7005 0831 6586 452 3 "),
            _repetir_ate("1, 2, 3, 4, 5, 6, 7, 8, "),
        ],
        ids=["CPF torto com vizinho", "cartão com vizinho", "lista de números curtos"],
    )
    def test_a_rede_do_cpf_por_trecho_nao_passa_de_dois_decimos_de_segundo(self, entrada):
        """A rede nova varre grupos de dígitos e testa o verificador em cada
        trecho de onze. É a passada mais cara que a issue acrescentou, e a
        lista de números curtos é o texto que mais grupos produz por
        caractere."""
        from app.services import ouvidoria_pseudonimizacao as modulo

        gasto = _melhor_tempo(lambda: modulo._BLOCO_NUMERICO.sub(modulo._mascarar_cpf_pontuado, entrada))

        assert gasto < TETO_DE_SEGUNDOS_POR_DESENHO, f"a rede do CPF levou {gasto:.3f}s"


class TestFuzzDeterministico:
    """A rede que fica de pé depois da issue #441.

    O fuzz que achou os defeitos rodou fora do CI, contra a `main`, com dezenas
    de milhares de entradas. O que fica versionado é o mesmo gerador, pequeno e
    de SEED FIXA: sem relógio, sem rede, sem sorteio novo a cada execução, e
    rápido o bastante para o gate. Ele não substitui os testes de cima, que
    dizem o que cada grafia deve virar; ele existe para que a próxima grafia
    quebrada apareça como falha, e não como vazamento em produção.
    """

    SEED = 441

    @staticmethod
    def _casos():
        import random

        rng = random.Random(TestFuzzDeterministico.SEED)
        pistas = ["CPF", "cpf numero:", "documento", "Tel", "telefone:", "celular", "cartao do SUS", "CNS"]
        fundos = [
            "Fui atendida na recepcao e ninguem soube informar.",
            "A equipe da enfermaria nao respondeu o chamado do leito.",
            "Peco retorno sobre o agendamento do exame.",
        ]
        vizinhos = ["", " leito 12", " 2 vezes", " no dia 12/08/2026", " sala 3"]
        bordas = [("", "."), ("(", ")."), ('"', '".'), ("", ","), ("[", "]")]
        # O NBSP e os outros espaços Unicode entraram depois da review
        # independente: o corpus só tinha espaço ASCII, e foi por esse buraco
        # que a regressão do separador passou sem ninguém ver.
        #
        # Os invisíveis (issue #460) entraram pela mesma razão, um degrau
        # acima: eles não são espaço para o Python, não aparecem na tela e
        # chegam colados no texto copiado da web.
        espacos = [" ", "  ", "\n", " \t", "\xa0", "\r", "\u2002", "\u3000", "\u200b", "\ufeff", "\u00ad"]

        cpfs = ["12345678909", "52998224725", "11144477735", "39053344705"]
        casos = []
        for numero in cpfs:
            for molde in (
                "{0}{1}{2}{3}",
                "{0}.{1}.{2}-{3}",
                "{0} {1} {2} {3}",
                "{0}.{1}.{2} - {3}",
                "{0}{1}.{2}-{3}",
                "{0}  {1}  {2}  {3}",
                "{0}.{1}.{2}.{3}",
                "{0}/{1}/{2}-{3}",
                "{0}.{1}.{2}\xa0{3}",
                "{0}\xa0{1}\xa0{2}\xa0{3}",
                "{0}\u3000{1}\u3000{2}\u3000{3}",
                # Issue #460: os traços de teclado CJK e os invisíveis. Entram
                # por escape, nunca como caractere literal.
                "{0}\uff0d{1}\uff0d{2}\uff0d{3}",
                "{0}\ufe63{1}\ufe63{2}\ufe63{3}",
                "{0}\u30fc{1}\u30fc{2}\u30fc{3}",
                "{0}\u301c{1}\u301c{2}\u301c{3}",
                "{0}\uff5e{1}\uff5e{2}\uff5e{3}",
                "{0}\u00ad{1}\u00ad{2}\u00ad{3}",
                "{0}.{1}.{2}\u200b{3}",
                "{0}\u200b{1}\u200b{2}\u200b{3}",
            ):
                escrito = molde.format(numero[:3], numero[3:6], numero[6:9], numero[9:])
                casos.append(("cpf", numero, escrito))
        for corpo in ("998433002", "941011974", "34567890"):
            for ddd in ("21", "85"):
                completo = ddd + corpo
                comeco, fim = corpo[:-4], corpo[-4:]
                for escrito in (
                    completo,
                    f"({ddd}) {comeco}-{fim}",
                    f"{ddd} {comeco}-{fim}",
                    f"{ddd}  {comeco}  {fim}",
                    f"+55 {ddd} {comeco}-{fim}",
                    f"{ddd}.{comeco}.{fim}",
                    f"({ddd}){comeco}{fim}",
                    f"{ddd}\xa0{comeco}\xa0{fim}",
                    f"({ddd})\xa0{comeco}-{fim}",
                    f"{ddd}\uff0d{comeco}\uff0d{fim}",
                    f"{ddd}\ufe63{comeco}\ufe63{fim}",
                    f"({ddd})\u200b{comeco}\u30fc{fim}",
                    f"{ddd}\uff5e{comeco}\u00ad{fim}",
                ):
                    casos.append(("telefone", completo, escrito))
                if corpo.startswith("9"):
                    for escrito in (
                        f"({ddd}) {corpo[0]} {corpo[1:5]}-{corpo[5:]}",
                        f"{ddd} {corpo[0]} {corpo[1:5]} {corpo[5:]}",
                    ):
                        casos.append(("telefone", completo, escrito))
        for cartao in ("700508365864523", "224800392446707"):
            for molde in (
                "{0}{1}{2}{3}",
                "{0} {1} {2} {3}",
                "{0}.{1}.{2}.{3}",
                "{0} - {1} - {2} - {3}",
                "{0}\uff0d{1}\uff0d{2}\uff0d{3}",
                "{0}\u200b{1}\u200b{2}\u200b{3}",
            ):
                escrito = molde.format(cartao[:3], cartao[3:7], cartao[7:11], cartao[11:])
                casos.append(("cns", cartao, escrito))
        for data in ("12/08/1975", "1.2.1975", "12-08-1975"):
            for pista in ("nasci em", "data de nascimento -", "nascimento no dia -", "nasc.", "DN:", "nasceu em:"):
                casos.append(("nascimento", "1975", f"{pista} {data}"))

        montados = []
        for tipo, assinatura, escrito in casos:
            abre, fecha = rng.choice(bordas)
            pista = rng.choice(pistas) if tipo != "nascimento" else ""
            miolo = f"{pista} {escrito}".strip()
            texto = (
                f"{rng.choice(fundos)}{rng.choice(espacos)}{abre}{miolo}{rng.choice(vizinhos)}{fecha} "
                f"{rng.choice(fundos)}"
            )
            montados.append((tipo, assinatura, texto))
        return montados

    # O que conta como "um número só" na hora de procurar o vazamento. A
    # primeira versão desta linha era `[ \t.,/-]`, e ela era ASCII: um documento
    # que saísse partido por NBSP ou por traço de teclado CJK virava quatro
    # bloquinhos de três dígitos, nenhum com os cinco que o piso exige, e o fuzz
    # dava verde num vazamento. Ou seja, TODO molde não-ASCII do corpus (os
    # desta issue e os que a #441 acrescentou) era decoração.
    #
    # A classe agora é "qualquer coisa que não seja dígito nem quebra de linha",
    # com o mesmo teto de três caracteres do separador do módulo. Ela é escrita
    # à mão, e não importada de `_TRACOS`: importar acoplaria o detector ao
    # código sob teste, e um mutante que tirasse um traço da peneira tiraria
    # junto a capacidade de o fuzz enxergar o vazamento que ele causou.
    _JUNTA_OS_DIGITOS = re.compile(r"\d+(?:[^\d\n]{1,3}\d+)*")

    def test_nenhum_identificador_gerado_sobrevive(self):
        from app.services.ouvidoria_pseudonimizacao import pseudonimizar

        sobreviventes = []
        for tipo, assinatura, texto in self._casos():
            saida = pseudonimizar(texto)
            blocos = [re.sub(r"\D", "", bloco) for bloco in self._JUNTA_OS_DIGITOS.findall(saida)]
            piso = 4 if tipo == "nascimento" else 5
            for tamanho in range(len(assinatura), piso - 1, -1):
                pedaco = next(
                    (
                        assinatura[i : i + tamanho]
                        for i in range(len(assinatura) - tamanho + 1)
                        if any(assinatura[i : i + tamanho] in bloco for bloco in blocos)
                    ),
                    None,
                )
                if pedaco:
                    sobreviventes.append((tipo, texto, saida, pedaco))
                    break

        assert not sobreviventes, f"{len(sobreviventes)} entradas vazaram: {sobreviventes[:3]}"

    def test_o_gerador_produz_o_mesmo_corpus_toda_vez(self):
        """Seed fixa é o que faz o gate ser gate: um corpus que muda a cada
        execução acha defeito num dia e passa no outro, e ninguém confia."""
        primeiro = self._casos()
        segundo = self._casos()

        assert primeiro == segundo
        assert len(primeiro) > 100


class TestAchadosDaReviewIndependente:
    """O que o fuzzer do revisor achou, e o meu não (issue #441, rodada 1).

    Os dois defeitos saíram de duas grafias que o meu gerador não escrevia: o
    espaço não-ASCII e o segundo identificador no mesmo relato. É a lição da
    própria issue virada contra ela: fuzzer só acha o que o gerador escreve.
    """

    @pytest.mark.parametrize(
        "espaco",
        ["\xa0", "\r", "\x0b", "\x0c", " ", " ", " ", " ", "　"],
        ids=["NBSP", "CR", "VT", "FF", "en space", "figure space", "thin space", "narrow nbsp", "ideographic"],
    )
    def test_cpf_com_espaco_que_nao_e_o_da_barra_de_espaco(self, espaco):
        """REGRESSÃO que este PR tinha introduzido: trocar `\\s` por uma classe
        literal de dois caracteres tirou todo o resto do espaço Unicode do
        separador, e o documento passava inteiro. O NBSP é justamente o que
        Word, PDF e página web colam no lugar do espaço, que é o cenário que
        este módulo diz cobrir."""
        from app.services.ouvidoria_pseudonimizacao import pseudonimizar

        saida = pseudonimizar(f"Segue o CPF 529.982.247{espaco}25 para contato.")

        assert saida == "Segue o CPF [CPF] para contato."

    @pytest.mark.parametrize(
        "espaco",
        ["\xa0", "\r", " ", "　"],
        ids=["NBSP", "CR", "en space", "ideographic"],
    )
    def test_telefone_com_espaco_que_nao_e_o_da_barra_de_espaco(self, espaco):
        """O mesmo buraco no telefone: o número saía inteiro quando o espaço
        entre os grupos era o NBSP do texto colado."""
        from app.services.ouvidoria_pseudonimizacao import pseudonimizar

        saida = pseudonimizar(f"Meu contato 21{espaco}99843{espaco}3002 para retorno.")

        assert saida == "Meu contato [TELEFONE] para retorno."

    def test_espaco_unicode_nao_derruba_a_parede_de_paragrafo(self):
        """A parede continua sendo a linha em branco, e ela não pode cair junto
        com a correção: dois números de parágrafos diferentes não são um
        telefone, nem com espaço Unicode em volta."""
        from app.services.ouvidoria_pseudonimizacao import pseudonimizar

        texto = "Esperei 98765\n\n\xa04321 pessoas na fila."

        assert pseudonimizar(texto) == texto

    @pytest.mark.parametrize(
        "texto, esperado",
        [
            ("CPFs 529982.247-25 111444.777-35 juntos.", "CPFs [CPF] [CPF] juntos."),
            ("Cadastro 111444.777-35 529982.247-25 duplicado.", "Cadastro [CPF] [CPF] duplicado."),
            (
                "Anotaram 529982.247-25, 111444.777-35 e 123456.789-09 na ficha.",
                "Anotaram [CPF], [CPF] e [CPF] na ficha.",
            ),
        ],
    )
    def test_todos_os_cpfs_tortos_do_mesmo_bloco_saem(self, texto, esperado):
        """A rede parava no primeiro acerto e devolvia o resto do bloco ao
        texto. Vírgula e espaço não quebram bloco, então dois documentos lado a
        lado caem no mesmo, e a saída ficava no pior formato possível: um
        `[CPF]` ao lado de um CPF inteiro tem cara de anonimizado e não é."""
        from app.services.ouvidoria_pseudonimizacao import pseudonimizar

        assert pseudonimizar(texto) == esperado

    def test_protocolo_com_sequencial_que_anda_pouco_para_tras(self):
        """A direção da conta não estava travada por teste: os casos existentes
        só usavam retrocesso longo, então trocar `0 <= dist` por `abs(dist)`
        passava verde e o Protocolo real "2026/2020" começaria a atravessar.
        Intervalo anda para a FRENTE."""
        from app.services.ouvidoria_pseudonimizacao import pseudonimizar

        saida = pseudonimizar("O atendimento 2026/2020 nao teve retorno.")

        assert saida == "O atendimento [PROTOCOLO] nao teve retorno."

    def test_protocolo_com_sequencial_muito_a_frente(self):
        """O teto de dez anos também não estava travado: subi-lo para cem
        passava verde, e "2026/2050" perderia a proteção em silêncio. Gestão e
        exercício andam POUCO."""
        from app.services.ouvidoria_pseudonimizacao import pseudonimizar

        saida = pseudonimizar("O atendimento 2026/2050 nao teve retorno.")

        assert saida == "O atendimento [PROTOCOLO] nao teve retorno."

    @pytest.mark.parametrize(
        "escrito",
        ["٥٢٩٩٨٢٢٤٧٢٥", "５２９９８２２４７２５"],
        ids=["arabe-indico", "fullwidth"],
    )
    def test_cpf_em_digito_unicode_ainda_e_cpf(self, escrito):
        """`\\d` casa dígito Unicode, então o número copiado de um teclado
        estrangeiro chega aqui. A conta do verificador precisa CONVERTER o
        dígito, e não subtrair 48 do código do caractere: com a subtração, o
        documento saía como `[TELEFONE]`. Nada vazava, mas rótulo errado no
        prompt é informação errada dada à IA."""
        from app.services.ouvidoria_pseudonimizacao import pseudonimizar

        assert pseudonimizar(f"Segue o CPF {escrito} para contato.") == "Segue o CPF [CPF] para contato."

    @pytest.mark.parametrize(
        "espaco",
        ["\xa0", "\r", " ", "　"],
        ids=["NBSP", "CR", "en space", "ideographic"],
    )
    def test_o_bloco_numerico_atravessa_espaco_que_nao_e_ascii(self, espaco):
        """O separador do BLOCO tinha a mesma doença ASCII do separador curto, e
        ela é anterior a esta issue: com NBSP entre os grupos, o bloco quebrava
        em dois, a contagem do cartão não chegava a quinze e a rede do CPF não
        via os onze dígitos. Os dois identificadores voltavam inteiros ao
        texto.

        O fuzz só achou isto depois que o gerador aprendeu a escrever espaço
        Unicode, o que é a lição da review: ele acha o que o gerador escreve."""
        from app.services.ouvidoria_pseudonimizacao import pseudonimizar

        cpf = pseudonimizar(f"Segue o CPF 529982.247{espaco}25 para contato.")
        cartao = pseudonimizar(f"O cartao 7005{espaco}0831{espaco}6586{espaco}452 do SUS.")

        assert cpf == "Segue o CPF [CPF] para contato."
        assert cartao == "O cartao [CNS] do SUS."

    def test_cpf_invalido_separado_por_barra_sai_pelo_desenho(self):
        """A barra vale no CPF e não vale no telefone, e o comentário dizia
        isso sem nenhum teste segurando. O documento aqui tem o verificador
        ERRADO de propósito: com um válido, a rede o pegaria mesmo sem a barra
        no desenho, e o teste passaria sem provar nada."""
        from app.services.ouvidoria_pseudonimizacao import pseudonimizar

        assert pseudonimizar("Anotaram 123/456/789/00 na ficha.") == "Anotaram [CPF] na ficha."

    def test_dois_documentos_sobrepostos_nao_viram_dois_marcadores(self):
        """Nestes catorze dígitos cabem DOIS trechos de onze que fecham o
        verificador, e eles se sobrepõem: o segundo começa dentro do primeiro.
        A varredura continua depois do trecho casado, e não de onde parou, para
        nenhum marcador cobrir dígito que já entrou em outro; sem essa trava, a
        montagem colava os dois marcadores e comia o texto entre eles.

        São catorze e não quinze de propósito: quinze viraria `[CNS]` antes de
        a rede do CPF ver qualquer coisa."""
        from app.services.ouvidoria_pseudonimizacao import pseudonimizar

        saida = pseudonimizar("O numero 123 4567 8909 061 no cadastro.")

        assert saida == "O numero [CPF] 061 no cadastro."

    @pytest.mark.parametrize(
        "hifen",
        ["\u2010", "\u2011", "\u2012", "\u2013", "\u2014", "\u2015", "\u2212"],
        ids=["hifen", "hifen que nao quebra", "traco de numero", "meia-risca", "travessao", "barra", "menos"],
    )
    def test_identificador_com_hifen_que_nao_e_o_do_teclado(self, hifen):
        """A mesma familia do NBSP, e o mesmo caminho de entrada: o autocorrect
        do Word troca o hifen digitado pelo tipografico, e o PDF cola a
        meia-risca. Com eles no meio do numero, CPF, telefone e cartao saiam
        INTEIROS, e isso vinha de antes desta issue.

        Os caracteres sao escritos por escape de proposito: o repositorio
        proibe travessao e meia-risca no texto, e aqui eles sao DADO de
        entrada, nao texto."""
        from app.services.ouvidoria_pseudonimizacao import pseudonimizar

        cpf = pseudonimizar(f"Segue o CPF 529{hifen}982{hifen}247{hifen}25 hoje.")
        telefone = pseudonimizar(f"Meu contato 21{hifen}99843{hifen}3002 para retorno.")
        cartao = pseudonimizar(f"O cartao 7005{hifen}0831{hifen}6586{hifen}452 do SUS.")

        assert cpf == "Segue o CPF [CPF] hoje."
        assert telefone == "Meu contato [TELEFONE] para retorno."
        assert cartao == "O cartao [CNS] do SUS."

    @pytest.mark.parametrize(
        "texto",
        [
            "Escala 12-36 do plantao.",
            "Sou do exercicio 2025/2026.",
            "Fiquei no leito 12 da enfermaria.",
            "O prazo era de 3 a 5 dias uteis.",
        ],
    )
    def test_o_que_o_hifen_novo_nao_pode_levar_junto(self, texto):
        """O outro lado: alargar o separador nao pode comecar a comer escala de
        plantao nem exercicio, que sao o contexto de que a sugestao de acao
        corretiva precisa."""
        from app.services.ouvidoria_pseudonimizacao import pseudonimizar

        assert pseudonimizar(texto) == texto

    @pytest.mark.parametrize("traco", ["-", "\u2013", "\u2014"], ids=["hifen do teclado", "meia-risca", "travessao"])
    def test_intervalo_de_anos_com_traco_vira_telefone_em_qualquer_traco(self, traco):
        """O preco de alargar o separador, e ele ja existia com o hifen do
        teclado: quatro digitos, traco, quatro digitos e o desenho de um fixo
        com DDD, entao "exercicio 2025-2026" ja virava `[TELEFONE]` na versao
        anterior. O que muda aqui e que a meia-risca passou a valer o mesmo, o
        que e coerencia, nao politica nova: a mesma grafia com o mesmo sentido
        recebe o mesmo tratamento.

        Com BARRA o intervalo continua atravessando, e e por isso que o teste
        do intervalo usa barra."""
        from app.services.ouvidoria_pseudonimizacao import pseudonimizar

        com_traco = pseudonimizar(f"Sou do exercicio 2025{traco}2026.")
        com_barra = pseudonimizar("Sou do exercicio 2025/2026.")

        assert com_traco == "Sou do exercicio [TELEFONE]."
        assert com_barra == "Sou do exercicio 2025/2026."


class TestTracosDeTecladoCJKDaIssue460:
    """A quarta rodada da mesma doença (issue #460).

    A #441 fechou a faixa de traços da pontuação geral mais o sinal de menos, e
    o revisor independente do PR #458 mostrou que três traços continuavam de
    fora: o hífen de largura total, o hífen pequeno e o prolongador katakana.
    São a pontuação de quem digita em teclado CJK, e com eles no meio do número
    o CPF, o telefone e o cartão saíam INTEIROS.

    A cura desta vez não é acrescentar três códigos: a lista vira a CATEGORIA
    do Unicode (traço de pontuação), que é o nome que a própria norma dá a esta
    família. É o que interrompe o ciclo de "cada fuzz com corpus mais largo
    acha mais um", e o teste do fim desta classe é quem segura a promessa.

    Os caracteres são escritos por ESCAPE de propósito: o repositório proíbe
    travessão e meia-risca no texto, e aqui eles são DADO de entrada."""

    @pytest.mark.parametrize(
        "traco",
        [
            "\uff0d",
            "\ufe63",
            "\u30fc",
            "\u058a",
            "\u05be",
            "\u1400",
            "\u1806",
            "\u2e17",
            "\u2e1a",
            "\u2e3a",
            "\u2e3b",
            "\u2e40",
            "\u2e5d",
            "\u301c",
            "\u3030",
            "\u30a0",
            "\ufe31",
            "\ufe32",
            "\ufe58",
            "\U00010ead",
            "\uff5e",
        ],
        ids=[
            "hifen de largura total",
            "hifen pequeno",
            "prolongador katakana",
            "hifen armenio",
            "maqaf hebraico",
            "hifen silabico canadense",
            "hifen todo mongol",
            "hifen obliquo duplo",
            "hifen com trema",
            "traco de dois quadratins",
            "traco de tres quadratins",
            "hifen duplo",
            "hifen obliquo",
            "traco de onda",
            "traco ondulado",
            "hifen duplo katakana",
            "quadratim vertical",
            "meio quadratim vertical",
            "quadratim pequeno",
            "marca de hifenizacao yezidi",
            "til de largura total",
        ],
    )
    def test_identificador_com_traco_fora_da_faixa_da_issue_441(self, traco):
        from app.services.ouvidoria_pseudonimizacao import pseudonimizar

        cpf = pseudonimizar(f"Segue o CPF 529{traco}982{traco}247{traco}25 hoje.")
        telefone = pseudonimizar(f"Meu contato 21{traco}99843{traco}3002 para retorno.")
        cartao = pseudonimizar(f"O cartao 7005{traco}0831{traco}6586{traco}452 do SUS.")

        assert cpf == "Segue o CPF [CPF] hoje."
        assert telefone == "Meu contato [TELEFONE] para retorno."
        assert cartao == "O cartao [CNS] do SUS."

    def test_a_peneira_cobre_a_categoria_inteira_de_traco_do_unicode(self):
        """A trava que fecha o ciclo, e o motivo de a lista ser categoria e não
        catálogo escrito à mão: quando o Python subir de versão do Unicode e a
        norma ganhar um traço novo, é AQUI que ele aparece, com o código e o
        nome na mensagem, e não num vazamento de produção.

        Vermelho aqui quer dizer "acrescente o traço que a mensagem nomeia", e
        NÃO "quebrei alguma coisa". O CI e a produção rodam Python 3.12 (Unicode
        15), mas `requires-python` aceita mais, e em 3.14 (Unicode 16) já entra
        o `U+10D6E` GARAY HYPHEN."""
        import unicodedata

        from app.services.ouvidoria_pseudonimizacao import _TRACOS

        peneira = re.compile(f"[{_TRACOS}]")
        de_fora = [
            f"U+{codigo:04X} {unicodedata.name(chr(codigo))}"
            for codigo in range(0x110000)
            if unicodedata.category(chr(codigo)) == "Pd" and not peneira.fullmatch(chr(codigo))
        ]

        assert not de_fora, f"traços de pontuação fora da peneira: {de_fora}"

    @pytest.mark.parametrize(
        "invisivel",
        [
            "\u00ad",
            "\u200b",
            "\u200c",
            "\u200d",
            "\u200e",
            "\u200f",
            "\u202a",
            "\u202e",
            "\u2060",
            "\u2066",
            "\u2069",
            "\ufeff",
            "\u180e",
            "\u061c",
            "\U000e0020",
        ],
        ids=[
            "hifen suave",
            "espaco de largura zero",
            "nao-juntor de largura zero",
            "juntor de largura zero",
            "marca da esquerda para a direita",
            "marca da direita para a esquerda",
            "embutido da esquerda para a direita",
            "sobreposicao da direita para a esquerda",
            "juntor de palavra",
            "isolado da esquerda para a direita",
            "fim do isolado de direcao",
            "espaco sem quebra de largura zero",
            "separador de vogal mongol",
            "marca de letra arabe",
            "espaco de etiqueta",
        ],
    )
    def test_identificador_partido_por_caractere_invisivel(self, invisivel):
        """A quarta FAMÍLIA que a varredura desta issue achou, e a mais séria
        das quatro: estes não são espaço para o Python (`\\s` não os pega) e
        não aparecem na tela. Word, editor de página web e PDF os colam no meio
        do texto, e um deles entre dois grupos de dígitos deixava o documento
        atravessar INTEIRO, sem que a leitura do relato desse qualquer pista de
        que havia um caractere ali.

        O `U+00AD` abre a lista porque a primeira versão desta issue o deixou de
        fora, e ele é o pior de todos: é o hífen de hifenização que o Word, o
        LibreOffice e a extração de PDF colam no texto, ou seja, exatamente a
        origem que o módulo diz cobrir. Foi ele que trocou o catálogo de cinco
        códigos pela categoria inteira."""
        from app.services.ouvidoria_pseudonimizacao import pseudonimizar

        cpf = pseudonimizar(f"Segue o CPF 529{invisivel}982{invisivel}247{invisivel}25 hoje.")
        telefone = pseudonimizar(f"Meu contato 21{invisivel}99843{invisivel}3002 para retorno.")
        cartao = pseudonimizar(f"O cartao 7005{invisivel}0831{invisivel}6586{invisivel}452 do SUS.")

        assert cpf == "Segue o CPF [CPF] hoje."
        assert telefone == "Meu contato [TELEFONE] para retorno."
        assert cartao == "O cartao [CNS] do SUS."

    def test_a_peneira_cobre_a_categoria_inteira_de_formato_do_unicode(self):
        """O espelho do teste acima, para a família dos invisíveis, e ele existe
        porque a falta dele custou um must-fix: a primeira versão desta issue
        listou cinco códigos à mão e 165 caracteres de formato continuavam
        deixando o documento passar. Vale a mesma leitura do vermelho: "a norma
        ganhou um caractere de formato, acrescente-o", e não "quebrei algo"."""
        import unicodedata

        from app.services.ouvidoria_pseudonimizacao import _INVISIVEIS

        peneira = re.compile(f"[{_INVISIVEIS}]")
        de_fora = [
            f"U+{codigo:04X} {unicodedata.name(chr(codigo), '?')}"
            for codigo in range(0x110000)
            if unicodedata.category(chr(codigo)) == "Cf" and not peneira.fullmatch(chr(codigo))
        ]

        assert not de_fora, f"caracteres de formato fora da peneira: {de_fora}"

    def test_um_caractere_entre_as_duas_quebras_cancela_o_paragrafo(self):
        """LIMITE ACEITO, e o teste está aqui para escrevê-lo, não para fingir
        que a parede é mais alta do que é.

        A primeira versão deste teste punha o invisível DEPOIS do `\\n\\n`, onde
        a parede nunca esteve em risco: ele passava igual contra a `main`, ou
        seja, não guardava nada (achado da review do PR #531). A posição exposta
        é ENTRE as duas quebras, e ali a parede cede.

        Não é dano novo desta issue: a `main` já cedia para `\\n \\n`, `\\n\\r\\n`,
        `\\n\\t\\n` e para o NBSP, porque a parede é literalmente "duas quebras
        SEGUIDAS" e qualquer coisa no meio já as separa. O invisível entrou no
        mesmo saco, por coerência. O contrato, então, é este: parágrafo novo é
        `\\n\\n` cru, e um caractere no meio o cancela. Se um dia a decisão virar
        (a parede passar a tolerar espaço entre as quebras), é este teste que
        muda, e ele muda para os cinco casos de uma vez."""
        from app.services.ouvidoria_pseudonimizacao import pseudonimizar

        assert pseudonimizar("Esperei 98765\n\n4321 pessoas na fila.") == "Esperei 98765\n\n4321 pessoas na fila."

        for miolo in (" ", "\r", "\t", "\xa0", "\u200b"):
            texto = f"Esperei 98765\n{miolo}\n4321 pessoas na fila."
            assert pseudonimizar(texto) == "Esperei [TELEFONE] pessoas na fila.", repr(miolo)

    def test_invisivel_depois_da_linha_em_branco_nao_atravessa_o_paragrafo(self):
        """O outro lado do limite acima, e a parte que a parede REALMENTE
        guarda: com as duas quebras coladas, o invisível do lado de fora não
        junta os dois parágrafos."""
        from app.services.ouvidoria_pseudonimizacao import pseudonimizar

        texto = "Esperei 98765\n\n\u200b4321 pessoas na fila."

        assert pseudonimizar(texto) == texto

    @pytest.mark.parametrize(
        "traco",
        ["\uff0d", "\ufe63", "\u30fc", "\u301c", "\uff5e"],
        ids=[
            "hifen de largura total",
            "hifen pequeno",
            "prolongador katakana",
            "traco de onda",
            "til de largura total",
        ],
    )
    def test_o_que_o_traco_novo_nao_pode_levar_junto(self, traco):
        """O outro lado, e é o mesmo contrato que a #441 assinou para o hífen do
        teclado: alargar o separador não pode comer escala de plantão nem leito,
        que são o contexto de que a sugestão de ação corretiva precisa.

        O intervalo de anos NÃO está nesta lista, e não é esquecimento: com
        qualquer traço ele já virava `[TELEFONE]` desde a #441, e a coerência
        entre grafias é a decisão de lá, não uma política nova daqui."""
        from app.services.ouvidoria_pseudonimizacao import pseudonimizar

        assert pseudonimizar(f"Escala 12{traco}36 do plantao.") == f"Escala 12{traco}36 do plantao."
        assert pseudonimizar("Fiquei no leito 12 da enfermaria.") == "Fiquei no leito 12 da enfermaria."
        assert pseudonimizar("O prazo era de 3 a 5 dias uteis.") == "O prazo era de 3 a 5 dias uteis."


class TestFuzzLimpoDaIssue460:
    """A medição de sobre-apagamento, do outro lado do fuzz que caça vazamento.

    O gerador aqui escreve relato de ouvidoria SEM nenhum identificador, com a
    mesma pontuação nova que esta issue acrescentou ao separador. Nenhum deles
    pode mudar ao passar pela pseudonimização.

    LINHA DE BASE: zero entradas alteradas, e é este número que a próxima
    rodada de alargamento tem de manter. Se um traço novo começar a comer
    contexto, é aqui que aparece antes de ir para produção.

    O que ele NÃO faz, e a review do PR #531 tem razão em cobrar a franqueza:
    ele não mede o custo DESTA rodada, porque a `main` também dá zero neste
    corpus. Ele é a rede da PRÓXIMA, e é para isso que a linha de base fica
    escrita aqui em vez de ser recalculada a cada leitura."""

    LINHA_DE_BASE_DE_ALTERADAS = 0

    @staticmethod
    def _casos_limpos():
        pontuacao = [
            "-",
            "\uff0d",
            "\ufe63",
            "\u30fc",
            "\u301c",
            "\uff5e",
            "\u2013",
            " ",
            "\xa0",
            "\u00ad",
            "\u200b",
            "\u202a",
        ]
        moldes = [
            "Escala 12{0}36 do plantao sem cobertura.",
            "Fiquei no leito 12{0}A da enfermaria a tarde toda.",
            "O prazo era de 3{0}5 dias uteis e ninguem cumpriu.",
            "A sala 3{0}B estava fechada quando cheguei.",
            "Esperei 4{0}5 horas na fila da recepcao.",
        ]
        limpos = [molde.format(sinal) for molde in moldes for sinal in pontuacao]
        limpos += [
            "Fui atendida na recepcao e ninguem soube informar.",
            "A equipe da enfermaria nao respondeu o chamado do leito.",
            "Peco retorno sobre o agendamento do exame.",
            "O convenio negou o exame e ninguem explicou o motivo.",
            "A recepcao nao sabia informar o horario da consulta remarcada.",
        ]
        return limpos

    def test_relato_sem_identificador_atravessa_intacto(self):
        from app.services.ouvidoria_pseudonimizacao import pseudonimizar

        alteradas = [texto for texto in self._casos_limpos() if pseudonimizar(texto) != texto]

        assert len(alteradas) == self.LINHA_DE_BASE_DE_ALTERADAS, f"sobre-apagamento novo: {alteradas}"

    def test_o_corpus_limpo_nao_encolheu_ate_virar_nada(self):
        """Uma lista vazia passaria no teste acima sem provar coisa alguma."""
        assert len(self._casos_limpos()) > 40
