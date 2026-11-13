"use client";

/**
 * A nota do cartaz (issue #1622, ADR 0086): as telas N1, N2 e N3 da seção 4.1
 * da especificação da Diretoria, que o endereço curto `/a/{código}` abre.
 *
 * N1 é a nota de 1 a 5, com o nome público e o título do cartaz. N2 são os
 * motivos e o comentário, opcionais; a avaliação é gravada no "Enviar
 * avaliação" ou no "Pular", antes de qualquer escolha seguinte. N3 agradece:
 * a nota de 1 a 3 pergunta se a pessoa quer retorno, e a 4 ou 5 oferece o
 * elogio. Quem segue vai para a Manifestação guiada com o id da avaliação, que
 * só viaja quando a pessoa se identifica (decisão 3).
 *
 * Cartaz aposentado, código desconhecido ou servidor fora do ar abrem a
 * Manifestação guiada direto: nunca uma página de erro (ADR 0036, decisão 6).
 * Sem login e feita para o celular: alvos de toque de 44 px (regra T4).
 */

import { useEffect, useState } from "react";
import { AlertCircle, CheckCircle2, Loader2 } from "lucide-react";
import { Logo } from "@/components/ui/Logo";
import { ManifestacaoPublica } from "@/components/ouvidoria/ManifestacaoPublica";
import {
  MOTIVOS_DA_AVALIACAO,
  TAMANHO_DO_COMENTARIO,
  montarAvaliacao,
  perguntaRetorno,
  tituloDaNota,
} from "@/lib/ouvidoria/avaliacao";
import type { TituloDoCartaz } from "@/lib/ouvidoria/pontos";
import type { NaturezaInformada } from "@/lib/ouvidoria/publico";

interface Cartaz {
  nomePublico: string | null;
  titulo: TituloDoCartaz | null;
}

type Tela =
  | { qual: "carregando" }
  | { qual: "nota" }
  | { qual: "motivos"; nota: number }
  | { qual: "depois"; nota: number; avaliacaoId: string }
  | { qual: "encerrada" }
  | { qual: "manifestacao"; avaliacaoId: string | null; natureza: NaturezaInformada | null };

const PRINCIPAL =
  "flex w-full min-h-[44px] items-center justify-center gap-2 rounded-xl bg-primary px-4 py-3 text-base font-semibold text-white shadow-premium transition-colors hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed";
const SECUNDARIO =
  "flex w-full min-h-[44px] items-center justify-center rounded-xl border border-border bg-white px-4 py-3 text-base font-semibold text-slate-600 hover:border-primary/40 disabled:opacity-50";
// O link discreto: botão por dentro (não muda de página), texto em caixa mista.
const LINK =
  "min-h-[44px] px-2 text-sm font-semibold normal-case tracking-normal text-primary underline underline-offset-2";

function escolha(marcada: boolean): string {
  return `min-h-[44px] rounded-xl border px-3 py-2.5 text-sm font-semibold normal-case tracking-normal text-left transition-colors ${
    marcada
      ? "border-primary bg-primary/10 text-primary"
      : "border-border bg-white text-slate-600 hover:border-primary/40"
  }`;
}

