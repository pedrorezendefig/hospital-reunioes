"""Os três avisos por e-mail da aba Tecnologia (issue #642, PRD #634, ADR 0050).

São três, e só três (PRD #634, histórias 41 a 44): **atribuição** (inclusive a
criação, para o dono do Produto), **@menção** numa resposta e **resposta nova**
numa Demanda de que a pessoa é a responsável. Mudança de coluna não avisa
ninguém, e não existe resumo diário.

Arquivo próprio, e não mais um bloco no `tecnologia.py`: lá moram as regras
PURAS, sem I/O, e o que está aqui fala com o banco, com o Jinja e com o
transporte. Quem decide QUEM recebe continua no serviço puro
(`destinatario_da_atribuicao`, `avisos_da_resposta`); aqui só se resolve o
endereço e se manda.

Todo envio passa pelo `email_service._enviar_email`, que já resolve Resend, SMTP
e modo mock, como o `pops_email_service` e o `reuniao_email_service` fazem. Duas
consequências assumidas, e as duas estão nos testes:

- **falha de envio nunca desfaz a ação.** Quando o aviso não sai, a função
  devolve `False` e o router transforma isso num aviso na tela
  (`AVISO_EMAIL_NAO_SAIU`), sem tocar no que já foi gravado. Um 500 aqui faria
  quem escreveu enviar de novo e duplicar a própria fala no fio;
- **modo mock NÃO conta como enviado, fora do desenvolvimento.** Sem
  transporte configurado o `_enviar_email` devolve `True` sem nada sair (a
  armadilha da issue #435, e o motivo de o `transporte_configurado()` existir
  com um docstring inteiro sobre isso). Esta fatia existe para a falha não
  passar calada, e a falha MAIS PROVÁVEL em produção é justamente essa: a
  `RESEND_API_KEY` rotacionada para vazio. Deixá-la passar seria o app dizer
  "avisei" em toda atribuição e toda resposta sem ninguém receber nada. Em
  `ENVIRONMENT=development` o modo mock continua contando como enviado, senão a
  máquina de quem desenvolve pintaria o alerta em cima de toda ação.
"""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import quote

from app.config import settings
from app.services.email_service import _enviar_email, jinja_env, transporte_configurado
from app.services.tecnologia import (
    SEM_PRODUTO,
    TIPO_ROTULO,
    e_pessoa_da_aba,
    trecho_do_aviso,
)

logger = logging.getLogger(__name__)

# Os três gatilhos e o molde de cada um. O dicionário existe para o teste poder
# afirmar que são TRÊS e-mails diferentes: um único template nos três gatilhos
# mandaria "chegou resposta" para quem foi mencionado.
TEMPLATES: dict[str, str] = {
    "atribuicao": "email_tecnologia_atribuicao.html",
    "mencao": "email_tecnologia_mencao.html",
    "resposta": "email_tecnologia_resposta.html",
}

# O endereço da Demanda, o mesmo que o botão "Copiar link" monta na tela
# (`demandas.ts`). Escrito aqui de novo porque o backend não lê o frontend; o
# teste do gatilho confere a forma.
ROTA_TECNOLOGIA = "/admin/tecnologia"
PARAM_DEMANDA = "demanda"

# O que a resolução de destinatário precisa ler. `ativo` e
# `is_super_admin`/`access_profile` entram porque a peneira roda em Python: um
# `.eq("ativo", True)` no PostgREST descartaria as linhas com `ativo` NULL, que
# contam como ativas (ver `e_pessoa_da_aba`).
_CAMPOS_PESSOA = "id, nome_completo, email, ativo, is_super_admin, access_profile"


def link_da_demanda(demanda_id: str) -> str:
    """O endereço que abre a Demanda com o card já aberto (issue #640)."""
    return f"{settings.frontend_url}{ROTA_TECNOLOGIA}?{PARAM_DEMANDA}={quote(str(demanda_id))}"


def _pessoas_por_id(supabase, ids: list[str]) -> dict[str, dict]:
    if not ids:
        return {}
    result = supabase.table("participantes").select(_CAMPOS_PESSOA).in_("id", sorted(set(ids))).execute()
    return {linha["id"]: linha for linha in (result.data or [])}


