"use client";

import { useEffect, useState } from "react";
import { AlertCircle, CheckCircle2, Loader2, Send, ShieldAlert } from "lucide-react";
import { AdminModal } from "@/components/admin/AdminModal";
import {
  AJUDA_GRAVIDADE,
  CLASSE_GRAVIDADE,
  GRAVIDADES,
  LABEL_GRAVIDADE,
  setorTemTitularVigente,
  type Gravidade,
  type Responsavel,
} from "@/lib/ouvidoria/validacao";

interface ValidarModalProps {
  manifestacao: { id: string; protocolo: string; categoria: string; setor: string } | null;
  token: string | null;
  onClose: () => void;
  onAcionada: () => void;
}

const CAMPO =
  "w-full px-3 py-2 rounded-lg border border-slate-200 text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary/40";
const ROTULO = "block text-xs font-semibold text-slate-500 uppercase tracking-wide mb-1";

function hojeLocal(): string {
  const agora = new Date();
  const mes = String(agora.getMonth() + 1).padStart(2, "0");
  const dia = String(agora.getDate()).padStart(2, "0");
  return `${agora.getFullYear()}-${mes}-${dia}`;
}

/**
 * Validar e acionar (issue #325, ADR 0034 decisão 3).
 *
 * O único caminho do despacho: o ouvidor confere tipo, área e gravidade, e a
 * área é acionada por email no mesmo ato. A tela avisa antes quando o setor
 * escolhido está sem titular vigente, porque aí a demanda sobe ao gestor e a
 * Diretoria recebe alerta: melhor o ouvidor saber disso antes de clicar.
 */
