"use client";

/**
 * A tela de Habilitação de Contas médicas (issue #1139, PRD #1129, ADR 0070).
 *
 * A matriz com os perfis nas linhas e as permissões nas colunas, cada célula
 * ligando ou desligando com um clique, e a busca de pessoa para dar, trocar ou
 * tirar o perfil do módulo. A mudança vale na próxima requisição de quem foi
 * mudado e fica registrada no servidor com autor, data, antes e depois. Só
 * quem tem a permissão "habilitar pessoas" usa; o backend recusa de novo, para
 * quem chamar a API direto.
 */

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { AlertCircle, ArrowLeft, Loader2, Search } from "lucide-react";
import { createClient } from "@/lib/supabase/client";
import { Select } from "@/components/ui/Select";
import type { PerfilContasMedicas } from "@/types";

type Matriz = Record<string, Record<string, boolean>>;

interface Pessoa {
  id: string;
  nome_completo: string;
  cargo: string | null;
  setor: string | null;
  perfil: PerfilContasMedicas | null;
}

const LABEL_PERFIL: Record<string, string> = {
  faturista: "Faturista",
  coordenadora: "Coordenadora de faturamento",
  gestao_contas_medicas: "Gestão de contas médicas",
  diretoria_medica: "Diretoria médica",
  diretoria_executiva: "Diretoria executiva",
  credenciamento: "Credenciamento",
};

const LABEL_PERMISSAO: Record<string, string> = {
  enviar_corrigir_contas: "Enviar e corrigir contas",
  decidir_validacao: "Decidir na validação",
  incluir_regra_operacional: "Incluir regra operacional",
  regra_contratual_tabelas: "Regra contratual e tabelas",
  contratos_avisos: "Contratos e avisos",
  painel_completo: "Painel completo",
  habilitar_pessoas: "Habilitar pessoas",
  conferencia_coordenacao: "Conferência da coordenação",
};

const rotulo = (labels: Record<string, string>, chave: string) => labels[chave] ?? chave.replaceAll("_", " ");

/** O valor do `Select` para quem não tem perfil no módulo. */
const SEM_PERFIL = "";

const OPCOES_DE_PERFIL = [
  ...Object.entries(LABEL_PERFIL).map(([value, label]) => ({ value, label })),
  { value: SEM_PERFIL, label: "Sem perfil no módulo" },
];

async function detalheDoErro(res: Response, padrao: string): Promise<string> {
  try {
    const corpo = await res.json();
    if (typeof corpo?.detail === "string") return corpo.detail;
  } catch {
    // resposta sem JSON (ex.: 500 do proxy)
  }
  return padrao;
}

const CARTAO = "bg-white rounded-2xl border border-border shadow-premium p-6";
const CAMPO =
  "w-full min-h-[38px] px-3 py-1.5 text-sm border border-slate-200 rounded-lg focus:outline-none focus:border-primary focus:ring-1 focus:ring-primary";
const BOTAO =
  "inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-primary text-white text-sm font-medium disabled:opacity-50";

