"""Retenção com anonimização após 5 anos (issue #343, PRD #319, ADR 0034).

A política de retenção da Ouvidoria: manifestação encerrada há mais de cinco
anos perde o Dossiê (relato, identificação de quem manifestou, anexos, e o
conteúdo dos registros filhos) e mantém os campos que os relatórios contam
(tipo, área, gravidade, canal, datas, marcos e desfecho). O ato entra na trilha
imutável e o carimbo garante que rodar de novo não mexe em nada.

Cobre os critérios de aceite da issue pelo seam do service (a função que o
scheduler chama), mais o registro do job no scheduler e a migration. Nenhum
email sai daqui: a retenção não notifica ninguém.
"""

from __future__ import annotations

import datetime as dt
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services import ouvidoria_respostas, ouvidoria_retencao  # noqa: E402

# Relógio congelado: 26 de agosto de 2026.
AGORA = dt.datetime(2026, 8, 26, 12, 0, tzinfo=dt.UTC)

# Encerrada em 2020: passou dos cinco anos com folga.
ENCERRADA_HA_SEIS_ANOS = "2020-08-26T12:00:00+00:00"
# Encerrada em 2024: dentro dos cinco anos.
ENCERRADA_HA_DOIS_ANOS = "2024-08-26T12:00:00+00:00"

# A resposta que a área digitou no portal do setor. Ela viaja inteira para a
# trilha (issue #374) e é servida pela rota do histórico de respostas.
RESPOSTA_DA_AREA = "Falamos com a paciente Joana da Silva no telefone 11 99999-0000 e pedimos desculpas."


def _manifestacao(numero: int = 7, **overrides) -> dict:
    """Caso encerrado há seis anos, com o Dossiê inteiro preenchido."""
    row = {
        "id": f"uuid-{numero}",
        "numero": numero,
        "protocolo": f"2020-{numero:04d}",
        "status": "encerrado",
        "data_abertura": "2020-08-01",
        "contato_em": "2020-08-01T10:00:00+00:00",
        "validada_em": "2020-08-02T10:00:00+00:00",
        "respondida_em": "2020-08-10T10:00:00+00:00",
        "encerrada_em": ENCERRADA_HA_SEIS_ANOS,
        "prazo_area_em": "2020-08-09T20:00:00+00:00",
        "tipo_manifestacao": "reclamacao",
        "categoria": "Demora no atendimento",
        "setor": "Recepcao",
        "gravidade": "medio",
        "canal": "telefone",
        "desfecho": "procedente",
        "minutos_pausados": 120,
        # Marcos de relógio do ciclo, todos com valor NÃO nulo de propósito: a
        # preservação deles é o contrato com o módulo de métricas (#341), e um
        # campo que já nasce nulo na fixture não prova preservação nenhuma (o
        # apagado e o preservado ficariam iguais). O caso conta uma história
        # coerente: reincidente, com o prazo da área estourado e uma pausa
        # registrada. Em produção, um caso encerrado normalmente teria
        # `pausada_em` nulo; aqui ele carrega valor para o teste ter o que
        # afirmar.
        "reincidencia": True,
        "reaberta_em": "2020-08-06T09:00:00+00:00",
        "area_estourou_em": "2020-08-09T20:00:01+00:00",
        "pausada_em": "2020-08-04T11:00:00+00:00",
        "anonimo": False,
        "sigilo_reforcado": False,
        # O Dossiê que a retenção apaga.
        "relato_integral": "Joana da Silva, RG 12.345.678, esperou tres horas na recepcao do dia 1.",
        "manifestante_nome": "Joana da Silva",
        "manifestante_contato": "joana@exemplo.com / 11 99999-0000",
        "manifestante_vinculo": "paciente",
        "resumo": "Paciente Joana relata espera acima de tres horas na recepcao.",
        "extrato_para_o_setor": "Espera de tres horas relatada por Joana da Silva. Apurar e responder.",
        "desfecho_descricao": "Confirmada a espera de Joana; a recepcao reforcou a escala.",
        "resposta_da_area": RESPOSTA_DA_AREA,
        "classificacao_ia": {"tipo": "reclamacao", "trecho": "Joana esperou tres horas"},
        "conversa_id": "chatwoot-4821",
        "anonimizada_em": None,
    }
    row.update(overrides)
    return row


def _movimento_de_resposta(manifestacao_id: str = "uuid-7", texto: str = RESPOSTA_DA_AREA) -> dict:
    """O movimento que o portal do setor grava com a resposta inteira dentro."""
    return {
        "id": "mov-resposta",
        "manifestacao_id": manifestacao_id,
        "ocorrido_em": "2020-08-10T10:00:00+00:00",
        "estado_anterior": "aguardando_area",
        "estado_novo": "respondido",
        "autor_id": None,
        "autor_nome": "Carlos Titular",
        "observacao": ouvidoria_respostas.observacao_da_resposta(texto),
    }