export function ValidarModal({ manifestacao, token, onClose, onAcionada }: ValidarModalProps) {
  const [categoria, setCategoria] = useState("");
  const [setor, setSetor] = useState("");
  const [gravidade, setGravidade] = useState<Gravidade | "">("");
  const [observacao, setObservacao] = useState("");
  const [setores, setSetores] = useState<string[]>([]);
  const [responsaveis, setResponsaveis] = useState<Responsavel[]>([]);
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    if (!manifestacao) return;
    setCategoria(manifestacao.categoria || "");
    setSetor(manifestacao.setor || "");
    setGravidade("");
    setObservacao("");
    setErro(null);
  }, [manifestacao]);

  useEffect(() => {
    if (!manifestacao || !token) return;
    let cancelado = false;
    const headers = { Authorization: `Bearer ${token}` };
    Promise.all([
      fetch("/api/participantes/setores", { headers }).then((r) => (r.ok ? r.json() : [])),
      fetch("/api/ouvidoria/responsaveis", { headers }).then((r) =>
        r.ok ? r.json() : { responsaveis: [] }
      ),
    ])
      .then(([lista, cadastro]) => {
        if (cancelado) return;
        setSetores(Array.isArray(lista) ? lista : []);
        setResponsaveis(cadastro.responsaveis ?? []);
      })
      .catch(() => {
        if (!cancelado) setSetores([]);
      });
    return () => {
      cancelado = true;
    };
  }, [manifestacao, token]);

  const doSetor = responsaveis.filter((r) => r.setor === setor);
  const semTitular = Boolean(setor) && !setorTemTitularVigente(doSetor, hojeLocal());
  const semNinguem = Boolean(setor) && doSetor.length === 0;
  const pronto = Boolean(categoria.trim() && setor.trim() && gravidade) && !salvando;

  async function acionar() {
    if (!manifestacao || !token || !gravidade) return;
    setSalvando(true);
    setErro(null);
    try {
      const res = await fetch(`/api/ouvidoria/manifestacoes/${manifestacao.id}/validar`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
        body: JSON.stringify({
          categoria: categoria.trim(),
          setor: setor.trim(),
          gravidade,
          observacao: observacao.trim() || null,
        }),
      });
      if (res.ok) {
        onAcionada();
        onClose();
        return;
      }
      const corpo = await res.json().catch(() => ({}));
      setErro(corpo.detail || "Não foi possível acionar a área. Tente novamente.");
    } catch {
      setErro("Não foi possível acionar a área. Tente novamente.");
    } finally {
      setSalvando(false);
    }
  }

  return (
    <AdminModal
      open={Boolean(manifestacao)}
      onClose={onClose}
      title={manifestacao ? `Validar e acionar ${manifestacao.protocolo}` : "Validar e acionar"}
      description="O setor recebe o email de acionamento com o prazo assim que você confirmar."
      icon={<Send className="w-5 h-5" />}
      size="lg"
      scrollable
    >
      <div className="space-y-5">
        <div>
          <label className={ROTULO} htmlFor="validar-categoria">
            Tipo da manifestação
          </label>
          <input
            id="validar-categoria"
            className={CAMPO}
            value={categoria}
            onChange={(e) => setCategoria(e.target.value)}
            placeholder="Reclamação, denúncia, elogio, sugestão..."
          />
        </div>

        <div>
          <label className={ROTULO} htmlFor="validar-setor">
            Área responsável
          </label>
          <select
            id="validar-setor"
            className={CAMPO}
            value={setor}
            onChange={(e) => setSetor(e.target.value)}
          >
            <option value="">Escolha o setor</option>
            {setores.map((nome) => (
              <option key={nome} value={nome}>
                {nome}
              </option>
            ))}
            {setor && !setores.includes(setor) && <option value={setor}>{setor}</option>}
          </select>
        </div>

        {semNinguem ? (
          <div className="flex items-start gap-2 px-4 py-3 rounded-xl bg-red-50 border border-red-200 text-red-700 text-sm">
            <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
            <span>
              Este setor não tem titular nem gestor cadastrado. Peça à Diretoria Executiva para
              cadastrar o responsável antes de acionar.
            </span>
          </div>
        ) : semTitular ? (
          <div className="flex items-start gap-2 px-4 py-3 rounded-xl bg-amber-50 border border-amber-200 text-amber-800 text-sm">
            <ShieldAlert className="w-4 h-4 shrink-0 mt-0.5" />
            <span>
              Setor sem titular vigente. A demanda vai subir ao gestor da área e a Diretoria
              Executiva recebe o alerta.
            </span>
          </div>
        ) : null}

        <div>
          <span className={ROTULO}>Gravidade</span>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            {GRAVIDADES.map((nivel) => (
              <button
                key={nivel}
                type="button"
                onClick={() => setGravidade(nivel)}
                className={`text-left px-3 py-2.5 rounded-xl border transition-colors ${
                  gravidade === nivel
                    ? CLASSE_GRAVIDADE[nivel]
                    : "bg-white border-slate-200 hover:bg-slate-50"
                }`}
              >
                <span className="block text-sm font-semibold">{LABEL_GRAVIDADE[nivel]}</span>
                <span className="block text-xs mt-0.5 opacity-80">{AJUDA_GRAVIDADE[nivel]}</span>
              </button>
            ))}
          </div>
        </div>

        <div>
          <label className={ROTULO} htmlFor="validar-observacao">
            Observação da validação (opcional)
          </label>
          <textarea
            id="validar-observacao"
            className={`${CAMPO} min-h-[70px]`}
            value={observacao}
            onChange={(e) => setObservacao(e.target.value)}
            placeholder="Fica na trilha do caso, junto do movimento de acionamento."
          />
        </div>

        {erro && (
          <div className="flex items-start gap-2 px-4 py-3 rounded-xl bg-red-50 border border-red-200 text-red-700 text-sm">
            <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
            {erro}
          </div>
        )}

        <div className="flex items-center justify-end gap-2 pt-1">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 rounded-lg text-sm font-medium text-slate-600 hover:bg-slate-100 transition-colors"
          >
            Cancelar
          </button>
          <button
            type="button"
            onClick={acionar}
            disabled={!pronto}
            className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-semibold bg-primary text-white hover:bg-primary/90 disabled:opacity-50 transition-colors"
          >
            {salvando ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <CheckCircle2 className="w-4 h-4" />
            )}
            Validar e acionar a área
          </button>
        </div>
      </div>
    </AdminModal>
  );
}

export default ValidarModal;
