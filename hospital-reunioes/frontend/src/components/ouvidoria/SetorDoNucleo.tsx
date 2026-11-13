"use client";

/**
 * Qual setor é o Núcleo de Segurança do Paciente (issue #1621, ADR 0088,
 * decisão 3).
 *
 * Mora na tela de Responsáveis por setor porque é ali que o Núcleo ganha o
 * titular (a presidência do NSP), o substituto e o gestor, como qualquer setor.
 * Aqui só se diz qual dos setores da taxonomia ele é.
 */

import { useEffect, useState } from "react";
import { AlertCircle, CheckCircle2, Loader2, ShieldAlert } from "lucide-react";

const FALHA = "Não foi possível salvar o setor do Núcleo agora. Tente novamente.";

interface SetorDoNucleoProps {
  token: string | null;
  setores: string[];
}

export function SetorDoNucleo({ token, setores }: SetorDoNucleoProps) {
  const [salvo, setSalvo] = useState<string | null>(null);
  const [escolhido, setEscolhido] = useState("");
  const [salvando, setSalvando] = useState(false);
  const [aviso, setAviso] = useState<{ tipo: "ok" | "erro"; texto: string } | null>(null);

  useEffect(() => {
    if (!token) return;
    let cancelado = false;
    fetch("/api/ouvidoria/nucleo", { headers: { Authorization: `Bearer ${token}` } })
      .then((res) => (res.ok ? res.json() : { setor: "" }))
      .then((corpo) => {
        if (cancelado) return;
        const setor = typeof corpo.setor === "string" ? corpo.setor : "";
        setSalvo(setor);
        setEscolhido(setor);
      })
      .catch(() => {
        if (!cancelado) setSalvo("");
      });
    return () => {
      cancelado = true;
    };
  }, [token]);

  async function salvar() {
    if (!token || !escolhido) return;
    setSalvando(true);
    setAviso(null);
    try {
      const res = await fetch("/api/ouvidoria/nucleo", {
        method: "PUT",
        headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
        body: JSON.stringify({ setor: escolhido }),
      });
      const corpo = await res.json().catch(() => ({}));
      if (!res.ok) {
        setAviso({ tipo: "erro", texto: typeof corpo.detail === "string" ? corpo.detail : FALHA });
        return;
      }
      setSalvo(corpo.setor ?? escolhido);
      setAviso({ tipo: "ok", texto: "Setor do Núcleo salvo." });
    } catch {
      setAviso({ tipo: "erro", texto: FALHA });
    } finally {
      setSalvando(false);
    }
  }

  return (
    <section className="bg-white rounded-2xl border border-border shadow-premium p-5 space-y-3">
      {/* Título curto: em caixa alta, só rótulo de até 30 caracteres (RN-76).
          O nome por extenso vem na frase logo abaixo. */}
      <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-700">Núcleo de Segurança</h2>
      <p className="text-sm text-slate-600">
        Os casos que falam de incidente com o paciente vão ao Núcleo de Segurança do Paciente. Escolha qual setor da lista é o
        Núcleo e cadastre abaixo a presidência do NSP como titular dele.
      </p>
      {salvo === "" && (
        <p className="flex items-start gap-2 text-sm text-amber-800 bg-amber-50 border border-amber-200 rounded-xl px-3 py-2.5">
          <ShieldAlert className="w-4 h-4 mt-0.5 shrink-0" />
          <span>Enquanto nenhum setor for escolhido, o envio ao Núcleo fica travado.</span>
        </p>
      )}
      <div className="flex flex-col sm:flex-row gap-2 sm:items-end">
        <div className="flex-1">
          <label
            htmlFor="setor-do-nucleo"
            className="block text-xs font-semibold text-slate-500 uppercase tracking-wide mb-1"
          >
            Setor do Núcleo
          </label>
          <select
            id="setor-do-nucleo"
            className="w-full px-3 py-2 rounded-lg border border-slate-200 text-sm text-slate-700"
            value={escolhido}
            onChange={(e) => setEscolhido(e.target.value)}
          >
            <option value="">Escolha o setor</option>
            {setores.map((nome) => (
              <option key={nome} value={nome}>
                {nome}
              </option>
            ))}
            {escolhido && !setores.includes(escolhido) && <option value={escolhido}>{escolhido}</option>}
          </select>
        </div>
        <button
          type="button"
          onClick={() => void salvar()}
          disabled={!escolhido || escolhido === salvo || salvando}
          className="inline-flex items-center justify-center gap-1.5 px-4 py-2 rounded-lg text-sm font-semibold uppercase tracking-wide bg-primary text-white hover:bg-primary/90 disabled:opacity-50"
        >
          {salvando && <Loader2 className="w-4 h-4 animate-spin" aria-hidden="true" />}
          Salvar setor do Núcleo
        </button>
      </div>
      {aviso && (
        <p
          role={aviso.tipo === "erro" ? "alert" : "status"}
          className={`flex items-start gap-2 text-sm ${aviso.tipo === "erro" ? "text-red-700" : "text-emerald-700"}`}
        >
          {aviso.tipo === "erro" ? (
            <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
          ) : (
            <CheckCircle2 className="w-4 h-4 mt-0.5 shrink-0" />
          )}
          <span>{aviso.texto}</span>
        </p>
      )}
    </section>
  );
}

export default SetorDoNucleo;
