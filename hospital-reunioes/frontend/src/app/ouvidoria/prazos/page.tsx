"use client";

/**
 * Tabela de prazos por gravidade (issue #322, RN-21).
 *
 * Os valores da especificação da Diretoria entram por aqui, sem programador.
 * Só a Diretoria Executiva abre esta tela: o ouvidor trabalha com o prazo,
 * quem o define é ela. O backend recusa de novo, para quem chamar a API direto.
 */

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { createClient } from "@/lib/supabase/client";
import { AlertCircle, ArrowLeft, CalendarOff, Check, Loader2, Plus, Trash2 } from "lucide-react";
import { useCurrentParticipante } from "@/hooks/useCurrentParticipante";
import { podeEditarPrazos } from "@/lib/ouvidoria/prazo";

type Gravidade = "critico" | "alto" | "medio" | "baixo";
type Marco = "triagem" | "area_resposta" | "conclusiva";
type Unidade = "horas_uteis" | "dias_uteis";

interface Prazo {
  gravidade: Gravidade;
  marco: Marco;
  valor: number | null;
  unidade: Unidade;
}

interface Feriado {
  data: string;
  nome: string;
  abrangencia: "nacional" | "estadual_rj" | "municipal_rio";
}

const GRAVIDADES: Gravidade[] = ["critico", "alto", "medio", "baixo"];
const MARCOS: Marco[] = ["triagem", "area_resposta", "conclusiva"];

const LABEL_GRAVIDADE: Record<Gravidade, string> = {
  critico: "Crítico",
  alto: "Alto",
  medio: "Médio",
  baixo: "Baixo",
};

const LABEL_MARCO: Record<Marco, string> = {
  triagem: "Triagem da ouvidoria",
  area_resposta: "Resposta da área",
  conclusiva: "Resposta conclusiva",
};

const AJUDA_MARCO: Record<Marco, string> = {
  triagem: "Da entrada até o ouvidor validar e acionar a área.",
  area_resposta: "Do acionamento até a área responder.",
  conclusiva: "Da entrada até a resposta final ao manifestante.",
};

const LABEL_ABRANGENCIA: Record<Feriado["abrangencia"], string> = {
  nacional: "Nacional",
  estadual_rj: "Estadual (RJ)",
  municipal_rio: "Municipal (Rio)",
};

function chave(gravidade: Gravidade, marco: Marco): string {
  return `${gravidade}:${marco}`;
}

