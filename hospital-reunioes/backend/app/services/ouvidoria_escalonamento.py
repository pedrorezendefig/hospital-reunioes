"""Escada de escalonamento da Ouvidoria (issue #336, PRD #318, ADR 0034 decisão 12).

A cobrança sobe sozinha quando ninguém responde. São quatro degraus sobre o
calendário útil, calculados pelo motor de prazos (issue #331):

1. **Véspera** do vencimento: lembra o titular do setor.
2. **Vencimento**: cobra titular e substituto. Este degrau mora ao lado, em
   `ouvidoria_cobranca` (issue #327), porque foi entregue antes e tem o próprio
   carimbo (`prazo_rompido_em`). Os outros três moram aqui.
3. **+24h úteis** sem resposta: o gestor da área. Setor sem gestor cadastrado
   não faz o degrau sumir: ele vira o alerta à Diretoria Executiva.
4. **+48h úteis** sem resposta: a Diretoria Executiva.

Fora da escada de prazo, um quinto aviso: **caso crítico validado** notifica a
Diretoria Executiva na hora, sem esperar vencimento nenhum. Quem chama esse é a
validação (a rota), não o job.

Cada degrau tem coluna própria de carimbo em `ouvidoria_protocolos`, gravada
por update condicional (`IS NULL`) antes de qualquer email sair: rodar o job
duas vezes, ou duas rodadas concorrentes, não duplicam degrau. A exceção é o
alerta de cadastro incompleto (issue #373), que sai ANTES do carimbo de
propósito: duas rodadas concorrentes podem mandá-lo duas vezes, e isso é
melhor que um caso carimbado sem sinal nenhum. A ordem dos
passos protege o caso de ficar sem cobrança para sempre, no mesmo desenho da
issue #327: os destinatários são carregados ANTES do carimbo, e um carimbo cuja
notificação não gravou é desfeito.

Quem chama é o scheduler (app/cron/scheduler.py), que carrega o relógio e os
feriados; aqui vive a lógica, testável com um Supabase falso.
"""

from __future__ import annotations

import datetime as dt
import logging
from dataclasses import dataclass

from app.services.ouvidoria_notificacoes import (
    GATILHO_ALERTA_CADASTRO_SETOR,
    GATILHO_CRITICO_IMEDIATO,
    GATILHO_ESCALONAMENTO_DIRETORIA,
    GATILHO_ESCALONAMENTO_GESTOR,
    GATILHO_VESPERA_VENCIMENTO,
    avisar_admins_tecnicos,
    despachar_agora_se_puder,
    ler_diretoria_executiva,
    quando_enviar,
    registrar,
)
from app.services.ouvidoria_prazos import FUSO, gatilhos_de_escalonamento
from app.services.ouvidoria_responsaveis import (
    CADEIA_DA_VESPERA,
    CADEIA_DO_GESTOR,
    Destinatario,
    destinatarios_nos_papeis,
)

logger = logging.getLogger(__name__)

AGUARDANDO_AREA = "aguardando_area"
PAPEL_DIRETORIA = "diretoria_executiva"

# Teto de degraus por rodada, no mesmo espírito do lote da issue #327: o
# primeiro tick depois do deploy acha todo o histórico vencido de uma vez, e o
# provedor de email não precisa engolir a rajada. O job roda de novo em 10
# minutos.
LOTE_POR_RODADA = 25

# Quantos casos a varredura lê. Folga grande de propósito: caso de setor sem
# ninguém para cobrar não é carimbado, volta na consulta a cada rodada e, por
# ser o mais antigo, vem sempre primeiro.
LEITURA_POR_RODADA = 200

# Até onde a varredura olha para frente. A véspera é um dia útil antes do
# vencimento, então um caso cujo degrau vence agora tem prazo a poucos dias de
# distância; a folga cobre feriado emendado sem ler a fila inteira.
HORIZONTE_DIAS = 15

_CAMPOS_DO_ESCALONAMENTO = (
    "id, protocolo, setor, gravidade, prazo_area_em, validada_em, "
    "vespera_avisada_em, escalonado_gestor_em, escalonado_diretoria_em"
)

