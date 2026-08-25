"use client";

/**
 * Responsáveis por setor (issue #325, ADR 0034 decisão 5).
 *
 * Titular, substituto e gestor de cada setor, com vigência. É este cadastro
 * que decide para quem o email de acionamento vai: setor sem titular vigente
 * não é acionável e a demanda sobe ao gestor, com alerta à Diretoria.
 *
 * Só a Diretoria Executiva abre esta tela, a mesma régua da tabela de prazos.
 * O backend recusa de novo, para quem chamar a API direto.
 */

import { useEffect, useState } from "react";
import Link from "next/link";
import { createClient } from "@/lib/supabase/client";
import { AlertCircle, ArrowLeft, Loader2, Plus, Trash2, UserRoundX } from "lucide-react";
import { useCurrentParticipante } from "@/hooks/useCurrentParticipante";
import {
  AJUDA_PAPEL,
  LABEL_PAPEL,
  PAPEIS,
  estaVigente,
  podeGerirResponsaveis,
  setorTemTitularVigente,
  type PapelResponsavel,
  type Responsavel,
} from "@/lib/ouvidoria/validacao";

const CAMPO =
  "w-full px-3 py-2 rounded-lg border border-slate-200 text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary/40";
const ROTULO = "block text-xs font-semibold text-slate-500 uppercase tracking-wide mb-1";

interface Novo {
  setor: string;
  papel: PapelResponsavel;
  nome: string;
  email: string;
  vigencia_inicio: string;
  vigencia_fim: string;
}

const VAZIO: Novo = {
  setor: "",
  papel: "titular",
  nome: "",
  email: "",
  vigencia_inicio: "",
  vigencia_fim: "",
};

function hojeLocal(): string {
  const agora = new Date();
  const mes = String(agora.getMonth() + 1).padStart(2, "0");
  const dia = String(agora.getDate()).padStart(2, "0");
  return `${agora.getFullYear()}-${mes}-${dia}`;
}

function formatarData(iso: string | null): string {
  if (!iso) return "sem data de saída";
  return new Date(`${iso}T12:00:00`).toLocaleDateString("pt-BR");
}

