"use client";

import { useCallback, useEffect, useState } from "react";

import { ErroDoCanal, chamarConduta } from "@/lib/conduta/configuracoes";
import { createClient } from "@/lib/supabase/client";

const ROTA = "/api/comite-de-conduta/codigo-de-conduta";
const CARTAO = "bg-white rounded-2xl border border-border shadow-premium";

interface VersaoDoCodigo {
  id: string;
  versao: number;
  vigente_desde: string;
  nome_arquivo: string;
  tamanho_bytes: number;
  autor: string;
  criado_em: string;
}

/** "2026-12-01" vira "01/12/2026", sem passar por fuso. */
function diaBr(iso: string): string {
  const [ano, mes, dia] = iso.slice(0, 10).split("-");
  return `${dia}/${mes}/${ano}`;
}

function linha(v: VersaoDoCodigo): string {
  return `Versão ${v.versao}, vigente desde ${diaBr(v.vigente_desde)}, por ${v.autor || "autor sem nome"}`;
}

async function token(): Promise<string> {
  const {
    data: { session },
  } = await createClient().auth.getSession();
  return session?.access_token ?? "";
}

async function detalhe(res: Response, padrao: string): Promise<string> {
  const corpo = await res.json().catch(() => null);
  return typeof corpo?.detail === "string" ? corpo.detail : padrao;
}

function LinhaDaVersao({ v, aoErrar }: { v: VersaoDoCodigo; aoErrar: (m: string) => void }) {
  async function baixar() {
    const res = await fetch(`${ROTA}/arquivo?versao=${v.versao}`, {
      headers: { Authorization: `Bearer ${await token()}` },
    });
    if (!res.ok) {
      aoErrar(await detalhe(res, "Não foi possível baixar o PDF. Tente de novo."));
      return;
    }
    const url = URL.createObjectURL(await res.blob());
    const link = document.createElement("a");
    link.href = url;
    link.download = v.nome_arquivo;
    link.click();
    URL.revokeObjectURL(url);
  }

  return (
    <li className="flex items-center justify-between gap-3 rounded-xl bg-slate-50 px-3 py-2">
      <p className="text-sm text-slate-700">{linha(v)}</p>
      <button
        type="button"
        onClick={baixar}
        aria-label={`Baixar o PDF da versão ${v.versao}`}
        className="shrink-0 rounded-xl border border-border px-3 py-1.5 text-sm font-semibold text-slate-700 hover:bg-slate-50"
      >
        Baixar o PDF
      </button>
    </li>
  );
}

/**
 * O Código de Conduta na tela Configurações (issue #1841, decisão 37 do
 * diretor): a coordenação publica o PDF com a data em que passa a valer, e
 * cada publicação é uma versão nova; as anteriores ficam para consulta. Quem
 * não é da coordenação não vê o bloco: a recusa da tela já aparece acima.
 */
export function CodigoDeConduta() {
  const [versoes, setVersoes] = useState<VersaoDoCodigo[] | null>(null);
  const [recusado, setRecusado] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [arquivo, setArquivo] = useState<File | null>(null);
  const [vigenteDesde, setVigenteDesde] = useState("");
  const [publicando, setPublicando] = useState(false);

  const carregar = useCallback(async () => {
    try {
      const corpo = await chamarConduta<{ versoes: VersaoDoCodigo[] }>(ROTA);
      setVersoes(corpo.versoes);
    } catch (e) {
      if (e instanceof ErroDoCanal && e.status === 403) setRecusado(true);
      else setErro(e instanceof Error ? e.message : "Não foi possível carregar. Tente de novo.");
    }
  }, []);

  useEffect(() => {
    void carregar();
  }, [carregar]);

  async function publicar() {
    if (!arquivo) return;
    setPublicando(true);
    setErro(null);
    const corpo = new FormData();
    corpo.append("arquivo", arquivo);
    if (vigenteDesde) corpo.append("vigente_desde", vigenteDesde);
    try {
      const res = await fetch(ROTA, {
        method: "POST",
        headers: { Authorization: `Bearer ${await token()}` },
        body: corpo,
      });
      if (!res.ok) {
        setErro(await detalhe(res, "Não foi possível publicar. Tente de novo."));
        return;
      }
      setArquivo(null);
      setVigenteDesde("");
      await carregar();
    } finally {
      setPublicando(false);
    }
  }

  if (recusado) return null;

  return (
    <section className="flex flex-col gap-3">
      <h2 className="text-base font-bold text-slate-900">Código de Conduta</h2>
      <article className={`${CARTAO} flex flex-col gap-3 px-4 py-4`}>
        {versoes === null && !erro && <p className="text-sm text-slate-500">Carregando...</p>}
        {versoes?.length === 0 && <p className="text-sm text-slate-500">Ainda não publicado.</p>}
        {versoes && versoes.length > 0 && (
          <ol className="flex flex-col gap-2">
            {versoes.map((v) => (
              <LinhaDaVersao key={v.id} v={v} aoErrar={setErro} />
            ))}
          </ol>
        )}

        <div className="flex flex-col gap-2 border-t border-border pt-3">
          <label htmlFor="codigo-pdf" className="text-sm font-semibold text-slate-700">
            PDF do Código de Conduta
          </label>
          <input
            id="codigo-pdf"
            type="file"
            accept="application/pdf,.pdf"
            onChange={(e) => setArquivo(e.target.files?.[0] ?? null)}
            className="text-sm text-slate-700"
          />
          <label htmlFor="codigo-vigencia" className="text-sm font-semibold text-slate-700">
            Vale a partir de
          </label>
          <input
            id="codigo-vigencia"
            type="date"
            value={vigenteDesde}
            onChange={(e) => setVigenteDesde(e.target.value)}
            className="w-48 rounded-xl border border-border px-3 py-2 text-sm text-slate-900"
          />
          <p className="text-xs text-slate-500">Sem data, vale a partir de hoje. As versões anteriores continuam guardadas.</p>
          {erro && <p className="text-sm text-red-700">{erro}</p>}
          <button
            type="button"
            onClick={publicar}
            disabled={publicando || !arquivo}
            className="self-start rounded-xl bg-primary px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
          >
            Publicar nova versão
          </button>
        </div>
      </article>
    </section>
  );
}
