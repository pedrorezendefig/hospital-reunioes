"use client";

import { useEffect, useState } from "react";
import { AlertCircle, Loader2 } from "lucide-react";

import { chamarNsp } from "@/lib/seguranca-do-paciente/membros";
import type { Cortes } from "@/lib/seguranca-do-paciente/triagem";

const CARTAO = "bg-white rounded-2xl border border-border shadow-premium";
const CAMPO =
  "w-24 rounded-xl border border-border bg-white px-3 py-2 text-sm text-slate-900 tabular-nums focus:outline-none focus:ring-2 focus:ring-primary/30";
const ROTA = "/api/nsp/configuracao/cortes-de-frequencia";

const CAMPOS: { campo: keyof Cortes; rotulo: string }[] = [
  { campo: "janela_meses", rotulo: "Janela, em meses" },
  { campo: "incomum_a_partir", rotulo: "Incomum a partir de" },
  { campo: "ocasional_a_partir", rotulo: "Ocasional a partir de" },
  { campo: "frequente_a_partir", rotulo: "Frequente a partir de" },
];

/**
 * Os cortes de frequência da matriz de prioridade (issue #1992): quantas
 * ocorrências anteriores da mesma categoria no mesmo setor, na janela, fazem
 * cada frequência. Abaixo do incomum, a frequência é remota. A mudança vale
 * para os cálculos seguintes.
 */
export function CortesDeFrequencia() {
  const [cortes, setCortes] = useState<Cortes | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [salvando, setSalvando] = useState(false);
  const [salvo, setSalvo] = useState(false);

  useEffect(() => {
    let vivo = true;
    chamarNsp<Cortes>(ROTA)
      .then((corpo) => vivo && setCortes(corpo))
      .catch((e: Error) => vivo && setErro(e.message));
    return () => {
      vivo = false;
    };
  }, []);

  if (cortes === null) {
    return erro ? (
      <div role="alert" className={`${CARTAO} flex gap-2 items-start px-4 py-4`}>
        <AlertCircle className="w-5 h-5 shrink-0 text-red-500" aria-hidden />
        <p className="text-sm text-red-700">{erro}</p>
      </div>
    ) : (
      <Loader2 className="w-5 h-5 animate-spin text-slate-400" aria-label="Carregando" />
    );
  }

  async function salvar() {
    if (!cortes) return;
    setSalvando(true);
    setErro(null);
    setSalvo(false);
    try {
      setCortes(await chamarNsp<Cortes>(ROTA, { method: "PUT", body: cortes }));
      setSalvo(true);
    } catch (e) {
      setErro((e as Error).message);
    } finally {
      setSalvando(false);
    }
  }

  return (
    <section aria-labelledby="cortes-titulo" className={`${CARTAO} px-4 py-4 space-y-3`}>
      <h2 id="cortes-titulo" className="text-base font-semibold text-slate-900">
        Cortes de frequência
      </h2>
      <p className="text-sm text-slate-600">
        A prioridade de cada caso sai da gravidade e da frequência. A frequência conta as ocorrências anteriores da
        mesma categoria no mesmo setor, dentro da janela. Abaixo do incomum, ela é remota.
      </p>
      <div className="flex flex-wrap gap-4">
        {CAMPOS.map(({ campo, rotulo }) => (
          <div key={campo} className="space-y-1">
            <label htmlFor={`corte-${campo}`} className="block text-xs font-semibold text-slate-600">
              {rotulo}
            </label>
            <input
              id={`corte-${campo}`}
              type="number"
              min={1}
              value={cortes[campo]}
              onChange={(e) => {
                setSalvo(false);
                setCortes({ ...cortes, [campo]: Number(e.target.value) });
              }}
              className={CAMPO}
            />
          </div>
        ))}
      </div>
      {erro && (
        <p role="alert" className="text-sm text-red-700">
          {erro}
        </p>
      )}
      {salvo && (
        <p role="status" className="text-sm text-emerald-700">
          Cortes salvos.
        </p>
      )}
      <button
        type="button"
        onClick={salvar}
        disabled={salvando}
        className="inline-flex min-h-[44px] items-center justify-center gap-2 rounded-xl bg-primary px-5 py-2 text-sm font-semibold text-white hover:bg-primary/90 disabled:opacity-50"
      >
        {salvando && <Loader2 className="w-4 h-4 animate-spin" aria-hidden />}
        Salvar os cortes
      </button>
    </section>
  );
}
