"use client";

/**
 * A tela do Instagram da Central de Comando (issue #819, PRD #809, ADR 0058).
 *
 * Pede ao backend o payload inteiro da tela e desenha o que veio: os três
 * números principais (Seguidores, Alcance, Visualizações), o bloco de
 * engajamento e as Principais publicações. A tela não faz conta: a variação de
 * Alcance e Visualizações e o crescimento de Seguidores já vêm prontos.
 *
 * Na interface diz-se sempre "Instagram", nunca a empresa dona da rede. Os
 * números usam a terminologia nativa do Instagram (Alcance, Visualizações,
 * Interações), a mesma que o diretor vê no próprio app.
 *
 * Honestidade do dado, como nas outras telas: sem credencial (503) a tela diz o
 * que falta e não mostra número; com o token vencido e números guardados, o
 * backend manda o último valor bom e a `BarraDeFrescor` avisa da renovação;
 * com o token vencido e nada guardado, o aviso é calmo, com a mesma frase de
 * renovação, e não o erro técnico (issue #846). O
 * frescor, o Atualizar agora e a renovação de hora em hora moram no
 * `useTelaDaCentral`. Os dados só saem do backend, que exige Super admin em
 * toda rota: esta tela não confia no guard do `layout.tsx` para nada.
 */

import { AlertTriangle, ArrowDown, ArrowUp, Camera, KeyRound, Loader2, PlugZap } from "lucide-react";

import { CAUSA_TOKEN_VENCIDO, type Frescor } from "@/lib/central-de-comando/api";
import { formatarInteiro, formatarPercentual } from "@/lib/central-de-comando/formato";
import { PERIODOS_DO_INSTAGRAM, type Periodo } from "@/lib/central-de-comando/periodo";

import { BarraDeFrescor } from "./BarraDeFrescor";
import type { PeriodoDoPayload } from "./BlocoVisitantes";
import { SeletorDePeriodo } from "./SeletorDePeriodo";
import { useTelaDaCentral } from "./useTelaDaCentral";

export const CAMINHO_INSTAGRAM = "/admin/central-de-comando/instagram";

type NumeroDeFluxo = { atual: number; anterior: number; variacao: number | null };
type ParteDoEngajamento = { chave: string; rotulo: string; valor: number };

type PublicacaoDoPayload = {
  id: string;
  legenda: string | null;
  tipo: string;
  rotulo_tipo: string;
  miniatura: string;
  link: string;
  interacoes: number;
};

/** O que `GET /api/admin/central-de-comando/instagram` devolve. */
export type InstagramPayload = {
  periodo: PeriodoDoPayload;
  seguidores: { total: number; crescimento: number; crescimento_anterior: number; ganhos: number; perdidos: number };
  alcance: NumeroDeFluxo;
  visualizacoes: NumeroDeFluxo;
  engajamento: {
    interacoes: number;
    interacoes_anterior: number;
    variacao: number | null;
    partes: ParteDoEngajamento[];
    contas_engajadas: number;
    contas_engajadas_anterior: number;
  };
  principais_publicacoes: PublicacaoDoPayload[];
  frescor: Frescor;
};

