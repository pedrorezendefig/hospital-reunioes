"use client";

/**
 * A tela Operadoras de Contas médicas (issues #1119, #1120 e #1140, ADR 0070).
 *
 * O mapa das operadoras (uma linha por operadora, com a situação, a memória e
 * a tabela em uso de cada categoria, e o link para a Memória da operadora), a
 * biblioteca de tabelas com "Nova versão", e os formulários de envio do
 * arquivo de memória que o diretor monta, das tabelas de preço em CSV e do
 * dicionário de itens do hospital, mais o cadastro dos planos como o MV
 * imprime e o dos setores com a acomodação. Só quem tem a permissão "regra
 * contratual e tabelas" usa; o backend recusa de novo, para quem chamar a API
 * direto.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { AlertCircle, ArrowLeft, Download, Loader2, Upload } from "lucide-react";
import { MapeamentoDaTabela } from "@/components/contas-medicas/MapeamentoDaTabela";
import { PropostasDoDicionario } from "@/components/contas-medicas/PropostasDoDicionario";
import { TabelasDePreco } from "@/components/contas-medicas/TabelasDePreco";
import { createClient } from "@/lib/supabase/client";
import { Select } from "@/components/ui/Select";
import {
  CATEGORIAS_DE_ENVIO,
  COR_SITUACAO,
  LABEL_CATEGORIA,
  LABEL_SITUACAO,
  type MapeamentoDeColunas,
  type PropostaDeMapeamento,
  type Situacao,
  type TabelaDaCategoria,
  baixarMemoria,
  detalheDoErro,
  plural,
  rotuloDaCategoria,
} from "@/lib/contas-medicas/operadoras";

interface Operadora {
  sigla: string;
  nome: string;
  situacao: Situacao;
  versao: string | null;
  regras: { vigentes: number; pendentes: number };
  tabelas: TabelaDaCategoria[];
}

interface TabelaImportada {
  operadora: string;
  categoria: string;
  descricao_formato: string;
  itens: number;
}

interface DicionarioImportado {
  termos: number;
  novos: number;
  atualizados: number;
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

/** As categorias do envio de tabela, na ordem da tela. */
const OPCOES_DE_CATEGORIA = CATEGORIAS_DE_ENVIO.map((c) => ({ value: c, label: LABEL_CATEGORIA[c] }));

/** As colunas do mapa: as categorias da migration, inclusive Honorários, que espera a CBHPM. */
const CATEGORIAS_DO_MAPA = [...CATEGORIAS_DE_ENVIO, "HONORARIO"];

interface EscolhaDeTabela {
  operadora: string;
  categoria: string;
  vez: number;
}

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

function contagemDeRegras(vigentes: number, pendentes: number): string {
  return `${plural(vigentes, "regra vigente", "regras vigentes")} e ${plural(pendentes, "pendente", "pendentes")}`;
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
  const [escolha, setEscolha] = useState<EscolhaDeTabela | null>(null);

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

      <MapaDasOperadoras operadoras={operadoras} token={token} />

      <BibliotecaDeTabelas
        operadoras={operadoras}
        aoPedirNovaVersao={(operadora, categoria) =>
          setEscolha({ operadora, categoria, vez: (escolha?.vez ?? 0) + 1 })
        }
      />

      <EnvioDeMemoria
        token={token}
        aoImportar={() => (token ? carregarOperadoras(token) : Promise.resolve())}
      />

      <EnvioDeTabela
        key={escolha?.vez ?? 0}
        inicial={escolha}
        token={token}
        operadoras={operadoras}
        aoImportar={() => (token ? carregarOperadoras(token) : Promise.resolve())}
      />

      <EnvioDeDicionario token={token} />

      <PropostasDoDicionario token={token} />

      <CadastroDePlanos token={token} operadoras={operadoras} planos={planos} aoCadastrar={(p) => setPlanos([...planos, p])} />

      <CadastroDeSetores token={token} setores={setores} aoCadastrar={(s) => setSetores([...setores, s])} />
    </div>
  );
}

function TabelaEmUso({ tabela }: { tabela: TabelaDaCategoria | undefined }) {
  const emUso = tabela?.versoes.find((v) => v.em_uso);
  if (emUso) {
    return (
      <>
        <span className="block text-slate-800 break-all">{emUso.tabela}</span>
        {emUso.versao && <span className="block text-slate-500">{emUso.versao}</span>}
      </>
    );
  }
  return (
    <span className="text-slate-500">
      {tabela?.situacao === "CARREGADA" ? "Sem versão em uso" : "Não carregada"}
    </span>
  );
}

