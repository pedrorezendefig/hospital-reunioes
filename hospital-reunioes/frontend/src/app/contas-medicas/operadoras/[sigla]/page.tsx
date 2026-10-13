"use client";

/**
 * A tela Memória da operadora de Contas médicas (issue #1140, PRD #1129, ADR 0070).
 *
 * O cabeçalho da memória vigente, as regras em abas com Editar (vigente) e
 * Decidir (pendente), as tabelas de preço da operadora, o histórico de versões
 * e o Exportar. Quem cria a versão nova, guarda o texto anterior e confere a
 * permissão do tipo da regra é o servidor; a tela só mostra os botões do tipo
 * que a pessoa pode mudar e relê a memória depois de cada mudança.
 */

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { AlertCircle, ArrowLeft, Download, Loader2 } from "lucide-react";

import { TabelasDePreco } from "@/components/contas-medicas/TabelasDePreco";
import { Select } from "@/components/ui/Select";
import {
  COR_SITUACAO,
  LABEL_SITUACAO,
  type Situacao,
  type TabelaDaCategoria,
  baixarMemoria,
  dataBr,
  detalheDoErro,
  plural,
} from "@/lib/contas-medicas/operadoras";
import { createClient } from "@/lib/supabase/client";

type Tipo = "CONTRATUAL" | "OPERACIONAL";

interface Regra {
  id: string;
  codigo: string;
  secao: string | null;
  texto: string;
  tipo: Tipo | null;
  origem: string | null;
  status: "VIGENTE" | "PENDENTE";
  validado_por: string | null;
  validado_em: string | null;
  modelo_id: string | null;
}

interface Mudanca {
  codigo: string | null;
  texto_anterior: string | null;
  texto_novo: string;
}

interface VersaoDaMemoria {
  versao: string;
  vigente: boolean;
  criado_em: string | null;
  autor: string | null;
  resumo: string | null;
  mudancas: Mudanca[];
}

interface Contrato {
  assinatura?: string;
  ultimo_aditivo?: { numero?: string | number; inicio_vigencia?: string };
}

interface Memoria {
  sigla: string;
  nome: string;
  situacao: Situacao;
  versao: string | null;
  data: string | null;
  contrato: Contrato | null;
  regras_contagem: { vigentes: number; pendentes: number };
  regras: Regra[];
  tabelas: TabelaDaCategoria[];
  historico: VersaoDaMemoria[];
  permissoes: string[];
}

interface Resultado {
  versao: string;
  outras_operadoras: { operadora: string; versao: string }[];
}

/** As abas da spec, pela seção da regra (o prefixo do ID); Pendentes, pela situação. */
const ABAS: { id: string; rotulo: string; filtro: (r: Regra) => boolean }[] = [
  { id: "todas", rotulo: "Todas", filtro: () => true },
  { id: "DIA", rotulo: "Diárias", filtro: (r) => r.secao === "DIA" },
  { id: "PAC", rotulo: "Pacotes", filtro: (r) => r.secao === "PAC" },
  { id: "TAX", rotulo: "Taxas e aluguéis", filtro: (r) => r.secao === "TAX" },
  { id: "INS", rotulo: "Insumos por tempo", filtro: (r) => r.secao === "INS" },
  { id: "MED", rotulo: "Medicamentos", filtro: (r) => r.secao === "MED" },
  { id: "HON", rotulo: "Honorários", filtro: (r) => r.secao === "HON" },
  { id: "pendentes", rotulo: "Pendentes", filtro: (r) => r.status === "PENDENTE" },
];

const TIPOS = [
  { value: "CONTRATUAL", label: "Contratual" },
  { value: "OPERACIONAL", label: "Operacional" },
];

/** Regra sem tipo é de preço, diária ou tabela: pede a permissão contratual, como no servidor. */
function permissaoDoTipo(tipo: Tipo | null): string {
  return tipo === "OPERACIONAL" ? "incluir_regra_operacional" : "regra_contratual_tabelas";
}

