"use client";

/**
 * A tela Contratos de Contas médicas (issue #1144, PRD #1129, ADR 0070).
 *
 * Uma linha por operadora com a assinatura, o último aditivo, o início da
 * vigência, o vencimento (marcado "calculado" quando veio da vigência mais um
 * ano), os dias que faltam e a situação, na cor dela. Quem pode mudar o
 * contrato envia o contrato ou o aditivo: a IA preenche os campos e nada vale
 * antes do "Confirmar". O credenciamento vê e recebe o aviso no sino; o backend
 * recusa o envio dele de novo, para quem chamar a API direto.
 */

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { AlertCircle, ArrowLeft, Download, Loader2, Upload } from "lucide-react";
import { createClient } from "@/lib/supabase/client";

type Situacao = "EM_DIA" | "NEGOCIAR" | "VENCIDO" | "SEM_CONTRATO";

interface Contrato {
  data_assinatura: string | null;
  aditivo_numero: string | null;
  aditivo_data: string | null;
  vigencia_inicio: string | null;
  vencimento: string | null;
  vencimento_calculado: boolean;
  vencimento_e_negociacao: boolean;
  arquivo: string | null;
}

interface LinhaDoContrato {
  sigla: string;
  nome: string;
  contrato: Contrato | null;
  dias: number | null;
  situacao: Situacao;
  data_aviso: string | null;
}

/** Os campos que a pessoa confirma: os quatro da spec, com o aditivo em número e data. */
interface Campos {
  data_assinatura: string | null;
  aditivo_numero: string | null;
  aditivo_data: string | null;
  vigencia_inicio: string | null;
  vencimento: string | null;
  vencimento_calculado: boolean;
}

interface Proposta {
  arquivo: string;
  tem_texto: boolean;
  aviso: string | null;
  campos: Campos;
}

const LABEL_SITUACAO: Record<Situacao, string> = {
  EM_DIA: "Em dia",
  NEGOCIAR: "Negociar reajuste",
  VENCIDO: "Vencido",
  SEM_CONTRATO: "Sem contrato",
};

/** A cor diz a situação (spec do diretor, quadro de cores): nunca decoração. */
const COR_DO_CARTAO: Record<Situacao, string> = {
  EM_DIA: "border-emerald-500 bg-emerald-50/40",
  NEGOCIAR: "border-amber-500 bg-amber-50/50",
  VENCIDO: "border-red-500 bg-red-50/50",
  SEM_CONTRATO: "border-slate-300 bg-slate-50",
};

const COR_DA_ETIQUETA: Record<Situacao, string> = {
  EM_DIA: "bg-emerald-100 text-emerald-800",
  NEGOCIAR: "bg-amber-100 text-amber-800",
  VENCIDO: "bg-red-100 text-red-800",
  SEM_CONTRATO: "bg-slate-200 text-slate-700",
};

const CARTAO = "bg-white rounded-2xl border border-border shadow-premium p-6";
const CAMPO =
  "w-full min-h-[38px] px-3 py-1.5 text-sm border border-slate-200 rounded-lg bg-white focus:outline-none focus:border-primary focus:ring-1 focus:ring-primary";
const BOTAO =
  "inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-primary text-white text-sm font-medium disabled:opacity-50";
const BOTAO_CLARO =
  "inline-flex items-center gap-2 px-3 py-1.5 rounded-lg border border-slate-200 bg-white text-sm text-slate-700 hover:border-slate-300 disabled:opacity-50";

/** "2027-05-01" vira "01/05/2027". */
function dataBr(iso: string | null): string {
  if (!iso) return "";
  const [ano, mes, dia] = iso.slice(0, 10).split("-");
  return `${dia}/${mes}/${ano}`;
}

