"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { Check, Edit3, Search, UserMinus, UserPlus, X } from "lucide-react";
import {
  useBuscaParticipantes,
  useInternosAtivos,
  type ParticipanteBusca,
} from "@/hooks/useBuscaParticipantes";

export type ResolucaoEstado =
  | { tipo: "pendente" }
  | { tipo: "vinculado"; participante: ParticipanteBusca }
  | {
      tipo: "cadastrar_externo";
      dados: { nome_completo: string; email?: string; cargo?: string };
    }
  | { tipo: "ignorar" };

interface ParticipanteComboboxProps {
  nomeSugerido: string;
  cargoSugerido?: string | null;
  estado: ResolucaoEstado;
  onSelecionarExistente: (p: ParticipanteBusca) => void;
  onCadastrarExterno: (dados: {
    nome_completo: string;
    email?: string;
    cargo?: string;
  }) => void;
  onIgnorar: () => void;
  onAlterar: () => void;
}

export function ParticipanteCombobox({
  nomeSugerido,
  cargoSugerido,
  estado,
  onSelecionarExistente,
  onCadastrarExterno,
  onIgnorar,
  onAlterar,
}: ParticipanteComboboxProps) {
  const [termo, setTermo] = useState(nomeSugerido);
  const [open, setOpen] = useState(false);
  const [highlight, setHighlight] = useState(-1);
  const [modoCadastro, setModoCadastro] = useState(false);
  const [emailNovo, setEmailNovo] = useState("");
  const [cargoNovo, setCargoNovo] = useState(cargoSugerido ?? "");

  const containerRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const { resultados, loading } = useBuscaParticipantes(termo, 250, 10);
  const { internos: todosInternos } = useInternosAtivos(open, 100);

  const { internos, externos } = useMemo(() => {
    const internos: ParticipanteBusca[] = [];
    const externos: ParticipanteBusca[] = [];
    for (const p of resultados) {
      if (p.is_externo) externos.push(p);
      else internos.push(p);
    }
    return { internos, externos };
  }, [resultados]);

  const sugestoesInternos = useMemo(() => {
    const idsNosResultados = new Set(internos.map((p) => p.id));
    return todosInternos.filter((p) => !idsNosResultados.has(p.id)).slice(0, 8);
  }, [todosInternos, internos]);

  const itensOrdenados = useMemo(
    () => [...internos, ...externos, ...sugestoesInternos],
    [internos, externos, sugestoesInternos],
  );

  useEffect(() => {
    if (estado.tipo === "pendente") {
      setTermo(nomeSugerido);
      setCargoNovo(cargoSugerido ?? "");
      setEmailNovo("");
      setModoCadastro(false);
    }
  }, [estado.tipo, nomeSugerido, cargoSugerido]);

  useEffect(() => {
    function clickFora(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
        setModoCadastro(false);
      }
    }
    document.addEventListener("mousedown", clickFora);
    return () => document.removeEventListener("mousedown", clickFora);
  }, []);

  useEffect(() => {
    setHighlight(itensOrdenados.length > 0 ? 0 : -1);
  }, [itensOrdenados.length]);

  // ── Estado resolvido: card compacto ──
  if (estado.tipo !== "pendente") {
    return (
      <ResumoResolvido estado={estado} onAlterar={onAlterar} />
    );
  }

  const termoTemConteudo = termo.trim().length > 0;
  const podeBuscar = termo.trim().length >= 2;
  const semResultados = podeBuscar && !loading && resultados.length === 0;

  function handleSelecionar(p: ParticipanteBusca) {
    setOpen(false);
    onSelecionarExistente(p);
  }

  function handleConfirmarCadastro() {
    const nome = termo.trim();
    if (!nome) return;
    setOpen(false);
    onCadastrarExterno({
      nome_completo: nome,
      email: emailNovo.trim() || undefined,
      cargo: cargoNovo.trim() || undefined,
    });
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (modoCadastro) return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setOpen(true);
      setHighlight((i) => Math.min(i + 1, itensOrdenados.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setHighlight((i) => Math.max(i - 1, 0));
    } else if (e.key === "Enter") {
      if (open && highlight >= 0 && itensOrdenados[highlight]) {
        e.preventDefault();
        handleSelecionar(itensOrdenados[highlight]);
      }
    } else if (e.key === "Escape") {
      setOpen(false);
    }
  }

  return (
    <div ref={containerRef} className="relative">
      <div className="flex items-start gap-2">
        <div className="relative flex-1">
          <div className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none">
            <Search className="w-4 h-4" />
          </div>
          <input
            ref={inputRef}
            type="text"
            value={termo}
            onChange={(e) => {
              setTermo(e.target.value);
              setOpen(true);
              setModoCadastro(false);
            }}
            onFocus={() => setOpen(true)}
            onKeyDown={handleKeyDown}
            placeholder="Buscar interno ou digite nome externo..."
            className="w-full pl-9 pr-3 py-2.5 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-amber-400 focus:border-transparent bg-white"
          />
        </div>
        <button
          type="button"
          onClick={onIgnorar}
          className="shrink-0 px-3 py-2.5 text-xs font-medium text-slate-500 hover:text-slate-700 hover:bg-slate-100 rounded-lg inline-flex items-center gap-1.5 transition-colors"
          title="Marcar como nome inexistente"
        >
          <UserMinus className="w-3.5 h-3.5" />
          Ignorar
        </button>
      </div>

      {/* Dropdown */}
      {open && (
        <div className="absolute left-0 right-0 mt-1 bg-white border border-slate-200 rounded-lg shadow-lg z-20 max-h-80 overflow-y-auto">
          {!podeBuscar && (
            <div className="px-3 py-4 text-xs text-slate-400 text-center">
              Digite pelo menos 2 caracteres para buscar participantes cadastrados
            </div>
          )}

          {loading && (
            <div className="px-3 py-4 text-xs text-slate-400 text-center">Buscando...</div>
          )}

          {!loading && internos.length > 0 && (
            <GrupoResultados
              titulo="Internos"
              cor="emerald"
              itens={internos}
              highlight={highlight}
              offset={0}
              onEscolher={handleSelecionar}
            />
          )}

          {!loading && externos.length > 0 && (
            <GrupoResultados
              titulo="Externos já cadastrados"
              cor="amber"
              itens={externos}
              highlight={highlight}
              offset={internos.length}
              onEscolher={handleSelecionar}
            />
          )}

          {sugestoesInternos.length > 0 && (
            <GrupoResultados
              titulo={
                resultados.length > 0
                  ? "Outros internos cadastrados"
                  : "Sugestões: Internos cadastrados"
              }
              cor="emerald"
              itens={sugestoesInternos}
              highlight={highlight}
              offset={internos.length + externos.length}
              onEscolher={handleSelecionar}
            />
          )}

          {semResultados && sugestoesInternos.length === 0 && !modoCadastro && (
            <div className="px-3 py-3 text-xs text-slate-500">
              Nenhum participante encontrado com esse nome.
            </div>
          )}

          {/* Rodapé fixo: cadastrar como externo */}
          {termoTemConteudo && !modoCadastro && (
            <button
              type="button"
              onClick={() => {
                setModoCadastro(true);
                setEmailNovo("");
                setCargoNovo(cargoSugerido ?? "");
              }}
              className="w-full border-t border-slate-100 px-3 py-2.5 text-xs font-medium text-left text-amber-700 hover:bg-amber-50 inline-flex items-center gap-1.5 transition-colors"
            >
              <UserPlus className="w-3.5 h-3.5" />
              Cadastrar &quot;{termo.trim()}&quot; como externo
            </button>
          )}

          {modoCadastro && (
            <div className="border-t border-slate-100 p-3 space-y-2 bg-amber-50/40">
              <div>
                <label className="text-[11px] font-medium text-slate-500 uppercase block mb-1">
                  Email (opcional)
                </label>
                <input
                  type="email"
                  value={emailNovo}
                  onChange={(e) => setEmailNovo(e.target.value)}
                  placeholder="email@exemplo.com"
                  className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-amber-400 focus:border-transparent"
                />
              </div>
              <div>
                <label className="text-[11px] font-medium text-slate-500 uppercase block mb-1">
                  Cargo (opcional)
                </label>
                <input
                  type="text"
                  value={cargoNovo}
                  onChange={(e) => setCargoNovo(e.target.value)}
                  placeholder="Cargo ou função"
                  className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-amber-400 focus:border-transparent"
                />
              </div>
              <div className="flex gap-2 pt-1">
                <button
                  type="button"
                  onClick={handleConfirmarCadastro}
                  className="flex-1 bg-amber-500 text-white px-3 py-1.5 rounded-lg text-sm font-medium hover:bg-amber-600 inline-flex items-center justify-center gap-1.5 transition-colors"
                >
                  <Check className="w-3.5 h-3.5" />
                  Confirmar externo
                </button>
                <button
                  type="button"
                  onClick={() => setModoCadastro(false)}
                  className="px-3 py-1.5 rounded-lg text-sm font-medium text-slate-500 hover:bg-slate-100 inline-flex items-center gap-1 transition-colors"
                >
                  <X className="w-3.5 h-3.5" />
                  Cancelar
                </button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ── Subcomponentes ──

function GrupoResultados({
  titulo,
  cor,
  itens,
  highlight,
  offset,
  onEscolher,
}: {
  titulo: string;
  cor: "emerald" | "amber";
  itens: ParticipanteBusca[];
  highlight: number;
  offset: number;
  onEscolher: (p: ParticipanteBusca) => void;
}) {
  const badgeClass =
    cor === "emerald"
      ? "bg-emerald-50 text-emerald-700 border-emerald-200"
      : "bg-amber-50 text-amber-800 border-amber-200";
  const titleColor = cor === "emerald" ? "text-emerald-700" : "text-amber-700";
  return (
    <div>
      <div
        className={`px-3 pt-2.5 pb-1 text-[10px] font-semibold uppercase tracking-wider ${titleColor}`}
      >
        {titulo}
      </div>
      <div className="pb-1">
        {itens.map((p, idx) => {
          const i = offset + idx;
          const isHighlighted = highlight === i;
          return (
            <button
              key={p.id}
              type="button"
              onClick={() => onEscolher(p)}
              className={`w-full flex items-center gap-3 px-3 py-2 text-left text-sm transition-colors ${
                isHighlighted ? "bg-slate-50" : "hover:bg-slate-50"
              }`}
            >
              <div className="flex-1 min-w-0">
                <div className="font-medium text-slate-800 truncate">{p.nome_completo}</div>
                <div className="text-xs text-slate-500 truncate">
                  {[p.cargo, p.setor].filter(Boolean).join(" • ") || "-"}
                </div>
              </div>
              <span
                className={`shrink-0 text-[10px] font-semibold uppercase border rounded px-1.5 py-0.5 ${badgeClass}`}
              >
                {cor === "emerald" ? "Interno" : "Externo"}
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}

function ResumoResolvido({
  estado,
  onAlterar,
}: {
  estado: Exclude<ResolucaoEstado, { tipo: "pendente" }>;
  onAlterar: () => void;
}) {
  let texto = "";
  let corClasse = "";
  let iconeClasse = "";

  if (estado.tipo === "vinculado") {
    texto = `Vinculado a ${estado.participante.nome_completo}`;
    corClasse = estado.participante.is_externo
      ? "bg-amber-50 border-amber-200 text-amber-900"
      : "bg-emerald-50 border-emerald-200 text-emerald-900";
    iconeClasse = estado.participante.is_externo ? "text-amber-600" : "text-emerald-600";
  } else if (estado.tipo === "cadastrar_externo") {
    texto = `Cadastrar ${estado.dados.nome_completo} como externo`;
    corClasse = "bg-amber-50 border-amber-200 text-amber-900";
    iconeClasse = "text-amber-600";
  } else {
    texto = "Ignorado (não é participante real)";
    corClasse = "bg-slate-50 border-slate-200 text-slate-600";
    iconeClasse = "text-slate-400";
  }

  return (
    <div className={`flex items-center gap-3 border rounded-lg px-3 py-2.5 ${corClasse}`}>
      <Check className={`w-4 h-4 shrink-0 ${iconeClasse}`} />
      <div className="flex-1 text-sm font-medium">{texto}</div>
      <button
        type="button"
        onClick={onAlterar}
        className="shrink-0 text-xs text-slate-500 hover:text-slate-800 inline-flex items-center gap-1 font-medium transition-colors"
      >
        <Edit3 className="w-3 h-3" />
        Alterar
      </button>
    </div>
  );
}