function linhaDoContrato(contrato: Contrato | null): string | null {
  if (!contrato) return null;
  const partes = [];
  if (contrato.assinatura) partes.push(`Contrato assinado em ${dataBr(contrato.assinatura)}`);
  const aditivo = contrato.ultimo_aditivo;
  if (aditivo?.numero != null) {
    partes.push(
      aditivo.inicio_vigencia
        ? `aditivo ${aditivo.numero}, vigente desde ${dataBr(aditivo.inicio_vigencia)}`
        : `aditivo ${aditivo.numero}`,
    );
  }
  return partes.length ? partes.join(", ") : null;
}

const CARTAO = "bg-white rounded-2xl border border-border shadow-premium p-6";
const CAMPO =
  "w-full min-h-[38px] px-3 py-1.5 text-sm border border-slate-200 rounded-lg focus:outline-none focus:border-primary focus:ring-1 focus:ring-primary";
const BOTAO =
  "inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-primary text-white text-sm font-medium disabled:opacity-50";
const BOTAO_SECUNDARIO =
  "inline-flex items-center gap-2 px-4 py-2 rounded-lg border border-slate-200 bg-white text-sm text-slate-700 hover:border-slate-300";

export default function MemoriaDaOperadoraPage() {
  const params = useParams<{ sigla: string }>();
  const sigla = decodeURIComponent(params?.sigla ?? "").toUpperCase();
  const [token, setToken] = useState<string | null>(null);
  const [memoria, setMemoria] = useState<Memoria | null>(null);
  const [carregando, setCarregando] = useState(true);
  const [semPermissao, setSemPermissao] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);

  const carregar = useCallback(
    async (sessao: string) => {
      const res = await fetch(`/api/contas-medicas/operadoras/${encodeURIComponent(sigla)}`, {
        headers: { Authorization: `Bearer ${sessao}` },
      });
      if (res.status === 403) {
        setSemPermissao(true);
        return;
      }
      if (!res.ok) {
        setErro(await detalheDoErro(res, "Não foi possível carregar a memória da operadora."));
        return;
      }
      setMemoria(await res.json());
    },
    [sigla],
  );

  useEffect(() => {
    async function init() {
      const {
        data: { session },
      } = await createClient().auth.getSession();
      const sessao = session?.access_token ?? null;
      setToken(sessao);
      try {
        if (sessao) await carregar(sessao);
      } catch {
        setErro("Não foi possível carregar a memória da operadora.");
      } finally {
        setCarregando(false);
      }
    }
    init();
  }, [carregar]);

  async function aoMudar(resultado: Resultado) {
    const outras = resultado.outras_operadoras.map((o) => `${o.operadora} (versão ${o.versao})`);
    setAviso(
      `Versão ${resultado.versao} da memória criada.` + (outras.length ? ` Também em ${outras.join(", ")}.` : ""),
    );
    if (token) await carregar(token);
  }

  async function exportar() {
    if (!token) return;
    setErro(await baixarMemoria(token, sigla));
  }

  if (carregando) {
    return (
      <div className="flex items-center gap-2 text-slate-500 text-sm">
        <Loader2 className="w-4 h-4 animate-spin" aria-hidden="true" /> Carregando a memória
      </div>
    );
  }

  if (semPermissao) {
    return (
      <div className={CARTAO}>
        <p className="text-slate-600 text-sm">
          Você não tem permissão para mudar as regras da memória: é a de incluir regra operacional ou a de regra
          contratual e tabelas.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <Link
        href="/contas-medicas/operadoras"
        className="inline-flex items-center gap-1 text-sm text-slate-500 hover:text-slate-700"
      >
        <ArrowLeft className="w-4 h-4" aria-hidden="true" /> Operadoras
      </Link>

      {erro && (
        <p role="alert" className="flex items-center gap-2 text-sm text-red-700">
          <AlertCircle className="w-4 h-4" aria-hidden="true" /> {erro}
        </p>
      )}

      {memoria && (
        <>
          <Cabecalho memoria={memoria} aoExportar={exportar} />
          {aviso && (
            <p role="status" className="rounded-xl bg-emerald-50 p-4 text-sm font-medium text-emerald-800">
              {aviso}
            </p>
          )}
          <Regras memoria={memoria} token={token} aoMudar={aoMudar} />
          <section aria-label="Tabelas de preço" className={CARTAO}>
            <h2 className="text-base font-semibold text-slate-900">Tabelas de preço</h2>
            <TabelasDePreco rotulo="Tabelas de preço da operadora" tabelas={memoria.tabelas} />
          </section>
          <Historico versoes={memoria.historico} />
        </>
      )}
    </div>
  );
}