export default function ResponsaveisDaOuvidoriaPage() {
  const { participante, loading: carregandoPerfil } = useCurrentParticipante();
  const podeEditar = podeGerirResponsaveis(participante?.perfil_ouvidoria);

  const [token, setToken] = useState<string | null>(null);
  const [responsaveis, setResponsaveis] = useState<Responsavel[]>([]);
  const [setores, setSetores] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [erro, setErro] = useState<string | null>(null);
  const [novo, setNovo] = useState<Novo>(VAZIO);
  const [salvando, setSalvando] = useState(false);
  const [encerrando, setEncerrando] = useState<string | null>(null);

  useEffect(() => {
    async function init() {
      const supabase = createClient();
      const {
        data: { session },
      } = await supabase.auth.getSession();
      const sessionToken = session?.access_token ?? null;
      setToken(sessionToken);
      if (!sessionToken) {
        setLoading(false);
        return;
      }
      const headers = { Authorization: `Bearer ${sessionToken}` };
      try {
        const [resCadastro, resSetores] = await Promise.all([
          fetch("/api/ouvidoria/responsaveis", { headers }),
          fetch("/api/participantes/setores", { headers }),
        ]);
        if (!resCadastro.ok) {
          setErro("Não foi possível carregar o cadastro de responsáveis.");
        } else {
          setResponsaveis((await resCadastro.json()).responsaveis);
          setSetores(resSetores.ok ? await resSetores.json() : []);
        }
      } catch (e) {
        console.error("Erro ao carregar responsáveis da ouvidoria:", e);
        setErro("Não foi possível carregar o cadastro de responsáveis.");
      } finally {
        setLoading(false);
      }
    }
    init();
  }, []);

  async function recarregar(sessionToken: string) {
    const res = await fetch("/api/ouvidoria/responsaveis", {
      headers: { Authorization: `Bearer ${sessionToken}` },
    });
    if (res.ok) setResponsaveis((await res.json()).responsaveis);
  }

  async function cadastrar() {
    if (!token) return;
    setSalvando(true);
    setErro(null);
    try {
      const res = await fetch("/api/ouvidoria/responsaveis", {
        method: "POST",
        headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
        body: JSON.stringify({
          setor: novo.setor,
          papel: novo.papel,
          nome: novo.nome,
          email: novo.email,
          vigencia_inicio: novo.vigencia_inicio || null,
          vigencia_fim: novo.vigencia_fim || null,
        }),
      });
      if (res.ok) {
        setNovo(VAZIO);
        await recarregar(token);
      } else {
        const corpo = await res.json().catch(() => ({}));
        setErro(
          typeof corpo.detail === "string"
            ? corpo.detail
            : "Não foi possível cadastrar o responsável. Confira os dados."
        );
      }
    } catch {
      setErro("Não foi possível cadastrar o responsável. Tente novamente.");
    } finally {
      setSalvando(false);
    }
  }

  async function encerrarVigencia(responsavel: Responsavel) {
    if (!token) return;
    setEncerrando(responsavel.id);
    setErro(null);
    try {
      const res = await fetch(`/api/ouvidoria/responsaveis/${responsavel.id}`, {
        method: "PUT",
        headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
        body: JSON.stringify({
          nome: responsavel.nome,
          email: responsavel.email,
          vigencia_inicio: responsavel.vigencia_inicio,
          vigencia_fim: hojeLocal(),
        }),
      });
      if (res.ok) await recarregar(token);
      else setErro("Não foi possível encerrar a vigência. Tente novamente.");
    } catch {
      setErro("Não foi possível encerrar a vigência. Tente novamente.");
    } finally {
      setEncerrando(null);
    }
  }

  async function remover(responsavel: Responsavel) {
    if (!token) return;
    setEncerrando(responsavel.id);
    try {
      const res = await fetch(`/api/ouvidoria/responsaveis/${responsavel.id}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) await recarregar(token);
      else setErro("Não foi possível remover o responsável. Tente novamente.");
    } catch {
      setErro("Não foi possível remover o responsável. Tente novamente.");
    } finally {
      setEncerrando(null);
    }
  }

  const hoje = hojeLocal();
  const porSetor = Array.from(new Set(responsaveis.map((r) => r.setor))).sort();
  const prontoParaCadastrar =
    Boolean(novo.setor && novo.nome.trim() && novo.email.trim()) && !salvando;

  if (!carregandoPerfil && !podeEditar) {
    return (
      <div className="p-4 md:p-8 max-w-3xl mx-auto">
        <div className="bg-white rounded-2xl border border-border shadow-premium p-10 text-center">
          <p className="text-slate-500 font-medium">
            Só a Diretoria Executiva mantém o cadastro de responsáveis por setor.
          </p>
          <Link href="/ouvidoria" className="text-primary text-sm font-semibold mt-3 inline-block">
            Voltar para a Ouvidoria
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="p-4 md:p-8 max-w-5xl mx-auto">
      <Link
        href="/ouvidoria"
        className="inline-flex items-center gap-1.5 text-sm text-slate-500 hover:text-slate-700 mb-4"
      >
        <ArrowLeft className="w-4 h-4" />
        Ouvidoria
      </Link>

      <h1 className="text-2xl font-bold text-slate-900">Responsáveis por setor</h1>
      <p className="text-slate-500 text-sm mt-0.5 mb-6">
        O titular recebe o acionamento da Ouvidoria. Setor sem titular vigente não é acionável: a
        demanda sobe ao gestor da área e a Diretoria recebe o alerta.
      </p>

      {erro && (
        <div className="flex items-start gap-2 mb-4 px-4 py-3 rounded-xl bg-red-50 border border-red-200 text-red-700 text-sm">
          <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
          {erro}
        </div>
      )}

      <section className="bg-white rounded-2xl border border-border shadow-premium p-5 mb-6">
        <h2 className="text-sm font-semibold text-slate-700 mb-3">Cadastrar responsável</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <div>
            <label className={ROTULO} htmlFor="resp-setor">
              Setor
            </label>
            <select
              id="resp-setor"
              className={CAMPO}
              value={novo.setor}
              onChange={(e) => setNovo({ ...novo, setor: e.target.value })}
            >
              <option value="">Escolha o setor</option>
              {setores.map((nome) => (
                <option key={nome} value={nome}>
                  {nome}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className={ROTULO} htmlFor="resp-papel">
              Papel
            </label>
            <select
              id="resp-papel"
              className={CAMPO}
              value={novo.papel}
              onChange={(e) => setNovo({ ...novo, papel: e.target.value as PapelResponsavel })}
            >
              {PAPEIS.map((papel) => (
                <option key={papel} value={papel}>
                  {LABEL_PAPEL[papel]}
                </option>
              ))}
            </select>
            <p className="text-[11px] text-slate-400 mt-1">{AJUDA_PAPEL[novo.papel]}</p>
          </div>
          <div>
            <label className={ROTULO} htmlFor="resp-nome">
              Nome
            </label>
            <input
              id="resp-nome"
              className={CAMPO}
              value={novo.nome}
              onChange={(e) => setNovo({ ...novo, nome: e.target.value })}
            />
          </div>
          <div>
            <label className={ROTULO} htmlFor="resp-email">
              Email
            </label>
            <input
              id="resp-email"
              type="email"
              className={CAMPO}
              value={novo.email}
              onChange={(e) => setNovo({ ...novo, email: e.target.value })}
            />
          </div>
          <div>
            <label className={ROTULO} htmlFor="resp-inicio">
              Início da vigência
            </label>
            <input
              id="resp-inicio"
              type="date"
              className={CAMPO}
              value={novo.vigencia_inicio}
              onChange={(e) => setNovo({ ...novo, vigencia_inicio: e.target.value })}
            />
          </div>
          <div>
            <label className={ROTULO} htmlFor="resp-fim">
              Fim da vigência (opcional)
            </label>
            <input
              id="resp-fim"
              type="date"
              className={CAMPO}
              value={novo.vigencia_fim}
              onChange={(e) => setNovo({ ...novo, vigencia_fim: e.target.value })}
            />
          </div>
        </div>
        <div className="flex justify-end mt-4">
          <button
            type="button"
            onClick={cadastrar}
            disabled={!prontoParaCadastrar}
            className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-semibold bg-primary text-white hover:bg-primary/90 disabled:opacity-50 transition-colors"
          >
            {salvando ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />}
            Cadastrar
          </button>
        </div>
      </section>

      <div className="bg-white rounded-2xl border border-border shadow-premium overflow-hidden">
        {loading ? (
          <div className="flex items-center justify-center h-40 gap-2 text-slate-400 text-sm">
            <Loader2 className="w-5 h-5 animate-spin text-primary/40" />
            Carregando o cadastro...
          </div>
        ) : responsaveis.length === 0 ? (
          <div className="text-center py-14 text-slate-500 text-sm">
            Nenhum responsável cadastrado. Enquanto isso, nenhum setor pode ser acionado.
          </div>
        ) : (
          <div className="divide-y divide-slate-100">
            {porSetor.map((setor) => {
              const doSetor = responsaveis.filter((r) => r.setor === setor);
              const acionavel = setorTemTitularVigente(doSetor, hoje);
              return (
                <section key={setor}>
                  <header className="flex items-center gap-2 px-5 py-3 bg-slate-50 border-b border-slate-100">
                    <span className="text-sm font-semibold text-slate-700">{setor}</span>
                    {!acionavel && (
                      <span className="inline-flex items-center gap-1 text-[11px] font-bold uppercase tracking-wide bg-amber-100 text-amber-700 px-2 py-0.5 rounded-full">
                        <UserRoundX className="w-3 h-3" />
                        Sem titular vigente
                      </span>
                    )}
                  </header>
                  <ul className="divide-y divide-slate-50">
                    {doSetor.map((r) => {
                      const vigente = estaVigente(r, hoje);
                      return (
                        <li
                          key={r.id}
                          className="flex flex-wrap items-center gap-3 px-5 py-3 text-sm"
                        >
                          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold bg-slate-100 text-slate-600">
                            {LABEL_PAPEL[r.papel]}
                          </span>
                          <span className="font-medium text-slate-800">{r.nome}</span>
                          <span className="text-slate-500">{r.email}</span>
                          <span className={vigente ? "text-slate-400 text-xs" : "text-amber-600 text-xs"}>
                            {vigente ? "vigente" : "fora de vigência"}, de{" "}
                            {formatarData(r.vigencia_inicio)} até {formatarData(r.vigencia_fim)}
                          </span>
                          <span className="ml-auto flex items-center gap-2">
                            {vigente && (
                              <button
                                type="button"
                                onClick={() => encerrarVigencia(r)}
                                disabled={encerrando === r.id}
                                className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-slate-100 text-slate-700 hover:bg-slate-200 disabled:opacity-50 transition-colors"
                              >
                                Encerrar vigência hoje
                              </button>
                            )}
                            <button
                              type="button"
                              onClick={() => remover(r)}
                              disabled={encerrando === r.id}
                              title="Remover do cadastro"
                              className="p-1.5 rounded-lg text-slate-400 hover:text-red-600 hover:bg-red-50 disabled:opacity-50 transition-colors"
                            >
                              <Trash2 className="w-4 h-4" />
                            </button>
                          </span>
                        </li>
                      );
                    })}
                  </ul>
                </section>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