def _tentativa_de_contato(numero: int = 1, manifestacao_id: str = "uuid-7") -> dict:
    return {
        "id": f"tentativa-{numero}",
        "manifestacao_id": manifestacao_id,
        "tentada_em": "2020-08-05T14:00:00+00:00",
        "canal": "telefone",
        "observacao": "Liguei para 11 99999-0000; Joana da Silva pediu para retornar amanha.",
        "autor_id": "P10",
        "autor_nome": "Marta Ouvidora",
    }


def _prorrogacao(manifestacao_id: str = "uuid-7") -> dict:
    return {
        "id": "prorrogacao-1",
        "manifestacao_id": manifestacao_id,
        "justificativa": "Precisamos ouvir a enfermeira que atendeu a Joana da Silva antes de responder.",
        "dias_uteis_pedidos": 3,
        "prazo_anterior": "2020-08-09T20:00:00+00:00",
        "prazo_novo": "2020-08-12T20:00:00+00:00",
        "status": "aprovada",
        "solicitada_em": "2020-08-08T10:00:00+00:00",
        "solicitante_nome": "Carlos Titular",
        "solicitante_email": "titular@hsm.br",
        "decidida_em": "2020-08-08T15:00:00+00:00",
        "decidida_por": "P10",
        "decidida_por_nome": "Marta Ouvidora",
        "decisao_justificativa": "Aprovado: ouvir a enfermeira que atendeu a Joana e razoavel.",
    }


def _notificacao(numero: int = 1, manifestacao_id: str = "uuid-7", **overrides) -> dict:
    """A notificação da devolução: o motivo escrito pelo ouvidor viaja no
    `detalhe` (migrations 074 e 075)."""
    row = {
        "id": f"notificacao-{numero}",
        "manifestacao_id": manifestacao_id,
        "gatilho": "devolucao",
        "destinatario_nome": "Carlos Titular",
        "destinatario_email": "titular@hsm.br",
        "papel_destinatario": "titular",
        "status": "enviada",
        "tentativas": 1,
        "enviar_a_partir_de": "2020-08-11T10:00:00+00:00",
        "enviada_em": "2020-08-11T10:01:00+00:00",
        "ultimo_erro": None,
        "detalhe": "Motivo da devolucao: a resposta nao explica a espera de tres horas da Joana da Silva.",
        "criada_em": "2020-08-11T10:00:00+00:00",
    }
    row.update(overrides)
    return row


def _anexo(numero: int = 1, manifestacao_id: str = "uuid-7", **overrides) -> dict:
    row = {
        "id": f"anexo-{numero}",
        "manifestacao_id": manifestacao_id,
        "filename": "foto-joana.jpg",
        "content_type": "image/jpeg",
        "tamanho_bytes": 1024,
        "storage_path": f"2020/anexo-{numero}.jpg",
        "enviado_por": "P10",
        "enviado_por_nome": "Marta Ouvidora",
        "created_at": "2020-08-02T10:00:00+00:00",
    }
    row.update(overrides)
    return row


class _TabelaFake:
    """Fake do PostgREST fiel no que importa: o select projeta só o que foi
    pedido, update e delete filtram antes de agir (inclusive IS NULL e NEQ) e o
    insert devolve a linha com o id que o banco geraria.

    Registra no dono cada UPDATE e cada DELETE executados, para os testes
    conseguirem afirmar que o job NÃO propôs uma escrita, que é diferente de
    ter proposto e não ter casado linha nenhuma."""

    def __init__(self, nome: str, rows: list[dict], dono: _SupabaseFake):
        self.nome = nome
        self.rows = rows
        self.dono = dono
        self._filters: dict = {}
        self._nulos: list[str] = []
        self._diferentes: dict = {}
        self._ate: dict = {}
        self._insert: dict | list | None = None
        self._update: dict | None = None
        self._delete = False
        self._colunas: tuple[str, ...] | None = None
        self._limite: int | None = None

    def select(self, colunas: str = "*", *_a, **_kw):
        if colunas.strip() != "*":
            self._colunas = tuple(c.strip() for c in colunas.split(","))
        return self

    def insert(self, payload):
        self._insert = payload
        return self

    def update(self, payload: dict):
        self._update = payload
        return self

    def delete(self):
        self._delete = True
        return self

    def eq(self, col, value):
        self._filters[col] = value
        return self

    def neq(self, col, value):
        self._diferentes[col] = value
        return self

    def is_(self, col, value):
        assert value in ("null", None)
        self._nulos.append(col)
        return self

    def lte(self, col, value):
        self._ate[col] = value
        return self

    def order(self, col, desc=False):
        self.rows = sorted(self.rows, key=lambda r: str(r.get(col) or ""), reverse=desc)
        return self

    def limit(self, n):
        self._limite = n
        return self

    def _projetar(self, row: dict) -> dict:
        if self._colunas is None:
            return dict(row)
        return {c: row.get(c) for c in self._colunas}

    def execute(self):
        if self._insert is not None:
            self.dono.quebrar_se_pedido(self.nome, "insert")
            novos = self._insert if isinstance(self._insert, list) else [self._insert]
            gravados = []
            for n in novos:
                linha = dict(n)
                linha.setdefault("id", f"{self.nome}-{len(self.rows) + 1}")
                self.rows.append(linha)
                gravados.append(dict(linha))
            return type("R", (), {"data": gravados})()

        if self._update is not None:
            self.dono.escritas.append((self.nome, "update"))
            self.dono.quebrar_se_pedido(self.nome, "update")
        if self._delete:
            self.dono.escritas.append((self.nome, "delete"))
            self.dono.quebrar_se_pedido(self.nome, "delete")

        casadas = [
            r
            for r in self.rows
            if all(r.get(c) == v for c, v in self._filters.items())
            and all(r.get(c) is None for c in self._nulos)
            and all(r.get(c) != v for c, v in self._diferentes.items())
            and all(r.get(c) is not None and str(r.get(c)) <= v for c, v in self._ate.items())
        ]
        if self._limite is not None:
            casadas = casadas[: self._limite]
        if self._update is not None:
            for r in casadas:
                r.update(self._update)
        if self._delete:
            apagadas = [dict(r) for r in casadas]
            for r in casadas:
                self.rows.remove(r)
            return type("R", (), {"data": apagadas})()
        resposta = type("R", (), {"data": [self._projetar(r) for r in casadas]})()
        if self._update is None:
            self.dono.apos_select(self.nome)
        return resposta