# Como um degrau termina. Três desfechos, não dois: "não havia ninguém a quem
# avisar" precisa ser distinguível de "a leitura falhou", porque só o primeiro
# tira o caso da varredura (issue #373, defeito 2).
SUBIU = "subiu"
SEM_NINGUEM = "sem_ninguem"
ADIADO = "adiado"

# O que o admin técnico lê quando um caso trava por buraco de cadastro. Sai por
# email, e não só no log: `logger.warning` num job que roda a cada 10 minutos
# não é sinal operacional, é ruído que ninguém lê.
# O alerta ao admin é UM por rodada, com todos os casos travados dentro. O
# primeiro tick depois do deploy acha todo o histórico travado de uma vez: um
# email por caso seria a rajada que `LOTE_POR_RODADA` existe para evitar, e um
# teto de emails por rodada deixaria casos sem sinal nenhum (o carimbo é
# condicional, então eles nunca voltariam a alertar).
ALERTA_CADASTRO_ASSUNTO = "Ouvidoria: {quantos} caso(s) travado(s) por cadastro incompleto"
# O texto diz exatamente o que a decisão checou, e nada além. A escada consulta
# o TITULAR (véspera) e o GESTOR (24h úteis); o substituto é cobrado pelo degrau
# do vencimento, que mora em `ouvidoria_cobranca` e não passa por aqui. Afirmar
# "sem titular, substituto ou gestor" mandaria o admin conferir um cadastro que
# pode estar correto (issue #373).
ALERTA_CADASTRO_ABERTURA = (
    "Os casos abaixo sairam da varredura do escalonamento porque nao sobrou a\n"
    "quem escalonar: nenhum degrau que eles ainda podem subir tem destinatario,\n"
    "e a Ouvidoria esta sem ninguem com perfil de Diretoria Executiva.\n\n"
)
ALERTA_CADASTRO_LINHA = "- {protocolo} | setor {setor} | parado no degrau: {degrau}\n"
# O conserto que FUNCIONA é um só. Cadastrar responsavel de setor exige o
# perfil de Diretoria Executiva, e o caso só trava quando ninguem o tem: quem
# recebe este email levaria 403 tentando por ali. Quem destrava é o Super Admin,
# na tela de Usuarios.
ALERTA_CADASTRO_FECHO = (
    "\nNenhum degrau foi queimado. Para destravar: o Super Admin concede o\n"
    "perfil de Diretoria Executiva a alguem com email, na tela de Usuarios.\n"
    "Todo caso travado volta a escalonar sozinho, do degrau em que parou.\n\n"
    "Depois disso, quem tiver o perfil pode cadastrar o responsavel do setor\n"
    "para a cobranca voltar a passar pelo proprio setor.\n"
)


@dataclass(frozen=True)
class Degrau:
    """Um degrau da escada: quando dispara, quem cobra e o que fica gravado.

    `carimbo` é a coluna de idempotência em `ouvidoria_protocolos`. `atributo` é
    o campo do resultado do motor de prazos que diz a hora do disparo."""

    nome: str
    carimbo: str
    atributo: str
    gatilho: str
    papeis: tuple[str, ...]
    observacao: str
    # Degrau que perde o sentido depois que o prazo estoura. Só a véspera é
    # assim: ela avisa que o prazo ESTÁ para vencer.
    caduca_no_vencimento: bool = False


VESPERA = Degrau(
    nome="véspera do vencimento",
    carimbo="vespera_avisada_em",
    atributo="vespera",
    gatilho=GATILHO_VESPERA_VENCIMENTO,
    papeis=CADEIA_DA_VESPERA,
    observacao="Véspera do vencimento: lembrete enviado ao titular do setor.",
    caduca_no_vencimento=True,
)

GESTOR = Degrau(
    nome="gestor da área",
    carimbo="escalonado_gestor_em",
    atributo="mais_24h",
    gatilho=GATILHO_ESCALONAMENTO_GESTOR,
    papeis=CADEIA_DO_GESTOR,
    observacao="Escalonamento: 24 horas úteis sem resposta, cobrança enviada ao gestor da área.",
)

