"use client";

/**
 * O registro rápido do Núcleo (issue #1998, PRD #1979).
 *
 * A Presidência e o membro com Termo lançam, numa tela só, o incidente que o
 * próprio Núcleo achou: relato, setor, data e origem. Quem registrou é o autor
 * pela sessão, e a notificação segue o mesmo caminho de qualquer outra. Fica
 * no alto de Notificações, que já só abre para quem tem o recurso de casos.
 */

import { useEffect, useState } from "react";
import { AlertCircle, CheckCircle2, Loader2, Plus } from "lucide-react";

import { chamarNsp } from "@/lib/seguranca-do-paciente/membros";
import {
  ORIGENS_DO_REGISTRO_RAPIDO,
  type OrigemDoRegistroRapido,
} from "@/lib/seguranca-do-paciente/notificacao";

interface Setor {
  id: string;
  nome: string;
}

const CARTAO = "bg-white rounded-2xl border border-border shadow-premium";
const CAMPO =
  "w-full min-h-[44px] rounded-xl border border-border px-3 py-2.5 text-base text-slate-800 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary";
const ROTULO = "block text-sm font-semibold text-slate-700";
const FALHA_DOS_SETORES = "Não foi possível carregar a lista de setores.";

function opcao(escolhida: boolean): string {
  return `min-h-[44px] rounded-xl border px-3 py-2.5 text-sm font-semibold transition-colors ${
    escolhida
      ? "border-primary bg-primary/10 text-primary"
      : "border-border bg-white text-slate-600 hover:border-primary/40"
  }`;
}

/** Hoje no fuso do aparelho, no formato do `<input type="date">`. */
function hoje(): string {
  const d = new Date();
  const dois = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${dois(d.getMonth() + 1)}-${dois(d.getDate())}`;
}

export function RegistroRapido({ aoRegistrar }: { aoRegistrar?: () => void }) {
  const [relato, setRelato] = useState("");
  const [setorId, setSetorId] = useState("");
  const [data, setData] = useState(hoje);
  const [origem, setOrigem] = useState<OrigemDoRegistroRapido | null>(null);
  const [setores, setSetores] = useState<Setor[]>([]);
  const [falhaDosSetores, setFalhaDosSetores] = useState(false);
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [protocolo, setProtocolo] = useState<string | null>(null);

  useEffect(() => {
    let vivo = true;
    fetch("/api/nsp/publico/setores")
      .then((res) => (res.ok ? res.json() : null))
      .then((corpo) => {
        if (!vivo) return;
        const lista = Array.isArray(corpo?.setores) ? corpo.setores : null;
        setSetores(lista ?? []);
        setFalhaDosSetores(lista === null);
      })
      .catch(() => {
        if (vivo) setFalhaDosSetores(true);
      });
    return () => {
      vivo = false;
    };
  }, []);

  const completo = relato.trim() !== "" && setorId !== "" && data !== "" && origem !== null;

  async function registrar(evento: React.FormEvent) {
    evento.preventDefault();
    if (!completo || enviando) return;
    setEnviando(true);
    setErro(null);
    setProtocolo(null);
    try {
      const recibo = await chamarNsp<{ protocolo: string }>("/api/nsp/notificacoes/registro-rapido", {
        method: "POST",
        body: { relato: relato.trim(), setor_id: setorId, data_ocorrencia: data, origem },
      });
      setProtocolo(recibo.protocolo);
      setRelato("");
      setSetorId("");
      setData(hoje());
      setOrigem(null);
      aoRegistrar?.();
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Não foi possível registrar agora. Tente de novo.");
    } finally {
      setEnviando(false);
    }
  }

  return (
    <section aria-labelledby="nsp-registro-rapido" className={`${CARTAO} px-4 py-4`}>
      <form onSubmit={registrar} className="space-y-3">
        <div>
          <h2 id="nsp-registro-rapido" className="text-base font-bold text-slate-900">
            Registro rápido
          </h2>
          <p className="text-sm text-slate-500">
            O incidente que o Núcleo encontrou. Você fica como autor do registro.
          </p>
        </div>

        <div className="space-y-1.5">
          <label htmlFor="nsp-rr-relato" className={ROTULO}>
            O que foi encontrado
          </label>
          <textarea
            id="nsp-rr-relato"
            rows={3}
            maxLength={10000}
            value={relato}
            onChange={(e) => setRelato(e.target.value)}
            className={`${CAMPO} resize-y`}
          />
        </div>

        <div data-linha className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div className="space-y-1.5">
            <label htmlFor="nsp-rr-setor" className={ROTULO}>
              Setor
            </label>
            <select id="nsp-rr-setor" value={setorId} onChange={(e) => setSetorId(e.target.value)} className={CAMPO}>
              <option value="">Escolha o setor</option>
              {setores.map((setor) => (
                <option key={setor.id} value={setor.id}>
                  {setor.nome}
                </option>
              ))}
            </select>
            {falhaDosSetores && <p className="text-sm text-red-700">{FALHA_DOS_SETORES}</p>}
          </div>
          <div className="space-y-1.5">
            <label htmlFor="nsp-rr-data" className={ROTULO}>
              Data
            </label>
            <input
              id="nsp-rr-data"
              type="date"
              max={hoje()}
              value={data}
              onChange={(e) => setData(e.target.value)}
              className={CAMPO}
            />
          </div>
        </div>

        <div className="space-y-1.5">
          <p id="nsp-rr-origem" className={ROTULO}>
            Origem
          </p>
          <div role="group" aria-labelledby="nsp-rr-origem" className="grid grid-cols-2 sm:grid-cols-5 gap-2">
            {ORIGENS_DO_REGISTRO_RAPIDO.map(({ valor, rotulo }) => (
              <button
                key={valor}
                type="button"
                aria-pressed={origem === valor}
                onClick={() => setOrigem(valor)}
                className={opcao(origem === valor)}
              >
                {rotulo}
              </button>
            ))}
          </div>
        </div>

        {erro && (
          <div role="alert" className="flex gap-2 items-start rounded-xl bg-red-50 border border-red-200 px-3 py-2.5">
            <AlertCircle className="w-4 h-4 mt-0.5 shrink-0 text-red-600" aria-hidden />
            <p className="text-sm text-red-700">{erro}</p>
          </div>
        )}
        {protocolo && (
          <p role="status" className="flex items-center gap-1.5 text-sm font-semibold text-emerald-700">
            <CheckCircle2 className="w-4 h-4 shrink-0" aria-hidden />
            {`Registrado com o protocolo ${protocolo}.`}
          </p>
        )}

        <button
          type="submit"
          disabled={!completo || enviando}
          className="flex w-full min-h-[44px] items-center justify-center gap-2 rounded-xl bg-primary px-4 py-2.5 text-base font-semibold text-white shadow-premium transition-colors hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {enviando ? <Loader2 className="w-4 h-4 animate-spin" aria-hidden /> : <Plus className="w-4 h-4" aria-hidden />}
          Registrar
        </button>
      </form>
    </section>
  );
}