class _StorageFake:
    def __init__(self):
        self.removidos: list[tuple[str, str]] = []
        self._bucket = ""

    def from_(self, bucket: str):
        self._bucket = bucket
        return self

    def remove(self, paths: list[str]):
        for p in paths:
            self.removidos.append((self._bucket, p))
        return {"data": []}


class _SupabaseFake:
    def __init__(
        self,
        manifestacoes: list[dict] | None = None,
        anexos: list[dict] | None = None,
        movimentos: list[dict] | None = None,
        tentativas: list[dict] | None = None,
        prorrogacoes: list[dict] | None = None,
        notificacoes: list[dict] | None = None,
    ):
        self.storage = _StorageFake()
        # Escritas propostas ao banco, na ordem. Um caso que o job recusou não
        # pode aparecer aqui.
        self.escritas: list[tuple[str, str]] = []
        # {(tabela, operação)} que devem levantar, para simular schema atrás do
        # código, corrida perdida ou provedor fora do ar.
        self.quebrar: set[tuple[str, str]] = set()
        # Callback disparado depois de cada SELECT numa tabela: é como um teste
        # simula o mundo mudando entre a varredura e a gravação.
        self.gatilhos_de_select: dict[str, list] = {}
        self.tabelas: dict[str, list[dict]] = {
            "ouvidoria_protocolos": manifestacoes if manifestacoes is not None else [_manifestacao()],
            "ouvidoria_anexos": anexos if anexos is not None else [],
            "ouvidoria_movimentos": movimentos if movimentos is not None else [],
            "ouvidoria_tentativas_contato": tentativas if tentativas is not None else [],
            "ouvidoria_prorrogacoes": prorrogacoes if prorrogacoes is not None else [],
            "ouvidoria_notificacoes": notificacoes if notificacoes is not None else [],
        }

    def table(self, nome: str):
        return _TabelaFake(nome, self.tabelas.setdefault(nome, []), self)

    def quebrar_se_pedido(self, tabela: str, operacao: str) -> None:
        if (tabela, operacao) in self.quebrar:
            raise RuntimeError(f"{operacao} recusado em {tabela} (simulado)")

    def apos_select(self, tabela: str) -> None:
        pendentes = self.gatilhos_de_select.get(tabela)
        if pendentes:
            pendentes.pop(0)(self)

    def depois_do_select_em(self, tabela: str, acao) -> None:
        self.gatilhos_de_select.setdefault(tabela, []).append(acao)

    def updates_em(self, tabela: str) -> int:
        return sum(1 for t, op in self.escritas if t == tabela and op == "update")

    def caso(self, indice: int = 0) -> dict:
        return self.tabelas["ouvidoria_protocolos"][indice]


def _todo_o_texto(*valores) -> str:
    partes = []
    for valor in valores:
        if isinstance(valor, dict):
            partes.append(" ".join(str(v) for v in valor.values()))
        elif isinstance(valor, list):
            partes.extend(_todo_o_texto(v) for v in valor)
        else:
            partes.append(str(valor))
    return " ".join(partes)


