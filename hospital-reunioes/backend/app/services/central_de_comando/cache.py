"""O cache com frescor da Central de Comando (issue #815, ADR 0058, decisão 2).

Porte de `src/lib/analytics/cache.ts` do repositório antigo, com as mesmas
regras, porque são elas que decidem de quando é o número que a tela mostra:

- **Uma hora.** O número buscado vale 60 minutos cravados (`TTL`). Dentro da
  hora, a leitura é servida daqui, sem ir à fonte; com a hora completa, a
  leitura seguinte busca outro.
- **Atualizar agora** (`forcar=True`) vai à fonte mesmo com o número dentro da
  hora, e o número novo passa a ser o guardado.
- **Último valor bom.** Se a fonte falha e há número guardado, a leitura
  devolve o guardado, marcado com "a atualização falhou" e a frase do porquê.
  O carimbo continua sendo o da hora em que o número bom foi buscado: a tela
  nunca zera, e nunca diz que um número velho é novo. Sem número guardado, a
  falha sobe (erro honesto, 502 na rota).
- **Só falha da fonte vira último valor bom.** Quem lê diz o que é falha da
  fonte (`falhas`); se não disser, nada vira último valor bom. Outro erro sobe
  mesmo com número guardado: a configuração que sumiu é 503, e defeito do
  código é defeito, não "falha passageira". A frase da falha declarada vai
  para a tela, então só se declara exceção de frase fixa e segura.
- **Registro de frescor.** Cada chave guarda quando foi renovada e se a última
  tentativa falhou. A marca de falha fica até a próxima busca dar certo.

**Em memória do processo, sem banco.** A Central é stateless: nenhuma tabela,
nenhuma migration. O backend roda com um processo só (`CMD` do Dockerfile, sem
`--workers`), como a Central antiga rodava, então este cache é o cache do app.
Se um dia rodar com mais de um processo, cada um terá o seu: a mesma tela pode
mostrar carimbos diferentes conforme o processo que responder, cada processo
vai à fonte uma vez por hora e chave, e o Atualizar agora só renova o processo
que o atendeu. É este o ponto que precisaria mudar (um cache compartilhado),
como o PRD #809 já registra. Deploy do backend zera o cache: a primeira leitura
depois de cada deploy vai à fonte (aceito na ADR 0058).

**Chaves finitas.** A chave é tela e período (`telas.py`), e as telas e os
períodos são poucos e fixos: nada precisa ser despejado.

**Threads.** A rota roda a leitura numa thread (`anyio.to_thread`), então duas
leituras podem chegar juntas. A trava protege só o registro; a ida à fonte
corre fora dela, para uma fonte lenta não segurar a leitura das outras chaves.
**Uma ida por chave de cada vez** (issue #858): a leitura comum que chega com
outra ida da mesma chave no ar espera por ela e serve o que ela trouxe. Com
várias abas abertas renovando na mesma hora, é uma ida à fonte, e não uma por
aba. O Atualizar agora não espera: vai por conta própria. Uma falha que volta
depois de outra leitura já ter renovado a chave não apaga o número novo: é ele
que as duas devolvem.

**Espera depois de falha** (issue #858). Depois de uma falha da fonte numa
chave, a leitura comum não volta a ela por `ESPERA_DEPOIS_DE_FALHA`: serve o
último valor bom (ou repete o erro, sem número guardado). O Atualizar agora
força mesmo assim.

**Sincronia pelo Atualizar agora** (issue #858). Cada chave diz de que fontes
vêm os números dela (fonte e período). O Atualizar agora que dá certo vence as
outras chaves da mesma fonte, que buscam na próxima leitura: a lente de um
Objetivo, a galeria e a tela do Instagram não ficam com números diferentes
para a mesma métrica.

O Ao vivo nunca passa por aqui (glossário, "Ao vivo"): é o único número em
tempo real da Central e não é guardado.
"""

from __future__ import annotations

import copy
import threading
from collections.abc import Callable, Hashable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

# A hora do cache: o número vale 60 minutos, como na Central antiga. A tela
# aberta relê quando o número faz 1 hora, pela leitura comum (issue #858).
TTL = timedelta(hours=1)

# Depois de uma falha da fonte, a leitura comum não volta a ela por este tempo
# (issue #858): serve o último valor bom, ou repete o erro, sem nova ida. Sem
# isso, com a fonte fora e o número vencido, toda leitura ia bater nela de novo.
# O Atualizar agora não espera.
ESPERA_DEPOIS_DE_FALHA = timedelta(minutes=5)


def agora_utc() -> datetime:
    """O relógio do cache, isolado para os testes o controlarem."""
    return datetime.now(UTC)