DIRETORIA = Degrau(
    nome="Diretoria Executiva",
    carimbo="escalonado_diretoria_em",
    atributo="mais_48h",
    gatilho=GATILHO_ESCALONAMENTO_DIRETORIA,
    # A Diretoria não sai do cadastro de responsáveis do setor: ela vem do
    # perfil da Ouvidoria, como no alerta de setor sem titular do núcleo.
    papeis=(),
    observacao="Escalonamento: 48 horas úteis sem resposta, caso levado à Diretoria Executiva.",
)

# Na ordem em que a escada sobe. Caso abandonado desde a véspera sobe os três
# degraus na mesma rodada, cada um uma vez: o job não inventa história, ele
# conta o que já deveria ter acontecido.
DEGRAUS = (VESPERA, GESTOR, DIRETORIA)

# Os papéis do setor que ESTA escada consulta. O substituto fica de fora: quem
# fala com ele é o degrau do vencimento, que mora em `ouvidoria_cobranca`
# (issue #327). Cadastrar substituto, então, não destrava caso nenhum daqui.
PAPEIS_DA_ESCADA = tuple(dict.fromkeys(CADEIA_DA_VESPERA + CADEIA_DO_GESTOR))

# O que a Diretoria lê quando o degrau chegou nela um dia antes do previsto.
SEM_GESTOR = "O setor {setor} não tem gestor cadastrado na Ouvidoria, então este degrau subiu direto à Diretoria."


def escalar_prazos(supabase, agora: dt.datetime, feriados: frozenset[dt.date]) -> int:
    """Varre os casos aguardando área e sobe os degraus que já venceram.

    Devolve quantos degraus subiram nesta rodada."""
    horizonte = (agora + dt.timedelta(days=HORIZONTE_DIAS)).isoformat()
    try:
        result = (
            supabase.table("ouvidoria_protocolos")
            .select(_CAMPOS_DO_ESCALONAMENTO)
            .eq("status", AGUARDANDO_AREA)
            # A Diretoria é o último degrau: com ele subido, a escada acabou e
            # o caso sai da varredura. Sem este filtro, caso abandonado em
            # aguardando área ficaria ocupando a janela de leitura para sempre
            # e, passando do teto, nenhum caso novo entraria (mesmo cuidado do
            # `is_("prazo_rompido_em", "null")` da issue #327).
            #
            # Caso sem ninguém a quem avisar não queima este degrau: ele leva
            # o carimbo próprio do filtro abaixo, e volta à escada intacto
            # quando o cadastro for corrigido.
            .is_(DIRETORIA.carimbo, "null")
            # Caso sem ninguém a quem escalonar sai da varredura por aqui. Sem
            # este filtro ele voltava em toda rodada e, por ser o mais antigo,
            # vinha primeiro: passando de `LEITURA_POR_RODADA` casos assim, o
            # job parava de escalonar qualquer um (issue #373, defeito 2).
            .is_("escalonamento_impossivel_em", "null")
            .lte("prazo_area_em", horizonte)
            .order("prazo_area_em")
            .limit(LEITURA_POR_RODADA)
            .execute()
        )
    except Exception:
        logger.error("[Ouvidoria] Falha ao ler os casos aguardando área para o escalonamento")
        return 0

    subidos = 0
    travados: list[tuple[dict, str]] = []
    # Cache da rodada, não do processo: o cenário da issue é uma fila cheia de
    # casos do MESMO setor órfão, e reler o cadastro por caso e por degrau seria
    # centenas de idas ao banco na rodada que existe para destravar o job. Vive
    # só enquanto esta chamada dura, então o cadastro corrigido vale já na
    # rodada seguinte.
    cadastros: dict[str, list[dict] | None] = {}
    diretoria: list[list[Destinatario] | None] = []
    for caso in result.data or []:
        if subidos >= LOTE_POR_RODADA:
            break
        pendentes = [d for d in DEGRAUS if caso.get(d.carimbo) is None]
        gatilhos = _gatilhos_do_caso(caso, feriados)
        if gatilhos is None:
            continue
        # Os degraus que já venceram e ainda cabem nesta rodada. Separar o
        # "estava na hora" do "deu certo" é o que permite decidir, no fim do
        # caso, se ele travou por cadastro ou só ainda não chegou a hora.
        # Viável é o degrau que ainda pode subir algum dia (não caducou);
        # devido é o que já venceu. A escada trava por falta de destinatário nos
        # VIÁVEIS, não nos devidos: o job roda a cada 10 minutos, e quase sempre
        # só um degrau está vencido.
        viaveis = [d for d in pendentes if not (d.caduca_no_vencimento and agora >= gatilhos.vencimento)]
        devidos = []
        for degrau in pendentes:
            quando = getattr(gatilhos, degrau.atributo)
            if quando is None or agora < quando:
                continue
            if degrau.caduca_no_vencimento and agora >= gatilhos.vencimento:
                # O primeiro tick depois do deploy acha o histórico vencido
                # inteiro sem carimbo nenhum, e o job parado por qualquer
                # motivo produz o mesmo efeito. Mandar "o prazo vence amanhã"
                # para quem já estourou seria mentira; quem cobra o vencido é o
                # degrau do vencimento (issue #327).
                continue
            devidos.append(degrau)

        desfechos = []
        for degrau in devidos:
            if subidos >= LOTE_POR_RODADA:
                break
            desfecho = _subir_degrau(supabase, caso, degrau, agora, feriados, cadastros, diretoria)
            desfechos.append((degrau, desfecho))
            if desfecho == SUBIU:
                subidos += 1
        # A pergunta NÃO é "este degrau tem destinatário?": o job roda a cada 10
        # minutos, então quase sempre só um degrau está vencido, e um degrau sem
        # ninguém hoje não prova nada sobre os seguintes (a véspera fala com o
        # titular, mas o degrau do gestor cai na Diretoria). A pergunta é sobre
        # o CASO: existe alguma ponta a quem falar? Só quando as duas estão
        # vazias o caso não tem saída (issue #373).
        sem_ninguem = [degrau for degrau, d in desfechos if d == SEM_NINGUEM]
        if sem_ninguem and _sem_qualquer_destinatario(supabase, caso, viaveis, agora, cadastros, diretoria):
            # O degrau que o admin lê é o que FICOU sem destinatário, e o mais
            # alto deles: dizer "véspera" de um caso travado nos três mandaria
            # o admin olhar o lugar errado.
            travados.append((caso, sem_ninguem[-1].nome))

    # O ALERTA VEM ANTES DO CARIMBO, E O CARIMBO DEPENDE DELE. O carimbo tira o
    # caso da varredura e é condicional (`IS NULL`), então um caso carimbado sem
    # alerta fica sem cobrança E sem sinal, para sempre: o desfecho que esta
    # fatia existe para impedir.
    #
    # A ordem sozinha só cobre o crash. A condição cobre a entrega: sem super
    # admin com email, ou com a leitura de `participantes` falhando, o alerta
    # não sai, nada é carimbado, e a rodada seguinte tenta de novo.
    if travados and _alertar_cadastro_incompleto(supabase, travados):
        for caso, _degrau in travados:
            _reivindicar_impossivel(supabase, caso["id"], agora)
    return subidos