function MapaDasOperadoras({ operadoras, token }: { operadoras: Operadora[]; token: string | null }) {
  const [erro, setErro] = useState<string | null>(null);

  async function baixar(sigla: string) {
    if (!token) return;
    setErro(await baixarMemoria(token, sigla));
  }

  return (
    <section aria-label="Operadoras" className={CARTAO}>
      <h2 className="text-base font-semibold text-slate-900">Operadoras</h2>
      <p className="text-sm text-slate-500 mt-0.5 mb-4">
        Uma linha por operadora, com a tabela em uso de cada categoria. Abra a operadora para editar a memória.
      </p>
      {operadoras.length === 0 ? (
        <p className="text-slate-500 text-sm">Nenhuma operadora ainda. Envie a primeira memória abaixo.</p>
      ) : (
        <div className="overflow-x-auto">
          <table aria-label="Mapa das operadoras" className="w-full text-xs">
            <thead>
              <tr className="text-left text-slate-500 uppercase">
                <th className="py-1 pr-3 font-medium">Operadora</th>
                <th className="py-1 pr-3 font-medium">Situação</th>
                <th className="py-1 pr-3 font-medium">Memória</th>
                {CATEGORIAS_DO_MAPA.map((c) => (
                  <th key={c} className="py-1 pr-3 font-medium">
                    {rotuloDaCategoria(c)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 align-top">
              {operadoras.map((op) => (
                <tr key={op.sigla} data-testid={`operadora-${op.sigla}`}>
                  <td className="py-2 pr-3 min-w-[8rem]">
                    <Link
                      href={`/contas-medicas/operadoras/${encodeURIComponent(op.sigla)}`}
                      className="text-sm font-semibold text-primary hover:underline"
                    >
                      {op.sigla}
                    </Link>
                    <span className="block text-slate-500">{op.nome}</span>
                    {op.versao && (
                      <button
                        type="button"
                        onClick={() => baixar(op.sigla)}
                        className="mt-1 inline-flex items-center gap-1 text-primary hover:underline whitespace-nowrap"
                      >
                        <Download className="w-3.5 h-3.5" aria-hidden="true" /> Baixar memória
                      </button>
                    )}
                  </td>
                  <td className="py-2 pr-3">
                    <span className={`font-medium px-2 py-0.5 rounded-full whitespace-nowrap ${COR_SITUACAO[op.situacao]}`}>
                      {LABEL_SITUACAO[op.situacao]}
                    </span>
                  </td>
                  <td className="py-2 pr-3 text-slate-600 min-w-[10rem]">
                    {op.versao
                      ? `Memória versão ${op.versao}, ${contagemDeRegras(op.regras.vigentes, op.regras.pendentes)}`
                      : "Nenhuma memória carregada"}
                  </td>
                  {CATEGORIAS_DO_MAPA.map((c) => (
                    <td key={c} className="py-2 pr-3 min-w-[7rem]">
                      <TabelaEmUso tabela={op.tabelas.find((t) => t.categoria === c)} />
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {erro && (
        <p role="alert" className="text-sm text-red-700 mt-3">
          {erro}
        </p>
      )}
    </section>
  );
}

function BibliotecaDeTabelas({
  operadoras,
  aoPedirNovaVersao,
}: {
  operadoras: Operadora[];
  aoPedirNovaVersao: (operadora: string, categoria: string) => void;
}) {
  return (
    <section aria-label="Biblioteca de tabelas" className={CARTAO}>
      <h2 className="text-base font-semibold text-slate-900">Biblioteca de tabelas</h2>
      <p className="text-sm text-slate-500 mt-0.5 mb-2">
        Todas as versões de cada tabela. A nova versão fica ao lado da anterior e passa a valer a partir do início da
        vigência dela; a conta de um atendimento antigo usa a tabela da data dele.
      </p>
      {operadoras.map((op) => (
        <div key={op.sigla} className="mt-4">
          <h3 className="text-sm font-semibold text-slate-800">{op.sigla}</h3>
          <TabelasDePreco
            rotulo={`Tabelas de preço de ${op.sigla}`}
            tabelas={op.tabelas}
            aoPedirNovaVersao={(categoria) => aoPedirNovaVersao(op.sigla, categoria)}
          />
        </div>
      ))}
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

function EnvioDeTabela({
  inicial,
  token,
  operadoras,
  aoImportar,
}: {
  /** A operadora e a categoria que o "Nova versão" da biblioteca escolheu. */
  inicial: EscolhaDeTabela | null;
  token: string | null;
  operadoras: Operadora[];
  aoImportar: () => Promise<void>;
}) {
  const [operadora, setOperadora] = useState(inicial?.operadora ?? "");
  const [categoria, setCategoria] = useState(inicial?.categoria ?? "");
  const secao = useRef<HTMLElement>(null);
  const campoDoInicio = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!inicial) return;
    secao.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    campoDoInicio.current?.focus();
  }, [inicial]);
  const [inicio, setInicio] = useState("");
  const [fim, setFim] = useState("");
  const [versao, setVersao] = useState("");
  const [arquivo, setArquivo] = useState<File | null>(null);
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [importada, setImportada] = useState<TabelaImportada | null>(null);
  const [proposta, setProposta] = useState<PropostaDeMapeamento | null>(null);
  const [mapeamento, setMapeamento] = useState<MapeamentoDeColunas | null>(null);
  const [alterado, setAlterado] = useState(false);
  const pronto = Boolean(operadora && categoria && inicio && arquivo);
  const rota = `/api/contas-medicas/operadoras/${encodeURIComponent(operadora)}/tabelas`;

  function dadosDaVersao(): FormData {
    const corpo = new FormData();
    corpo.append("categoria", categoria);
    corpo.append("vigencia_inicio", inicio);
    if (fim) corpo.append("vigencia_fim", fim);
    if (versao.trim()) corpo.append("versao", versao.trim());
    corpo.append("arquivo", arquivo!);
    return corpo;
  }

  /** Um POST da seção: devolve o corpo da resposta, ou `null` com o erro já na tela. */
  async function postar(url: string, corpo: FormData, padrao: string): Promise<Record<string, unknown> | null> {
    setEnviando(true);
    setErro(null);
    try {
      const res = await fetch(url, { method: "POST", headers: { Authorization: `Bearer ${token}` }, body: corpo });
      if (!res.ok) {
        setErro(await detalheDoErro(res, `${padrao} (HTTP ${res.status}).`));
        return null;
      }
      return await res.json();
    } catch {
      setErro(`${padrao}.`);
      return null;
    } finally {
      setEnviando(false);
    }
  }

  async function gravada(resposta: Record<string, unknown> | null) {
    if (!resposta) return;
    setImportada(resposta as unknown as TabelaImportada);
    setProposta(null);
    setMapeamento(null);
    await aoImportar();
  }

  function mostrarProposta(resposta: Record<string, unknown>) {
    const nova = resposta as unknown as PropostaDeMapeamento;
    setProposta(nova);
    setMapeamento(nova.mapeamento);
    setAlterado(false);
  }

  async function enviar(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!token || !arquivo || !pronto) return;
    setImportada(null);
    setProposta(null);
    // A proposta diz se o arquivo é um CSV de formato conhecido (carga direta)
    // ou se precisa do mapeamento das colunas. Nada é gravado nela.
    const corpo = new FormData();
    corpo.append("arquivo", arquivo);
    const resposta = await postar(`${rota}/proposta`, corpo, "Não foi possível ler a tabela");
    if (!resposta) return;
    if (resposta.conhecido) {
      await gravada(await postar(rota, dadosDaVersao(), "Não foi possível enviar a tabela"));
      return;
    }
    mostrarProposta(resposta);
  }

  async function verAmostra() {
    if (!arquivo || !mapeamento) return;
    const corpo = new FormData();
    corpo.append("arquivo", arquivo);
    corpo.append("mapeamento", JSON.stringify(mapeamento));
    const resposta = await postar(`${rota}/proposta`, corpo, "Não foi possível ler a tabela");
    if (resposta) mostrarProposta(resposta);
  }

  async function confirmar() {
    if (!arquivo || !mapeamento || !pronto) return;
    const corpo = dadosDaVersao();
    corpo.append("mapeamento", JSON.stringify(mapeamento));
    await gravada(await postar(`${rota}/mapeada`, corpo, "Não foi possível gravar a tabela"));
  }

  return (
    <section ref={secao} aria-label="Enviar tabela de preço" className={CARTAO}>
      <h2 className="text-base font-semibold text-slate-900">Enviar tabela de preço</h2>
      <p className="text-sm text-slate-500 mt-0.5 mb-4">
        A tabela do convênio, com a categoria e a vigência. O CSV de formato conhecido entra direto; o PDF, a planilha
        e o CSV de outro cabeçalho mostram as colunas que a IA propõe e 20 linhas de amostra, e só valem depois de
        confirmados. Uma versão nova fica ao lado da anterior: a conta de um atendimento antigo usa a tabela da data
        dele.
      </p>
      <form aria-label="Enviar tabela de preço" onSubmit={enviar} className="grid gap-3 sm:grid-cols-3 items-end">
        <Select
          label="Operadora da tabela"
          value={operadora}
          onChange={setOperadora}
          options={operadoras.map((op) => ({ value: op.sigla, label: op.sigla }))}
        />
        <Select label="Categoria" value={categoria} onChange={setCategoria} options={OPCOES_DE_CATEGORIA} />
        <label className="flex flex-col gap-1.5 text-xs font-medium text-slate-500 uppercase">
          Versão (opcional)
          <input
            value={versao}
            onChange={(e) => setVersao(e.target.value)}
            className={`${CAMPO} normal-case font-normal`}
          />
        </label>
        <label className="flex flex-col gap-1.5 text-xs font-medium text-slate-500 uppercase">
          Início da vigência
          <input
            ref={campoDoInicio}
            type="date"
            value={inicio}
            onChange={(e) => setInicio(e.target.value)}
            className={`${CAMPO} normal-case font-normal`}
          />
        </label>
        <label className="flex flex-col gap-1.5 text-xs font-medium text-slate-500 uppercase">
          Fim da vigência (opcional)
          <input
            type="date"
            value={fim}
            onChange={(e) => setFim(e.target.value)}
            className={`${CAMPO} normal-case font-normal`}
          />
        </label>
        <label className="flex flex-col gap-1.5 text-xs font-medium text-slate-500 uppercase">
          Arquivo da tabela
          <input
            type="file"
            accept=".csv,.xlsx,.pdf,text/csv,application/pdf,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            onChange={(e) => {
              setArquivo(e.target.files?.[0] ?? null);
              setProposta(null);
            }}
            className="text-sm normal-case font-normal text-slate-700"
          />
        </label>
        <button type="submit" disabled={!pronto || enviando} className={`${BOTAO} justify-center sm:col-start-3`}>
          {enviando ? (
            <Loader2 className="w-4 h-4 animate-spin" aria-hidden="true" />
          ) : (
            <Upload className="w-4 h-4" aria-hidden="true" />
          )}
          Enviar tabela
        </button>
      </form>
      {erro && (
        <p role="alert" className="flex items-start gap-2 text-sm text-red-700 mt-4 break-words">
          <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" aria-hidden="true" /> {erro}
        </p>
      )}
      {proposta && mapeamento && (
        <MapeamentoDaTabela
          proposta={proposta}
          mapeamento={mapeamento}
          alterado={alterado}
          ocupado={enviando}
          aoMudar={(novo) => {
            setMapeamento(novo);
            setAlterado(true);
          }}
          aoVerAmostra={verAmostra}
          aoConfirmar={confirmar}
        />
      )}
      {importada && (
        <p role="status" className="mt-4 rounded-xl bg-emerald-50 p-4 text-sm font-medium text-emerald-800">
          Tabela carregada: {plural(importada.itens, "item", "itens")} de {importada.descricao_formato}, em{" "}
          {importada.operadora} ({rotuloDaCategoria(importada.categoria)}).
        </p>
      )}
    </section>
  );
}

function EnvioDeDicionario({ token }: { token: string | null }) {
  const [arquivo, setArquivo] = useState<File | null>(null);
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [importado, setImportado] = useState<DicionarioImportado | null>(null);

  async function enviar(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!token || !arquivo) return;
    setEnviando(true);
    setErro(null);
    setImportado(null);
    try {
      const corpo = new FormData();
      corpo.append("arquivo", arquivo);
      const res = await fetch("/api/contas-medicas/dicionario", {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        body: corpo,
      });
      if (!res.ok) {
        setErro(await detalheDoErro(res, `Não foi possível enviar o dicionário (HTTP ${res.status}).`));
        return;
      }
      setImportado(await res.json());
    } catch {
      setErro("Não foi possível enviar o dicionário.");
    } finally {
      setEnviando(false);
    }
  }

  return (
    <section aria-label="Dicionário de itens" className={CARTAO}>
      <h2 className="text-base font-semibold text-slate-900">Dicionário de itens</h2>
      <p className="text-sm text-slate-500 mt-0.5 mb-4">
        O dicionário do hospital, em CSV: o nome do produto na prescrição e na ficha anestésica, com os sinônimos
        separados por barra vertical, ligado ao código da conta. Termo que já existe é atualizado.
      </p>
      <form aria-label="Dicionário de itens" onSubmit={enviar} className="flex flex-wrap items-end gap-3">
        <label className="flex flex-col gap-1.5 text-xs font-medium text-slate-500 uppercase">
          Arquivo do dicionário
          <input
            type="file"
            accept=".csv,text/csv"
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
          Enviar dicionário
        </button>
      </form>
      {erro && (
        <p role="alert" className="flex items-start gap-2 text-sm text-red-700 mt-4">
          <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" aria-hidden="true" /> {erro}
        </p>
      )}
      {importado && (
        <p role="status" className="mt-4 rounded-xl bg-emerald-50 p-4 text-sm font-medium text-emerald-800">
          Dicionário carregado: {plural(importado.termos, "termo", "termos")},{" "}
          {plural(importado.novos, "novo", "novos")} e {plural(importado.atualizados, "atualizado", "atualizados")}.
        </p>
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