class TestDossieApagado:
    def test_caso_encerrado_ha_mais_de_cinco_anos_perde_o_dossie(self):
        supabase = _SupabaseFake()

        anonimizadas = ouvidoria_retencao.anonimizar_encerradas_antigas(supabase, AGORA)

        assert anonimizadas == 1
        caso = supabase.caso()
        assert caso["relato_integral"] is None
        assert caso["manifestante_nome"] is None
        assert caso["manifestante_contato"] is None
        # O que sobrou de texto livre não pode carregar quem manifestou.
        assert "Joana" not in _todo_o_texto(caso)

    def test_campos_estatisticos_sobrevivem_inteiros_a_anonimizacao(self):
        """O que os relatórios contam não pode mudar: tipo, área, gravidade,
        canal, datas, marcos e desfecho seguem iguais ao que eram antes."""
        supabase = _SupabaseFake()
        antes = dict(supabase.caso())

        ouvidoria_retencao.anonimizar_encerradas_antigas(supabase, AGORA)

        depois = supabase.caso()
        for campo in ouvidoria_retencao.CAMPOS_ESTATISTICOS:
            assert campo in antes, f"a fixture não cobre o campo estatístico {campo}"
            assert depois[campo] == antes[campo], f"a anonimização mexeu em {campo}"

    def test_nenhum_rastro_do_manifestante_sobra_em_tabela_nenhuma(self):
        """A varredura completa: manifestação, trilha, tentativas de contato,
        prorrogação e anexos. Um único lugar que guarde o nome derruba isto."""
        supabase = _SupabaseFake(
            movimentos=[_movimento_de_resposta()],
            tentativas=[_tentativa_de_contato()],
            prorrogacoes=[_prorrogacao()],
            notificacoes=[_notificacao()],
            anexos=[_anexo()],
        )

        ouvidoria_retencao.anonimizar_encerradas_antigas(supabase, AGORA)

        tudo = _todo_o_texto(*[linhas for linhas in supabase.tabelas.values()])
        assert "Joana" not in tudo
        assert "99999-0000" not in tudo


class TestRespostaDaAreaNaTrilha:
    """Must-fix da review: a resposta da área viaja inteira para a trilha
    (issue #374) e é servida pela rota do histórico. Apagar só a coluna
    `resposta_da_area` deixaria o original legível."""

    def test_o_texto_da_resposta_some_da_trilha(self):
        supabase = _SupabaseFake(movimentos=[_movimento_de_resposta()])

        ouvidoria_retencao.anonimizar_encerradas_antigas(supabase, AGORA)

        movimento = next(m for m in supabase.tabelas["ouvidoria_movimentos"] if m["id"] == "mov-resposta")
        assert movimento["observacao"] is None

    def test_o_historico_de_respostas_deixa_de_entregar_o_relato(self):
        """A prova pela mesma porta que a rota usa: depois da retenção, o
        histórico do caso não devolve mais texto nenhum."""
        supabase = _SupabaseFake(movimentos=[_movimento_de_resposta()])
        assert ouvidoria_respostas.historico(supabase, "uuid-7")[0]["resposta"] == RESPOSTA_DA_AREA

        ouvidoria_retencao.anonimizar_encerradas_antigas(supabase, AGORA)

        assert ouvidoria_respostas.historico(supabase, "uuid-7") == []

    def test_o_fato_registrado_na_trilha_continua_de_pe(self):
        """Sai o conteúdo, fica o fato: quem, quando, de que estado para qual.
        É o que separa anonimização de apagar a auditoria."""
        supabase = _SupabaseFake(movimentos=[_movimento_de_resposta()])

        ouvidoria_retencao.anonimizar_encerradas_antigas(supabase, AGORA)

        movimento = next(m for m in supabase.tabelas["ouvidoria_movimentos"] if m["id"] == "mov-resposta")
        assert movimento["ocorrido_em"] == "2020-08-10T10:00:00+00:00"
        assert movimento["estado_anterior"] == "aguardando_area"
        assert movimento["estado_novo"] == "respondido"
        assert movimento["autor_nome"] == "Carlos Titular"

    def test_a_trilha_de_outro_caso_nao_e_tocada(self):
        supabase = _SupabaseFake(
            manifestacoes=[_manifestacao(7), _manifestacao(8, encerrada_em=ENCERRADA_HA_DOIS_ANOS)],
            movimentos=[
                _movimento_de_resposta("uuid-7"),
                dict(_movimento_de_resposta("uuid-8"), id="mov-vizinho"),
            ],
        )

        ouvidoria_retencao.anonimizar_encerradas_antigas(supabase, AGORA)

        vizinho = next(m for m in supabase.tabelas["ouvidoria_movimentos"] if m["id"] == "mov-vizinho")
        assert vizinho["observacao"] == ouvidoria_respostas.observacao_da_resposta(RESPOSTA_DA_AREA)