def _contexto(demanda: dict[str, Any], *, trecho: str, quem_fez_nome: str) -> dict[str, Any]:
    """O que os três templates mostram: o critério de conteúdo da issue #642."""
    from app.services.email_constants import get_logo_data_uri

    return {
        "titulo": str(demanda.get("titulo") or "").strip(),
        "tipo": TIPO_ROTULO.get(str(demanda.get("tipo")), str(demanda.get("tipo") or "")),
        "produto": demanda.get("produto_nome") or SEM_PRODUTO,
        "trecho": trecho,
        "link": link_da_demanda(str(demanda.get("id") or "")),
        "quem_fez_nome": quem_fez_nome,
        "logo_base64": get_logo_data_uri(),
    }


def _texto_simples(*, abertura: str, contexto: dict[str, Any]) -> str:
    """O corpo em texto puro, para o cliente de e-mail que não desenha HTML."""
    return (
        f"{abertura}\n\n"
        f"Demanda: {contexto['titulo']}\n"
        f"Tipo: {contexto['tipo']}\n"
        f"Produto: {contexto['produto']}\n\n"
        f"{contexto['trecho']}\n\n"
        f"Abrir a Demanda: {contexto['link']}\n"
    )


def _mandar(
    supabase,
    *,
    gatilho: str,
    destinatarios: list[str],
    assunto: str,
    abertura: str,
    demanda: dict[str, Any],
    trecho: str,
    quem_fez_nome: str,
) -> bool:
    """Manda um aviso a cada destinatário. `True` quando todos os que deviam
    receber receberam.

    A peneira e a falha são coisas DIFERENTES, e a diferença é o que a tela vê:

    - quem **não está mais na lista de gente da aba** é descartado sem falha, e
      o aviso NÃO DEVE sair. Chamar isso de falha cobraria de quem agiu um
      conserto que não existe;
    - quem **tem acesso e não tem endereço** conta como falha: esse aviso devia
      ter saído e não chegou a lugar nenhum.

    **De onde vem, na prática, um destinatário fora da lista.** Não é da menção:
    o `_texto_e_mencoes` valida as menções e o envio acontece na MESMA
    requisição, então uma menção a quem não tem acesso vira 422 e nunca chega
    aqui. Quem chega é o **responsável** gravado na Demanda, que pode ter
    perdido o Super admin ou ter sido desativado dias depois de virar
    responsável. A peneira vale para os dois caminhos porque a regra é uma só, e
    porque quem escrever o próximo gatilho não deve precisar saber qual dos dois
    é o real de hoje.

    O `except` de fora é largo de propósito: template que sumiu, logo que não
    abre, provedor que estourou de um jeito novo. Todos têm o mesmo desfecho, e
    nenhum deles pode derrubar uma ação que já está gravada no banco.
    """
    if not destinatarios:
        return True
    if not transporte_configurado() and settings.environment != "development":
        # Modo mock em produção: o `_enviar_email` devolveria `True` sem nada
        # sair. Ver o docstring do módulo.
        logger.error(
            "[tecnologia:%s] sem transporte de email configurado: o aviso da Demanda %s não saiu",
            gatilho,
            demanda.get("id"),
        )
        return False
    try:
        pessoas = _pessoas_por_id(supabase, destinatarios)
        contexto = _contexto(demanda, trecho=trecho, quem_fez_nome=quem_fez_nome)
        html_base = jinja_env.get_template(TEMPLATES[gatilho])
        texto = _texto_simples(abertura=abertura, contexto=contexto)
        # Quebra de linha no meio do assunto é injeção de cabeçalho: o título da
        # Demanda é campo livre, e `_titulo_valido` só faz `strip()`, então um
        # `\r\n` no MEIO passa. Pelo SMTP o `EmailMessage` recusa e o envio
        # falha; pelo Resend a string viaja como JSON e quem monta o MIME é o
        # provedor, e daqui não dá para afirmar que ele higieniza. Uma linha
        # fecha os dois.
        assunto = " ".join(assunto.split())
        # O que vai para o LOG no lugar do assunto de verdade.
        #
        # O assunto que a pessoa recebe carrega o título da Demanda, que é texto
        # que alguém digitou num campo livre ("Prontuário da paciente Maria não
        # abre"). O log corre em INFO em produção, e quem tem acesso a ele e
        # nenhum perfil na aba não pode ler isso. O que fica é o que responde à
        # única pergunta que o log precisa responder: o aviso desta Demanda
        # saiu? Nem título, nem nome de Produto (que também é texto digitado).
        assunto_para_o_log = f"aviso de {gatilho} da Demanda {demanda.get('id')}"

        tudo_saiu = True
        for pid in destinatarios:
            pessoa = pessoas.get(pid)
            if not e_pessoa_da_aba(pessoa):
                logger.info(
                    "[tecnologia:%s] %s não está na lista de acesso à aba: aviso da Demanda %s não sai",
                    gatilho,
                    pid,
                    demanda.get("id"),
                )
                continue
            endereco = str((pessoa or {}).get("email") or "").strip()
            if not endereco:
                logger.warning(
                    "[tecnologia:%s] participante %s sem e-mail: aviso da Demanda %s não saiu",
                    gatilho,
                    pid,
                    demanda.get("id"),
                )
                tudo_saiu = False
                continue
            html = html_base.render(
                destinatario_nome=pessoa.get("nome_completo") or "Olá",
                abertura=abertura,
                **contexto,
            )
            if not _enviar_email(
                endereco,
                assunto,
                html,
                texto,
                # O endereço fora do log pelo mesmo motivo do assunto: o par
                # "quem recebeu" + "sobre o quê" é o que monta um índice para
                # quem lê o log sem ter acesso à aba.
                endereco_fora_do_log=True,
                assunto_no_log=assunto_para_o_log,
            ):
                # O `_enviar_email` já logou a causa (e o `email_service` decide
                # o que do endereço entra no log). Aqui fica o que liga a falha
                # à Demanda, que é o que serve para reconstruir depois.
                logger.warning(
                    "[tecnologia:%s] o transporte recusou o aviso da Demanda %s para o participante %s",
                    gatilho,
                    demanda.get("id"),
                    pid,
                )
                tudo_saiu = False
        return tudo_saiu
    except Exception:  # noqa: BLE001 (e-mail nunca derruba a ação que o disparou)
        logger.exception("[tecnologia:%s] falha ao montar o aviso da Demanda %s", gatilho, demanda.get("id"))
        return False