def _sem_qualquer_destinatario(
    supabase, caso: dict, viaveis: list[Degrau], agora: dt.datetime, cadastros: dict, diretoria: list
) -> bool:
    """Se NENHUM degrau que este caso ainda pode subir tem a quem avisar.

    Perguntar só pelo degrau devido agora seria errado: setor sem titular não
    manda a véspera, mas o degrau do gestor um dia depois cai na Diretoria e o
    caso escalona normalmente. Tirá-lo da varredura na véspera mataria a
    cobrança que funcionaria.

    Falha de leitura em qualquer degrau devolve False. Adiar é sempre seguro;
    carimbar não é: o carimbo só sai por ato humano no cadastro, então um
    timeout tiraria o caso da fila até alguém mexer num cadastro já correto."""
    algum_vazio = False
    for degrau in viaveis:
        alvo = _destinatarios_do_degrau(supabase, caso, degrau, agora, cadastros, diretoria)
        if alvo is None:
            return False
        if alvo[0]:
            return False
        algum_vazio = True
    return algum_vazio


def _alertar_cadastro_incompleto(supabase, travados: list[tuple[dict, str]]) -> bool:
    """Um email por rodada, com todos os casos que travaram nela. Devolve se o
    alerta chegou a alguém, que é o que autoriza o carimbo.

    Sinal operacional de verdade, e não `logger.warning`: um job que roda a
    cada 10 minutos enche o log de aviso que ninguém lê. O carimbo é condicional
    (`IS NULL`), então cada caso aparece em um alerta só, e um teto de emails
    por rodada deixaria os que sobrassem sem sinal nenhum, para sempre."""
    corpo = ALERTA_CADASTRO_ABERTURA + "".join(
        ALERTA_CADASTRO_LINHA.format(
            protocolo=caso.get("protocolo") or caso["id"], setor=caso.get("setor") or "(sem setor)", degrau=degrau
        )
        for caso, degrau in travados
    )
    return bool(
        avisar_admins_tecnicos(
            supabase, ALERTA_CADASTRO_ASSUNTO.format(quantos=len(travados)), corpo + ALERTA_CADASTRO_FECHO
        )
    )


