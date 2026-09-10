/**
 * A seção "O que muda" do modal (issue #676, PRD #673, ADR 0054, decisão 7).
 *
 * O texto vem do bloco "Para o diretor" da issue e do de cada parte, lido do
 * GitHub e guardado no cache da Demanda. Ninguém o digita no app, e nada aqui é
 * técnico: título de fatia, número, link e nome de label não aparecem, porque o
 * diretor não vê nada do GitHub (decisão 9).
 *
 * O texto é desenhado como TEXTO, com um Markdown simples de negrito e lista.
 * Nada vira HTML nem link: ele vem de fora do app, e um `dangerouslySetInnerHTML`
 * aqui transformaria o corpo de uma issue em elemento da nossa tela.
 *
 * Sem Vínculo não há seção: é o mesmo `temSelo` do card que decide, e não uma
 * segunda condição escrita aqui, que divergiria dele na primeira mudança.
 */

import {
  BlocoDoTextoSimples,
  blocosDoTextoSimples,
  Demanda,
  ETAPA_CLASSE,
  ETAPA_ROTULO,
  EtapaDemanda,
  ParteDaEntrega,
  PedacoForte,
  temSelo,
} from "./demandas";

export const TITULO_O_QUE_MUDA = "O que muda";

/**
 * O que a tela diz no lugar do texto que ainda não existe.
 *
 * A mesma frase para a raiz e para a parte: as duas ausências significam a
 * mesma coisa para quem lê, e mostrar o corpo técnico da issue no lugar dela é
 * exatamente o que a decisão 7 proíbe.
 */
export const SEM_O_QUE_MUDA = "Descrição em preparação";

function Pedacos({ linha }: { linha: PedacoForte[] }) {
  return (
    <>
      {linha.map((pedaco, i) =>
        pedaco.forte ? (
          <strong key={i} className="font-semibold text-text">
            {pedaco.texto}
          </strong>
        ) : (
          <span key={i}>{pedaco.texto}</span>
        ),
      )}
    </>
  );
}

function Bloco({ bloco }: { bloco: BlocoDoTextoSimples }) {
  if (bloco.lista) {
    return (
      <ul className="list-disc pl-5 space-y-0.5">
        {bloco.linhas.map((linha, i) => (
          <li key={i}>
            <Pedacos linha={linha} />
          </li>
        ))}
      </ul>
    );
  }
  return (
    <>
      {bloco.linhas.map((linha, i) => (
        <p key={i}>
          <Pedacos linha={linha} />
        </p>
      ))}
    </>
  );
}

function TextoSimples({ texto }: { texto: string | null }) {
  const blocos = blocosDoTextoSimples(texto);
  if (blocos.length === 0) {
    return <p className="text-text-secondary italic">{SEM_O_QUE_MUDA}</p>;
  }
  return (
    <div className="space-y-2">
      {blocos.map((bloco, i) => (
        <Bloco key={i} bloco={bloco} />
      ))}
    </div>
  );
}

function SeloDaSituacao({ situacao }: { situacao: EtapaDemanda | null }) {
  const rotulo = situacao ? ETAPA_ROTULO[situacao as EtapaDemanda] : undefined;
  if (!rotulo) return null;

  return (
    <span
      className={`shrink-0 px-2 py-0.5 rounded text-xs font-medium ${ETAPA_CLASSE[situacao as EtapaDemanda]}`}
    >
      {rotulo}
    </span>
  );
}

function Parte({ parte }: { parte: ParteDaEntrega }) {
  return (
    <li className="flex items-start gap-2">
      <SeloDaSituacao situacao={parte.situacao} />
      <div className="min-w-0 flex-1">
        <TextoSimples texto={parte.o_que_muda} />
      </div>
    </li>
  );
}

export function OQueMudaDaDemanda({ demanda }: { demanda: Demanda }) {
  if (!temSelo(demanda)) return null;

  const partes = demanda.partes ?? [];

  return (
    <section
      aria-labelledby={`o-que-muda-${demanda.id}`}
      className="md:col-span-2 px-4 py-3 rounded-xl bg-slate-50 border border-slate-200"
    >
      <h3 id={`o-que-muda-${demanda.id}`} className="text-xs font-medium text-text-secondary uppercase">
        {TITULO_O_QUE_MUDA}
      </h3>

      <div className="mt-2 text-sm text-text">
        <TextoSimples texto={demanda.o_que_muda ?? null} />
      </div>

      {partes.length > 0 && (
        <ul className="mt-3 pt-3 border-t border-slate-200 space-y-2 text-sm text-text">
          {partes.map((parte, i) => (
            // Pela posição: o número da parte é justamente o que não vem para
            // quem não é da Vitta, e a lista é redesenhada inteira a cada
            // sincronização.
            <Parte key={i} parte={parte} />
          ))}
        </ul>
      )}
    </section>
  );
}