def avisar_atribuicao(
    supabase,
    *,
    demanda: dict[str, Any],
    destinatario_id: str,
    quem_fez_nome: str,
    trecho: str | None = None,
) -> bool:
    """Gatilho 1: a Demanda caiu na mão de alguém (PRD #634, história 41).

    O `trecho` é o que MOTIVA o aviso, e por isso ele é parâmetro desde a issue
    #679: quando quem atribui é a Entrega, o que a pessoa precisa ler não é a
    descrição do pedido (que ela mesma escreveu, meses atrás), e sim o recado
    "Entregue, confira e conclua". É o mesmo e-mail, com o mesmo assunto e o
    mesmo link, porque a ação é a mesma: a Demanda caiu na mão dela.
    """
    titulo = str(demanda.get("titulo") or "").strip()
    return _mandar(
        supabase,
        gatilho="atribuicao",
        destinatarios=[destinatario_id],
        assunto=f"Demanda na sua mão: {titulo}",
        abertura=f"{quem_fez_nome} deixou esta Demanda com você.",
        demanda=demanda,
        # O trecho da atribuição feita por gente é a DESCRIÇÃO da Demanda: é o
        # que diz do que se trata para quem está recebendo o pedido agora.
        trecho=trecho or trecho_do_aviso(demanda.get("descricao")),
        quem_fez_nome=quem_fez_nome,
    )


def avisar_mencao(
    supabase, *, demanda: dict[str, Any], destinatarios: list[str], texto: str, quem_fez_nome: str
) -> bool:
    """Gatilho 2: alguém foi chamado pelo nome (PRD #634, história 42)."""
    titulo = str(demanda.get("titulo") or "").strip()
    return _mandar(
        supabase,
        gatilho="mencao",
        destinatarios=destinatarios,
        assunto=f"{quem_fez_nome} mencionou você numa Demanda: {titulo}",
        abertura=f"{quem_fez_nome} chamou você numa resposta desta Demanda.",
        demanda=demanda,
        trecho=trecho_do_aviso(texto),
        quem_fez_nome=quem_fez_nome,
    )


def avisar_resposta(supabase, *, demanda: dict[str, Any], destinatario_id: str, texto: str, quem_fez_nome: str) -> bool:
    """Gatilho 3: a bola voltou para o responsável (PRD #634, história 43)."""
    titulo = str(demanda.get("titulo") or "").strip()
    return _mandar(
        supabase,
        gatilho="resposta",
        destinatarios=[destinatario_id],
        assunto=f"Resposta nova numa Demanda sua: {titulo}",
        abertura=f"{quem_fez_nome} respondeu numa Demanda de que você é a pessoa responsável.",
        demanda=demanda,
        trecho=trecho_do_aviso(texto),
        quem_fez_nome=quem_fez_nome,
    )