export default function PrazosDaOuvidoriaPage() {
  const { participante, loading: carregandoPerfil } = useCurrentParticipante();
  const podeEditar = podeEditarPrazos(participante?.perfil_ouvidoria);

  const [token, setToken] = useState<string | null>(null);
  const [prazos, setPrazos] = useState<Prazo[]>([]);
  // O que o servidor confirmou. É a partir daqui que se decide se houve
  // mudança de verdade e para onde a célula volta quando o PUT falha.
  const [persistidos, setPersistidos] = useState<Map<string, Prazo>>(new Map());
  const [feriados, setFeriados] = useState<Feriado[]>([]);
  const [loading, setLoading] = useState(true);
  const [erro, setErro] = useState<string | null>(null);
  const [salvando, setSalvando] = useState<string | null>(null);
  const [salvo, setSalvo] = useState<string | null>(null);
  const [novoFeriado, setNovoFeriado] = useState<Feriado>({
    data: "",
    nome: "",
    abrangencia: "nacional",
  });

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
      try {
        const headers = { Authorization: `Bearer ${sessionToken}` };
        const [resPrazos, resFeriados] = await Promise.all([
          fetch("/api/ouvidoria/prazos", { headers }),
          fetch("/api/ouvidoria/feriados", { headers }),
        ]);
        if (!resPrazos.ok || !resFeriados.ok) {
          setErro("Não foi possível carregar a tabela de prazos.");
        } else {
          const carregados: Prazo[] = (await resPrazos.json()).prazos;
          setPrazos(carregados);
          setPersistidos(new Map(carregados.map((p) => [chave(p.gravidade, p.marco), p])));
          setFeriados((await resFeriados.json()).feriados);
        }
      } catch (e) {
        console.error("Erro ao carregar prazos da ouvidoria:", e);
        setErro("Não foi possível carregar a tabela de prazos.");
      } finally {
        setLoading(false);
      }
    }
    init();
  }, []);

  const salvarPrazo = useCallback(
    async (gravidade: Gravidade, marco: Marco, valor: number | null, unidade: Unidade) => {
      if (!token) return;
      const id = chave(gravidade, marco);
      const anterior = persistidos.get(id);
      // Sair da célula sem mexer em nada não é alteração. O histórico da RN-21
      // é append-only e não se limpa depois: não pode encher de "mudou de 2
      // para 2" só porque a Diretoria passou o olho pela tabela.
      if (anterior && anterior.valor === valor && anterior.unidade === unidade) return;

      setSalvando(id);
      setSalvo(null);
      try {
        const res = await fetch(`/api/ouvidoria/prazos/${gravidade}/${marco}`, {
          method: "PUT",
          headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
          body: JSON.stringify({ valor, unidade }),
        });
        if (!res.ok) {
          // Sem isto a célula continuaria exibindo o número novo como se
          // estivesse salvo, e a Diretoria sairia achando que mudou o prazo.
          if (anterior) {
            setPrazos((atuais) => atuais.map((p) => (chave(p.gravidade, p.marco) === id ? { ...anterior } : p)));
          }
          setErro("Não foi possível salvar o prazo. O valor anterior foi mantido.");
          return;
        }
        const salvoAgora: Prazo = { gravidade, marco, valor, unidade };
        setPrazos((atuais) => atuais.map((p) => (chave(p.gravidade, p.marco) === id ? salvoAgora : p)));
        setPersistidos((atuais) => new Map(atuais).set(id, salvoAgora));
        setErro(null);
        setSalvo(id);
      } finally {
        setSalvando(null);
      }
    },
    [token, persistidos]
  );

  async function cadastrarFeriado() {
    if (!token || !novoFeriado.data || !novoFeriado.nome.trim()) return;
    const res = await fetch("/api/ouvidoria/feriados", {
      method: "POST",
      headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
      body: JSON.stringify(novoFeriado),
    });
    if (!res.ok) {
      setErro(res.status === 409 ? "Esse dia já está no calendário." : "Não foi possível cadastrar o feriado.");
      return;
    }
    setFeriados((atuais) => [...atuais, novoFeriado].sort((a, b) => a.data.localeCompare(b.data)));
    setNovoFeriado({ data: "", nome: "", abrangencia: "nacional" });
    setErro(null);
  }

  async function removerFeriado(data: string) {
    if (!token) return;
    const res = await fetch(`/api/ouvidoria/feriados/${data}`, {
      method: "DELETE",
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!res.ok) {
      setErro("Não foi possível remover o feriado.");
      return;
    }
    setFeriados((atuais) => atuais.filter((f) => f.data !== data));
    setErro(null);
  }

  if (carregandoPerfil || loading) {
    return (
      <div className="flex items-center justify-center h-64 gap-2 text-slate-400 text-sm">
        <Loader2 className="w-5 h-5 animate-spin text-primary/40" />
        Carregando tabela de prazos...
      </div>
    );
  }

  if (!podeEditar) {
    return (
      <div className="p-4 md:p-8 max-w-3xl mx-auto text-center py-16">
        <p className="text-slate-500 font-medium">
          Só a Diretoria Executiva ajusta a tabela de prazos da Ouvidoria.
        </p>
        <Link href="/ouvidoria" className="inline-block mt-4 text-sm text-primary hover:underline">
          Voltar ao painel
        </Link>
      </div>
    );
  }

  const porCelula = new Map(prazos.map((p) => [chave(p.gravidade, p.marco), p]));

  return (
    <div className="p-4 md:p-8 max-w-5xl mx-auto">
      <Link
        href="/ouvidoria"
        className="inline-flex items-center gap-1.5 text-sm text-slate-500 hover:text-slate-700 mb-4"
      >
        <ArrowLeft className="w-4 h-4" />
        Painel da Ouvidoria
      </Link>

      <h1 className="text-2xl font-bold text-slate-900">Tabela de prazos</h1>
      <p className="text-slate-500 text-sm mt-0.5 mb-6">
        Prazos por gravidade, contados em calendário útil (segunda a sexta, 08h às 17h, sem
        feriados). Alterar aqui vale para as validações novas: caso já despachado mantém o prazo
        que o setor recebeu.
      </p>

      {erro && (
        <div className="flex items-center gap-2 mb-4 px-4 py-3 rounded-xl bg-red-50 border border-red-200 text-red-700 text-sm">
          <AlertCircle className="w-4 h-4 shrink-0" />
          {erro}
        </div>
      )}

      <div className="bg-white rounded-2xl border border-border shadow-premium overflow-hidden mb-8">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-slate-50 border-b border-slate-100">
                <th className="px-5 py-3 text-left font-semibold text-slate-600">Marco</th>
                {GRAVIDADES.map((g) => (
                  <th key={g} className="px-5 py-3 text-left font-semibold text-slate-600">
                    {LABEL_GRAVIDADE[g]}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-50">
              {MARCOS.map((marco) => (
                <tr key={marco}>
                  <td className="px-5 py-4 align-top">
                    <div className="font-medium text-slate-800">{LABEL_MARCO[marco]}</div>
                    <div className="text-xs text-slate-400 mt-0.5 max-w-[220px]">
                      {AJUDA_MARCO[marco]}
                    </div>
                  </td>
                  {GRAVIDADES.map((gravidade) => {
                    const id = chave(gravidade, marco);
                    const prazo = porCelula.get(id);
                    if (!prazo) return <td key={id} className="px-5 py-4 text-slate-300">-</td>;
                    return (
                      <td key={id} className="px-5 py-4">
                        <div className="flex items-center gap-1.5">
                          <input
                            type="number"
                            min={0}
                            aria-label={`Prazo ${LABEL_MARCO[marco]} para gravidade ${LABEL_GRAVIDADE[gravidade]}`}
                            value={prazo.valor ?? ""}
                            placeholder="sem prazo"
                            onChange={(e) =>
                              setPrazos((atuais) =>
                                atuais.map((p) =>
                                  chave(p.gravidade, p.marco) === id
                                    ? { ...p, valor: e.target.value === "" ? null : Number(e.target.value) }
                                    : p
                                )
                              )
                            }
                            onBlur={() => salvarPrazo(gravidade, marco, prazo.valor, prazo.unidade)}
                            className="w-20 px-2 py-1.5 rounded-lg border border-slate-200 text-sm focus:outline-none focus:ring-2 focus:ring-primary/30"
                          />
                          <select
                            aria-label={`Unidade do prazo ${LABEL_MARCO[marco]} para gravidade ${LABEL_GRAVIDADE[gravidade]}`}
                            value={prazo.unidade}
                            onChange={(e) => {
                              const unidade = e.target.value as Unidade;
                              setPrazos((atuais) =>
                                atuais.map((p) =>
                                  chave(p.gravidade, p.marco) === id ? { ...p, unidade } : p
                                )
                              );
                              salvarPrazo(gravidade, marco, prazo.valor, unidade);
                            }}
                            className="px-2 py-1.5 rounded-lg border border-slate-200 text-xs focus:outline-none focus:ring-2 focus:ring-primary/30"
                          >
                            <option value="horas_uteis">horas úteis</option>
                            <option value="dias_uteis">dias úteis</option>
                          </select>
                          {salvando === id && (
                            <Loader2 className="w-3.5 h-3.5 animate-spin text-slate-300" />
                          )}
                          {salvo === id && salvando !== id && (
                            <Check className="w-3.5 h-3.5 text-emerald-500" />
                          )}
                        </div>
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="px-5 py-3 bg-slate-50 border-t border-slate-100 text-xs text-slate-400">
          Campo em branco significa sem prazo para essa combinação (crítico não tem prazo
          conclusivo fixo; baixo não passa pela área). Zero significa imediato.
        </p>
      </div>

      <h2 className="text-lg font-bold text-slate-900 flex items-center gap-2">
        <CalendarOff className="w-4 h-4 text-slate-400" />
        Feriados
      </h2>
      <p className="text-slate-500 text-sm mt-0.5 mb-4">
        Dias que saem da contagem. Feriado removido volta a contar como dia útil.
      </p>

      <div className="bg-white rounded-2xl border border-border shadow-premium overflow-hidden">
        <div className="flex flex-wrap items-end gap-2 px-5 py-4 bg-slate-50 border-b border-slate-100">
          <label className="flex flex-col gap-1 text-xs text-slate-500">
            Data
            <input
              type="date"
              value={novoFeriado.data}
              onChange={(e) => setNovoFeriado({ ...novoFeriado, data: e.target.value })}
              className="px-2 py-1.5 rounded-lg border border-slate-200 text-sm focus:outline-none focus:ring-2 focus:ring-primary/30"
            />
          </label>
          <label className="flex flex-col gap-1 text-xs text-slate-500 flex-1 min-w-[180px]">
            Nome
            <input
              type="text"
              value={novoFeriado.nome}
              placeholder="Ex.: Sao Jorge"
              onChange={(e) => setNovoFeriado({ ...novoFeriado, nome: e.target.value })}
              className="px-2 py-1.5 rounded-lg border border-slate-200 text-sm focus:outline-none focus:ring-2 focus:ring-primary/30"
            />
          </label>
          <label className="flex flex-col gap-1 text-xs text-slate-500">
            Abrangência
            <select
              value={novoFeriado.abrangencia}
              onChange={(e) =>
                setNovoFeriado({
                  ...novoFeriado,
                  abrangencia: e.target.value as Feriado["abrangencia"],
                })
              }
              className="px-2 py-1.5 rounded-lg border border-slate-200 text-sm focus:outline-none focus:ring-2 focus:ring-primary/30"
            >
              {(Object.keys(LABEL_ABRANGENCIA) as Feriado["abrangencia"][]).map((a) => (
                <option key={a} value={a}>
                  {LABEL_ABRANGENCIA[a]}
                </option>
              ))}
            </select>
          </label>
          <button
            onClick={cadastrarFeriado}
            disabled={!novoFeriado.data || !novoFeriado.nome.trim()}
            className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm font-semibold bg-primary text-white disabled:bg-slate-200 disabled:text-slate-400 transition-colors"
          >
            <Plus className="w-4 h-4" />
            Adicionar
          </button>
        </div>

        {feriados.length === 0 ? (
          <p className="text-center py-10 text-slate-400 text-sm">Nenhum feriado cadastrado.</p>
        ) : (
          <table className="w-full text-sm">
            <tbody className="divide-y divide-slate-50">
              {feriados.map((f) => (
                <tr key={f.data}>
                  <td className="px-5 py-3 text-slate-800 whitespace-nowrap font-mono">
                    {new Date(`${f.data}T12:00:00`).toLocaleDateString("pt-BR")}
                  </td>
                  <td className="px-5 py-3 text-slate-600">{f.nome}</td>
                  <td className="px-5 py-3 text-slate-400 text-xs whitespace-nowrap">
                    {LABEL_ABRANGENCIA[f.abrangencia]}
                  </td>
                  <td className="px-5 py-3 text-right">
                    <button
                      onClick={() => removerFeriado(f.data)}
                      aria-label={`Remover feriado ${f.nome}`}
                      className="inline-flex items-center gap-1 px-2 py-1 rounded-lg text-xs text-slate-500 hover:bg-red-50 hover:text-red-600 transition-colors"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                      Remover
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
