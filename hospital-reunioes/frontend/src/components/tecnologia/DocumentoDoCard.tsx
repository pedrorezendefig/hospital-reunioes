/**
 * O Documento do card (issue #1552, PRD #1548, ADR 0084, decisão 7), que
 * substituiu a seção "O que muda" de texto corrido (issue #676).
 *
 * Seções fixas: Em uma frase, O que muda (até cinco tópicos, o resto atrás do
 * "Ver tudo"), Partes (com a Etapa e a data de fechamento) e Datas (criado,
 * entregue, em produção). A Demonstração, num cartão próprio, só quando a
 * issue traz o link do vídeo (issue #1559). O texto vem do bloco "Para o diretor" da issue e do
 * de cada parte, lido do GitHub e guardado no cache da Demanda. Ninguém o
 * digita no app, e o app só o separa em seções, sem reescrever.
 *
 * Nada aqui é técnico para o diretor: título de fatia, número, link e nome de
 * label não aparecem (ADR 0054, decisão 9). O número e o link da issue
 * aparecem só para o Desenvolvedor, porque só para ele o servidor os manda.
 *
 * O texto é desenhado como TEXTO, com um Markdown simples de negrito e lista.
 * Nada vira HTML nem link: ele vem de fora do app, e um `dangerouslySetInnerHTML`
 * aqui transformaria o corpo de uma issue em elemento da nossa tela.
 *
 * Sem Vínculo não há documento: é o mesmo `temSelo` do card que decide, e não
 * uma segunda condição escrita aqui, que divergiria dele na primeira mudança.
 */

import { useState } from "react";

import {
  BlocoDoTextoSimples,
  blocosDoTextoSimples,
  Demanda,
  diaDoHospital,
  diaEHoraDoHospital,
  documentoDoBloco,
  ETAPA_CLASSE,
  ETAPA_ROTULO,
  EtapaDemanda,
  linkDaDemonstracao,
  ParteDaEntrega,
  PedacoForte,
  temSelo,
} from "./demandas";

export const TITULO_DOCUMENTO = "Documento do card";
export const TITULO_EM_UMA_FRASE = "Em uma frase";
export const TITULO_O_QUE_MUDA = "O que muda";
export const TITULO_PARTES = "Partes";
export const TITULO_DATAS = "Datas";
export const TITULO_DEMONSTRACAO = "Demonstração";
export const ASSISTIR_A_DEMONSTRACAO = "Assistir à demonstração";
export const VER_TUDO = "Ver tudo";

/** Quantos tópicos de O que muda aparecem antes do "Ver tudo" (ADR 0084). */
export const TOPICOS_VISIVEIS = 5;

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
  const fechou = diaDoHospital(parte.fechada_em);
  return (
    <li className="flex items-start gap-2">
      <SeloDaSituacao situacao={parte.situacao} />
      {fechou && <span className="shrink-0 text-xs text-text-secondary pt-0.5">em {fechou}</span>}
      <div className="min-w-0 flex-1">
        <TextoSimples texto={parte.o_que_muda} />
      </div>
    </li>
  );
}

function Titulo({ children }: { children: string }) {
  return <h3 className="text-xs font-medium text-text-secondary uppercase">{children}</h3>;
}

/** O link da issue, só para o Desenvolvedor e só se apontar para o GitHub. */
function LinkDaIssue({ demanda }: { demanda: Demanda }) {
  const url = demanda.issue_url;
  if (!demanda.issue_numero || !url || !url.startsWith("https://github.com/")) return null;
  return (
    <a href={url} target="_blank" rel="noopener noreferrer" className="text-xs font-semibold text-primary underline">
      #{demanda.issue_numero}
    </a>
  );
}

function Topicos({ topicos }: { topicos: PedacoForte[][] }) {
  const [tudo, setTudo] = useState(false);
  const visiveis = tudo ? topicos : topicos.slice(0, TOPICOS_VISIVEIS);
  return (
    <>
      <Titulo>{TITULO_O_QUE_MUDA}</Titulo>
      <ul className="list-disc pl-5 space-y-0.5 text-sm text-text">
        {visiveis.map((linha, i) => (
          <li key={i}>
            <Pedacos linha={linha} />
          </li>
        ))}
      </ul>
      {!tudo && topicos.length > TOPICOS_VISIVEIS && (
        <button type="button" onClick={() => setTudo(true)} className="text-xs font-semibold text-primary underline">
          {VER_TUDO}
        </button>
      )}
    </>
  );
}