class TestRegistrosFilhos:
    def test_observacao_da_tentativa_de_contato_sai_e_a_contagem_fica(self):
        supabase = _SupabaseFake(tentativas=[_tentativa_de_contato(1), _tentativa_de_contato(2)])

        ouvidoria_retencao.anonimizar_encerradas_antigas(supabase, AGORA)

        tentativas = supabase.tabelas["ouvidoria_tentativas_contato"]
        # Quantas vezes e por onde a Ouvidoria tentou é estatística do
        # encerramento por sem retorno: as linhas ficam.
        assert len(tentativas) == 2
        for tentativa in tentativas:
            assert tentativa["observacao"] is None
            assert tentativa["canal"] == "telefone"
            assert tentativa["tentada_em"] == "2020-08-05T14:00:00+00:00"

    def test_justificativas_da_prorrogacao_saem_e_os_numeros_ficam(self):
        supabase = _SupabaseFake(prorrogacoes=[_prorrogacao()])

        ouvidoria_retencao.anonimizar_encerradas_antigas(supabase, AGORA)

        prorrogacao = supabase.tabelas["ouvidoria_prorrogacoes"][0]
        # `justificativa` é NOT NULL com CHECK anti-vazio: vira marcador.
        assert prorrogacao["justificativa"] == ouvidoria_retencao.MARCADOR_ANONIMIZADO
        assert prorrogacao["decisao_justificativa"] is None
        # A taxa de prorrogação por área do PRD #319 sai daqui.
        assert prorrogacao["dias_uteis_pedidos"] == 3
        assert prorrogacao["status"] == "aprovada"
        assert prorrogacao["prazo_anterior"] == "2020-08-09T20:00:00+00:00"
        assert prorrogacao["prazo_novo"] == "2020-08-12T20:00:00+00:00"

    def test_motivo_da_devolucao_sai_do_detalhe_da_notificacao(self):
        """O comentário da migration 068 chama `detalhe` de "nome do gestor",
        mas a 074 e a 075 reaproveitaram a coluna: o motivo da devolução e o da
        reabertura viajam ali, escritos à mão pelo ouvidor."""
        supabase = _SupabaseFake(notificacoes=[_notificacao()])

        ouvidoria_retencao.anonimizar_encerradas_antigas(supabase, AGORA)

        notificacao = supabase.tabelas["ouvidoria_notificacoes"][0]
        assert notificacao["detalhe"] is None
        # O rastro de entrega fica: é do hospital, não de quem manifestou.
        assert notificacao["destinatario_email"] == "titular@hsm.br"
        assert notificacao["gatilho"] == "devolucao"
        assert notificacao["status"] == "enviada"
        assert notificacao["enviada_em"] == "2020-08-11T10:01:00+00:00"

    def test_notificacao_de_outro_caso_nao_e_tocada(self):
        supabase = _SupabaseFake(
            manifestacoes=[_manifestacao(7), _manifestacao(8, encerrada_em=ENCERRADA_HA_DOIS_ANOS)],
            notificacoes=[_notificacao(1, "uuid-7"), _notificacao(2, "uuid-8")],
        )

        ouvidoria_retencao.anonimizar_encerradas_antigas(supabase, AGORA)

        vizinha = next(n for n in supabase.tabelas["ouvidoria_notificacoes"] if n["id"] == "notificacao-2")
        assert vizinha["detalhe"] is not None


class TestQuemNaoEhTocado:
    """As recusas, cada uma com as outras portas escancaradas, e cada guarda
    presa sozinha: a do SELECT pela ausência de escrita proposta, a do UPDATE
    pelo mundo mudando entre a varredura e a gravação."""

    def test_caso_encerrado_ha_menos_de_cinco_anos_fica_intacto(self):
        supabase = _SupabaseFake(manifestacoes=[_manifestacao(encerrada_em=ENCERRADA_HA_DOIS_ANOS)])
        antes = dict(supabase.caso())

        anonimizadas = ouvidoria_retencao.anonimizar_encerradas_antigas(supabase, AGORA)

        assert anonimizadas == 0
        assert supabase.caso() == antes
        assert supabase.escritas == []

    def test_caso_encerrado_sem_o_marco_do_encerramento_fica_intacto(self):
        """Sem `encerrada_em` não há como afirmar que os cinco anos passaram:
        o caso espera decisão humana em vez de perder o Dossiê por chute. É
        esta guarda que segura o histórico importado do NocoDB, que nasceu
        `encerrado` sem marco."""
        supabase = _SupabaseFake(manifestacoes=[_manifestacao(encerrada_em=None)])
        antes = dict(supabase.caso())

        anonimizadas = ouvidoria_retencao.anonimizar_encerradas_antigas(supabase, AGORA)

        assert anonimizadas == 0
        assert supabase.caso() == antes
        assert supabase.escritas == []

    def test_caso_antigo_em_tramitacao_nao_chega_a_ser_proposto_ao_banco(self):
        """Manifestação reaberta por reincidência guarda o `encerrada_em` do
        ciclo anterior. A varredura nem pode propor a escrita: prende a guarda
        do SELECT sozinha, sem depender da do UPDATE."""
        supabase = _SupabaseFake(manifestacoes=[_manifestacao(status="aguardando_area", reincidencia=True)])
        antes = dict(supabase.caso())

        anonimizadas = ouvidoria_retencao.anonimizar_encerradas_antigas(supabase, AGORA)

        assert anonimizadas == 0
        assert supabase.caso() == antes
        assert supabase.escritas == []
        assert supabase.tabelas["ouvidoria_movimentos"] == []

    def test_caso_que_reabre_entre_a_varredura_e_a_gravacao_nao_perde_o_dossie(self):
        """O manifestante voltou no segundo em que o job varria. A guarda do
        UPDATE é a última linha de defesa, e é ela que este teste prende."""
        supabase = _SupabaseFake()

        def _reabre(sb):
            sb.caso()["status"] = "aguardando_area"

        supabase.depois_do_select_em("ouvidoria_protocolos", _reabre)

        anonimizadas = ouvidoria_retencao.anonimizar_encerradas_antigas(supabase, AGORA)

        assert anonimizadas == 0
        assert supabase.caso()["relato_integral"] is not None
        assert supabase.caso()["anonimizada_em"] is None

    def test_caso_ja_carimbado_nao_entra_na_varredura(self):
        supabase = _SupabaseFake(manifestacoes=[_manifestacao(anonimizada_em="2026-01-01T04:00:00+00:00")])
        antes = dict(supabase.caso())

        anonimizadas = ouvidoria_retencao.anonimizar_encerradas_antigas(supabase, AGORA)

        assert anonimizadas == 0
        assert supabase.caso() == antes
        assert supabase.escritas == []

    def test_carimbo_de_rodada_concorrente_barra_a_gravacao(self):
        """Duas rodadas em voo no mesmo caso: quem carimba primeiro ganha, e a
        segunda não reescreve nada. Prende a guarda do carimbo no UPDATE."""
        supabase = _SupabaseFake()

        def _outra_rodada_carimba(sb):
            sb.caso()["anonimizada_em"] = "2026-08-26T04:00:00+00:00"

        supabase.depois_do_select_em("ouvidoria_protocolos", _outra_rodada_carimba)

        anonimizadas = ouvidoria_retencao.anonimizar_encerradas_antigas(supabase, AGORA)

        assert anonimizadas == 0
        assert supabase.caso()["relato_integral"] is not None


