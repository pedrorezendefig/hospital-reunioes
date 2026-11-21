"""O e-mail de segunda (issue #1876; Refino 19 do PRD #1757 e decisões 20, 21,
23, 27, 64 e 68 do diretor).

Toda segunda, o job manda um e-mail por pessoa, com até duas partes:

- a do Facilitador: nas Reuniões que ele facilita, o que foi concluído,
  atualizado (iniciado ou anotado) e repactuado na semana que passou (de
  segunda a domingo, no fuso de São Paulo), mais o que segue atrasado;
- a do responsável: só as Pendências dele em aberto, como responsável ou
  co-responsável.

Quem é as duas coisas recebe um e-mail só, com as duas partes separadas, e quem
não tem nada para ver não recebe (um e-mail vazio acostuma a ignorar o de
segunda). As Reuniões do Núcleo que a pessoa não alcança ficam de fora (ADR
0095).

A guarda é uma linha por pessoa e por semana em `email_de_segunda`, gravada
antes do envio: o job roda de hora em hora das 8h às 12h e só a primeira
passada manda. Se o envio falha, a linha sai e a hora seguinte tenta de novo.
No modo de teste do e-mail (sem Resend nem SMTP), o e-mail vai para o log e
nada é marcado. Sem IA (ADR 0082).

O link é o comum do app; o link pessoal de quem nunca entrou vem em outro card.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta

from app.config import settings
from app.dependencies import _PARTICIPANTE_FULL_FIELDS, foi_desligado, is_secretaria, reunioes_ocultas
from app.services.email_constants import get_logo_data_uri
from app.services.email_service import _enviar_email, jinja_env, transporte_configurado
from app.services.paginacao import ler_tudo
from app.services.pendencia_ciclo import ABERTOS, esta_atrasada
from app.services.pendencias_consulta import FUSO, as_data
from app.services.seguranca_do_paciente.reunioes import reunioes_do_nucleo

TABELA = "email_de_segunda"
TEMPLATE = "email_resumo_de_segunda.html"
_CAMPOS_DA_PENDENCIA = (
    "id_acao, id_reuniao, descricao_acao, responsavel_id, co_responsavel_id, responsavel_nome, status, prazo"
)

# O evento do histórico e a parte do e-mail do Facilitador em que ele entra.
_SECAO_DO_COMANDO = {
    "concluir": "concluidas",
    "iniciar": "atualizadas",
    "anotar": "atualizadas",
    "repactuar": "repactuadas",
}


def segunda_da_semana(dia: date) -> date:
    return dia - timedelta(days=dia.weekday())


@dataclass(frozen=True)
class ItemDoEmail:
    id_reuniao: str | None
    descricao: str
    reuniao: str
    responsavel: str
    prazo: date | None
    atrasada: bool = False
    anotacao: str | None = None

    @property
    def prazo_formatado(self) -> str:
        return self.prazo.strftime("%d/%m/%Y") if self.prazo else "Sem prazo"


@dataclass
class EmailDaPessoa:
    concluidas: list[ItemDoEmail] = field(default_factory=list)
    atualizadas: list[ItemDoEmail] = field(default_factory=list)
    repactuadas: list[ItemDoEmail] = field(default_factory=list)
    atrasadas: list[ItemDoEmail] = field(default_factory=list)
    abertas: list[ItemDoEmail] = field(default_factory=list)

    @property
    def do_facilitador(self) -> bool:
        return bool(self.concluidas or self.atualizadas or self.repactuadas or self.atrasadas)

    @property
    def do_responsavel(self) -> bool:
        return bool(self.abertas)

    def sem(self, ocultas: set[str]) -> EmailDaPessoa:
        """O mesmo e-mail sem as Reuniões que a pessoa não alcança."""
        if not ocultas:
            return self

        def _fora(itens):
            return [i for i in itens if i.id_reuniao not in ocultas]

        return EmailDaPessoa(
            _fora(self.concluidas),
            _fora(self.atualizadas),
            _fora(self.repactuadas),
            _fora(self.atrasadas),
            _fora(self.abertas),
        )


def _ordem(item: ItemDoEmail):
    return (item.prazo is None, item.prazo or date.max, item.descricao)


def montar_emails(
    *, reunioes: Iterable[dict], pendencias: Iterable[dict], eventos: Iterable[dict], hoje: date
) -> dict[str, EmailDaPessoa]:
    """O e-mail de cada pessoa, por id, a partir das Reuniões, das Pendências
    e dos eventos do histórico da semana. Função pura."""
    por_reuniao = {r["id_reuniao"]: r for r in reunioes}
    por_id = {p["id_acao"]: p for p in pendencias}
    emails: dict[str, EmailDaPessoa] = {}

    def _email(pid: str) -> EmailDaPessoa:
        return emails.setdefault(pid, EmailDaPessoa())

    def _item(p: dict, *, anotacao: str | None = None, prazo=None) -> ItemDoEmail:
        reuniao = por_reuniao.get(p.get("id_reuniao")) or {}
        prazo = as_data(prazo) if prazo is not None else as_data(p.get("prazo"))
        return ItemDoEmail(
            id_reuniao=p.get("id_reuniao"),
            descricao=p.get("descricao_acao") or "",
            reuniao=reuniao.get("titulo") or p.get("id_reuniao") or "",
            responsavel=p.get("responsavel_nome") or "",
            prazo=prazo,
            atrasada=esta_atrasada(p.get("status"), as_data(p.get("prazo")), hoje),
            anotacao=anotacao,
        )

    def _facilitador_de(p: dict) -> str | None:
        return (por_reuniao.get(p.get("id_reuniao")) or {}).get("facilitador_id")

    # O último evento de cada Pendência em cada parte, por Facilitador.
    da_semana: dict[tuple[str, str], dict[str, ItemDoEmail]] = {}
    for evento in sorted(eventos, key=lambda e: str(e.get("criado_em") or "")):
        secao = _SECAO_DO_COMANDO.get(evento.get("comando"))
        p = por_id.get(evento.get("id_acao"))
        facilitador = _facilitador_de(p) if p else None
        if not secao or not facilitador:
            continue
        prazo = evento.get("prazo_depois") if secao == "repactuadas" else None
        da_semana.setdefault((facilitador, secao), {})[p["id_acao"]] = _item(
            p, anotacao=evento.get("anotacao"), prazo=prazo
        )
    for (facilitador, secao), itens in da_semana.items():
        concluidas = da_semana.get((facilitador, "concluidas"), {}) if secao == "atualizadas" else {}
        # A concluída na semana sai das atualizadas: a conclusão já conta a história.
        setattr(
            _email(facilitador),
            secao,
            sorted((i for a, i in itens.items() if a not in concluidas), key=_ordem),
        )

    for p in por_id.values():
        if p.get("status") not in ABERTOS:
            continue
        item = _item(p)
        facilitador = _facilitador_de(p)
        if item.atrasada and facilitador:
            _email(facilitador).atrasadas.append(item)
        for pid in dict.fromkeys(x for x in (p.get("responsavel_id"), p.get("co_responsavel_id")) if x):
            _email(pid).abertas.append(item)

    for email in emails.values():
        email.atrasadas.sort(key=_ordem)
        email.abertas.sort(key=_ordem)
    return {pid: e for pid, e in emails.items() if e.do_facilitador or e.do_responsavel}


def _assunto(email: EmailDaPessoa) -> str:
    if email.do_facilitador and email.do_responsavel:
        return "Resumo de segunda: suas reuniões e suas pendências"
    if email.do_facilitador:
        return "Resumo de segunda: a semana das suas reuniões"
    return "Resumo de segunda: suas pendências em aberto"


def _texto(nome: str, email: EmailDaPessoa, link: str) -> str:
    linhas = [f"Olá, {nome}.", ""]

    def _bloco(titulo: str, itens: list[ItemDoEmail]):
        if not itens:
            return
        linhas.append(titulo)
        for i in itens:
            linhas.append(f"- {i.descricao} ({i.reuniao}; responsável: {i.responsavel}; prazo: {i.prazo_formatado})")
        linhas.append("")

    if email.do_facilitador:
        linhas += ["DAS REUNIÕES QUE VOCÊ FACILITA", ""]
        _bloco("Concluídas na semana:", email.concluidas)
        _bloco("Atualizadas na semana:", email.atualizadas)
        _bloco("Repactuadas na semana:", email.repactuadas)
        _bloco("Seguem atrasadas:", email.atrasadas)
    if email.do_responsavel:
        linhas += ["SUAS PENDÊNCIAS EM ABERTO", ""]
        _bloco("Em aberto:", email.abertas)
    linhas.append(f"Acesse o sistema em {link}")
    return "\n".join(linhas)


def montar_mensagem(nome: str, email: EmailDaPessoa) -> tuple[str, str, str]:
    """Assunto, HTML e texto do e-mail de uma pessoa."""
    link = f"{settings.frontend_url}/inicio"
    html = jinja_env.get_template(TEMPLATE).render(nome=nome, email=email, link=link, logo_base64=get_logo_data_uri())
    return _assunto(email), html, _texto(nome, email, link)


def _limites_da_semana(segunda: date) -> tuple[str, str]:
    """A semana que passou, de segunda a domingo no fuso de São Paulo, em ISO
    no UTC, como o banco devolve o `criado_em`."""
    fim = datetime.combine(segunda, time.min, tzinfo=FUSO)
    inicio = fim - timedelta(weeks=1)
    return inicio.astimezone(UTC).isoformat(), fim.astimezone(UTC).isoformat()


def _ocultas_por_pessoa(supabase) -> Callable[[dict], set[str]]:
    if not reunioes_do_nucleo(supabase):
        return lambda _pessoa: set()
    return lambda pessoa: set(reunioes_ocultas(supabase, pessoa))


def enviar_semana(supabase, *, hoje: date) -> int:
    """Manda o e-mail de segunda da semana de `hoje` a quem ainda não recebeu.
    Devolve quantos saíram de verdade."""
    semana = segunda_da_semana(hoje).isoformat()
    inicio, fim = _limites_da_semana(segunda_da_semana(hoje))
    ja_recebeu = {
        linha["participante_id"]
        for linha in ler_tudo(
            lambda: supabase.table(TABELA).select("participante_id").eq("semana", semana).order("participante_id"),
            rotulo="e-mails de segunda da semana",
        )
    }
    # O cadastro inteiro: o sigilo do Núcleo lê `perfil_nsp` e `role`.
    pessoas = {
        p["id"]: p
        for p in ler_tudo(
            lambda: (
                supabase.table("participantes").select(_PARTICIPANTE_FULL_FIELDS).not_.is_("email", "null").order("id")
            ),
            rotulo="quem recebe o e-mail de segunda",
        )
    }
    reunioes = ler_tudo(
        lambda: (
            supabase.table("reunioes")
            .select("id_reuniao, titulo, facilitador_id")
            .is_("deleted_at", "null")
            .order("id_reuniao")
        ),
        rotulo="reuniões do e-mail de segunda",
    )
    # A Pendência sem Reunião é o lembrete da Agenda regulatória do Núcleo:
    # como nas listas de Pendências, não entra (`e_lembrete_do_nucleo`).
    pendencias = ler_tudo(
        lambda: (
            supabase.table("pendencias")
            .select(_CAMPOS_DA_PENDENCIA)
            .is_("deleted_at", "null")
            .not_.is_("id_reuniao", "null")
            .order("id_acao")
        ),
        rotulo="pendências do e-mail de segunda",
    )
    eventos = ler_tudo(
        lambda: (
            supabase.table("pendencia_historico")
            .select("id_acao, comando, anotacao, criado_em, prazo_depois")
            .in_("comando", list(_SECAO_DO_COMANDO))
            .gte("criado_em", inicio)
            .lt("criado_em", fim)
            .order("id")
        ),
        rotulo="eventos da semana",
    )
    ocultas_de = _ocultas_por_pessoa(supabase)

    enviados = 0
    emails = montar_emails(reunioes=reunioes, pendencias=pendencias, eventos=eventos, hoje=hoje)
    for pid, email in sorted(emails.items()):
        pessoa = pessoas.get(pid)
        if pid in ja_recebeu or not pessoa or is_secretaria(pessoa) or foi_desligado(pessoa):
            continue
        email = email.sem(ocultas_de(pessoa))
        if not (email.do_facilitador or email.do_responsavel):
            continue
        assunto, html, texto = montar_mensagem(pessoa.get("nome_completo") or "", email)
        if not transporte_configurado():
            # Modo de teste: o e-mail vai para o log e nada é marcado.
            _enviar_email(pessoa["email"], assunto, html, texto)
            continue
        guarda = (
            supabase.table(TABELA)
            .upsert(
                [{"participante_id": pid, "semana": semana}],
                on_conflict="participante_id,semana",
                ignore_duplicates=True,
            )
            .execute()
        )
        if not guarda.data:
            continue
        if _enviar_email(pessoa["email"], assunto, html, texto):
            enviados += 1
        else:
            supabase.table(TABELA).delete().eq("participante_id", pid).eq("semana", semana).execute()
    return enviados