/**
 * O vídeo de demonstração da entrega, num cartão próprio (issue #1559). Só com
 * link `https`: o link vem do corpo da issue, de fora do app.
 */
function Demonstracao({ demanda }: { demanda: Demanda }) {
  const url = linkDaDemonstracao(demanda);
  if (!url) return null;
  const dia = diaDoHospital(demanda.demonstracao_em);
  return (
    <section
      aria-label={TITULO_DEMONSTRACAO}
      className="px-3 py-2 rounded-lg bg-white border border-violet-200 space-y-1"
    >
      <Titulo>{TITULO_DEMONSTRACAO}</Titulo>
      <a href={url} target="_blank" rel="noopener noreferrer" className="text-sm font-semibold text-primary underline">
        {ASSISTIR_A_DEMONSTRACAO}
      </a>
      {dia && <p className="text-xs text-text-secondary">Adicionada em {dia}</p>}
    </section>
  );
}

/**
 * Em uma frase e O que muda, lidos do bloco "Para o diretor". É a parte do
 * documento que o planejamento monta ao vivo ao lado do chat (issue #1553):
 * o mesmo componente nos dois lugares, para o rascunho e o card não divergirem.
 * `chave` recolhe o "Ver tudo" ao trocar de card.
 */
export function FraseEOQueMuda({ texto, chave }: { texto: string | null | undefined; chave: string }) {
  const bloco = documentoDoBloco(texto);
  return (
    <>
      {/* Sem bloco, a frase de preparação no lugar da frase; o bloco só de
          tópicos não tem frase a mostrar, e a seção some. */}
      {(!bloco || bloco.frase.length > 0) && (
        <>
          <Titulo>{TITULO_EM_UMA_FRASE}</Titulo>
          <div className="text-sm text-text">
            {bloco ? (
              bloco.frase.map((linha, i) => (
                <p key={i}>
                  <Pedacos linha={linha} />
                </p>
              ))
            ) : (
              <p className="text-text-secondary italic">{SEM_O_QUE_MUDA}</p>
            )}
          </div>
        </>
      )}

      {bloco && bloco.topicos.length > 0 && <Topicos key={chave} topicos={bloco.topicos} />}
    </>
  );
}

export function DocumentoDoCard({ demanda }: { demanda: Demanda }) {
  if (!temSelo(demanda)) return null;

  const partes = demanda.partes ?? [];
  const datas = [
    ["Criado em", diaEHoraDoHospital(demanda.criado_em)],
    ["Entregue em", diaEHoraDoHospital(demanda.fechada_em)],
    ["Em produção em", diaEHoraDoHospital(demanda.em_producao_em)],
  ].filter((par): par is [string, string] => par[1] !== null);

  return (
    <section
      aria-label={TITULO_DOCUMENTO}
      className="md:col-span-2 px-4 py-3 rounded-xl bg-slate-50 border border-slate-200 space-y-2"
    >
      <LinkDaIssue demanda={demanda} />

      <FraseEOQueMuda texto={demanda.o_que_muda} chave={demanda.id} />

      <Demonstracao demanda={demanda} />

      {partes.length > 0 && (
        <>
          <Titulo>{TITULO_PARTES}</Titulo>
          <ul className="space-y-2 text-sm text-text">
            {partes.map((parte, i) => (
              // Pela posição: o número da parte é justamente o que não vem para
              // quem não é da Vitta, e a lista é redesenhada inteira a cada
              // sincronização.
              <Parte key={i} parte={parte} />
            ))}
          </ul>
        </>
      )}

      {datas.length > 0 && (
        <>
          <Titulo>{TITULO_DATAS}</Titulo>
          <ul className="space-y-0.5 text-sm text-text">
            {datas.map(([rotulo, dia]) => (
              <li key={rotulo}>
                {rotulo} {dia}
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}