function quantoFalta(dias: number | null): string {
  if (dias === null) return "";
  if (dias === 0) return "vence hoje";
  if (dias > 0) return dias === 1 ? "falta 1 dia" : `faltam ${dias} dias`;
  return -dias === 1 ? "venceu há 1 dia" : `venceu há ${-dias} dias`;
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

export default function ContratosPage() {
  const [token, setToken] = useState<string | null>(null);
  const [linhas, setLinhas] = useState<LinhaDoContrato[]>([]);
  const [podeEditar, setPodeEditar] = useState(false);
  const [carregando, setCarregando] = useState(true);
  const [semPermissao, setSemPermissao] = useState(false);
  const [erroGeral, setErroGeral] = useState<string | null>(null);

  const carregar = useCallback(async (sessao: string) => {
    try {
      const res = await fetch("/api/contas-medicas/contratos", { headers: { Authorization: `Bearer ${sessao}` } });
      if (res.status === 403) {
        setSemPermissao(true);
        return;
      }
      if (!res.ok) {
        setErroGeral("Não foi possível carregar os contratos.");
        return;
      }
      const corpo = await res.json();
      setLinhas(corpo.contratos);
      setPodeEditar(Boolean(corpo.pode_editar));
    } catch (e) {
      console.error("Erro ao carregar os contratos de Contas médicas:", e);
      setErroGeral("Não foi possível carregar os contratos.");
    }
  }, []);

  useEffect(() => {
    async function init() {
      const {
        data: { session },
      } = await createClient().auth.getSession();
      const sessao = session?.access_token ?? null;
      setToken(sessao);
      if (sessao) await carregar(sessao);
      setCarregando(false);
    }
    init();
  }, [carregar]);

  if (carregando) {
    return (
      <div className="flex items-center gap-2 text-slate-500 text-sm">
        <Loader2 className="w-4 h-4 animate-spin" aria-hidden="true" /> Carregando os contratos
      </div>
    );
  }

  if (semPermissao) {
    return (
      <div className={CARTAO}>
        <p className="text-slate-600 text-sm">
          Você não tem a permissão de contratos e avisos, que é a de quem acompanha o vencimento dos contratos.
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
        <h1 className="text-2xl font-bold text-slate-900">Contratos</h1>
        <p className="text-slate-500 text-sm mt-0.5">
          O contrato de cada operadora e o vencimento. Na data do aviso, quem acompanha os contratos recebe o lembrete
          de reajuste no sino.
        </p>
      </div>

      {erroGeral && (
        <p role="alert" className="flex items-center gap-2 text-sm text-red-700">
          <AlertCircle className="w-4 h-4" aria-hidden="true" /> {erroGeral}
        </p>
      )}

      <section aria-label="Contratos" className={CARTAO}>
        {linhas.length === 0 ? (
          <p className="text-slate-500 text-sm">
            Nenhuma operadora ainda. O contrato nasce com a memória da operadora, na tela Operadoras.
          </p>
        ) : (
          <ul className="space-y-3">
            {linhas.map((linha) => (
              <CartaoDoContrato
                key={linha.sigla}
                linha={linha}
                token={token}
                podeEditar={podeEditar}
                aoConfirmar={() => (token ? carregar(token) : Promise.resolve())}
              />
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

function Dado({ rotulo, children }: { rotulo: string; children: React.ReactNode }) {
  return (
    <div>
      <dt className="text-xs text-slate-500">{rotulo}</dt>
      <dd className="text-sm text-slate-900">{children || <span className="text-slate-400">não informado</span>}</dd>
    </div>
  );
}

function CartaoDoContrato({
  linha,
  token,
  podeEditar,
  aoConfirmar,
}: {
  linha: LinhaDoContrato;
  token: string | null;
  podeEditar: boolean;
  aoConfirmar: () => Promise<void>;
}) {
  const [editando, setEditando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const contrato = linha.contrato;

  async function baixar() {
    if (!token) return;
    setErro(null);
    const res = await fetch(`/api/contas-medicas/contratos/${encodeURIComponent(linha.sigla)}/arquivo`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!res.ok) {
      setErro(await detalheDoErro(res, "Não foi possível baixar o contrato."));
      return;
    }
    const nome = res.headers.get("content-disposition")?.match(/filename="([^"]+)"/)?.[1] ?? `CONTRATO-${linha.sigla}`;
    const url = URL.createObjectURL(await res.blob());
    const link = document.createElement("a");
    link.href = url;
    link.download = nome;
    link.click();
    URL.revokeObjectURL(url);
  }

  const aditivo = contrato?.aditivo_numero
    ? [`nº ${contrato.aditivo_numero}`, dataBr(contrato.aditivo_data)].filter(Boolean).join(", ")
    : dataBr(contrato?.aditivo_data ?? null);

  return (
    <li aria-label={linha.sigla} className={`rounded-xl border border-l-4 p-4 ${COR_DO_CARTAO[linha.situacao]}`}>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <div className="min-w-[10rem] flex-1">
          <p className="text-sm font-semibold text-slate-900">{linha.sigla}</p>
          <p className="text-xs text-slate-500">{linha.nome}</p>
        </div>
        {linha.dias !== null && <span className="text-sm text-slate-700">{quantoFalta(linha.dias)}</span>}
        <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${COR_DA_ETIQUETA[linha.situacao]}`}>
          {LABEL_SITUACAO[linha.situacao]}
        </span>
      </div>

      {contrato && (
        <dl className="mt-3 grid grid-cols-2 md:grid-cols-4 gap-3">
          <Dado rotulo="Assinatura">{dataBr(contrato.data_assinatura)}</Dado>
          <Dado rotulo="Último aditivo">{aditivo}</Dado>
          <Dado rotulo="Início da vigência">{dataBr(contrato.vigencia_inicio)}</Dado>
          <Dado rotulo={contrato.vencimento_e_negociacao ? "Início do debate do reajuste" : "Vencimento"}>
            {contrato.vencimento && (
              <span className="inline-flex items-center gap-2">
                <span>{dataBr(contrato.vencimento)}</span>
                {contrato.vencimento_calculado && (
                  <span className="text-xs px-1.5 py-0.5 rounded bg-slate-200 text-slate-700">calculado</span>
                )}
              </span>
            )}
          </Dado>
        </dl>
      )}

      {linha.data_aviso && (
        <p className="mt-2 text-xs text-slate-500">Aviso de reajuste no sino em {dataBr(linha.data_aviso)}.</p>
      )}

      {erro && (
        <p role="alert" className="mt-2 flex items-center gap-2 text-sm text-red-700">
          <AlertCircle className="w-4 h-4" aria-hidden="true" /> {erro}
        </p>
      )}

      {(podeEditar || contrato?.arquivo) && !editando && (
        <div className="mt-3 flex flex-wrap gap-2">
          {contrato?.arquivo && (
            <button type="button" className={BOTAO_CLARO} onClick={baixar}>
              <Download className="w-4 h-4" aria-hidden="true" /> Baixar contrato
            </button>
          )}
          {podeEditar && (
            <button type="button" className={BOTAO_CLARO} onClick={() => setEditando(true)}>
              <Upload className="w-4 h-4" aria-hidden="true" /> Enviar contrato ou aditivo
            </button>
          )}
        </div>
      )}

      {editando && (
        <FormularioDoContrato
          sigla={linha.sigla}
          token={token}
          atual={contrato}
          aoCancelar={() => setEditando(false)}
          aoConfirmar={async () => {
            setEditando(false);
            await aoConfirmar();
          }}
        />
      )}
    </li>
  );
}

function camposDe(contrato: Contrato | null): Campos {
  return {
    data_assinatura: contrato?.data_assinatura ?? null,
    aditivo_numero: contrato?.aditivo_numero ?? null,
    aditivo_data: contrato?.aditivo_data ?? null,
    vigencia_inicio: contrato?.vigencia_inicio ?? null,
    vencimento: contrato?.vencimento ?? null,
    vencimento_calculado: contrato?.vencimento_calculado ?? false,
  };
}

function FormularioDoContrato({
  sigla,
  token,
  atual,
  aoCancelar,
  aoConfirmar,
}: {
  sigla: string;
  token: string | null;
  atual: Contrato | null;
  aoCancelar: () => void;
  aoConfirmar: () => Promise<void>;
}) {
  const [campos, setCampos] = useState<Campos>(camposDe(atual));
  const [arquivo, setArquivo] = useState<string | null>(null);
  const [lendo, setLendo] = useState(false);
  const [salvando, setSalvando] = useState(false);
  const [aviso, setAviso] = useState<string | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  async function enviar(escolhido: File | undefined) {
    if (!token || !escolhido) return;
    setErro(null);
    setAviso(null);
    setLendo(true);
    try {
      const corpo = new FormData();
      corpo.append("arquivo", escolhido);
      const res = await fetch(`/api/contas-medicas/contratos/${encodeURIComponent(sigla)}/arquivo`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        body: corpo,
      });
      if (!res.ok) {
        setErro(await detalheDoErro(res, "Não foi possível enviar o arquivo."));
        return;
      }
      const proposta: Proposta = await res.json();
      setArquivo(proposta.arquivo);
      setCampos(proposta.campos);
      setAviso(proposta.aviso);
    } catch {
      setErro("Não foi possível enviar o arquivo.");
    } finally {
      setLendo(false);
    }
  }

  async function confirmar() {
    if (!token) return;
    setErro(null);
    setSalvando(true);
    try {
      const res = await fetch(`/api/contas-medicas/contratos/${encodeURIComponent(sigla)}`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
        body: JSON.stringify({ ...campos, arquivo }),
      });
      if (!res.ok) {
        setErro(await detalheDoErro(res, "Não foi possível confirmar o contrato."));
        return;
      }
      await aoConfirmar();
    } catch {
      setErro("Não foi possível confirmar o contrato.");
    } finally {
      setSalvando(false);
    }
  }

  function mudar(campo: keyof Campos, valor: string) {
    setCampos((atuais) => ({
      ...atuais,
      [campo]: valor || null,
      // A data digitada pela pessoa é a do documento, não a calculada.
      ...(campo === "vencimento" ? { vencimento_calculado: false } : {}),
    }));
  }

  const id = (campo: string) => `contrato-${sigla}-${campo}`;

  return (
    <div className="mt-3 rounded-lg border border-slate-200 bg-white p-4 space-y-4">
      <div>
        <label htmlFor={id("arquivo")} className="block text-xs font-medium text-slate-600 mb-1">
          Arquivo do contrato ou aditivo
        </label>
        <input
          id={id("arquivo")}
          type="file"
          accept=".pdf,.png,.jpg,.jpeg"
          disabled={lendo}
          onChange={(e) => enviar(e.target.files?.[0])}
          className="text-sm"
        />
        <p className="text-xs text-slate-500 mt-1">
          Em PDF com texto, os campos são preenchidos pela leitura do arquivo. Confira antes de confirmar.
        </p>
        {lendo && (
          <p className="mt-2 flex items-center gap-2 text-sm text-slate-500">
            <Loader2 className="w-4 h-4 animate-spin" aria-hidden="true" /> Lendo o arquivo
          </p>
        )}
        {aviso && <p className="mt-2 text-sm text-amber-800">{aviso}</p>}
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3">
        <CampoDeData id={id("assinatura")} rotulo="Assinatura" valor={campos.data_assinatura} aoMudar={(v) => mudar("data_assinatura", v)} />
        <div>
          <label htmlFor={id("aditivo")} className="block text-xs font-medium text-slate-600 mb-1">
            Número do aditivo
          </label>
          <input
            id={id("aditivo")}
            type="text"
            maxLength={40}
            value={campos.aditivo_numero ?? ""}
            onChange={(e) => mudar("aditivo_numero", e.target.value)}
            className={CAMPO}
          />
        </div>
        <CampoDeData id={id("aditivo-data")} rotulo="Data do aditivo" valor={campos.aditivo_data} aoMudar={(v) => mudar("aditivo_data", v)} />
        <CampoDeData
          id={id("vigencia")}
          rotulo="Início da vigência"
          valor={campos.vigencia_inicio}
          aoMudar={(v) => mudar("vigencia_inicio", v)}
        />
        <CampoDeData id={id("vencimento")} rotulo="Vencimento" valor={campos.vencimento} aoMudar={(v) => mudar("vencimento", v)} />
      </div>
      {campos.vencimento_calculado && (
        <p className="text-xs text-slate-500">
          Vencimento calculado: início da vigência mais um ano. Se o documento traz a data, digite.
        </p>
      )}

      {erro && (
        <p role="alert" className="flex items-center gap-2 text-sm text-red-700">
          <AlertCircle className="w-4 h-4" aria-hidden="true" /> {erro}
        </p>
      )}

      <div className="flex flex-wrap gap-2">
        <button type="button" className={BOTAO} disabled={lendo || salvando} onClick={confirmar}>
          Confirmar
        </button>
        <button type="button" className={BOTAO_CLARO} disabled={salvando} onClick={aoCancelar}>
          Cancelar
        </button>
      </div>
    </div>
  );
}

function CampoDeData({
  id,
  rotulo,
  valor,
  aoMudar,
}: {
  id: string;
  rotulo: string;
  valor: string | null;
  aoMudar: (valor: string) => void;
}) {
  return (
    <div>
      <label htmlFor={id} className="block text-xs font-medium text-slate-600 mb-1">
        {rotulo}
      </label>
      <input id={id} type="date" value={valor ?? ""} onChange={(e) => aoMudar(e.target.value)} className={CAMPO} />
    </div>
  );
}