class TestTrilha:
    def test_anonimizacao_entra_na_trilha_do_caso(self):
        supabase = _SupabaseFake()

        ouvidoria_retencao.anonimizar_encerradas_antigas(supabase, AGORA)

        movimentos = supabase.tabelas["ouvidoria_movimentos"]
        assert len(movimentos) == 1
        movimento = movimentos[0]
        assert movimento["manifestacao_id"] == "uuid-7"
        # Anonimizar não muda o estado: o caso segue encerrado.
        assert movimento["estado_anterior"] == "encerrado"
        assert movimento["estado_novo"] == "encerrado"
        assert movimento["autor_id"] is None
        assert "anonimiza" in (movimento["observacao"] or "").lower()

    def test_a_observacao_da_trilha_nao_reintroduz_o_dossie(self):
        """Este é o único movimento do caso que sobrevive à limpeza: um nome
        escrito aqui seria dado pessoal que a retenção nunca mais apagaria."""
        supabase = _SupabaseFake()

        ouvidoria_retencao.anonimizar_encerradas_antigas(supabase, AGORA)

        assert "Joana" not in _todo_o_texto(supabase.tabelas["ouvidoria_movimentos"][0])

    def test_o_movimento_descreve_o_ato_em_curso_e_nao_um_servico_ja_feito(self):
        """O movimento é gravado ANTES de qualquer coisa ser apagada, e a
        trilha é append-only. Uma frase no pretérito viraria afirmação falsa e
        permanente se a rodada morresse logo depois daqui, então quem atesta a
        conclusão é o carimbo, e a observação diz isso."""
        supabase = _SupabaseFake()
        supabase.quebrar.add(("ouvidoria_tentativas_contato", "update"))

        ouvidoria_retencao.anonimizar_encerradas_antigas(supabase, AGORA)

        # A rodada morreu no meio: o Dossiê está inteiro e sem carimbo.
        assert supabase.caso()["relato_integral"] is not None
        assert supabase.caso()["anonimizada_em"] is None
        # E o que ficou gravado para sempre na trilha não mente sobre isso.
        observacao = supabase.tabelas["ouvidoria_movimentos"][0]["observacao"]
        assert "anonimizada_em" in observacao
        assert "apagados" not in observacao

    def test_o_movimento_da_propria_retencao_nao_e_apagado_pela_limpeza(self):
        supabase = _SupabaseFake(movimentos=[_movimento_de_resposta()])

        ouvidoria_retencao.anonimizar_encerradas_antigas(supabase, AGORA)

        da_retencao = [
            m
            for m in supabase.tabelas["ouvidoria_movimentos"]
            if m["autor_nome"] == ouvidoria_retencao.AUTOR_DA_RETENCAO
        ]
        assert len(da_retencao) == 1
        assert da_retencao[0]["observacao"] is not None