def destravar_setor(supabase, setor: str) -> int:
    """Devolve à varredura os casos DESTE setor que pararam por não ter a quem
    escalonar. Devolve quantos voltaram.

    Chamada quando o cadastro do setor ganha alguém que a escada consulta. O
    carimbo não queimou degrau nenhum, então a escada volta a subir do ponto em
    que parou. Só este setor: o buraco de cadastro é por setor, e destravar o
    hospital inteiro devolveria à fila casos que seguem sem ninguém."""
    return _destravar(supabase, lambda q: q.eq("setor", setor))


def destravar_todos(supabase) -> int:
    """Devolve à varredura TODO caso travado. Devolve quantos voltaram.

    Chamada quando alguém ganha o perfil de Diretoria Executiva: essa é a
    segunda ponta do cadastro, e ela vale para o hospital inteiro. Caso travado
    num setor que já tem responsáveis só volta por aqui, porque cadastrar
    responsável de novo num setor que já tem não conserta nada (issue #373)."""
    return _destravar(supabase, lambda q: q)


def _destravar(supabase, filtrar) -> int:
    """O update do destrave, sempre restrito às linhas realmente carimbadas.

    Sem o `not.is null` o update reescreveria todo o histórico de protocolos a
    cada cadastro de responsável, e devolveria todas elas no corpo da resposta.

    Melhor esforço: quem chama acabou de gravar um cadastro, e falhar aqui não
    pode desfazê-lo. O caso volta no próximo ato de cadastro, e o job não fica
    pior do que estava."""
    try:
        result = filtrar(
            supabase.table("ouvidoria_protocolos")
            .update({"escalonamento_impossivel_em": None})
            .not_.is_("escalonamento_impossivel_em", "null")
        ).execute()
    except Exception:  # noqa: BLE001
        logger.warning("[Ouvidoria] Falha ao destravar o escalonamento de casos travados")
        return 0
    return len(result.data or [])


def _reivindicar_impossivel(supabase, manifestacao_id: str, agora: dt.datetime) -> bool:
    """Carimba o caso como sem saída.

    Quem impede o alerta de se repetir a cada 10 minutos é o filtro da varredura
    (`escalonamento_impossivel_em IS NULL`), que tira da leitura o caso já
    carimbado. O `IS NULL` daqui protege de outra coisa: duas rodadas
    concorrentes carimbando o mesmo caso. O `status` repete a guarda do carimbo
    de degrau."""
    try:
        result = (
            supabase.table("ouvidoria_protocolos")
            .update({"escalonamento_impossivel_em": agora.isoformat()})
            .eq("id", manifestacao_id)
            # Mesma guarda do carimbo de degrau: o caso pode ter sido respondido
            # entre a leitura e a escrita, e travar um caso que já andou o
            # deixaria fora da varredura se ele voltasse à área depois.
            .eq("status", AGUARDANDO_AREA)
            .is_("escalonamento_impossivel_em", "null")
            .execute()
        )
    except Exception:
        logger.error("[Ouvidoria] Falha ao carimbar o escalonamento impossível do caso %s", manifestacao_id)
        return False
    return bool(result.data)


