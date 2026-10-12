"use client";

/**
 * A tela Operadoras de Contas médicas (issue #1119, PRD #1113, ADR 0070).
 *
 * A tela mínima da carga: a lista das operadoras com a situação de cada uma e
 * três formulários, o envio do arquivo de memória que o diretor monta, o
 * cadastro dos planos como o MV imprime e o dos setores com a acomodação. Só
 * quem tem a permissão "regra contratual e tabelas" usa; o backend recusa de
 * novo, para quem chamar a API direto.
 */

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { AlertCircle, ArrowLeft, Download, Loader2, Upload } from "lucide-react";
import { createClient } from "@/lib/supabase/client";
import { Select } from "@/components/ui/Select";

type Situacao = "PRONTA" | "PARCIAL" | "SEM_MEMORIA";

interface Operadora {
  sigla: string;
  nome: string;
  situacao: Situacao;
  versao: string | null;
  regras: { vigentes: number; pendentes: number };
  tabelas_carregadas: string[];
}

interface MemoriaImportada {
  operadora: string;
  versao: string;
  regras: { total: number; vigentes: number; pendentes: number };
  parametros: Record<string, unknown>;
}

interface Plano {
  id: string;
  nome_mv: string;
  operadora: string | null;
  coluna_preco: string | null;
}

interface Setor {
  id: string;
  nome_mv: string;
  acomodacao: string | null;
}

const LABEL_SITUACAO: Record<Situacao, string> = {
  PRONTA: "Pronta",
  PARCIAL: "Parcial",
  SEM_MEMORIA: "Sem memória",
};

const COR_SITUACAO: Record<Situacao, string> = {
  PRONTA: "bg-emerald-50 text-emerald-700",
  PARCIAL: "bg-amber-50 text-amber-700",
  SEM_MEMORIA: "bg-slate-100 text-slate-600",
};

const LABEL_TABELA: Record<string, string> = {
  MEDICAMENTO: "medicamentos",
  MATERIAL: "materiais",
  DIARIA_TAXA: "diárias e taxas",
  PACOTE: "pacotes",
  HONORARIO: "honorários",
};

/** As acomodações do cadastro de setor, na ordem da migration 116. */
const ACOMODACOES: { value: string; label: string }[] = [
  { value: "CTI", label: "CTI" },
  { value: "ENFERMARIA", label: "Enfermaria" },
  { value: "APARTAMENTO", label: "Apartamento" },
  { value: "ISOLAMENTO", label: "Isolamento" },
  { value: "CENTRO_CIRURGICO", label: "Centro cirúrgico" },
  { value: "HOSPITAL_DIA", label: "Hospital dia" },
  { value: "PEDIATRIA", label: "Pediatria" },
  { value: "UTI_PEDIATRICA", label: "UTI pediátrica" },
  { value: "UTI_NEONATAL", label: "UTI neonatal" },
];

const LABEL_ACOMODACAO = Object.fromEntries(ACOMODACOES.map((a) => [a.value, a.label]));

function plural(n: number, singular: string, varias: string): string {
  return `${n} ${n === 1 ? singular : varias}`;
}

function contagemDeRegras(vigentes: number, pendentes: number): string {
  return `${plural(vigentes, "regra vigente", "regras vigentes")} e ${plural(pendentes, "pendente", "pendentes")}`;
}

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