class TestOQueNaoPodeSumirEmSilencio:
    """Must-fix da review: o registro que prova a legalidade do ato tem que
    existir ANTES de o Dossiê morrer. Se ele não gravar, nada é destruído."""

    def test_falha_ao_gravar_o_movimento_deixa_tudo_intacto(self):
        supabase = _SupabaseFake(
            movimentos=[_movimento_de_resposta()],
            tentativas=[_tentativa_de_contato()],
            anexos=[_anexo()],
        )
        supabase.quebrar.add(("ouvidoria_movimentos", "insert"))
        antes = dict(supabase.caso())

        anonimizadas = ouvidoria_retencao.anonimizar_encerradas_antigas(supabase, AGORA)

        assert anonimizadas == 0
        assert supabase.caso() == antes
        assert supabase.caso()["anonimizada_em"] is None
        # Nada foi destruído: o caso volta inteiro para a fila da próxima rodada.
        assert supabase.tabelas["ouvidoria_anexos"] != []
        assert supabase.storage.removidos == []
        assert supabase.tabelas["ouvidoria_tentativas_contato"][0]["observacao"] is not None
        movimento = next(m for m in supabase.tabelas["ouvidoria_movimentos"] if m["id"] == "mov-resposta")
        assert movimento["observacao"] is not None

    def test_falha_ao_limpar_a_trilha_nao_carimba_o_caso(self):
        """Sem carimbo o caso volta na varredura seguinte, e a limpeza recomeça.
        Carimbar aqui deixaria o relato vivo na trilha para sempre."""
        supabase = _SupabaseFake(movimentos=[_movimento_de_resposta()])
        supabase.quebrar.add(("ouvidoria_movimentos", "update"))

        anonimizadas = ouvidoria_retencao.anonimizar_encerradas_antigas(supabase, AGORA)

        assert anonimizadas == 0
        assert supabase.caso()["anonimizada_em"] is None
        assert supabase.caso()["relato_integral"] is not None

    def test_falha_ao_limpar_a_prorrogacao_nao_carimba_o_caso(self):
        supabase = _SupabaseFake(prorrogacoes=[_prorrogacao()])
        supabase.quebrar.add(("ouvidoria_prorrogacoes", "update"))

        anonimizadas = ouvidoria_retencao.anonimizar_encerradas_antigas(supabase, AGORA)

        assert anonimizadas == 0
        assert supabase.caso()["anonimizada_em"] is None

    def test_falha_ao_limpar_a_notificacao_nao_carimba_o_caso(self):
        supabase = _SupabaseFake(notificacoes=[_notificacao()])
        supabase.quebrar.add(("ouvidoria_notificacoes", "update"))

        anonimizadas = ouvidoria_retencao.anonimizar_encerradas_antigas(supabase, AGORA)

        assert anonimizadas == 0
        assert supabase.caso()["anonimizada_em"] is None
        assert supabase.caso()["relato_integral"] is not None

    def test_rodada_seguinte_reaproveita_o_movimento_e_termina_o_servico(self):
        """A retomada depois de uma falha no meio não duplica a trilha."""
        supabase = _SupabaseFake(movimentos=[_movimento_de_resposta()])
        supabase.quebrar.add(("ouvidoria_protocolos", "update"))

        primeira = ouvidoria_retencao.anonimizar_encerradas_antigas(supabase, AGORA)
        supabase.quebrar.clear()
        segunda = ouvidoria_retencao.anonimizar_encerradas_antigas(supabase, AGORA + dt.timedelta(days=1))

        assert primeira == 0
        assert segunda == 1
        da_retencao = [
            m
            for m in supabase.tabelas["ouvidoria_movimentos"]
            if m["autor_nome"] == ouvidoria_retencao.AUTOR_DA_RETENCAO
        ]
        assert len(da_retencao) == 1
        assert supabase.caso()["relato_integral"] is None


class TestFreio:
    """O job destrói dado sozinho, de madrugada, sem backup. Precisa ter como
    parar sem esperar deploy de código."""

    def test_com_o_freio_puxado_nada_e_anonimizado(self, monkeypatch):
        monkeypatch.setattr(ouvidoria_retencao.settings, "ouvidoria_retencao_ativa", False)
        supabase = _SupabaseFake(
            movimentos=[_movimento_de_resposta()], anexos=[_anexo()], notificacoes=[_notificacao()]
        )
        antes = dict(supabase.caso())

        anonimizadas = ouvidoria_retencao.anonimizar_encerradas_antigas(supabase, AGORA)

        assert anonimizadas == 0
        assert supabase.caso() == antes
        assert supabase.escritas == []
        assert supabase.tabelas["ouvidoria_anexos"] != []
        assert supabase.storage.removidos == []

    def test_por_default_a_retencao_esta_ligada(self):
        """A política do PRD existe desde o primeiro dia. O default ligado não
        destrói nada hoje, porque nenhum caso tem cinco anos."""
        from app.config import Settings

        assert Settings.model_fields["ouvidoria_retencao_ativa"].default is True


class TestAnexos:
    def test_anexos_do_caso_saem_do_banco_e_do_storage(self):
        supabase = _SupabaseFake(anexos=[_anexo(1), _anexo(2)])

        ouvidoria_retencao.anonimizar_encerradas_antigas(supabase, AGORA)

        assert supabase.tabelas["ouvidoria_anexos"] == []
        caminhos = {caminho for _bucket, caminho in supabase.storage.removidos}
        assert caminhos == {"2020/anexo-1.jpg", "2020/anexo-2.jpg"}
        assert {bucket for bucket, _c in supabase.storage.removidos} == {"anexos-ouvidoria"}

    def test_anexo_de_outro_caso_nao_e_apagado(self):
        """O caso vizinho é recente: o binário dele não pode ir junto."""
        supabase = _SupabaseFake(
            manifestacoes=[_manifestacao(7), _manifestacao(8, encerrada_em=ENCERRADA_HA_DOIS_ANOS)],
            anexos=[_anexo(1, manifestacao_id="uuid-7"), _anexo(9, manifestacao_id="uuid-8")],
        )

        ouvidoria_retencao.anonimizar_encerradas_antigas(supabase, AGORA)

        restantes = supabase.tabelas["ouvidoria_anexos"]
        assert [a["id"] for a in restantes] == ["anexo-9"]
        assert supabase.storage.removidos == [("anexos-ouvidoria", "2020/anexo-1.jpg")]