def _gatilhos_do_caso(caso: dict, feriados: frozenset[dt.date]):
    """Os quatro instantes da escada para este caso, ou None quando não dá para
    calcular (caso sem prazo, sem marco de validação ou com data ilegível). Um
    caso torto não pode calar o escalonamento dos demais."""
    bruto = caso.get("prazo_area_em")
    inicio = caso.get("validada_em")
    if not bruto or not inicio:
        return None
    try:
        return gatilhos_de_escalonamento(
            dt.datetime.fromisoformat(str(inicio)),
            dt.datetime.fromisoformat(str(bruto)),
            feriados,
        )
    except ValueError:
        logger.error(
            "[Ouvidoria] Caso %s com prazo ou validação ilegível: %r / %r",
            caso.get("protocolo"),
            bruto,
            inicio,
        )
        return None


def _subir_degrau(
    supabase,
    caso: dict,
    degrau: Degrau,
    agora: dt.datetime,
    feriados: frozenset[dt.date],
    cadastros: dict,
    diretoria: list,
) -> str:
    """Sobe um degrau: carimbo, notificações, movimento na trilha e entrega do
    que a janela comercial permitir.

    Devolve `SUBIU`, `SEM_NINGUEM` (não há a quem avisar, e o caso pode estar
    travado por cadastro) ou `ADIADO` (qualquer outro motivo de não ter subido:
    leitura falha, corrida, notificação que não gravou). Nenhum dos três queima
    o degrau."""
    alvo = _destinatarios_do_degrau(supabase, caso, degrau, agora, cadastros, diretoria)
    if alvo is None:
        # Leitura do cadastro falhou. Não é a mesma coisa que cadastro vazio:
        # tirar o caso da varredura por causa de um timeout o deixaria parado
        # até alguém mexer no cadastro sem necessidade.
        return ADIADO
    destinatarios, gatilho, detalhe = alvo
    if not destinatarios:
        # Sem ninguém para cobrar hoje. Sem carimbo de degrau: quando o
        # cadastro tiver gente, a escada sobe do ponto em que parou.
        logger.warning(
            "[Ouvidoria] Caso %s sem destinatário para o degrau %s (setor %s)",
            caso.get("protocolo"),
            degrau.nome,
            caso.get("setor"),
        )
        return SEM_NINGUEM

    if not _reivindicar_degrau(supabase, caso["id"], degrau, agora):
        return ADIADO

    quando = quando_enviar(agora, caso.get("gravidade"), feriados)
    criadas = []
    for destinatario in destinatarios:
        notificacao = registrar(
            supabase,
            manifestacao_id=caso["id"],
            gatilho=gatilho,
            destinatario_nome=destinatario.nome,
            destinatario_email=destinatario.email,
            papel_destinatario=destinatario.papel,
            enviar_a_partir_de=quando,
            detalhe=detalhe,
        )
        if notificacao:
            criadas.append(notificacao)

    if not criadas:
        # Nenhuma notificação gravou (ex.: schema de produção atrás do código).
        # Sem linha na fila não há cobrança nem botão de reenvio: devolve o
        # degrau para a próxima rodada em vez de queimá-lo em silêncio.
        logger.error("[Ouvidoria] Caso %s: nenhuma notificação do degrau %s gravou", caso.get("protocolo"), degrau.nome)
        _devolver_degrau(supabase, caso["id"], degrau, agora.isoformat())
        return ADIADO

    registrar_movimento(supabase, caso["id"], degrau.observacao)
    for notificacao in criadas:
        despachar_agora_se_puder(supabase, notificacao, agora, feriados)
    return SUBIU


def _destinatarios_do_degrau(
    supabase, caso: dict, degrau: Degrau, agora: dt.datetime, cadastros: dict, diretoria: list
) -> tuple[list[Destinatario], str, str | None] | None:
    """Quem recebe este degrau, com que gatilho e com que contexto extra.

    None significa que a LEITURA do cadastro falhou. Lista de destinatários
    vazia significa que o cadastro está mesmo vazio. Os dois adiam o degrau e
    nenhum dos dois o queima, mas só o segundo tira o caso da varredura."""
    if degrau is DIRETORIA:
        diretores = _diretoria_da_rodada(supabase, diretoria)
        return None if diretores is None else (diretores, degrau.gatilho, None)

    responsaveis = _cadastro_da_rodada(supabase, caso.get("setor") or "", cadastros)
    if responsaveis is None:
        return None
    hoje = agora.astimezone(FUSO).date()
    destinatarios = destinatarios_nos_papeis(responsaveis, hoje, degrau.papeis)
    if destinatarios:
        return (destinatarios, degrau.gatilho, None)

    if degrau is not GESTOR:
        return ([], degrau.gatilho, None)

    # Sem gestor cadastrado o degrau não some: vira o alerta de cadastro à
    # Diretoria, com o motivo escrito, porque ela precisa saber por que o caso
    # chegou nela um dia antes do previsto.
    diretores = _diretoria_da_rodada(supabase, diretoria)
    if diretores is None:
        return None
    # Sem `detalhe`: desde a issue #373 este gatilho tem montador próprio, e a
    # abertura dele já diz que o setor não tem gestor. Repetir a frase no
    # detalhe deixaria o email dizendo a mesma coisa duas vezes seguidas.
    return (diretores, GATILHO_ALERTA_CADASTRO_SETOR, None)