export function AvaliacaoPublica({ codigoDoCartaz }: { codigoDoCartaz: string }) {
  const codigo = codigoDoCartaz.trim().toUpperCase();
  const [tela, setTela] = useState<Tela>({ qual: "carregando" });
  const [cartaz, setCartaz] = useState<Cartaz>({ nomePublico: null, titulo: null });
  const [motivos, setMotivos] = useState<string[]>([]);
  const [comentario, setComentario] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [limitada, setLimitada] = useState(false);

  useEffect(() => {
    let vivo = true;
    fetch(`/api/ouvidoria/publico/pontos/${encodeURIComponent(codigo)}`)
      .then((res) => (res.ok ? res.json() : null))
      .then((corpo) => {
        if (!vivo) return;
        if (!corpo) {
          setTela({ qual: "manifestacao", avaliacaoId: null, natureza: null });
          return;
        }
        setCartaz({ nomePublico: corpo.nome_publico ?? null, titulo: corpo.titulo_cartaz ?? null });
        setTela({ qual: "nota" });
      })
      .catch(() => {
        if (vivo) setTela({ qual: "manifestacao", avaliacaoId: null, natureza: null });
      });
    return () => {
      vivo = false;
    };
  }, [codigo]);

  if (tela.qual === "manifestacao") {
    return (
      <ManifestacaoPublica
        codigoDoCartaz={codigo}
        avaliacaoId={tela.avaliacaoId}
        naturezaInicial={tela.natureza}
      />
    );
  }

  function irParaManifestacao(avaliacaoId: string | null, natureza: NaturezaInformada | null) {
    setTela({ qual: "manifestacao", avaliacaoId, natureza });
  }

  async function enviar(nota: number, pulou: boolean) {
    if (enviando) return;
    setEnviando(true);
    setErro(null);
    try {
      const res = await fetch(`/api/ouvidoria/publico/pontos/${encodeURIComponent(codigo)}/avaliacoes`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(montarAvaliacao(nota, motivos, comentario, pulou)),
      });
      if (res.status === 429) {
        setLimitada(true);
        return;
      }
      if (res.status === 404) {
        // O cartaz saiu da parede enquanto a página estava aberta: a nota é
        // sempre de um cartaz ativo, e a pessoa ainda pode se manifestar.
        irParaManifestacao(null, null);
        return;
      }
      if (!res.ok) {
        setErro("Não foi possível enviar sua nota agora. Tente de novo em instantes.");
        return;
      }
      const recibo = (await res.json()) as { id: string };
      setTela({ qual: "depois", nota, avaliacaoId: recibo.id });
    } catch {
      setErro("Não foi possível falar com o hospital agora. Verifique sua conexão e tente de novo.");
    } finally {
      setEnviando(false);
    }
  }

  function alternarMotivo(valor: string) {
    setMotivos((atuais) => (atuais.includes(valor) ? atuais.filter((m) => m !== valor) : [...atuais, valor]));
  }

  let conteudo: React.ReactNode;
  if (tela.qual === "carregando") {
    conteudo = (
      <div className="flex justify-center py-10" aria-label="Carregando">
        <Loader2 className="w-6 h-6 animate-spin text-slate-400" />
      </div>
    );
  } else if (tela.qual === "nota") {
    conteudo = (
      <div className="space-y-4">
        <p className="text-sm text-slate-500 text-center">Toque na nota que mais combina com o seu atendimento.</p>
        <div role="group" aria-label="Sua nota" className="grid grid-cols-5 gap-2">
          {[1, 2, 3, 4, 5].map((nota) => (
            // Cor neutra, sem vermelho nem verde: a escala não sugere resposta.
            <button
              key={nota}
              type="button"
              aria-label={`Nota ${nota}`}
              onClick={() => setTela({ qual: "motivos", nota })}
              className="min-h-[52px] rounded-xl border border-border bg-white text-xl font-bold text-slate-700 tabular-nums transition-colors hover:border-primary/60 hover:bg-primary/5"
            >
              {nota}
            </button>
          ))}
        </div>
        <div className="flex justify-between text-xs text-slate-500" aria-hidden="true">
          <span>Muito ruim</span>
          <span>Muito bom</span>
        </div>
      </div>
    );
  } else if (tela.qual === "motivos") {
    const { nota } = tela;
    conteudo = limitada ? (
      <div className="space-y-4">
        <div className="flex items-start gap-2 rounded-xl bg-amber-50 border border-amber-200 px-3 py-2.5">
          <AlertCircle className="w-4 h-4 text-amber-500 mt-0.5 shrink-0" />
          <p className="text-sm text-amber-800">
            Já recebemos algumas notas deste cartaz agora há pouco. Se quiser falar com a Ouvidoria,
            registre uma manifestação.
          </p>
        </div>
        <button type="button" onClick={() => irParaManifestacao(null, null)} className={PRINCIPAL}>
          Registrar uma manifestação
        </button>
      </div>
    ) : (
      <div className="space-y-5">
        <div className="space-y-2">
          <p id="rotulo-motivos" className="etiqueta text-sm font-semibold text-slate-700">
            O que mais marcou seu atendimento?
          </p>
          <p className="text-xs text-slate-400">Pode marcar mais de um, ou nenhum.</p>
          <div role="group" aria-labelledby="rotulo-motivos" className="grid grid-cols-2 gap-2">
            {MOTIVOS_DA_AVALIACAO.map(({ valor, rotulo }) => (
              <button
                key={valor}
                type="button"
                aria-pressed={motivos.includes(valor)}
                onClick={() => alternarMotivo(valor)}
                className={escolha(motivos.includes(valor))}
              >
                {rotulo}
              </button>
            ))}
          </div>
        </div>
        <div className="space-y-1.5">
          <label htmlFor="comentario" className="block text-sm font-semibold text-slate-700">
            Quer contar mais? <span className="font-normal text-slate-400">(opcional)</span>
          </label>
          <textarea
            id="comentario"
            value={comentario}
            onChange={(e) => setComentario(e.target.value)}
            maxLength={TAMANHO_DO_COMENTARIO}
            rows={4}
            className="w-full min-h-[44px] rounded-xl border border-border px-3 py-2.5 text-base text-slate-800 focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary resize-y"
          />
          <p className="text-xs text-slate-400 text-right tabular-nums">
            {comentario.length} / {TAMANHO_DO_COMENTARIO}
          </p>
        </div>
        {erro && (
          <div className="flex items-start gap-2 rounded-xl bg-amber-50 border border-amber-200 px-3 py-2.5">
            <AlertCircle className="w-4 h-4 text-amber-500 mt-0.5 shrink-0" />
            <p className="text-sm text-amber-800">{erro}</p>
          </div>
        )}
        {/* Uma ação principal por tela (regra T2): só ela é azul preenchida. */}
        <div className="space-y-2">
          <button type="button" disabled={enviando} onClick={() => enviar(nota, false)} className={PRINCIPAL}>
            {enviando && <Loader2 className="w-4 h-4 animate-spin" />}
            Enviar avaliação
          </button>
          <button type="button" disabled={enviando} onClick={() => enviar(nota, true)} className={SECUNDARIO}>
            Pular
          </button>
        </div>
      </div>
    );
  } else if (tela.qual === "depois") {
    const { nota, avaliacaoId } = tela;
    conteudo = (
      <div className="space-y-5 text-center">
        <CheckCircle2 className="w-10 h-10 text-emerald-500 mx-auto" />
        <div className="space-y-1">
          <p className="text-lg font-semibold text-slate-900">Obrigado por nos contar.</p>
          {perguntaRetorno(nota) && (
            <p className="text-sm text-slate-500">Sua avaliação já chegou à Ouvidoria.</p>
          )}
        </div>
        {perguntaRetorno(nota) ? (
          <div className="space-y-3">
            <p className="text-base font-semibold text-slate-700">Quer que a Ouvidoria entre em contato?</p>
            <button type="button" onClick={() => irParaManifestacao(avaliacaoId, null)} className={PRINCIPAL}>
              Sim, quero retorno
            </button>
            <button type="button" onClick={() => setTela({ qual: "encerrada" })} className={SECUNDARIO}>
              Não, obrigado
            </button>
          </div>
        ) : (
          <button type="button" onClick={() => irParaManifestacao(avaliacaoId, "elogio")} className={LINK}>
            Quer deixar um elogio para a equipe?
          </button>
        )}
      </div>
    );
  } else {
    conteudo = (
      <div className="space-y-2 text-center py-4">
        <CheckCircle2 className="w-10 h-10 text-emerald-500 mx-auto" />
        <p className="text-lg font-semibold text-slate-900">Obrigado por nos contar.</p>
        <p className="text-sm text-slate-500">Pode fechar esta página.</p>
      </div>
    );
  }

  return (
    <main className="min-h-screen bg-bg">
      <div className="max-w-lg mx-auto px-4 py-8 space-y-5">
        <div className="flex items-center justify-center">
          <Logo variant="default" size="sm" />
        </div>
        {tela.qual !== "carregando" && (
          <div className="text-center space-y-1">
            {cartaz.nomePublico && <p className="text-sm font-semibold text-slate-500">{cartaz.nomePublico}</p>}
            <h1 className="text-xl font-bold text-slate-900">{tituloDaNota(cartaz.titulo)}</h1>
          </div>
        )}
        <div className="bg-white rounded-2xl border border-border shadow-premium px-5 py-6">{conteudo}</div>
        {(tela.qual === "nota" || tela.qual === "motivos") && !limitada && (
          <div className="flex justify-center">
            <button type="button" onClick={() => irParaManifestacao(null, null)} className={LINK}>
              Prefiro registrar uma manifestação
            </button>
          </div>
        )}
      </div>
    </main>
  );
}