class TestIdempotencia:
    def test_segunda_execucao_nao_muda_nada_nem_gera_movimento_novo(self):
        supabase = _SupabaseFake(
            anexos=[_anexo(1)],
            movimentos=[_movimento_de_resposta()],
            tentativas=[_tentativa_de_contato()],
            prorrogacoes=[_prorrogacao()],
            notificacoes=[_notificacao()],
        )

        primeira = ouvidoria_retencao.anonimizar_encerradas_antigas(supabase, AGORA)
        depois_da_primeira = {nome: [dict(r) for r in linhas] for nome, linhas in supabase.tabelas.items()}
        removidos_na_primeira = list(supabase.storage.removidos)

        segunda = ouvidoria_retencao.anonimizar_encerradas_antigas(supabase, AGORA + dt.timedelta(days=1))

        assert primeira == 1
        assert segunda == 0
        assert supabase.tabelas == depois_da_primeira
        assert supabase.storage.removidos == removidos_na_primeira


class TestDataDeCorte:
    def test_corte_recua_cinco_anos_no_mesmo_dia(self):
        assert ouvidoria_retencao.data_de_corte(AGORA) == dt.datetime(2021, 8, 26, 12, 0, tzinfo=dt.UTC)

    def test_vinte_e_nove_de_fevereiro_recua_para_o_dia_28(self):
        """2024 é bissexto, 2019 não: sem tratar isso o job quebraria no dia."""
        bissexto = dt.datetime(2024, 2, 29, 12, 0, tzinfo=dt.UTC)

        assert ouvidoria_retencao.data_de_corte(bissexto) == dt.datetime(2019, 2, 28, 12, 0, tzinfo=dt.UTC)


class TestMigration:
    """A 079 dá ao caso o carimbo de idempotência da retenção, o índice da
    varredura e o único furo (estreito) na imutabilidade da trilha."""

    @pytest.fixture
    def ddl(self) -> str:
        caminho = os.path.join(
            os.path.dirname(__file__),
            "..",
            "..",
            "supabase",
            "migrations",
            "079_ouvidoria_retencao_anonimizacao.sql",
        )
        with open(caminho, encoding="utf-8") as f:
            return f.read().lower()

    @pytest.fixture
    def comandos(self, ddl) -> str:
        """Só o SQL, sem os comentários: afirmar o que a migration NÃO faz
        exige olhar os comandos, não a prosa que explica o porquê."""
        return "\n".join(linha for linha in ddl.splitlines() if not linha.strip().startswith("--"))

    def test_caso_ganha_o_carimbo_de_anonimizacao(self, ddl):
        assert "add column if not exists anonimizada_em" in ddl

    def test_migration_e_idempotente(self, ddl):
        assert "add column if not exists" in ddl
        assert "create index if not exists" in ddl
        assert "create or replace function" in ddl
        assert "drop trigger if exists" in ddl

    def test_indice_cobre_exatamente_a_varredura_do_job(self, ddl):
        assert "idx_ouvidoria_protocolos_retencao" in ddl
        assert "encerrada_em" in ddl
        assert "anonimizada_em is null" in ddl
        assert "'encerrado'" in ddl

    def test_a_guarda_da_trilha_so_aceita_zerar_a_observacao(self, ddl):
        """Primeiro eixo do caminho estreito: qualquer outra coluna diferente,
        ou uma observação com texto novo, continua levantando exceção."""
        assert "new.observacao is not null" in ddl
        for coluna in ("id", "manifestacao_id", "ocorrido_em", "estado_anterior", "estado_novo", "autor_nome"):
            assert f"new.{coluna}" in ddl and "is distinct from" in ddl

    def test_a_guarda_da_trilha_so_aceita_caso_coberto_pela_politica(self, ddl):
        """Segundo eixo: não basta alguém ter carimbado a manifestação, o
        gatilho confere a condição da política na linha do caso."""
        assert "interval '5 years'" in ddl
        assert "p.status = 'encerrado'" in ddl
        assert "p.encerrada_em is not null" in ddl

    def test_o_delete_da_trilha_continua_barrado(self, comandos):
        """Terceiro eixo: só o gatilho de UPDATE de `ouvidoria_movimentos`
        troca de função. DELETE e o log de acesso ficam onde estavam."""
        assert "before update on ouvidoria_movimentos" in comandos
        assert "ouvidoria_movimento_anonimizavel" in comandos
        assert "before delete" not in comandos
        assert "ouvidoria_acessos" not in comandos


class TestJobNoScheduler:
    """A retenção roda sozinha, sem ninguém pedir."""

    def test_job_de_retencao_esta_registrado(self):
        from app.cron import scheduler as cron

        try:
            cron.start_scheduler()
            assert cron.scheduler.get_job("retencao_ouvidoria") is not None
        finally:
            cron.stop_scheduler()