def _cadastro_da_rodada(supabase, setor: str, cadastros: dict) -> list[dict] | None:
    """O cadastro do setor, lido uma vez por rodada. Falha de leitura NÃO entra
    no cache: a rodada seguinte tenta de novo em vez de herdar o erro."""
    if setor in cadastros:
        return cadastros[setor]
    responsaveis = _carregar_responsaveis(supabase, setor)
    if responsaveis is not None:
        cadastros[setor] = responsaveis
    return responsaveis


def _diretoria_da_rodada(supabase, cache: list) -> list[Destinatario] | None:
    """A Diretoria Executiva, lida uma vez por rodada. Mesma regra do cadastro:
    falha de leitura não é memorizada."""
    if cache:
        return cache[0]
    diretores = _diretoria(supabase)
    if diretores is not None:
        cache.append(diretores)
    return diretores


def _diretoria(supabase) -> list[Destinatario] | None:
    """A Diretoria Executiva como destinatários. None quando a LEITURA falhou,
    que não é a mesma coisa que ninguém ter o perfil (issue #373)."""
    crus = ler_diretoria_executiva(supabase)
    if crus is None:
        return None
    return [
        Destinatario(
            nome=d.get("nome_completo") or d["email"],
            email=d["email"],
            papel=PAPEL_DIRETORIA,
            # O campo significa "setor acionado sem titular vigente" (issue
            # #325), que não é o caso aqui: quem chegou a este ponto é a
            # própria Diretoria.
            alerta_diretoria=False,
        )
        for d in crus
    ]


def _carregar_responsaveis(supabase, setor: str) -> list[dict] | None:
    """O cadastro de quem responde pelo setor. None significa que a leitura
    falhou, que não é a mesma coisa que setor sem ninguém."""
    try:
        result = (
            supabase.table("ouvidoria_setor_responsaveis")
            .select("setor, papel, nome, email, vigencia_inicio, vigencia_fim")
            .eq("setor", setor)
            .execute()
        )
    except Exception:
        logger.error("[Ouvidoria] Falha ao carregar os responsáveis do setor %s", setor)
        return None
    return result.data or []


def _reivindicar_degrau(supabase, manifestacao_id: str, degrau: Degrau, agora: dt.datetime) -> bool:
    """Carimba a coluna do degrau antes de cobrar. O update é condicional
    (`IS NULL`): a segunda rodada do job, ou uma rodada concorrente, não acha
    caso para carimbar e não cobra de novo."""
    try:
        result = (
            supabase.table("ouvidoria_protocolos")
            .update({degrau.carimbo: agora.isoformat()})
            .eq("id", manifestacao_id)
            .eq("status", AGUARDANDO_AREA)
            .is_(degrau.carimbo, "null")
            .execute()
        )
    except Exception:
        logger.error("[Ouvidoria] Falha ao carimbar o degrau %s do caso %s", degrau.nome, manifestacao_id)
        return False
    return bool(result.data)


def _devolver_degrau(supabase, manifestacao_id: str, degrau: Degrau, carimbo: str) -> None:
    """Desfaz o carimbo de um degrau cuja cobrança não chegou a existir, para a
    próxima rodada tentar de novo. Só apaga o carimbo desta execução, nunca o
    de outra rodada."""
    try:
        (
            supabase.table("ouvidoria_protocolos")
            .update({degrau.carimbo: None})
            .eq("id", manifestacao_id)
            .eq(degrau.carimbo, carimbo)
            .execute()
        )
    except Exception:
        logger.error("[Ouvidoria] Falha ao devolver o degrau %s do caso %s", degrau.nome, manifestacao_id)


