"use client";

/**
 * Pontos de escuta: os cartazes de QR da Ouvidoria (issue #378, ADR 0036).
 *
 * Cada linha é um cartaz impresso. O ouvidor cadastra o lugar, vê o QR na tela
 * e baixa o cartaz A5 pronto para a gráfica. O código curto que vai no papel é
 * sorteado pelo servidor e nunca muda: renomear o ponto ou aposentar o cartaz
 * não invalida o que já está na parede.
 *
 * Os dois perfis da Ouvidoria abrem esta tela, e não só a Diretoria: cartaz é
 * operação do canal. O backend recusa de novo, para quem chamar a API direto.
 */

import { useEffect, useState } from "react";
import Link from "next/link";
import { createClient } from "@/lib/supabase/client";
import {
  AlertCircle,
  ArrowLeft,
  Download,
  FileText,
  Loader2,
  MapPin,
  Plus,
  Power,
} from "lucide-react";
import { useCurrentParticipante } from "@/hooks/useCurrentParticipante";
import {
  agruparPorSetor,
  nomeDoArquivo,
  podeGerirPontos,
  pontoEstaCompleto,
  type PontoDeEscuta,
} from "@/lib/ouvidoria/pontos";

const CAMPO =
  "w-full px-3 py-2 rounded-lg border border-slate-200 text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary/40";
const ROTULO = "block text-xs font-semibold text-slate-500 uppercase tracking-wide mb-1";

const VAZIO = { setor: "", ponto: "" };