export function Instagram({ periodo }: { periodo: Periodo }) {
  const { estado, atualizando, aviso, atualizarAgora } = useTelaDaCentral<InstagramPayload>("instagram", periodo);
  const tokenVencido = estado.tipo === "falhou" && estado.causa === CAUSA_TOKEN_VENCIDO;

  return (
    <div className="animate-fade-in-up space-y-6">
      <header className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="rounded-xl bg-primary/10 p-2 text-primary">
            <Camera className="h-6 w-6" />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-text">Instagram</h1>
            <p className="text-sm text-text-secondary">
              Central de Comando: o Instagram do hospital, na linguagem do próprio app.
            </p>
          </div>
        </div>
        <SeletorDePeriodo ativo={periodo} caminho={CAMINHO_INSTAGRAM} periodos={PERIODOS_DO_INSTAGRAM} />
      </header>

      <p className="text-xs text-text-secondary">
        Só 7 e 28 dias: o Instagram entrega no máximo 30 dias por consulta.
      </p>

      {estado.tipo === "carregando" && (
        <div
          role="status"
          className="flex items-center gap-2 rounded-2xl border border-border bg-white p-6 text-sm text-text-secondary shadow-premium"
        >
          <Loader2 className="h-4 w-4 animate-spin" />
          Carregando os números do Instagram
        </div>
      )}

      {estado.tipo === "pronto" && (
        <>
          <BarraDeFrescor
            frescor={estado.dados.frescor}
            atualizando={atualizando}
            aviso={aviso}
            onAtualizar={atualizarAgora}
          />
          <div className={`space-y-6 transition-opacity ${atualizando ? "pointer-events-none opacity-50" : ""}`}>
            <div className="grid gap-4 sm:grid-cols-3">
              <CartaoDeSeguidores seguidores={estado.dados.seguidores} />
              <CartaoDeFluxo rotulo="Alcance" numero={estado.dados.alcance} />
              <CartaoDeFluxo rotulo="Visualizações" numero={estado.dados.visualizacoes} />
            </div>
            <p className="text-xs text-text-secondary">
              Alcance é quantas pessoas viram; Visualizações é quantas vezes o conteúdo foi visto (a mesma pessoa
              pode ver mais de uma vez).
            </p>

            <BlocoDeEngajamento engajamento={estado.dados.engajamento} />

            <section
              aria-labelledby="central-instagram-publicacoes"
              className="space-y-4 rounded-2xl border border-border bg-white p-6 shadow-premium"
            >
              <div className="space-y-1">
                <h2 id="central-instagram-publicacoes" className="text-lg font-bold text-text">
                  Principais publicações
                </h2>
                <p className="text-xs text-text-secondary">As que mais engajaram no período</p>
              </div>
              <GradeDePublicacoes publicacoes={estado.dados.principais_publicacoes} />
            </section>
          </div>
        </>
      )}

      {estado.tipo === "nao-configurado" && (
        <div role="status" className="flex gap-3 rounded-2xl border border-amber-200 bg-amber-50 p-6 text-amber-900">
          <PlugZap className="mt-0.5 h-5 w-5 shrink-0" />
          <div className="space-y-1">
            <p className="font-semibold">Conta do Instagram ainda não configurada</p>
            <p className="text-sm">{estado.mensagem}</p>
          </div>
        </div>
      )}

      {tokenVencido && (
        <div role="status" className="flex gap-3 rounded-2xl border border-amber-200 bg-amber-50 p-6 text-amber-900">
          <KeyRound className="mt-0.5 h-5 w-5 shrink-0" />
          <div className="space-y-1">
            <p className="font-semibold">É preciso renovar o acesso ao Instagram</p>
            <p className="text-sm">{estado.mensagem}</p>
          </div>
        </div>
      )}

      {((estado.tipo === "falhou" && !tokenVencido) || estado.tipo === "sem-conexao") && (
        <div role="alert" className="flex gap-3 rounded-2xl border border-red-200 bg-red-50 p-6 text-red-900">
          <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0" />
          <div className="space-y-1">
            <p className="font-semibold">Não foi possível buscar os números do Instagram agora.</p>
            <p className="text-sm">{estado.mensagem}</p>
          </div>
        </div>
      )}
    </div>
  );
}

/**
 * Seguidores é estoque: o total agora e o crescimento do período ao lado (sem
 * variação percentual, que não faz sentido sobre um estoque), com quantos
 * seguiram e quantos saíram.
 */
function CartaoDeSeguidores({
  seguidores,
}: {
  seguidores: InstagramPayload["seguidores"];
}) {
  const sinal = seguidores.crescimento >= 0 ? "+" : "";
  return (
    <div
      role="group"
      aria-label="Seguidores"
      className="space-y-1 rounded-2xl border border-border bg-white p-6 shadow-premium"
    >
      <p className="text-sm text-text-secondary">Seguidores</p>
      <p className="text-3xl font-bold text-text">{formatarInteiro(seguidores.total)}</p>
      <p className="text-sm font-medium text-text">
        {sinal}
        {formatarInteiro(seguidores.crescimento)} no período
      </p>
      <p className="text-xs text-text-secondary">
        {formatarInteiro(seguidores.ganhos)} seguiram · {formatarInteiro(seguidores.perdidos)} saíram
      </p>
    </div>
  );
}

/** Um número de fluxo (Alcance, Visualizações): o do período e a variação. */
function CartaoDeFluxo({ rotulo, numero }: { rotulo: string; numero: NumeroDeFluxo }) {
  return (
    <div className="space-y-1 rounded-2xl border border-border bg-white p-6 shadow-premium">
      <p className="text-sm text-text-secondary">{rotulo}</p>
      <p className="text-3xl font-bold text-text">{formatarInteiro(numero.atual)}</p>
      <Seta variacao={numero.variacao} />
    </div>
  );
}

/**
 * A seta da variação contra o período anterior. Sem base comparável (variação
 * nula), não desenha seta nenhuma: a tela não inventa comparação.
 */
function Seta({ variacao }: { variacao: number | null }) {
  if (variacao === null) return null;
  if (variacao === 0) return <p className="text-xs text-text-secondary">sem mudança</p>;
  const subiu = variacao > 0;
  const Icone = subiu ? ArrowUp : ArrowDown;
  return (
    <p className={`flex items-center gap-1 text-sm font-medium ${subiu ? "text-emerald-600" : "text-red-600"}`}>
      <Icone className="h-4 w-4" aria-hidden="true" />
      {formatarPercentual(Math.abs(variacao))}
    </p>
  );
}