def registrar_movimento(supabase, manifestacao_id: str, observacao: str) -> None:
    """O degrau entra na trilha do caso. Não é transição de estado (o caso
    segue aguardando área), então o insert é direto, no molde do movimento de
    prazo rompido. O carimbo do degrau garante a vez única."""
    try:
        supabase.table("ouvidoria_movimentos").insert(
            {
                "manifestacao_id": manifestacao_id,
                "estado_anterior": AGUARDANDO_AREA,
                "estado_novo": AGUARDANDO_AREA,
                "autor_id": None,
                "autor_nome": "Sistema (escalonamento)",
                "observacao": observacao,
            }
        ).execute()
    except Exception:
        logger.warning("Falha ao gravar o movimento de escalonamento do caso %s", manifestacao_id)


# =====================================================================
# Caso crítico validado: a Diretoria sabe na hora (PRD #318, história 18)
# =====================================================================

OBSERVACAO_CRITICO = "Caso crítico validado: Diretoria Executiva avisada imediatamente."


def alertar_diretoria_caso_critico(
    supabase, manifestacao_id: str, agora: dt.datetime, feriados: frozenset[dt.date]
) -> None:
    """Avisa a Diretoria Executiva de um caso crítico recém validado.

    Não passa pela escada nem pela janela comercial: crítico é justamente o
    caso que não espera o expediente abrir, e `quando_enviar` já sabe disso. O
    carimbo `critico_avisado_em` garante um aviso só por caso, mesmo que a
    validação aconteça de novo depois de uma reabertura.

    Melhor esforço, como o alerta de setor sem titular: o acionamento da área
    já aconteceu quando esta função roda, e falhar aqui não pode desfazê-lo."""
    diretores = _diretoria(supabase)
    if not diretores:
        # None (leitura falhou) e lista vazia (ninguém tem o perfil) param
        # igual aqui: o aviso é melhor esforço e não carimba nada.
        logger.warning("[Ouvidoria] Caso crítico %s sem Diretoria Executiva com email cadastrado", manifestacao_id)
        return

    if not _reivindicar_aviso_critico(supabase, manifestacao_id, agora):
        return

    criadas = []
    for diretor in diretores:
        notificacao = registrar(
            supabase,
            manifestacao_id=manifestacao_id,
            gatilho=GATILHO_CRITICO_IMEDIATO,
            destinatario_nome=diretor.nome,
            destinatario_email=diretor.email,
            papel_destinatario=PAPEL_DIRETORIA,
            enviar_a_partir_de=quando_enviar(agora, "critico", feriados),
        )
        if notificacao:
            criadas.append(notificacao)

    if not criadas:
        logger.error("[Ouvidoria] Caso crítico %s: nenhum aviso à Diretoria gravou", manifestacao_id)
        _desfazer_aviso_critico(supabase, manifestacao_id, agora.isoformat())
        return

    registrar_movimento(supabase, manifestacao_id, OBSERVACAO_CRITICO)
    for notificacao in criadas:
        despachar_agora_se_puder(supabase, notificacao, agora, feriados)


def _reivindicar_aviso_critico(supabase, manifestacao_id: str, agora: dt.datetime) -> bool:
    try:
        result = (
            supabase.table("ouvidoria_protocolos")
            .update({"critico_avisado_em": agora.isoformat()})
            .eq("id", manifestacao_id)
            .is_("critico_avisado_em", "null")
            .execute()
        )
    except Exception:
        logger.error("[Ouvidoria] Falha ao carimbar o aviso de caso crítico %s", manifestacao_id)
        return False
    return bool(result.data)


def _desfazer_aviso_critico(supabase, manifestacao_id: str, carimbo: str) -> None:
    try:
        (
            supabase.table("ouvidoria_protocolos")
            .update({"critico_avisado_em": None})
            .eq("id", manifestacao_id)
            .eq("critico_avisado_em", carimbo)
            .execute()
        )
    except Exception:
        logger.error("[Ouvidoria] Falha ao devolver o aviso de caso crítico %s", manifestacao_id)