@dataclass(frozen=True)
class Frescor:
    """De quando é o número e se a última tentativa de renová-lo falhou.

    `atualizado_em` é a hora em que a fonte entregou o número que está sendo
    mostrado, e não a hora da leitura. `motivo` é a frase da falha, a mesma que
    a rota mostraria no erro, para a tela dizer por que não atualizou.
    """

    atualizado_em: datetime | None
    atualizacao_falhou: bool = False
    motivo: str | None = None

    def como_dict(self) -> dict[str, Any]:
        """O frescor como vai no payload de toda tela: hora em ISO 8601, com o
        fuso (UTC). Quem a escreve no horário do hospital é a tela."""
        return {
            "atualizado_em": self.atualizado_em.isoformat(timespec="seconds") if self.atualizado_em else None,
            "atualizacao_falhou": self.atualizacao_falhou,
            "motivo": self.motivo,
        }


@dataclass(frozen=True)
class Leitura[T]:
    """O valor e o frescor dele, lidos juntos: o número nunca sai daqui sem
    dizer de quando é, e o carimbo nunca é de outra leitura."""

    valor: T
    frescor: Frescor


@dataclass(frozen=True)
class _Guardado:
    valor: Any
    frescor: Frescor
    fontes: frozenset[Hashable] = frozenset()


@dataclass(frozen=True)
class _Falha:
    """A última ida à fonte que falhou numa chave: quando, e o erro, para a
    leitura dentro da espera repetir sem ir à fonte."""

    quando: datetime | None
    erro: Exception