/**
 * O bloco de engajamento: as Interações (a manchete, com a variação) e as
 * quatro partes, e as Contas que engajaram (pessoas). Ações e pessoas,
 * distintas: a mesma pessoa pode interagir mais de uma vez.
 */
function BlocoDeEngajamento({
  engajamento,
}: {
  engajamento: InstagramPayload["engajamento"];
}) {
  return (
    <section
      aria-labelledby="central-instagram-engajamento"
      className="space-y-4 rounded-2xl border border-border bg-white p-6 shadow-premium"
    >
      <div className="space-y-1">
        <h2 id="central-instagram-engajamento" className="text-lg font-bold text-text">
          Engajamento
        </h2>
        <p className="text-xs text-text-secondary">Como o público interage com o conteúdo</p>
      </div>
      <div className="flex flex-wrap items-baseline gap-3">
        <p className="text-3xl font-bold text-text">{formatarInteiro(engajamento.interacoes)}</p>
        <p className="text-sm text-text-secondary">Interações</p>
        <Seta variacao={engajamento.variacao} />
      </div>
      <ul className="grid gap-3 sm:grid-cols-4">
        {engajamento.partes.map((parte) => (
          <li key={parte.chave} className="rounded-xl border border-border bg-surface p-3">
            <p className="text-lg font-semibold text-text">{formatarInteiro(parte.valor)}</p>
            <p className="text-xs text-text-secondary">{parte.rotulo}</p>
          </li>
        ))}
      </ul>
      <div>
        <p className="text-2xl font-bold text-text">{formatarInteiro(engajamento.contas_engajadas)}</p>
        <p className="text-sm text-text-secondary">Contas que engajaram</p>
      </div>
    </section>
  );
}

/**
 * A grade das Principais publicações: cada uma abre no Instagram, em outra aba.
 * Sem publicação no período, o estado vazio é calmo, e não uma grade em branco.
 */
function GradeDePublicacoes({ publicacoes }: { publicacoes: PublicacaoDoPayload[] }) {
  if (publicacoes.length === 0) {
    return <p className="text-sm text-text-secondary">Sem publicações no período selecionado.</p>;
  }
  return (
    <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {publicacoes.map((pub) => (
        <li key={pub.id}>
          <CartaoDaPublicacao pub={pub} />
        </li>
      ))}
    </ul>
  );
}

/**
 * Uma publicação da grade. Abre no Instagram, em outra aba, só se o link for
 * `https://` (issue #846): link de outro esquema não vira `href`, e a
 * publicação aparece do mesmo jeito, sem link.
 */
function CartaoDaPublicacao({ pub }: { pub: PublicacaoDoPayload }) {
  const moldura = "block overflow-hidden rounded-xl border border-border bg-white";
  const conteudo = (
    <>
      <Miniatura pub={pub} />
      <div className="space-y-1 p-3">
        <span className="inline-block rounded-full bg-primary/10 px-2 py-0.5 text-xs font-medium text-primary">
          {pub.rotulo_tipo}
        </span>
        {pub.legenda && <p className="line-clamp-2 text-sm text-text">{pub.legenda}</p>}
        <p className="text-xs text-text-secondary">{formatarInteiro(pub.interacoes)} interações</p>
      </div>
    </>
  );
  if (!ehHttps(pub.link)) return <div className={moldura}>{conteudo}</div>;
  return (
    <a
      href={pub.link}
      target="_blank"
      rel="noopener noreferrer"
      className={`${moldura} transition-shadow hover:shadow-premium`}
    >
      {conteudo}
    </a>
  );
}

/**
 * A miniatura da publicação, ou o marcador quando não há uma para mostrar: a
 * publicação sem `thumbnail_url` nem `media_url` chega com a miniatura vazia, e
 * vira o marcador, nunca uma imagem quebrada (issue #846). O nome acessível é
 * o mesmo nos dois casos, a legenda.
 */
function Miniatura({ pub }: { pub: PublicacaoDoPayload }) {
  const descricao = pub.legenda ?? "Publicação do Instagram";
  if (!ehHttps(pub.miniatura)) {
    return (
      <div
        role="img"
        aria-label={descricao}
        className="flex aspect-square w-full flex-col items-center justify-center gap-2 bg-surface text-text-secondary"
      >
        <Camera className="h-8 w-8" aria-hidden="true" />
        <span className="text-xs">Sem miniatura</span>
      </div>
    );
  }
  return (
    <>
      {/* Miniatura externa da conta do Instagram: `<img>` puro, porque o
          host da imagem é da rede e varia (o next/image pediria whitelist). */}
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src={pub.miniatura} alt={descricao} className="aspect-square w-full object-cover" />
    </>
  );
}

/**
 * Só endereço `https://` vira `src` ou `href` na tela (issue #846): a miniatura
 * vazia, ou de outro esquema, vira o marcador; o link de outro esquema, como
 * `javascript:` ou `http://`, não vira link.
 */
function ehHttps(endereco: string): boolean {
  return endereco.startsWith("https://");
}
