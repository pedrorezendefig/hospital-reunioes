"""O alerta ao admin técnico não leva o email do manifestante no corpo
(issue #572, levantada na revisão do PR #565).

Na TERCEIRA falha de envio, `despachar` chama `alertar_admin_tecnico`, e o corpo
do alerta vai para todos os super admins do app, que não têm necessariamente
perfil na Ouvidoria. Quando a notificação que falhou é o acuse de recebimento ou
o aviso de encerramento, `Destinatario` é o email pessoal de quem manifestou, e
`Ultimo erro` é a segunda cópia do mesmo dado: a recusa do provedor carrega o
endereço dentro.

Quem decide é a mesma pergunta única da #547
(`ouvidoria_contato.destinatario_e_o_manifestante`), e o marcador é o mesmo que
o log usa (`(endereco omitido)`). O alerta continua acionável sem os dois: o
admin técnico precisa saber que o provedor caiu e qual manifestação travou.

Os testes daqui passam pela TERCEIRA falha de verdade: a linha entra na fila com
`tentativas=2`, o provedor recusa, e é `despachar` quem chama o alerta. O teste
da #547 para nas duas primeiras, e um teste que chamasse `alertar_admin_tecnico`
direto não provaria que a linha chega lá com o `papel_destinatario` que ela
carrega.

Cuidado herdado da revisão: assere-se o MARCADOR de omissão, não a ausência do
email. Um teste que só procura a string do endereço fica verde diante de
upper, split ou quote.
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# O dublê de banco da fatia que criou o acuse, reaproveitado de propósito.
from test_ouvidoria_acuse_recebimento import SABADO_DE_MADRUGADA, _BancoFake, _caso  # noqa: E402

from app.services import ouvidoria_notificacoes  # noqa: E402
from app.services.ouvidoria_contato import PAPEL_MANIFESTANTE  # noqa: E402

# O que o `email_service` escreve no lugar do endereço no log. O alerta usa o
# mesmo, e asserir a PRESENÇA dele é mais forte do que asserir a ausência do
# endereço.
MARCADOR = "(endereco omitido)"

ASSUNTO = "Ouvidoria 2026-0007: assunto do caso"
ADMIN_TECNICO = {
    "id": "P03",
    "nome_completo": "Pedro Admin",
    "email": "pedro@hsm.br",
    "access_profile": "super_admin",
    "ativo": True,
}

EMAIL_DO_MANIFESTANTE = "joana.silva@gmial.com"
EMAIL_DO_SETOR = "carlos@hsm.br"


def _recusa_do_provedor(destinatario: str) -> str:
    """O erro real de destinatário recusado carrega o endereço inteiro."""
    return f"{{'{destinatario}': (550, b'5.1.1 User unknown')}}"


@pytest.fixture
def correio(monkeypatch) -> list[dict]:
    """O provedor recusa a notificação e entrega o alerta ao admin técnico.

    Devolve tudo o que passou por `_enviar_email`, para o teste ler o corpo do
    alerta exatamente como ele sairia."""
    enviados: list[dict] = []

    def _fake(destinatario, assunto, html, texto=None, **_kwargs):
        enviados.append({"destinatario": destinatario, "assunto": assunto, "texto": texto})
        if destinatario == ADMIN_TECNICO["email"]:
            return True
        raise RuntimeError(_recusa_do_provedor(destinatario))

    monkeypatch.setattr(ouvidoria_notificacoes, "_enviar_email", _fake)
    monkeypatch.setattr(ouvidoria_notificacoes, "_montar", lambda *_a, **_kw: (ASSUNTO, "<p>html</p>", "texto"))
    return enviados


def _terceira_falha(banco, *, gatilho, papel, email) -> dict:
    """Põe na fila uma notificação que já falhou duas vezes e a despacha. O
    despacho falha de novo, e essa terceira falha é a que dispara o alerta."""
    linha = {
        "id": f"n-{len(banco.notificacoes) + 1}",
        "manifestacao_id": "uuid-7",
        "gatilho": gatilho,
        "destinatario_nome": "Quem recebe",
        "destinatario_email": email,
        "papel_destinatario": papel,
        "status": ouvidoria_notificacoes.AGENDADA,
        "tentativas": 2,
    }
    banco.notificacoes.append(linha)
    entregue = ouvidoria_notificacoes.despachar(banco, linha, SABADO_DE_MADRUGADA, frozenset())
    assert entregue is False, "Sem falha não há alerta para inspecionar"
    assert linha["status"] == ouvidoria_notificacoes.FALHA, "A terceira falha tinha que esgotar as tentativas"
    return linha


def _alerta_ao_admin(correio: list[dict]) -> str:
    """O corpo do alerta que chegou ao super admin. Falha alto se ele não saiu:
    o teste de omissão não pode passar em cima de um alerta que nem existiu."""
    alertas = [e for e in correio if e["destinatario"] == ADMIN_TECNICO["email"]]
    assert len(alertas) == 1, "O alerta ao admin técnico não saiu (ou saiu mais de uma vez)"
    assert "uuid-7" in alertas[0]["texto"], "O alerta perdeu a manifestação, e sem ela não é acionável"
    return alertas[0]["texto"]


def _nao_aparece(email: str, texto: str) -> None:
    """O endereço não sobrou no corpo, NEM EM PEDAÇOS (parte local, domínio,
    caixa dobrada)."""
    corpo = texto.casefold()
    local, _, dominio = email.partition("@")

    assert email.casefold() not in corpo
    assert local.casefold() not in corpo, "a parte local do endereço sobrou no corpo do alerta"
    assert dominio.casefold() not in corpo, "o domínio do endereço sobrou no corpo do alerta"


class TestAlertaDaNotificacaoAoManifestante:
    @pytest.mark.parametrize(
        "papel",
        # O papel gravado, e as duas formas que só a pergunta pelo avesso da
        # #547 salva: sem papel e com caixa e espaço diferentes. Um alerta
        # fiado em `papel == "manifestante"` passaria no primeiro e vazaria nos
        # outros dois.
        [PAPEL_MANIFESTANTE, None, "Manifestante "],
        ids=["manifestante", "sem-papel", "caixa-e-espaco"],
    )
    def test_o_destinatario_sai_do_corpo_com_o_marcador_do_log(self, papel, correio):
        """CA 1: o corpo omite o `Destinatario`, com o mesmo marcador que o log
        usa, e decide pela MESMA pergunta única que o log (não por uma
        comparação com a string exata)."""
        banco = _BancoFake([_caso()])
        banco.tabelas["participantes"] = [ADMIN_TECNICO]

        _terceira_falha(
            banco,
            gatilho=ouvidoria_notificacoes.GATILHO_ACUSAR_RECEBIMENTO,
            papel=papel,
            email=EMAIL_DO_MANIFESTANTE,
        )

        texto = _alerta_ao_admin(correio)
        assert f"Destinatario: {MARCADOR}" in texto, "O alerta não diz que omitiu: a omissão virou outra coisa"
        _nao_aparece(EMAIL_DO_MANIFESTANTE, texto)

    def test_o_ultimo_erro_tambem_sai_do_corpo(self, correio):
        """CA 2: a mensagem do provedor carrega o endereço que ela recusou. Ficar
        com ela no corpo seria omitir o `Destinatario` e entregá-lo uma linha
        abaixo."""
        banco = _BancoFake([_caso()])
        banco.tabelas["participantes"] = [ADMIN_TECNICO]

        linha = _terceira_falha(
            banco,
            gatilho=ouvidoria_notificacoes.GATILHO_ACUSAR_RECEBIMENTO,
            papel=PAPEL_MANIFESTANTE,
            email=EMAIL_DO_MANIFESTANTE,
        )

        assert EMAIL_DO_MANIFESTANTE in str(linha["ultimo_erro"]), "A recusa do dublê não carrega o endereço"
        texto = _alerta_ao_admin(correio)
        assert _recusa_do_provedor(EMAIL_DO_MANIFESTANTE) not in texto
        assert "Ultimo erro: (omitido" in texto, "O alerta não diz que omitiu o erro: a omissão virou outra coisa"
        _nao_aparece(EMAIL_DO_MANIFESTANTE, texto)


class TestAlertaDaNotificacaoInterna:
    def test_destinatario_e_erro_continuam_no_corpo(self, correio):
        """CA 3: para gente do hospital o alerta segue completo. Omitir TUDO não
        é o lado seguro, é outro bug: o admin técnico perderia o endereço que
        diz qual caixa do setor o provedor está recusando."""
        banco = _BancoFake([_caso(status="aguardando_area")])
        banco.tabelas["participantes"] = [ADMIN_TECNICO]

        _terceira_falha(
            banco,
            gatilho=ouvidoria_notificacoes.GATILHO_NOVA_DEMANDA,
            papel="titular",
            email=EMAIL_DO_SETOR,
        )

        texto = _alerta_ao_admin(correio)
        assert f"Destinatario: {EMAIL_DO_SETOR}" in texto
        assert f"Ultimo erro: {_recusa_do_provedor(EMAIL_DO_SETOR)}" in texto
        assert MARCADOR not in texto, "O email do hospital não devia ter o endereço omitido"
        assert "(omitido" not in texto