export default function OperadorasPage() {
  const [token, setToken] = useState<string | null>(null);
  const [operadoras, setOperadoras] = useState<Operadora[]>([]);
  const [planos, setPlanos] = useState<Plano[]>([]);
  const [setores, setSetores] = useState<Setor[]>([]);
  const [carregando, setCarregando] = useState(true);
  const [semPermissao, setSemPermissao] = useState(false);
  const [erroGeral, setErroGeral] = useState<string | null>(null);

  const carregarOperadoras = useCallback(async (sessao: string) => {
    const res = await fetch("/api/contas-medicas/operadoras", {
      headers: { Authorization: `Bearer ${sessao}` },
    });
    if (res.status === 403) {
      setSemPermissao(true);
      return;
    }
    if (!res.ok) {
      setErroGeral("Não foi possível carregar as operadoras.");
      return;
    }
    setOperadoras((await res.json()).operadoras);
  }, []);

  useEffect(() => {
    async function init() {
      const supabase = createClient();
      const {
        data: { session },
      } = await supabase.auth.getSession();
      const sessao = session?.access_token ?? null;
      setToken(sessao);
      if (!sessao) {
        setCarregando(false);
        return;
      }
      try {
        const headers = { Authorization: `Bearer ${sessao}` };
        await carregarOperadoras(sessao);
        const [resPlanos, resSetores] = await Promise.all([
          fetch("/api/contas-medicas/planos", { headers }),
          fetch("/api/contas-medicas/setores", { headers }),
        ]);
        if (resPlanos.ok) setPlanos((await resPlanos.json()).planos);
        if (resSetores.ok) setSetores((await resSetores.json()).setores);
      } catch (e) {
        console.error("Erro ao carregar as operadoras de Contas médicas:", e);
        setErroGeral("Não foi possível carregar as operadoras.");
      } finally {
        setCarregando(false);
      }
    }
    init();
  }, [carregarOperadoras]);

  if (carregando) {
    return (
      <div className="flex items-center gap-2 text-slate-500 text-sm">
        <Loader2 className="w-4 h-4 animate-spin" aria-hidden="true" /> Carregando operadoras
      </div>
    );
  }

  if (semPermissao) {
    return (
      <div className={CARTAO}>
        <p className="text-slate-600 text-sm">
          Você não tem a permissão de regra contratual e tabelas, que é a de quem carrega a memória das operadoras.
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
        <h1 className="text-2xl font-bold text-slate-900">Operadoras</h1>
        <p className="text-slate-500 text-sm mt-0.5">
          A memória de cada convênio, os planos como o MV imprime e os setores com a acomodação.
        </p>
      </div>

      {erroGeral && (
        <p role="alert" className="flex items-center gap-2 text-sm text-red-700">
          <AlertCircle className="w-4 h-4" aria-hidden="true" /> {erroGeral}
        </p>
      )}

      <ListaDeOperadoras operadoras={operadoras} token={token} />

      <EnvioDeMemoria
        token={token}
        aoImportar={() => (token ? carregarOperadoras(token) : Promise.resolve())}
      />

      <CadastroDePlanos token={token} operadoras={operadoras} planos={planos} aoCadastrar={(p) => setPlanos([...planos, p])} />

      <CadastroDeSetores token={token} setores={setores} aoCadastrar={(s) => setSetores([...setores, s])} />
    </div>
  );
}

function ListaDeOperadoras({ operadoras, token }: { operadoras: Operadora[]; token: string | null }) {
  const [erro, setErro] = useState<string | null>(null);

  async function baixar(sigla: string) {
    if (!token) return;
    setErro(null);
    const res = await fetch(`/api/contas-medicas/operadoras/${encodeURIComponent(sigla)}/memoria`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!res.ok) {
      setErro(await detalheDoErro(res, "Não foi possível baixar a memória."));
      return;
    }
    const nome =
      res.headers.get("content-disposition")?.match(/filename="([^"]+)"/)?.[1] ?? `MEMORIA-${sigla}.md`;
    const url = URL.createObjectURL(await res.blob());
    const link = document.createElement("a");
    link.href = url;
    link.download = nome;
    link.click();
    URL.revokeObjectURL(url);
  }

  return (
    <section aria-label="Operadoras" className={CARTAO}>
      <h2 className="text-base font-semibold text-slate-900 mb-4">Operadoras</h2>
      {operadoras.length === 0 ? (
        <p className="text-slate-500 text-sm">Nenhuma operadora ainda. Envie a primeira memória abaixo.</p>
      ) : (
        <ul className="divide-y divide-slate-100">
          {operadoras.map((op) => (
            <li
              key={op.sigla}
              data-testid={`operadora-${op.sigla}`}
              className="py-3 flex flex-wrap items-center gap-x-4 gap-y-1"
            >
              <div className="min-w-[10rem]">
                <p className="text-sm font-semibold text-slate-900">{op.sigla}</p>
                <p className="text-xs text-slate-500">{op.nome}</p>
              </div>
              <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${COR_SITUACAO[op.situacao]}`}>
                {LABEL_SITUACAO[op.situacao]}
              </span>
              <div className="text-sm text-slate-600 flex-1 min-w-[14rem]">
                {op.versao ? (
                  <p>
                    Memória versão {op.versao}, {contagemDeRegras(op.regras.vigentes, op.regras.pendentes)}
                  </p>
                ) : (
                  <p>Nenhuma memória carregada</p>
                )}
                <p className="text-xs text-slate-500">
                  Tabelas de preço:{" "}
                  {op.tabelas_carregadas.length === 0
                    ? "não carregadas"
                    : op.tabelas_carregadas.map((t) => LABEL_TABELA[t] ?? t).join(", ")}
                </p>
              </div>
              {op.versao && (
                <button
                  type="button"
                  onClick={() => baixar(op.sigla)}
                  className="inline-flex items-center gap-1 text-sm text-primary hover:underline"
                >
                  <Download className="w-4 h-4" aria-hidden="true" /> Baixar memória
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
      {erro && (
        <p role="alert" className="text-sm text-red-700 mt-3">
          {erro}
        </p>
      )}
    </section>
  );
}

function EnvioDeMemoria({ token, aoImportar }: { token: string | null; aoImportar: () => Promise<void> }) {
  const [arquivo, setArquivo] = useState<File | null>(null);
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [importada, setImportada] = useState<MemoriaImportada | null>(null);

  async function enviar(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!token || !arquivo) return;
    setEnviando(true);
    setErro(null);
    setImportada(null);
    try {
      const corpo = new FormData();
      corpo.append("arquivo", arquivo);
      const res = await fetch("/api/contas-medicas/operadoras/memoria", {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        body: corpo,
      });
      if (!res.ok) {
        setErro(await detalheDoErro(res, `Não foi possível enviar a memória (HTTP ${res.status}).`));
        return;
      }
      setImportada(await res.json());
      await aoImportar();
    } catch {
      setErro("Não foi possível enviar a memória.");
    } finally {
      setEnviando(false);
    }
  }

  return (
    <section aria-label="Enviar memória" className={CARTAO}>
      <h2 className="text-base font-semibold text-slate-900">Enviar memória</h2>
      <p className="text-sm text-slate-500 mt-0.5 mb-4">
        O arquivo de memória do convênio, como o diretor monta. Uma versão nova aposenta a anterior.
      </p>
      <form aria-label="Enviar memória" onSubmit={enviar} className="flex flex-wrap items-end gap-3">
        <label className="flex flex-col gap-1.5 text-xs font-medium text-slate-500 uppercase">
          Arquivo de memória
          <input
            type="file"
            accept=".md,text/markdown,text/plain"
            onChange={(e) => setArquivo(e.target.files?.[0] ?? null)}
            className="text-sm normal-case font-normal text-slate-700"
          />
        </label>
        <button type="submit" disabled={!arquivo || enviando} className={BOTAO}>
          {enviando ? (
            <Loader2 className="w-4 h-4 animate-spin" aria-hidden="true" />
          ) : (
            <Upload className="w-4 h-4" aria-hidden="true" />
          )}
          Enviar memória
        </button>
      </form>
      {erro && (
        <p role="alert" className="flex items-start gap-2 text-sm text-red-700 mt-4">
          <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" aria-hidden="true" /> {erro}
        </p>
      )}
      {importada && (
        <div role="status" className="mt-4 rounded-xl bg-emerald-50 p-4 text-sm text-slate-700">
          <p className="font-medium text-emerald-800">
            Memória carregada: {importada.operadora}, versão {importada.versao}, com{" "}
            {contagemDeRegras(importada.regras.vigentes, importada.regras.pendentes)}.
          </p>
          <p className="mt-2 text-xs text-slate-500">Parâmetros lidos do cabeçalho:</p>
          <dl className="mt-1 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-xs">
            {Object.entries(importada.parametros).map(([chave, valor]) => (
              <div key={chave} className="contents">
                <dt className="font-mono text-slate-600">{chave}</dt>
                <dd className="font-mono text-slate-800 break-all">{JSON.stringify(valor)}</dd>
              </div>
            ))}
          </dl>
        </div>
      )}
    </section>
  );
}

function CadastroDePlanos({
  token,
  operadoras,
  planos,
  aoCadastrar,
}: {
  token: string | null;
  operadoras: Operadora[];
  planos: Plano[];
  aoCadastrar: (plano: Plano) => void;
}) {
  const [nome, setNome] = useState("");
  const [operadora, setOperadora] = useState("");
  const [coluna, setColuna] = useState("");
  const [erro, setErro] = useState<string | null>(null);
  const [salvando, setSalvando] = useState(false);

  async function cadastrar(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!token || !nome.trim() || !operadora) return;
    setSalvando(true);
    setErro(null);
    try {
      const res = await fetch("/api/contas-medicas/planos", {
        method: "POST",
        headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
        body: JSON.stringify({ nome_mv: nome.trim(), operadora, coluna_preco: coluna.trim() || null }),
      });
      if (!res.ok) {
        setErro(await detalheDoErro(res, "Não foi possível cadastrar o plano."));
        return;
      }
      aoCadastrar(await res.json());
      setNome("");
      setColuna("");
    } finally {
      setSalvando(false);
    }
  }

  return (
    <section aria-label="Planos do MV" className={CARTAO}>
      <h2 className="text-base font-semibold text-slate-900">Planos do MV</h2>
      <p className="text-sm text-slate-500 mt-0.5 mb-4">
        O nome do plano como sai na conta, a operadora e a coluna de preço. Conta de plano sem cadastro é recusada no
        envio.
      </p>
      <form aria-label="Cadastrar plano" onSubmit={cadastrar} className="grid gap-3 sm:grid-cols-[2fr_1fr_1fr_auto] items-end">
        <label className="flex flex-col gap-1.5 text-xs font-medium text-slate-500 uppercase">
          Nome no MV
          <input value={nome} onChange={(e) => setNome(e.target.value)} className={`${CAMPO} normal-case font-normal`} />
        </label>
        <Select
          label="Operadora"
          value={operadora}
          onChange={setOperadora}
          options={operadoras.map((op) => ({ value: op.sigla, label: op.sigla }))}
        />
        <label className="flex flex-col gap-1.5 text-xs font-medium text-slate-500 uppercase">
          Coluna de preço
          <input
            value={coluna}
            onChange={(e) => setColuna(e.target.value)}
            placeholder="COMUM ou CARIOCA"
            className={`${CAMPO} normal-case font-normal`}
          />
        </label>
        <button type="submit" disabled={!nome.trim() || !operadora || salvando} className={BOTAO}>
          Cadastrar plano
        </button>
      </form>
      {erro && (
        <p role="alert" className="text-sm text-red-700 mt-3">
          {erro}
        </p>
      )}
      {planos.length === 0 ? (
        <p className="text-sm text-slate-500 mt-4">Nenhum plano cadastrado.</p>
      ) : (
        <table className="w-full text-sm mt-4">
          <thead>
            <tr className="text-left text-xs text-slate-500 uppercase">
              <th className="py-1 font-medium">Nome no MV</th>
              <th className="py-1 font-medium">Operadora</th>
              <th className="py-1 font-medium">Coluna de preço</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {planos.map((p) => (
              <tr key={p.id}>
                <td className="py-1.5 text-slate-800">{p.nome_mv}</td>
                <td className="py-1.5 text-slate-600">{p.operadora}</td>
                <td className="py-1.5 text-slate-600">{p.coluna_preco ?? "padrão da operadora"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}

function CadastroDeSetores({
  token,
  setores,
  aoCadastrar,
}: {
  token: string | null;
  setores: Setor[];
  aoCadastrar: (setor: Setor) => void;
}) {
  const [nome, setNome] = useState("");
  const [acomodacao, setAcomodacao] = useState("");
  const [erro, setErro] = useState<string | null>(null);
  const [salvando, setSalvando] = useState(false);

  async function cadastrar(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!token || !nome.trim() || !acomodacao) return;
    setSalvando(true);
    setErro(null);
    try {
      const res = await fetch("/api/contas-medicas/setores", {
        method: "POST",
        headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
        body: JSON.stringify({ nome_mv: nome.trim(), acomodacao }),
      });
      if (!res.ok) {
        setErro(await detalheDoErro(res, "Não foi possível cadastrar o setor."));
        return;
      }
      aoCadastrar(await res.json());
      setNome("");
    } finally {
      setSalvando(false);
    }
  }

  return (
    <section aria-label="Setores do MV" className={CARTAO}>
      <h2 className="text-base font-semibold text-slate-900">Setores do MV</h2>
      <p className="text-sm text-slate-500 mt-0.5 mb-4">
        O setor como o MV imprime e a acomodação dele, que decide a diária e o teto por dia.
      </p>
      <form aria-label="Cadastrar setor" onSubmit={cadastrar} className="grid gap-3 sm:grid-cols-[2fr_1fr_auto] items-end">
        <label className="flex flex-col gap-1.5 text-xs font-medium text-slate-500 uppercase">
          Nome no MV
          <input value={nome} onChange={(e) => setNome(e.target.value)} className={`${CAMPO} normal-case font-normal`} />
        </label>
        <Select label="Acomodação" value={acomodacao} onChange={setAcomodacao} options={ACOMODACOES} />
        <button type="submit" disabled={!nome.trim() || !acomodacao || salvando} className={BOTAO}>
          Cadastrar setor
        </button>
      </form>
      {erro && (
        <p role="alert" className="text-sm text-red-700 mt-3">
          {erro}
        </p>
      )}
      {setores.length === 0 ? (
        <p className="text-sm text-slate-500 mt-4">Nenhum setor cadastrado.</p>
      ) : (
        <table className="w-full text-sm mt-4">
          <thead>
            <tr className="text-left text-xs text-slate-500 uppercase">
              <th className="py-1 font-medium">Nome no MV</th>
              <th className="py-1 font-medium">Acomodação</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {setores.map((s) => (
              <tr key={s.id}>
                <td className="py-1.5 text-slate-800">{s.nome_mv}</td>
                <td className="py-1.5 text-slate-600">{s.acomodacao ? LABEL_ACOMODACAO[s.acomodacao] : ""}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