export default function HabilitacaoPage() {
  const [token, setToken] = useState<string | null>(null);
  const [perfis, setPerfis] = useState<string[]>([]);
  const [permissoes, setPermissoes] = useState<string[]>([]);
  const [matriz, setMatriz] = useState<Matriz>({});
  const [carregando, setCarregando] = useState(true);
  const [semPermissao, setSemPermissao] = useState(false);
  const [erroGeral, setErroGeral] = useState<string | null>(null);

  useEffect(() => {
    async function init() {
      const {
        data: { session },
      } = await createClient().auth.getSession();
      const sessao = session?.access_token ?? null;
      setToken(sessao);
      if (!sessao) {
        setCarregando(false);
        return;
      }
      try {
        const res = await fetch("/api/contas-medicas/habilitacao", {
          headers: { Authorization: `Bearer ${sessao}` },
        });
        if (res.status === 403) {
          setSemPermissao(true);
          return;
        }
        if (!res.ok) {
          setErroGeral("Não foi possível carregar a matriz de permissões.");
          return;
        }
        const corpo = await res.json();
        setPerfis(corpo.perfis);
        setPermissoes(corpo.permissoes);
        setMatriz(corpo.matriz);
      } catch (e) {
        console.error("Erro ao carregar a Habilitação de Contas médicas:", e);
        setErroGeral("Não foi possível carregar a matriz de permissões.");
      } finally {
        setCarregando(false);
      }
    }
    init();
  }, []);

  if (carregando) {
    return (
      <div className="flex items-center gap-2 text-slate-500 text-sm">
        <Loader2 className="w-4 h-4 animate-spin" aria-hidden="true" /> Carregando a Habilitação
      </div>
    );
  }

  if (semPermissao) {
    return (
      <div className={CARTAO}>
        <p className="text-slate-600 text-sm">
          Você não tem a permissão de habilitar pessoas, que é a de quem decide o que cada perfil faz no módulo.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <Link
          href="/contas-medicas"
          className="inline-flex items-center gap-1 text-sm text-slate-500 hover:text-slate-700 mb-2"
        >
          <ArrowLeft className="w-4 h-4" aria-hidden="true" /> Contas médicas
        </Link>
        <h1 className="text-2xl font-bold text-slate-900">Habilitação</h1>
        <p className="text-slate-500 text-sm mt-0.5">
          O que cada perfil pode fazer no módulo e quem tem cada perfil. A mudança vale na hora e fica registrada.
        </p>
      </div>

      {erroGeral && (
        <p role="alert" className="flex items-center gap-2 text-sm text-red-700">
          <AlertCircle className="w-4 h-4" aria-hidden="true" /> {erroGeral}
        </p>
      )}

      {perfis.length > 0 && (
        <MatrizDePermissoes
          token={token}
          perfis={perfis}
          permissoes={permissoes}
          matriz={matriz}
          aoMudar={(perfil, permissao, ligada) =>
            setMatriz((atual) => ({ ...atual, [perfil]: { ...atual[perfil], [permissao]: ligada } }))
          }
        />
      )}

      <Pessoas token={token} />
    </div>
  );
}

function MatrizDePermissoes({
  token,
  perfis,
  permissoes,
  matriz,
  aoMudar,
}: {
  token: string | null;
  perfis: string[];
  permissoes: string[];
  matriz: Matriz;
  aoMudar: (perfil: string, permissao: string, ligada: boolean) => void;
}) {
  const [salvando, setSalvando] = useState<string | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  async function mudar(perfil: string, permissao: string, ligada: boolean) {
    if (!token) return;
    setErro(null);
    setSalvando(`${perfil}:${permissao}`);
    try {
      const res = await fetch("/api/contas-medicas/habilitacao/matriz", {
        method: "PUT",
        headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
        body: JSON.stringify({ perfil, permissao, ligada }),
      });
      if (!res.ok) {
        setErro(await detalheDoErro(res, "Não foi possível mudar a permissão."));
        return;
      }
      const celula = await res.json();
      aoMudar(celula.perfil, celula.permissao, celula.ligada);
    } catch {
      setErro("Não foi possível mudar a permissão.");
    } finally {
      setSalvando(null);
    }
  }

  return (
    <section aria-label="Perfis e permissões" className={CARTAO}>
      <h2 className="text-base font-semibold text-slate-900 mb-1">Perfis e permissões</h2>
      <p className="text-sm text-slate-500 mb-4">
        Cada célula liga ou desliga a permissão para todas as pessoas do perfil.
      </p>
      {erro && (
        <p role="alert" className="flex items-center gap-2 text-sm text-red-700 mb-3">
          <AlertCircle className="w-4 h-4" aria-hidden="true" /> {erro}
        </p>
      )}
      <div className="overflow-x-auto">
        <table aria-label="Perfis e permissões" className="w-full text-sm">
          <thead>
            <tr className="border-b border-slate-200">
              <th scope="col" className="text-left font-medium text-slate-500 py-2 pr-3">
                Perfil
              </th>
              {permissoes.map((permissao) => (
                <th
                  key={permissao}
                  scope="col"
                  className="font-medium text-slate-500 py-2 px-2 text-center align-bottom min-w-[6.5rem]"
                >
                  {rotulo(LABEL_PERMISSAO, permissao)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {perfis.map((perfil) => (
              <tr key={perfil}>
                <th scope="row" className="text-left font-medium text-slate-900 py-2 pr-3 whitespace-nowrap">
                  {rotulo(LABEL_PERFIL, perfil)}
                </th>
                {permissoes.map((permissao) => {
                  const ligada = Boolean(matriz[perfil]?.[permissao]);
                  return (
                    <td key={permissao} className="py-2 px-2 text-center">
                      <input
                        type="checkbox"
                        aria-label={`${rotulo(LABEL_PERMISSAO, permissao)}: ${rotulo(LABEL_PERFIL, perfil)}`}
                        checked={ligada}
                        disabled={salvando !== null}
                        onChange={() => mudar(perfil, permissao, !ligada)}
                        className="w-4 h-4 accent-primary cursor-pointer disabled:cursor-wait"
                      />
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function Pessoas({ token }: { token: string | null }) {
  const [busca, setBusca] = useState("");
  const [buscou, setBuscou] = useState(false);
  const [pessoas, setPessoas] = useState<Pessoa[]>([]);
  const [carregando, setCarregando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  const carregar = useCallback(
    async (termo: string) => {
      if (!token) return;
      setErro(null);
      setCarregando(true);
      try {
        const url = termo
          ? `/api/contas-medicas/habilitacao/pessoas?busca=${encodeURIComponent(termo)}`
          : "/api/contas-medicas/habilitacao/pessoas";
        const res = await fetch(url, { headers: { Authorization: `Bearer ${token}` } });
        if (!res.ok) {
          setErro(await detalheDoErro(res, "Não foi possível buscar as pessoas."));
          return;
        }
        setPessoas((await res.json()).pessoas);
        setBuscou(Boolean(termo));
      } catch {
        setErro("Não foi possível buscar as pessoas.");
      } finally {
        setCarregando(false);
      }
    },
    [token],
  );

  useEffect(() => {
    carregar("");
  }, [carregar]);

  async function mudarPerfil(pessoa: Pessoa, valor: string) {
    if (!token) return;
    setErro(null);
    const perfil = valor === SEM_PERFIL ? null : valor;
    try {
      const res = await fetch(`/api/contas-medicas/habilitacao/pessoas/${encodeURIComponent(pessoa.id)}`, {
        method: "PUT",
        headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
        body: JSON.stringify({ perfil }),
      });
      if (!res.ok) {
        setErro(await detalheDoErro(res, "Não foi possível mudar o perfil."));
        return;
      }
      const atualizada: Pessoa = await res.json();
      setPessoas((atuais) => atuais.map((p) => (p.id === atualizada.id ? atualizada : p)));
    } catch {
      setErro("Não foi possível mudar o perfil.");
    }
  }

  return (
    <section aria-label="Pessoas" className={CARTAO}>
      <h2 className="text-base font-semibold text-slate-900 mb-1">Pessoas</h2>
      <p className="text-sm text-slate-500 mb-4">
        Busque pelo nome para dar, trocar ou tirar o perfil de Contas médicas de alguém.
      </p>
      <form
        role="search"
        className="flex gap-2 mb-4"
        onSubmit={(e) => {
          e.preventDefault();
          carregar(busca.trim());
        }}
      >
        <input
          type="search"
          aria-label="Buscar pessoa pelo nome"
          placeholder="Nome da pessoa"
          value={busca}
          onChange={(e) => setBusca(e.target.value)}
          className={CAMPO}
        />
        <button type="submit" className={BOTAO} disabled={carregando}>
          <Search className="w-4 h-4" aria-hidden="true" /> Buscar
        </button>
      </form>

      {erro && (
        <p role="alert" className="flex items-center gap-2 text-sm text-red-700 mb-3">
          <AlertCircle className="w-4 h-4" aria-hidden="true" /> {erro}
        </p>
      )}

      <p className="text-xs font-medium text-slate-500 uppercase mb-2">
        {buscou ? "Resultado da busca" : "Quem tem perfil no módulo"}
      </p>
      {pessoas.length === 0 ? (
        <p className="text-slate-500 text-sm">
          {buscou ? "Ninguém encontrado com esse nome." : "Ninguém tem perfil no módulo ainda."}
        </p>
      ) : (
        <ul className="divide-y divide-slate-100">
          {pessoas.map((pessoa) => (
            <li
              key={pessoa.id}
              aria-label={pessoa.nome_completo}
              className="py-3 flex flex-wrap items-end justify-between gap-3"
            >
              <div className="min-w-[12rem]">
                <p className="text-sm font-semibold text-slate-900">{pessoa.nome_completo}</p>
                <p className="text-xs text-slate-500">
                  {[pessoa.cargo, pessoa.setor].filter(Boolean).join(", ") || "Sem cargo informado"}
                </p>
              </div>
              <Select
                label="Perfil"
                className="w-64"
                options={OPCOES_DE_PERFIL}
                value={pessoa.perfil ?? SEM_PERFIL}
                onChange={(valor) => mudarPerfil(pessoa, valor)}
              />
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
