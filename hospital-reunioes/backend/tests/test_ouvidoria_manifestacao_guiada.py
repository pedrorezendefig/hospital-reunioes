"""A Manifestação guiada em cinco passos (issue #1620, PRD #1527, ADR 0086).

O formulário público deixa de ser uma tela só e vira os passos M1 a M5 da
seção 4.2 da especificação da Diretoria: identificação, sobre o quê, quando e
onde, o que aconteceu e contato. O que muda no servidor:

- o caso guarda quando e onde foi (data, período, hora aproximada, o local que
  a pessoa escolheu e o quarto), os profissionais citados, a data de
  nascimento do paciente e o que a pessoa espera da Ouvidoria;
- o telefone ganha coluna própria, e o e-mail continua no contato de hoje,
  que é o que o acuse lê;
- quem se identifica deixa nome e ao menos um dos dois.

Os testes sobem a rota real com o mesmo banco falso do formulário público.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.limiter import limiter  # noqa: E402
from app.routers import ouvidoria_publica  # noqa: E402
from test_ouvidoria_formulario_publico import CARTAZ, _BancoFake, _make_app  # noqa: E402

ROTA = "/api/ouvidoria/publico/manifestacoes"


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    limiter._storage.reset()
    yield
    limiter._storage.reset()


def _guiada(**overrides) -> dict:
    """O envio do passo a passo com o mínimo que a especificação exige, de quem
    se identifica e deixa só o e-mail."""
    payload = {
        "anonimo": False,
        "sobre": "mim",
        "data_ocorrencia": "2026-11-10",
        "periodo": "tarde",
        "local_informado": "Emergência adulta",
        "relato": "Esperei duas horas na emergência sem nenhuma informação.",
        "expectativa": "resposta",
        "nome": "Maria Souza",
        "contato": "maria@exemplo.com",
    }
    payload.update(overrides)
    return {chave: valor for chave, valor in payload.items() if valor is not None}


class TestOCasoGuardaQuandoEOnde:
    def test_o_envio_guiado_grava_quando_onde_e_o_que_a_pessoa_espera(self):
        client, banco = _make_app()

        r = client.post(ROTA, json=_guiada(hora_aprox="14:30"))

        assert r.status_code == 201, r.text
        gravado = banco.inserts[0]
        assert gravado["data_ocorrencia"] == "2026-11-10"
        assert gravado["periodo"] == "tarde"
        assert gravado["hora_aprox"] == "14:30:00"
        assert gravado["local_informado"] == "Emergência adulta"
        assert gravado["expectativa"] == "resposta"


class TestObrigatoriosDoAnexo:
    """Seção 4.2 da especificação: o que é obrigatório barra o envio, o que é
    opcional nunca barra. A página de antes, que não conhece nenhum campo do
    passo a passo, continua passando (ver `TestAPaginaDeAntes`)."""

    @pytest.mark.parametrize("faltando", ["sobre", "data_ocorrencia", "periodo", "local_informado", "expectativa"])
    def test_sem_um_obrigatorio_o_envio_guiado_e_recusado(self, faltando):
        client, banco = _make_app()

        r = client.post(ROTA, json={k: v for k, v in _guiada().items() if k != faltando})

        assert r.status_code == 422, faltando
        assert banco.rows == []

    @pytest.mark.parametrize(
        "campo,valor",
        [("periodo", "almoco"), ("expectativa", "indenizacao"), ("local_informado", "   ")],
    )
    def test_obrigatorio_com_valor_fora_da_regra_e_recusado(self, campo, valor):
        client, banco = _make_app()

        r = client.post(ROTA, json=_guiada(**{campo: valor}))

        assert r.status_code == 422
        assert banco.rows == []

    def test_data_da_ocorrencia_no_futuro_e_recusada(self):
        client, banco = _make_app()

        r = client.post(ROTA, json=_guiada(data_ocorrencia="2999-01-01"))

        assert r.status_code == 422
        assert banco.rows == []

    def test_os_opcionais_em_branco_nao_barram_o_envio(self):
        """Hora, quarto, profissionais e o paciente servem para localizar o
        atendimento, e o CONTEXT.md pede para nunca torná-los obrigatórios."""
        client, banco = _make_app()

        r = client.post(
            ROTA,
            json=_guiada(hora_aprox=None, quarto="", profissionais="  ", paciente_nascimento=None, natureza_informada=""),
        )

        assert r.status_code == 201, r.text
        gravado = banco.inserts[0]
        for campo in ("hora_aprox", "quarto", "profissionais", "paciente_nascimento", "natureza_informada"):
            assert gravado[campo] is None, campo

    def test_os_opcionais_preenchidos_chegam_ao_caso(self):
        client, banco = _make_app()

        r = client.post(
            ROTA,
            json=_guiada(
                sobre="outra_pessoa",
                local_informado="Internação · Ala 2A",
                quarto="Apto 204",
                profissionais="Enfermeira do plantão da noite",
                paciente_nome="José Souza",
                paciente_nascimento="1948-03-02",
            ),
        )

        assert r.status_code == 201, r.text
        gravado = banco.inserts[0]
        assert gravado["quarto"] == "Apto 204"
        assert gravado["profissionais"] == "Enfermeira do plantão da noite"
        assert gravado["paciente_nome"] == "José Souza"
        assert gravado["paciente_nascimento"] == "1948-03-02"


class TestContatoDeQuemSeIdentifica:
    """M5: quem se identifica deixa o nome e ao menos um jeito de a Ouvidoria
    falar com ele. Só telefone vale (decisão 8 do diretor no PRD #1527), e a
    tela avisa que as respostas saem por e-mail."""

    def test_identificado_sem_telefone_nem_email_e_recusado(self):
        client, banco = _make_app()

        r = client.post(ROTA, json=_guiada(contato=None))

        assert r.status_code == 422
        assert banco.rows == []

    def test_identificado_sem_nome_e_recusado(self):
        client, banco = _make_app()

        r = client.post(ROTA, json=_guiada(nome=" "))

        assert r.status_code == 422
        assert banco.rows == []

    def test_so_com_telefone_passa_e_o_telefone_tem_coluna_propria(self):
        client, banco = _make_app()

        r = client.post(ROTA, json=_guiada(contato=None, telefone="(21) 99999-0000"))

        assert r.status_code == 201, r.text
        gravado = banco.inserts[0]
        assert gravado["manifestante_telefone"] == "(21) 99999-0000"
        assert gravado["manifestante_contato"] is None
        # Nome e telefone fecham a identificação: nada a completar.
        assert gravado["dados_incompletos"] is False

    def test_o_email_continua_no_contato_que_o_acuse_le(self):
        client, banco = _make_app()

        r = client.post(ROTA, json=_guiada(telefone="21999990000"))

        assert r.status_code == 201, r.text
        gravado = banco.inserts[0]
        assert gravado["manifestante_contato"] == "maria@exemplo.com"
        assert gravado["manifestante_telefone"] == "21999990000"

    @pytest.mark.parametrize("telefone", ["não tenho", "123"])
    def test_telefone_sem_numero_de_telefone_nao_conta_como_contato(self, telefone):
        client, banco = _make_app()

        r = client.post(ROTA, json=_guiada(contato=None, telefone=telefone))

        assert r.status_code == 422
        assert banco.rows == []

    def test_email_que_nao_e_email_e_recusado(self):
        """O e-mail mora no contato que o acuse lê; um telefone digitado ali
        faria o caso parecer ter e-mail e a pessoa não receberia nada."""
        client, banco = _make_app()

        r = client.post(ROTA, json=_guiada(contato="21 99999-0000"))

        assert r.status_code == 422
        assert banco.rows == []

    def test_anonimo_passa_sem_contato_e_descarta_o_telefone_que_venha(self):
        client, banco = _make_app()

        r = client.post(ROTA, json=_guiada(anonimo=True, nome=None, contato=None, telefone="21999990000"))

        assert r.status_code == 201, r.text
        gravado = banco.inserts[0]
        assert gravado["manifestante_nome"] is None
        assert gravado["manifestante_telefone"] is None


def _ponto(codigo: str, ponto: str, nome_publico: str | None, *, ativo: bool = True, ala: bool = False) -> dict:
    return {
        "id": f"ponto-{codigo}",
        "codigo": codigo,
        "setor": "Auditoria",
        "ponto": ponto,
        "ativo": ativo,
        "criado_em": "2026-11-01T12:00:00+00:00",
        "nome_publico": nome_publico,
        "descricao_local": "Hall, parede ao lado da passagem",
        "titulo_cartaz": "atendimento_hoje",
        "codigo_controle": None,
        "ala_internacao": ala,
    }


class TestAListaDeLocais:
    """M3, "Onde": a lista de nomes que o paciente entende, que são os nomes
    públicos dos cartazes ativos (ADR 0086, decisão 10)."""

    def test_lista_os_nomes_publicos_dos_cartazes_ativos_com_a_marca_de_ala(self):
        pontos = [
            _ponto("AAAAA2", "Hall", "Emergência adulta"),
            _ponto("AAAAA3", "Corredor", "Internação · Ala 2A", ala=True),
            # Dois cartazes no mesmo lugar público viram uma opção só.
            _ponto("AAAAA4", "Hall dos fundos", "Emergência adulta"),
            # Cartaz aposentado não é lugar para escolher.
            _ponto("AAAAA5", "Saguão", "Centro Médico", ativo=False),
        ]
        client, _banco = _make_app(_BancoFake(pontos=pontos))

        r = client.get("/api/ouvidoria/publico/locais")

        assert r.status_code == 200
        assert r.json() == {
            "locais": [
                {"nome": "Emergência adulta", "ala_internacao": False},
                {"nome": "Internação · Ala 2A", "ala_internacao": True},
            ]
        }

    def test_nunca_mostra_o_nome_interno_do_setor(self):
        """Sem nome público vale o rótulo do ponto, nunca o setor da taxonomia
        ("Você leu o QR de Auditoria" era o defeito da especificação)."""
        client, _banco = _make_app(_BancoFake(pontos=[_ponto("AAAAA2", "Recepção principal", None)]))

        r = client.get("/api/ouvidoria/publico/locais")

        assert r.json() == {"locais": [{"nome": "Recepção principal", "ala_internacao": False}]}
        assert "Auditoria" not in r.text


class TestOAnonimoNaoGravaOCartaz:
    """ADR 0086, decisão 3: o anônimo que vem de um cartaz guarda o local que
    confirmou, e não o código do cartaz nem o ponto."""

    def test_anonimo_vindo_do_cartaz_guarda_o_local_e_nao_o_codigo(self):
        client, banco = _make_app(_BancoFake(pontos=[dict(CARTAZ)]))

        r = client.post(
            ROTA,
            json=_guiada(anonimo=True, nome=None, contato=None, p="AB2CD3", local_informado="Recepção"),
        )

        assert r.status_code == 201, r.text
        gravado = banco.inserts[0]
        assert gravado["local_informado"] == "Recepção"
        assert gravado["canal_ponto"] is None
        valores = " ".join(str(v) for v in gravado.values())
        assert "AB2CD3" not in valores
        assert "Poltrona 12" not in valores

    def test_identificado_vindo_do_cartaz_continua_guardando_o_ponto(self):
        """O par do teste de cima: sem ele, um cartaz que nunca resolvesse
        passaria pelo anônimo como se a regra existisse."""
        client, banco = _make_app(_BancoFake(pontos=[dict(CARTAZ)]))

        r = client.post(ROTA, json=_guiada(p="AB2CD3", local_informado="Recepção"))

        assert r.status_code == 201, r.text
        assert banco.inserts[0]["canal_ponto"] == "Poltrona 12"


MIGRATION = Path(__file__).parent.parent.parent / "supabase" / "migrations" / "138_ouvidoria_manifestacao_guiada.sql"


def _ddl() -> str:
    return re.sub(r"--[^\n]*", "", MIGRATION.read_text(encoding="utf-8"))


class TestAMigration:
    """O fake do PostgREST não aplica CHECK, então é a leitura do arquivo que
    segura as regras do banco."""

    def test_as_colunas_novas_nascem_no_caso(self):
        ddl = _ddl()
        for coluna in (
            "data_ocorrencia DATE",
            "periodo TEXT",
            "hora_aprox TIME",
            "local_informado TEXT",
            "quarto TEXT",
            "profissionais TEXT",
            "paciente_nascimento DATE",
            "expectativa TEXT",
            "manifestante_telefone TEXT",
        ):
            assert f"ADD COLUMN IF NOT EXISTS {coluna}" in ddl, coluna

    def test_as_listas_fechadas_do_banco_batem_com_as_da_rota(self):
        ddl = _ddl()
        periodos = ", ".join(f"'{p}'" for p in ouvidoria_publica.PERIODOS)
        expectativas = ", ".join(f"'{e}'" for e in ouvidoria_publica.EXPECTATIVAS)

        assert f"periodo IS NULL OR periodo IN ({periodos})" in ddl
        assert f"expectativa IS NULL OR expectativa IN ({expectativas})" in ddl

    def test_nenhuma_tabela_nova_nem_policy(self):
        """Só colunas: a linha do caso continua com a RLS que nega por padrão
        e o backend escreve com a service role."""
        ddl = _ddl().upper()

        assert "CREATE TABLE" not in ddl
        assert "CREATE POLICY" not in ddl


class TestAPaginaDeAntes:
    """Quem abriu o formulário antes do deploy continua com a página velha na
    aba até recarregar, e ela não manda nenhum campo do passo a passo. A rota
    aceita esse envio como aceitava, pelo mesmo motivo que tolera a falta do
    `sobre` (issue #666): recusar fecharia o canal justamente para quem está
    parado na frente do cartaz escrevendo devagar."""

    def test_o_envio_da_pagina_de_antes_continua_registrando(self):
        client, banco = _make_app()

        r = client.post(ROTA, json={"relato": "Esperei duas horas.", "sobre": "mim", "nome": "Maria"})

        assert r.status_code == 201, r.text
        gravado = banco.inserts[0]
        for campo in ("data_ocorrencia", "periodo", "local_informado", "expectativa", "manifestante_telefone"):
            assert gravado[campo] is None, campo