export default function PontosDeEscutaPage() {
  const { participante, loading: carregandoPerfil } = useCurrentParticipante();
  const podeGerir = podeGerirPontos(participante?.perfil_ouvidoria);

  const [token, setToken] = useState<string | null>(null);
  const [pontos, setPontos] = useState<PontoDeEscuta[]>([]);
  const [setores, setSetores] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [erro, setErro] = useState<string | null>(null);
  const [novo, setNovo] = useState(VAZIO);
  const [salvando, setSalvando] = useState(false);
  const [mudando, setMudando] = useState<string | null>(null);
  const [editando, setEditando] = useState<string | null>(null);
  const [rotuloEditado, setRotuloEditado] = useState("");

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
        const [resPontos, resSetores] = await Promise.all([
          fetch("/api/ouvidoria/pontos", { headers }),
          fetch("/api/participantes/setores", { headers }),
        ]);
        if (!resPontos.ok) {
          setErro("Não foi possível carregar os pontos de escuta.");
        } else {
          setPontos((await resPontos.json()).pontos);
          setSetores(resSetores.ok ? await resSetores.json() : []);
        }
      } catch (e) {
        console.error("Erro ao carregar pontos de escuta:", e);
        setErro("Não foi possível carregar os pontos de escuta.");
      } finally {
        setLoading(false);
      }
    }
    init();
  }, []);

  async function recarregar(sessionToken: string) {
    const res = await fetch("/api/ouvidoria/pontos", {
      headers: { Authorization: `Bearer ${sessionToken}` },
    });
    if (res.ok) setPontos((await res.json()).pontos);
  }

  async function cadastrar() {
    if (!token) return;
    setSalvando(true);
    setErro(null);
    try {
      const res = await fetch("/api/ouvidoria/pontos", {
        method: "POST",
        headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
        body: JSON.stringify({ setor: novo.setor, ponto: novo.ponto.trim() }),
      });
      if (res.ok) {
        setNovo(VAZIO);
        await recarregar(token);
      } else {
        const corpo = await res.json().catch(() => ({}));
        setErro(
          typeof corpo.detail === "string"
            ? corpo.detail
            : "Não foi possível cadastrar o ponto de escuta. Confira os dados."
        );
      }
    } catch {
      setErro("Não foi possível cadastrar o ponto de escuta. Tente novamente.");
    } finally {
      setSalvando(false);
    }
  }

  async function editar(ponto: PontoDeEscuta, mudanca: Record<string, unknown>) {
    if (!token) return;
    setMudando(ponto.id);
    setErro(null);
    try {
      const res = await fetch(`/api/ouvidoria/pontos/${ponto.id}`, {
        method: "PATCH",
        headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
        body: JSON.stringify(mudanca),
      });
      if (res.ok) await recarregar(token);
      else setErro("Não foi possível salvar a mudança. Tente novamente.");
    } catch {
      setErro("Não foi possível salvar a mudança. Tente novamente.");
    } finally {
      setMudando(null);
      setEditando(null);
    }
  }

  async function baixar(ponto: PontoDeEscuta, tipo: "png" | "pdf") {
    if (!token) return;
    const caminho = tipo === "pdf" ? "cartaz.pdf" : "qr.png";
    try {
      // O download passa por fetch porque a rota é autenticada por header, e um
      // `<a href>` direto iria sem o token.
      const res = await fetch(`/api/ouvidoria/pontos/${ponto.id}/${caminho}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) {
        setErro("Não foi possível baixar o arquivo. Tente novamente.");
        return;
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = nomeDoArquivo(ponto, tipo);
      link.click();
      URL.revokeObjectURL(url);
    } catch {
      setErro("Não foi possível baixar o arquivo. Tente novamente.");
    }
  }

  const grupos = agruparPorSetor(pontos);
  const prontoParaCadastrar = pontoEstaCompleto(novo) && !salvando;

  if (!carregandoPerfil && !podeGerir) {
    return (
      <div className="p-4 md:p-8 max-w-3xl mx-auto">
        <div className="bg-white rounded-2xl border border-border shadow-premium p-10 text-center">
          <p className="text-slate-500 font-medium">
            Só o Perfil da Ouvidoria mantém os pontos de escuta.
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

      <h1 className="text-2xl font-bold text-slate-900">Pontos de escuta</h1>
      <p className="text-slate-500 text-sm mt-0.5 mb-6">
        Cada ponto é um cartaz de QR code. Baixe o cartaz A5 e cole no lugar cadastrado: quem ler o
        código cai no formulário da Ouvidoria, e o caso já chega dizendo de onde veio.
      </p>

      {erro && (
        <div className="flex items-start gap-2 mb-4 px-4 py-3 rounded-xl bg-red-50 border border-red-200 text-red-700 text-sm">
          <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
          {erro}
        </div>
      )}

      <section className="bg-white rounded-2xl border border-border shadow-premium p-5 mb-6">
        <h2 className="text-sm font-semibold text-slate-700 mb-3">Novo ponto de escuta</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <div>
            <label className={ROTULO} htmlFor="ponto-setor">
              Setor
            </label>
            <select
              id="ponto-setor"
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
            <label className={ROTULO} htmlFor="ponto-rotulo">
              Onde o cartaz vai ficar
            </label>
            <input
              id="ponto-rotulo"
              className={CAMPO}
              placeholder="Poltrona 12"
              maxLength={80}
              value={novo.ponto}
              onChange={(e) => setNovo({ ...novo, ponto: e.target.value })}
            />
          </div>
        </div>
        <button
          type="button"
          disabled={!prontoParaCadastrar}
          onClick={cadastrar}
          className="mt-4 inline-flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-semibold bg-primary text-white disabled:opacity-40 disabled:cursor-not-allowed"
        >
          {salvando ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />}
          Criar cartaz
        </button>
      </section>

      {loading ? (
        <div className="flex justify-center py-12">
          <Loader2 className="w-6 h-6 text-primary animate-spin" />
        </div>
      ) : grupos.length === 0 ? (
        <div className="bg-white rounded-2xl border border-border shadow-premium p-10 text-center">
          <MapPin className="w-8 h-8 text-slate-300 mx-auto mb-3" />
          <p className="text-slate-500 text-sm">
            Nenhum cartaz cadastrado ainda. Crie o primeiro acima e cole na parede.
          </p>
        </div>
      ) : (
        grupos.map((grupo) => (
          <section key={grupo.setor} className="mb-6">
            <h2 className="text-sm font-bold text-slate-700 mb-2">{grupo.setor}</h2>
            <div className="space-y-3">
              {grupo.pontos.map((ponto) => (
                <div
                  key={ponto.id}
                  className={`bg-white rounded-2xl border border-border shadow-premium p-4 flex flex-col sm:flex-row sm:items-center gap-4 ${
                    ponto.ativo ? "" : "opacity-60"
                  }`}
                >
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img
                    src={ponto.qr_data_uri}
                    alt={`QR code do cartaz ${ponto.codigo}`}
                    className="w-24 h-24 shrink-0 rounded-lg border border-slate-100"
                  />

                  <div className="flex-1 min-w-0">
                    {editando === ponto.id ? (
                      <div className="flex items-center gap-2">
                        <input
                          className={CAMPO}
                          maxLength={80}
                          value={rotuloEditado}
                          onChange={(e) => setRotuloEditado(e.target.value)}
                        />
                        <button
                          type="button"
                          disabled={!rotuloEditado.trim()}
                          onClick={() => editar(ponto, { ponto: rotuloEditado.trim() })}
                          className="px-3 py-2 rounded-lg text-sm font-semibold bg-slate-100 text-slate-700 disabled:opacity-40"
                        >
                          Salvar
                        </button>
                      </div>
                    ) : (
                      <button
                        type="button"
                        onClick={() => {
                          setEditando(ponto.id);
                          setRotuloEditado(ponto.ponto);
                        }}
                        className="text-left font-semibold text-slate-800 hover:text-primary"
                      >
                        {ponto.ponto}
                      </button>
                    )}
                    <p className="text-xs text-slate-500 mt-1">
                      Código <span className="font-mono font-semibold">{ponto.codigo}</span>
                      {!ponto.ativo && <span className="ml-2 text-amber-600">Aposentado</span>}
                    </p>
                  </div>

                  <div className="flex flex-wrap items-center gap-2">
                    <button
                      type="button"
                      onClick={() => baixar(ponto, "pdf")}
                      className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm font-semibold bg-primary/10 text-primary"
                    >
                      <FileText className="w-4 h-4" />
                      Cartaz A5
                    </button>
                    <button
                      type="button"
                      onClick={() => baixar(ponto, "png")}
                      className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm font-semibold bg-slate-100 text-slate-700"
                    >
                      <Download className="w-4 h-4" />
                      PNG
                    </button>
                    <button
                      type="button"
                      disabled={mudando === ponto.id}
                      onClick={() => editar(ponto, { ativo: !ponto.ativo })}
                      className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm font-semibold bg-slate-100 text-slate-600 disabled:opacity-40"
                    >
                      {mudando === ponto.id ? (
                        <Loader2 className="w-4 h-4 animate-spin" />
                      ) : (
                        <Power className="w-4 h-4" />
                      )}
                      {ponto.ativo ? "Aposentar" : "Reativar"}
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </section>
        ))
      )}

      <p className="text-xs text-slate-400 mt-6 leading-relaxed">
        Aposentar não apaga o cartaz nem muda o código: quem ler um QR aposentado continua caindo no
        formulário da Ouvidoria, só que sem dizer de onde veio.
      </p>
    </div>
  );
}