class CacheComFrescor:
    """O cache de uma hora com o registro de frescor de cada chave.

    `relogio` existe para os testes; o do processo é `agora_utc`.
    """

    def __init__(self, ttl: timedelta = TTL, relogio: Callable[[], datetime] | None = None):
        self._ttl = ttl
        # Procurado a cada leitura, e não guardado na construção: é assim que o
        # teste troca o relógio da instância do processo (`agora_utc`).
        self._relogio = relogio or (lambda: agora_utc())
        self._guardados: dict[Hashable, _Guardado] = {}
        # A ida à fonte que está no ar, por chave: quem chega a espera.
        self._no_ar: dict[Hashable, threading.Event] = {}
        # A falha da fonte que ainda segura a leitura comum, por chave.
        self._falhas: dict[Hashable, _Falha] = {}
        # As chaves vencidas pelo Atualizar agora de uma vizinha da mesma fonte,
        # cada uma com a marca do clique que a venceu: uma busca que saiu antes
        # do clique volta com número de antes dele, e não tira a marca.
        self._vencidas: dict[Hashable, int] = {}
        self._cliques = 0
        self._trava = threading.Lock()

    def ler[T](
        self,
        chave: Hashable,
        buscar: Callable[[], T],
        *,
        forcar: bool = False,
        falhas: tuple[type[Exception], ...] = (),
        fontes: Iterable[Hashable] = (),
    ) -> Leitura[T]:
        """Serve o número guardado se ele está dentro da hora; senão, busca.

        `forcar` é o Atualizar agora: busca mesmo dentro da hora. `falhas` são
        as exceções que querem dizer "a fonte falhou" e, com número guardado,
        viram o último valor bom. Sem número guardado, elas sobem.

        `falhas` começa vazio de propósito: nada vira último valor bom sem ser
        declarado. A frase da exceção declarada vai para a tela (`motivo`) e
        fica guardada aqui, então só entra exceção de frase fixa, sem URL,
        token ou detalhe interno (a `GoogleError` do provedor é assim).

        `fontes` diz de onde vêm os números da chave (fonte e período, como
        `("instagram", "28d")`). O Atualizar agora que dá certo vence as outras
        chaves que dividem uma fonte com ele: a próxima leitura delas busca, e
        as telas vizinhas não ficam com números diferentes para a mesma métrica
        (issue #858). Só marca, não busca junto, então um clique não vira uma
        rajada de idas. A renovação pela hora não vence ninguém: se vencesse,
        cada leitura derrubaria a vizinha, e as telas iam à fonte a toda hora.
        """
        fontes = frozenset(fontes)
        while True:
            with self._trava:
                guardado = self._guardados.get(chave)
                if (
                    guardado is not None
                    and not forcar
                    and chave not in self._vencidas
                    and self._dentro_da_hora(guardado.frescor)
                ):
                    return Leitura(guardado.valor, guardado.frescor)
                falha = self._falhas.get(chave)
                if falha is not None and not forcar and self._dentro_da_espera(falha):
                    if guardado is None:
                        # Uma cópia, e não a guardada: relançar a mesma faria o
                        # traceback dela crescer a cada leitura da espera.
                        raise copy.copy(falha.erro)
                    return Leitura(guardado.valor, guardado.frescor)
                no_ar = self._no_ar.get(chave)
                if no_ar is None or forcar:
                    # Esta leitura vai à fonte. Registra a ida para as leituras
                    # comuns que chegarem esperarem por ela; a forçada que chega
                    # com outra ida no ar vai por conta própria, sem registrar.
                    minha_ida = threading.Event() if no_ar is None else None
                    if minha_ida is not None:
                        self._no_ar[chave] = minha_ida
                    marca = self._vencidas.get(chave)
                    break
            # Outra leitura já foi à fonte por esta chave: espera ela voltar e
            # olha de novo o que ficou guardado.
            no_ar.wait()

        try:
            return self._buscar(chave, buscar, guardado, falhas, fontes, forcar, marca)
        finally:
            if minha_ida is not None:
                with self._trava:
                    del self._no_ar[chave]
                minha_ida.set()

    def _buscar[T](
        self,
        chave: Hashable,
        buscar: Callable[[], T],
        guardado: _Guardado | None,
        falhas: tuple[type[Exception], ...],
        fontes: frozenset[Hashable],
        forcar: bool,
        marca: int | None,
    ) -> Leitura[T]:
        """A ida à fonte, fora da trava, e o registro do que ela trouxe.
        `marca` é a do vencimento da chave quando a ida saiu."""
        try:
            valor = buscar()
        except falhas as exc:
            with self._trava:
                self._falhas[chave] = _Falha(self._relogio(), exc)
                atual = self._guardados.get(chave)
                if atual is not None and atual is not guardado:
                    # Outra leitura renovou a chave enquanto esta esperava a
                    # fonte: o número dela é mais novo que a falha desta.
                    return Leitura(atual.valor, atual.frescor)
                if guardado is None:
                    raise
                frescor = Frescor(guardado.frescor.atualizado_em, atualizacao_falhou=True, motivo=str(exc))
                self._guardados[chave] = _Guardado(guardado.valor, frescor, guardado.fontes)
            return Leitura(guardado.valor, frescor)

        frescor = Frescor(self._relogio())
        with self._trava:
            self._guardados[chave] = _Guardado(valor, frescor, fontes)
            self._falhas.pop(chave, None)
            if self._vencidas.get(chave) == marca:
                self._vencidas.pop(chave, None)
            if forcar and fontes:
                self._vencer_vizinhas(chave, fontes)
        return Leitura(valor, frescor)

    def _vencer_vizinhas(self, chave: Hashable, fontes: frozenset[Hashable]) -> None:
        """Vence as chaves que dividem uma fonte com a que o Atualizar agora
        acabou de renovar. A espera da falha antiga delas cai junto: o clique
        que deu certo mostra que a fonte voltou. Chamado com a trava."""
        self._cliques += 1
        for outra, g in self._guardados.items():
            if outra != chave and g.fontes & fontes:
                self._vencidas[outra] = self._cliques
                self._falhas.pop(outra, None)

    def frescor(self, *chaves: Hashable) -> Frescor:
        """O frescor de uma tela feita de várias chaves: a hora do número mais
        velho, e falhou se a atualização de qualquer uma falhou.

        Chave que nunca foi lida não conta; nenhuma lida é "sem hora". É o
        ponto de extensão para quem guardar uma tela em mais de uma chave (um
        bloco que venha de outra fonte, por exemplo).
        """
        with self._trava:
            registrados = [self._guardados[c].frescor for c in chaves if c in self._guardados]
        if not registrados:
            return Frescor(None)
        return Frescor(
            atualizado_em=min((f.atualizado_em for f in registrados if f.atualizado_em is not None), default=None),
            atualizacao_falhou=any(f.atualizacao_falhou for f in registrados),
            motivo=next((f.motivo for f in registrados if f.motivo), None),
        )

    def limpar(self) -> None:
        """Esquece tudo. Usado pelos testes; o processo só esquece no deploy."""
        with self._trava:
            self._guardados.clear()
            self._falhas.clear()
            self._vencidas.clear()

    def _dentro_da_espera(self, falha: _Falha) -> bool:
        agora = self._relogio()
        return falha.quando is not None and agora is not None and agora - falha.quando < ESPERA_DEPOIS_DE_FALHA

    def _dentro_da_hora(self, frescor: Frescor) -> bool:
        return frescor.atualizado_em is not None and self._relogio() - frescor.atualizado_em < self._ttl


# O cache do processo: um só para todas as telas da Central.
cache_da_central = CacheComFrescor()