function Cabecalho({ memoria, aoExportar }: { memoria: Memoria; aoExportar: () => void }) {
  const contrato = linhaDoContrato(memoria.contrato);
  const pendentes = memoria.regras_contagem.pendentes;
  return (
    <section aria-label="Cabeçalho da memória" className={CARTAO}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Memória da operadora {memoria.sigla}</h1>
          <p className="text-slate-500 text-sm mt-0.5">{memoria.nome}</p>
        </div>
        {memoria.versao && (
          <button type="button" onClick={aoExportar} className={BOTAO_SECUNDARIO}>
            <Download className="w-4 h-4" aria-hidden="true" /> Exportar
          </button>
        )}
      </div>
      <div className="mt-4 flex flex-wrap items-center gap-x-4 gap-y-2 text-sm text-slate-700">
        <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${COR_SITUACAO[memoria.situacao]}`}>
          {LABEL_SITUACAO[memoria.situacao]}
        </span>
        {memoria.versao ? (
          <span>
            Versão {memoria.versao}
            {memoria.data ? `, de ${dataBr(memoria.data)}` : ""}
          </span>
        ) : (
          <span>Nenhuma memória carregada</span>
        )}
        {contrato && <span>{contrato}</span>}
        <span className={pendentes ? "text-amber-700 font-medium" : "text-slate-500"}>
          {plural(pendentes, "regra pendente", "regras pendentes")}
        </span>
      </div>
    </section>
  );
}

function Regras({
  memoria,
  token,
  aoMudar,
}: {
  memoria: Memoria;
  token: string | null;
  aoMudar: (resultado: Resultado) => Promise<void>;
}) {
  const [aba, setAba] = useState("todas");
  const [aberta, setAberta] = useState<{ codigo: string; modo: "editar" | "decidir" } | null>(null);
  const filtro = ABAS.find((a) => a.id === aba)?.filtro ?? (() => true);
  const regras = memoria.regras.filter(filtro);
  const pendentes = memoria.regras.filter((r) => r.status === "PENDENTE").length;
  const pode = (r: Regra) => memoria.permissoes.includes(permissaoDoTipo(r.tipo));

  return (
    <section aria-label="Regras" className={CARTAO}>
      <h2 className="text-base font-semibold text-slate-900 mb-3">Regras</h2>
      <div className="flex flex-wrap gap-1 border-b border-border" role="tablist">
        {ABAS.map((a) => (
          <button
            key={a.id}
            type="button"
            role="tab"
            aria-selected={aba === a.id}
            onClick={() => setAba(a.id)}
            className={`px-3 py-2 text-sm font-medium border-b-2 transition-colors ${
              aba === a.id ? "border-primary text-primary" : "border-transparent text-text-secondary hover:text-text"
            }`}
          >
            {a.id === "pendentes" ? `${a.rotulo} (${pendentes})` : a.rotulo}
          </button>
        ))}
      </div>
      <div role="tabpanel" className="overflow-x-auto">
        <table aria-label="Regras da memória" className="w-full text-sm mt-3">
          <thead>
            <tr className="text-left text-xs text-slate-500 uppercase">
              <th className="py-1 pr-3 font-medium">Regra</th>
              <th className="py-1 pr-3 font-medium">Origem</th>
              <th className="py-1 pr-3 font-medium">Validada por</th>
              <th className="py-1 pr-3 font-medium">Data</th>
              <th className="py-1 pr-3 font-medium">Situação</th>
              <th className="py-1 font-medium" aria-label="Ação" />
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 align-top">
            {regras.length === 0 && (
              <tr>
                <td colSpan={6} className="py-4 text-slate-500">
                  Nenhuma regra nesta aba.
                </td>
              </tr>
            )}
            {regras.flatMap((r) => {
              const linhas = [
                <tr key={r.id} data-testid={`regra-${r.codigo}`}>
                  <td className="py-2 pr-3">
                    <span className="block font-mono text-xs text-slate-500">{r.codigo}</span>
                    <p className="text-slate-800 whitespace-pre-line">{r.texto}</p>
                  </td>
                  <td className="py-2 pr-3 text-slate-600">{r.origem ?? ""}</td>
                  <td className="py-2 pr-3 text-slate-600">{r.validado_por ?? ""}</td>
                  <td className="py-2 pr-3 text-slate-600 whitespace-nowrap">
                    {r.validado_em ? dataBr(r.validado_em) : ""}
                  </td>
                  <td className={`py-2 pr-3 ${r.status === "PENDENTE" ? "text-amber-700 font-medium" : "text-emerald-700"}`}>
                    {r.status === "PENDENTE" ? "Pendente" : "Vigente"}
                  </td>
                  <td className="py-2">
                    {pode(r) && (
                      <button
                        type="button"
                        onClick={() =>
                          setAberta({ codigo: r.codigo, modo: r.status === "PENDENTE" ? "decidir" : "editar" })
                        }
                        className="text-sm font-medium text-primary hover:underline"
                      >
                        {r.status === "PENDENTE" ? "Decidir" : "Editar"}
                      </button>
                    )}
                  </td>
                </tr>,
              ];
              if (aberta?.codigo === r.codigo) {
                linhas.push(
                  <tr key={`${r.id}-form`}>
                    <td colSpan={6} className="pb-4">
                      <MudancaDaRegra
                        sigla={memoria.sigla}
                        regra={r}
                        modo={aberta.modo}
                        token={token}
                        aoFechar={() => setAberta(null)}
                        aoMudar={async (resultado) => {
                          setAberta(null);
                          await aoMudar(resultado);
                        }}
                      />
                    </td>
                  </tr>,
                );
              }
              return linhas;
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function MudancaDaRegra({
  sigla,
  regra,
  modo,
  token,
  aoFechar,
  aoMudar,
}: {
  sigla: string;
  regra: Regra;
  modo: "editar" | "decidir";
  token: string | null;
  aoFechar: () => void;
  aoMudar: (resultado: Resultado) => Promise<void>;
}) {
  const [texto, setTexto] = useState(regra.texto);
  const [tipo, setTipo] = useState<string>(regra.tipo ?? "");
  const [origem, setOrigem] = useState(regra.origem ?? "");
  const [aplicarATodas, setAplicarATodas] = useState(false);
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const decidir = modo === "decidir";

  async function gravar(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!token || !texto.trim()) return;
    setSalvando(true);
    setErro(null);
    try {
      const corpo: Record<string, unknown> = { texto: texto.trim(), tipo: tipo || null, origem: origem.trim() || null };
      if (!decidir) corpo.aplicar_a_todas = aplicarATodas;
      const base = `/api/contas-medicas/operadoras/${encodeURIComponent(sigla)}/regras/${encodeURIComponent(regra.codigo)}`;
      const res = await fetch(decidir ? `${base}/decisao` : base, {
        method: decidir ? "POST" : "PUT",
        headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
        body: JSON.stringify(corpo),
      });
      if (!res.ok) {
        setErro(await detalheDoErro(res, `Não foi possível gravar a regra (HTTP ${res.status}).`));
        return;
      }
      await aoMudar(await res.json());
    } catch {
      setErro("Não foi possível gravar a regra.");
    } finally {
      setSalvando(false);
    }
  }

  return (
    <form
      aria-label={`${decidir ? "Decidir" : "Editar"} a regra ${regra.codigo}`}
      onSubmit={gravar}
      className="rounded-xl border border-slate-200 bg-slate-50 p-4 space-y-3"
    >
      <label className="flex flex-col gap-1.5 text-xs font-medium text-slate-500 uppercase">
        Texto da regra
        <textarea
          value={texto}
          onChange={(e) => setTexto(e.target.value)}
          rows={3}
          className={`${CAMPO} normal-case font-normal text-slate-800 bg-white`}
        />
      </label>
      <div className="grid gap-3 sm:grid-cols-2">
        <Select label="Tipo" value={tipo} onChange={setTipo} options={TIPOS} />
        <label className="flex flex-col gap-1.5 text-xs font-medium text-slate-500 uppercase">
          Origem
          <input
            value={origem}
            onChange={(e) => setOrigem(e.target.value)}
            className={`${CAMPO} normal-case font-normal text-slate-800 bg-white`}
          />
        </label>
      </div>
      {!decidir && regra.modelo_id && (
        <label className="flex items-center gap-2 text-sm text-slate-700">
          <input type="checkbox" checked={aplicarATodas} onChange={(e) => setAplicarATodas(e.target.checked)} />
          Aplicar a todas as operadoras que têm esta regra
        </label>
      )}
      <p className="text-xs text-slate-500">
        Gravar cria uma versão nova da memória; a anterior fica no histórico, com o texto de antes.
      </p>
      {erro && (
        <p role="alert" className="flex items-start gap-2 text-sm text-red-700">
          <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" aria-hidden="true" /> {erro}
        </p>
      )}
      <div className="flex flex-wrap gap-2">
        <button type="submit" disabled={!texto.trim() || salvando} className={BOTAO}>
          {salvando && <Loader2 className="w-4 h-4 animate-spin" aria-hidden="true" />}
          {decidir ? "Validar regra" : "Salvar"}
        </button>
        <button type="button" onClick={aoFechar} className={BOTAO_SECUNDARIO}>
          {decidir ? "Deixar pendente" : "Cancelar"}
        </button>
      </div>
    </form>
  );
}

function Historico({ versoes }: { versoes: VersaoDaMemoria[] }) {
  return (
    <section aria-label="Histórico de versões" className={CARTAO}>
      <h2 className="text-base font-semibold text-slate-900 mb-3">Histórico de versões</h2>
      {versoes.length === 0 ? (
        <p className="text-sm text-slate-500">Nenhuma versão ainda.</p>
      ) : (
        <ul className="divide-y divide-slate-100">
          {versoes.map((v) => (
            <li key={v.versao} className="py-3 text-sm">
              <p className="text-slate-900">
                <span className="font-semibold">Versão {v.versao}</span>
                {v.vigente && <span className="ml-2 text-xs font-medium text-emerald-700">(vigente)</span>}
              </p>
              <p className="text-xs text-slate-500 mt-0.5">
                {[v.criado_em ? dataBr(v.criado_em) : null, v.autor].filter(Boolean).join(", por ")}
              </p>
              {v.resumo && <p className="text-slate-700 mt-1">{v.resumo}</p>}
              {v.mudancas.map((m, i) => (
                <div key={`${m.codigo}-${i}`} className="mt-2 rounded-lg bg-slate-50 p-3 text-xs space-y-1">
                  <p className="font-mono text-slate-500">{m.codigo}</p>
                  <p className="text-slate-600 whitespace-pre-line">Antes: {m.texto_anterior ?? ""}</p>
                  <p className="text-slate-800 whitespace-pre-line">Depois: {m.texto_novo}</p>
                </div>
              ))}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
