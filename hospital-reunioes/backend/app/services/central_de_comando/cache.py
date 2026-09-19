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
  fonte (`falhas`). Outro erro sobe mesmo com número guardado: a configuração
  que sumiu é 503, e defeito do código é defeito, não "falha passageira".
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
corre fora dela, e duas leituras da mesma chave vencida ao mesmo tempo vão as
duas à fonte (a última a voltar é a que fica). Com um Super admin olhando, é
raro e barato, e evita que uma fonte lenta segure a leitura das outras telas.
Uma falha que volta depois de outra leitura já ter renovado a chave não apaga
o número novo: é ele que as duas devolvem.

O Ao vivo nunca passa por aqui (glossário, "Ao vivo"): é o único número em
tempo real da Central e não é guardado.
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Hashable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

# A hora do cache: o número vale 60 minutos, como na Central antiga. É também o
# ritmo da renovação automática da tela aberta, no front.
TTL = timedelta(hours=1)


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
        self._trava = threading.Lock()

    def ler[T](
        self,
        chave: Hashable,
        buscar: Callable[[], T],
        *,
        forcar: bool = False,
        falhas: tuple[type[Exception], ...] = (Exception,),
    ) -> Leitura[T]:
        """Serve o número guardado se ele está dentro da hora; senão, busca.

        `forcar` é o Atualizar agora: busca mesmo dentro da hora. `falhas` são
        as exceções que querem dizer "a fonte falhou" e, com número guardado,
        viram o último valor bom. Sem número guardado, elas sobem.
        """
        with self._trava:
            guardado = self._guardados.get(chave)
            if guardado is not None and not forcar and self._dentro_da_hora(guardado.frescor):
                return Leitura(guardado.valor, guardado.frescor)

        try:
            valor = buscar()
        except falhas as exc:
            with self._trava:
                atual = self._guardados.get(chave)
                if atual is not None and atual is not guardado:
                    # Outra leitura renovou a chave enquanto esta esperava a
                    # fonte: o número dela é mais novo que a falha desta.
                    return Leitura(atual.valor, atual.frescor)
                if guardado is None:
                    raise
                frescor = Frescor(guardado.frescor.atualizado_em, atualizacao_falhou=True, motivo=str(exc))
                self._guardados[chave] = _Guardado(guardado.valor, frescor)
            return Leitura(guardado.valor, frescor)

        frescor = Frescor(self._relogio())
        with self._trava:
            self._guardados[chave] = _Guardado(valor, frescor)
        return Leitura(valor, frescor)

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
            atualizado_em=min(f.atualizado_em for f in registrados if f.atualizado_em is not None),
            atualizacao_falhou=any(f.atualizacao_falhou for f in registrados),
            motivo=next((f.motivo for f in registrados if f.motivo), None),
        )

    def limpar(self) -> None:
        """Esquece tudo. Usado pelos testes; o processo só esquece no deploy."""
        with self._trava:
            self._guardados.clear()

    def _dentro_da_hora(self, frescor: Frescor) -> bool:
        return frescor.atualizado_em is not None and self._relogio() - frescor.atualizado_em < self._ttl


# O cache do processo: um só para todas as telas da Central.
cache_da_central = CacheComFrescor()
