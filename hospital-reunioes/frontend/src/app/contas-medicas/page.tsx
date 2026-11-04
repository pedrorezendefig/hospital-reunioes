"use client";

/**
 * A tela Contas de Contas médicas (issues #1114 e #1123, PRD #1113, ADR 0070).
 *
 * Quem envia arrasta a conta e o prontuário do MV (ou clica em "Selecionar
 * arquivos"), recebe na hora o "Último envio" por atendimento e acompanha em
 * "Meus envios" o que ainda não ficou pronto. A faturista puxa da Fila comum,
 * em ordem de envio, e segue em "Minhas" (issue #1307, ADR 0073). Cada bloco
 * aparece pela permissão: "Enviar contas" dá o envio e "Meus envios", e
 * "Analisar contas" dá a Fila, "Minhas" e as Concluídas (issue #1308). Quem pareia,
 * recusa, ordena e decide quem vê o quê é o servidor; a tela só confere os
 * limites que dá para conferir antes de subir e manda os arquivos em lotes que
 * cabem no teto do corpo.
 *
 * A conta é sempre identificada pelo atendimento, com a conta como complemento.
 * Na aba de envios, cada conta é um cartão com um quadrado para a Conta e outro
 * para o Prontuário (issue #1336): verde o que chegou, tracejado o que falta,
 * com o botão para mandar só aquele arquivo. O envio em Erro ou com arquivo
 * faltando tem ainda "Descartar", que pergunta antes de apagar (issue #1338).
 */

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { AlertCircle, Loader2, ReceiptText, Upload } from "lucide-react";

import { LinkParaContratos } from "@/components/contas-medicas/LinkParaContratos";
import { LinkParaCoordenacao } from "@/components/contas-medicas/LinkParaCoordenacao";
import { LinkParaHabilitacao } from "@/components/contas-medicas/LinkParaHabilitacao";
import { LinkParaOperadoras } from "@/components/contas-medicas/LinkParaOperadoras";
import { LinkParaPainel } from "@/components/contas-medicas/LinkParaPainel";
import { LinkParaValidacao } from "@/components/contas-medicas/LinkParaValidacao";
import {
  ANALISAR_CONTAS,
  ENVIAR_CONTAS,
  type Fila,
  type ItemDaFila,
  type RespostaDoEnvio,
  ROTA_FILA,
  ROTA_ME,
  ROTA_MEUS_ENVIOS,
  analisarAssimMesmo,
  analisarDeNovo,
  detalheDaConta,
  enviarEmLotes,
  perguntaDoDescarte,
  rotaDoDescarte,
  rotuloDaSituacao,
  separarArquivos,
  textoParaATI,
} from "@/lib/contas-medicas/envio";
import { dataCurta } from "@/lib/contas-medicas/guia";
import { createClient } from "@/lib/supabase/client";

const CARTAO = "bg-white rounded-2xl border border-border shadow-premium";

const COR_DA_SITUACAO: Record<string, string> = {
  AGUARDANDO_ARQUIVO: "bg-slate-100 text-slate-600",
  NA_FILA: "bg-slate-100 text-slate-600",
  PROCESSANDO: "bg-[#DBEAFE] text-[#1E40AF]",
  A_FAZER: "bg-[#FEE2E2] text-[#991B1B]",
  EM_CORRECAO: "bg-[#FEF3C7] text-[#92400E]",
  ERRO: "bg-[#FEE2E2] text-[#991B1B]",
  CONCLUIDA: "bg-[#DCFCE7] text-[#166534]",
  CONCLUIDA_COM_PENDENCIA: "bg-[#FEF3C7] text-[#92400E]",
  RETORNO: "bg-[#FEF3C7] text-[#92400E]",
};

/** Enquanto houver conta esperando a análise, a fila se relê sozinha. */
const RELER_A_CADA_MS = 20_000;
const ESPERANDO_ANALISE = ["NA_FILA", "PROCESSANDO"];

type Aba = "fila" | "minhas" | "meus_envios" | "concluidas";

/** O que a pessoa pode fazer na tela, pela matriz que `/contas-medicas/me` resolve. */
interface Pode {
  enviar: boolean;
  analisar: boolean;
}

/** As abas na ordem da tela, só as das permissões da pessoa. */
function abasDe(pode: Pode): Aba[] {
  const abas: Aba[] = [];
  if (pode.analisar) abas.push("fila", "minhas");
  if (pode.enviar) abas.push("meus_envios");
  if (pode.analisar) abas.push("concluidas");
  return abas;
}

async function lerJson(rota: string, token: string) {
  const resposta = await fetch(rota, { headers: { Authorization: `Bearer ${token}` } });
  if (!resposta.ok) throw new Error(rota);
  return resposta.json();
}

/** O rótulo de cada aba; com o painel completo, as listas são de todas. */
function rotuloDaAba(aba: Aba, todas: boolean): string {
  if (aba === "fila") return "Fila";
  if (aba === "minhas") return todas ? "Em análise" : "Minhas";
  if (aba === "meus_envios") return todas ? "Envios" : "Meus envios";
  return "Concluídas";
}

const VAZIO: Record<Aba, string> = {
  fila: "Nenhuma conta livre na fila",
  minhas: "Nenhuma conta em análise",
  meus_envios: "Nenhum envio esperando o guia",
  concluidas: "Nenhuma conta concluída ainda",
};

function periodoDaConta(conta: ItemDaFila): string | null {
  return conta.periodo_inicio && conta.periodo_fim
    ? `${dataCurta(conta.periodo_inicio)} a ${dataCurta(conta.periodo_fim)}`
    : null;
}

function complemento(conta: ItemDaFila): string {
  const periodo = periodoDaConta(conta);
  return [conta.numero_conta ? `conta ${conta.numero_conta}` : null, periodo].filter(Boolean).join(" · ");
}

/** A borda do cartão do envio pela situação, nas cores dos cartões da Ouvidoria. */
const BORDA_DA_SITUACAO: Record<string, string> = {
  ERRO: "border-l-red-500",
  AGUARDANDO_ARQUIVO: "border-l-amber-500",
  NA_FILA: "border-l-slate-300",
  PROCESSANDO: "border-l-emerald-500",
};

/** O quadrado de cada estado: o que falta, o que chegou e o arquivo em que a análise parou (issue #1337). */
const COR_DO_QUADRADO = {
  falta: { caixa: "border-dashed border-slate-300 bg-white", rotulo: "text-slate-500", texto: "text-slate-600" },
  chegou: { caixa: "border-emerald-200 bg-emerald-50", rotulo: "text-emerald-800", texto: "text-emerald-900" },
  erro: { caixa: "border-red-300 bg-red-50", rotulo: "text-red-800", texto: "text-red-900" },
};

function Quadrado({
  nome,
  falta,
  comErro = false,
  rotuloDoBotao,
  onEnviar,
  children,
}: {
  nome: "Conta" | "Prontuário";
  falta: boolean;
  comErro?: boolean;
  rotuloDoBotao: string;
  onEnviar: () => void;
  children: React.ReactNode;
}) {
  const estado = falta ? "falta" : comErro ? "erro" : "chegou";
  const cor = COR_DO_QUADRADO[estado];
  return (
    <section
      aria-label={nome}
      data-estado={estado}
      className={`min-w-0 rounded-xl border px-3 py-2.5 ${cor.caixa}`}
    >
      <p className={`text-xs font-semibold uppercase tracking-wide ${cor.rotulo}`}>
        {nome}
      </p>
      {falta ? (
        <>
          <p className="mt-0.5 text-sm text-slate-600">Falta enviar</p>
          <button
            type="button"
            onClick={onEnviar}
            className="mt-2 inline-flex items-center gap-1.5 rounded-lg bg-primary px-3 py-1.5 text-xs font-semibold text-white"
          >
            <Upload className="h-3.5 w-3.5" aria-hidden="true" />
            {rotuloDoBotao}
          </button>
        </>
      ) : (
        <div className={`mt-0.5 text-sm break-words ${cor.texto}`}>{children}</div>
      )}
    </section>
  );
}

/**
 * A frase da cópia que não aconteceu. O `writeText` falha igual quando a API
 * não existe e quando o navegador nega: a frase diz o desfecho e a saída, que
 * é a caixa logo abaixo (o mesmo cuidado do "Copiar para IA" da Tecnologia).
 */
const NAO_COPIOU =
  "O navegador não liberou a cópia automática. O texto está na caixa abaixo, já selecionado: copie com Ctrl+C (ou Cmd+C).";

/**
 * O Erro do cartão do envio (issue #1337): a frase, o Código do erro, "Ver
 * detalhes" com o detalhe técnico e "Copiar para a TI", que leva o que a TI
 * precisa para achar o erro sem ver a tela. Quando o servidor diz que a ação é
 * Analisar de novo (o erro não foi no PDF e ele ainda está guardado), o botão
 * põe a conta de volta na fila sem anexar nada (issue #1339). Na conta parada
 * por folha escaneada ilegível, "Analisar assim mesmo" fica ao lado de "Enviar
 * de novo" quando o servidor deixa (issue #1401).
 */
function ErroDoEnvio({
  conta,
  onEnviar,
  onAnalisarDeNovo,
  onAnalisarAssimMesmo,
  onDescartar,
}: {
  conta: ItemDaFila;
  onEnviar: () => void;
  onAnalisarDeNovo: () => Promise<string | null>;
  onAnalisarAssimMesmo: () => Promise<string | null>;
  onDescartar?: () => void;
}) {
  const [aberto, setAberto] = useState(false);
  const [analisando, setAnalisando] = useState(false);
  const [recusa, setRecusa] = useState<string | null>(null);
  const [copiou, setCopiou] = useState(false);
  const [paraPegarAMao, setParaPegarAMao] = useState<string | null>(null);
  const caixa = useRef<HTMLTextAreaElement | null>(null);

  useEffect(() => {
    if (paraPegarAMao) caixa.current?.select();
  }, [paraPegarAMao]);

  async function copiar() {
    const texto = textoParaATI(conta);
    setCopiou(false);
    setParaPegarAMao(null);
    try {
      await navigator.clipboard.writeText(texto);
      setCopiou(true);
    } catch (e) {
      console.error("[contas-medicas] o navegador não copiou", e);
      setParaPegarAMao(texto);
    }
  }

  async function analisar(pedir: () => Promise<string | null>) {
    setAnalisando(true);
    setRecusa(null);
    const frase = await pedir();
    setAnalisando(false);
    setRecusa(frase);
  }

  const idDoDetalhe = `detalhe-do-erro-${conta.id}`;
  return (
    <div className="space-y-2">
      {conta.erro_motivo && <p className="min-w-0 break-words text-sm text-red-700">{conta.erro_motivo}</p>}
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        {conta.erro_codigo && (
          <span className="text-xs text-slate-500">
            Código <span className="font-mono font-semibold text-slate-800">{conta.erro_codigo}</span>
          </span>
        )}
        <button
          type="button"
          aria-expanded={aberto}
          aria-controls={idDoDetalhe}
          onClick={() => setAberto((valor) => !valor)}
          className="text-sm font-medium text-primary hover:underline"
        >
          Ver detalhes
        </button>
        <button type="button" onClick={copiar} className="text-sm font-medium text-primary hover:underline">
          Copiar para a TI
        </button>
        {conta.erro_acao === "analisar_de_novo" ? (
          <button
            type="button"
            onClick={() => analisar(onAnalisarDeNovo)}
            disabled={analisando}
            className="text-sm font-medium text-primary hover:underline disabled:opacity-50"
          >
            Analisar de novo
          </button>
        ) : (
          <button type="button" onClick={onEnviar} className="text-sm font-medium text-primary hover:underline">
            Enviar de novo
          </button>
        )}
        {conta.pode_analisar_assim_mesmo && (
          <button
            type="button"
            onClick={() => analisar(onAnalisarAssimMesmo)}
            disabled={analisando}
            className="text-sm font-medium text-primary hover:underline disabled:opacity-50"
          >
            Analisar assim mesmo
          </button>
        )}
        {onDescartar && (
          <button type="button" onClick={onDescartar} className="text-sm font-medium text-red-700 hover:underline">
            Descartar
          </button>
        )}
      </div>
      {recusa && (
        <p role="alert" className="text-sm text-red-700">
          {recusa}
        </p>
      )}
      {aberto && (
        <p id={idDoDetalhe} className="break-all rounded-lg bg-slate-50 px-3 py-2 font-mono text-xs text-slate-700">
          {conta.erro_detalhe ?? "Sem detalhe técnico gravado."}
        </p>
      )}
      {copiou && (
        <p role="status" className="text-xs text-emerald-700">
          Copiado. Cole na conversa com a TI.
        </p>
      )}
      {paraPegarAMao && (
        <>
          <p role="status" className="text-xs text-amber-800">
            {NAO_COPIOU}
          </p>
          <textarea
            ref={caixa}
            readOnly
            value={paraPegarAMao}
            rows={5}
            aria-label="Texto para a TI"
            className="w-full rounded-lg border border-border bg-white px-3 py-2 font-mono text-xs text-slate-800"
          />
        </>
      )}
    </div>
  );
}

/** A conta da aba de envios, com o quadrado de cada arquivo (issue #1336). */
function CartaoDoEnvio({
  conta,
  onEnviar,
  onAnalisarDeNovo,
  onAnalisarAssimMesmo,
  onDescartar,
}: {
  conta: ItemDaFila;
  onEnviar: () => void;
  onAnalisarDeNovo: () => Promise<string | null>;
  onAnalisarAssimMesmo: () => Promise<string | null>;
  onDescartar: () => void;
}) {
  const detalhe = detalheDaConta(conta);
  const periodo = periodoDaConta(conta);
  const paginas = conta.prontuario_paginas;
  const erro = conta.situacao === "ERRO";
  return (
    <li>
      <article
        className={`rounded-xl border border-border border-l-4 bg-white p-4 space-y-3 ${
          BORDA_DA_SITUACAO[conta.situacao] ?? "border-l-slate-300"
        }`}
      >
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
          <p className="min-w-0 flex-1 text-sm font-semibold text-slate-900">Atendimento {conta.numero_atendimento}</p>
          <span
            className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${COR_DA_SITUACAO[conta.situacao] ?? "bg-slate-100 text-slate-600"}`}
          >
            {rotuloDaSituacao(conta)}
          </span>
          {conta.com && <span className="text-xs text-slate-500">com {conta.com}</span>}
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <Quadrado
            nome="Conta"
            falta={conta.falta === "conta"}
            comErro={erro && conta.erro_arquivo === "conta"}
            rotuloDoBotao="Enviar a conta"
            onEnviar={onEnviar}
          >
            <p>{conta.numero_conta ? `Conta ${conta.numero_conta}` : "Chegou"}</p>
            {periodo && <p className="text-xs">{periodo}</p>}
          </Quadrado>
          <Quadrado
            nome="Prontuário"
            falta={conta.falta === "prontuario"}
            comErro={erro && conta.erro_arquivo === "prontuario"}
            rotuloDoBotao="Enviar o prontuário"
            onEnviar={onEnviar}
          >
            <p>{paginas != null ? `${paginas} ${paginas === 1 ? "página" : "páginas"}` : "Chegou"}</p>
          </Quadrado>
        </div>
        {erro ? (
          <ErroDoEnvio
            conta={conta}
            onEnviar={onEnviar}
            onAnalisarDeNovo={onAnalisarDeNovo}
            onAnalisarAssimMesmo={onAnalisarAssimMesmo}
            onDescartar={conta.pode_descartar ? onDescartar : undefined}
          />
        ) : (
          (detalhe || conta.pode_descartar) && (
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
              {detalhe && <span className="min-w-0 break-words text-xs text-slate-600">{detalhe}</span>}
              {conta.pode_descartar && (
                <button type="button" onClick={onDescartar} className="text-sm font-medium text-red-700 hover:underline">
                  Descartar
                </button>
              )}
            </div>
          )
        )}
      </article>
    </li>
  );
}

function LinhaDaFila({ conta, onEnviarDeNovo }: { conta: ItemDaFila; onEnviarDeNovo: () => void }) {
  const detalhe = detalheDaConta(conta);
  const guia = `/contas-medicas/guia/${conta.id}`;
  let acao: React.ReactNode = null;
  if (conta.situacao === "A_FAZER" || conta.situacao.startsWith("CONCLUIDA")) {
    acao = (
      <Link href={guia} className="text-sm font-medium text-primary hover:underline">
        Abrir
      </Link>
    );
  } else if (conta.situacao === "EM_CORRECAO" || conta.situacao === "RETORNO") {
    acao = (
      <Link href={guia} className="text-sm font-medium text-primary hover:underline">
        Continuar
      </Link>
    );
  } else if (conta.situacao === "ERRO") {
    acao = (
      <button type="button" onClick={onEnviarDeNovo} className="text-sm font-medium text-primary hover:underline">
        Enviar de novo
      </button>
    );
  }

  return (
    <li className="flex flex-wrap items-center gap-x-4 gap-y-1 px-5 py-3">
      <div className="min-w-0 flex-1">
        <p className="text-sm font-semibold text-slate-900">Atendimento {conta.numero_atendimento}</p>
        {complemento(conta) && <p className="text-xs text-slate-500">{complemento(conta)}</p>}
      </div>
      <span
        className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${COR_DA_SITUACAO[conta.situacao] ?? "bg-slate-100 text-slate-600"}`}
      >
        {rotuloDaSituacao(conta)}
      </span>
      {detalhe && (
        <span className={`text-xs ${conta.situacao === "ERRO" ? "text-red-700" : "text-slate-600"}`}>{detalhe}</span>
      )}
      {conta.com && <span className="text-xs text-slate-500">com {conta.com}</span>}
      {acao}
    </li>
  );
}

function UltimoEnvio({ resposta }: { resposta: RespostaDoEnvio }) {
  return (
    <section aria-label="Último envio" className={`${CARTAO} p-5`}>
      <h2 className="text-sm font-semibold text-slate-900 mb-3">Último envio</h2>
      {resposta.ultimo_envio.length > 0 ? (
        <ul className="space-y-2">
          {resposta.ultimo_envio.map((linha) => (
            <li key={linha.numero_atendimento} className="text-sm text-slate-800">
              {linha.texto}
              {linha.aviso && <p className="mt-0.5 text-xs text-amber-700">{linha.aviso}</p>}
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-sm text-slate-500">Nenhum atendimento entrou neste envio.</p>
      )}
      {resposta.recusas.length > 0 && (
        <ul aria-label="Arquivos recusados" className="mt-4 space-y-2 border-t border-border pt-3">
          {resposta.recusas.map((recusa, i) => (
            <li key={`${recusa.arquivo}-${i}`} className="flex gap-2 text-sm text-red-700">
              <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" aria-hidden="true" />
              <span>
                {recusa.motivo}
                <span className="block text-xs text-slate-500">
                  {[recusa.arquivo, recusa.numero_atendimento ? `atendimento ${recusa.numero_atendimento}` : null]
                    .filter(Boolean)
                    .join(", ")}
                </span>
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

export default function ContasMedicasPage() {
  const [token, setToken] = useState<string | null>(null);
  const [pode, setPode] = useState<Pode | null>(null);
  const [fila, setFila] = useState<Fila | null>(null);
  const [erroDaFila, setErroDaFila] = useState<string | null>(null);
  const [aba, setAba] = useState<Aba>("fila");
  const [arrastando, setArrastando] = useState(false);
  const [enviando, setEnviando] = useState<number | null>(null);
  const [ultimo, setUltimo] = useState<RespostaDoEnvio | null>(null);
  const [recusaDoDescarte, setRecusaDoDescarte] = useState<string | null>(null);
  const seletor = useRef<HTMLInputElement>(null);

  /** Cada lista vem da rota da permissão dela; a que a pessoa não tem fica vazia. */
  const carregarFila = useCallback(async (tk: string, quem: Pode) => {
    try {
      const [analise, envios] = await Promise.all([
        quem.analisar ? lerJson(ROTA_FILA, tk) : null,
        quem.enviar ? lerJson(ROTA_MEUS_ENVIOS, tk) : null,
      ]);
      setErroDaFila(null);
      setFila({
        todas: Boolean(analise?.todas ?? envios?.todas),
        fila: analise?.fila ?? [],
        minhas: analise?.minhas ?? [],
        meus_envios: envios?.meus_envios ?? [],
        concluidas: analise?.concluidas ?? [],
      });
    } catch {
      setErroDaFila("Não consegui carregar a fila.");
    }
  }, []);

  useEffect(() => {
    let vivo = true;
    async function iniciar() {
      const {
        data: { session },
      } = await createClient().auth.getSession();
      const tk = session?.access_token ?? null;
      if (!vivo) return;
      setToken(tk);
      if (!tk) {
        setErroDaFila("Sessão expirada. Entre de novo.");
        return;
      }
      let quem: Pode;
      try {
        const { permissoes } = await lerJson(ROTA_ME, tk);
        const lista: string[] = Array.isArray(permissoes) ? permissoes : [];
        quem = { enviar: lista.includes(ENVIAR_CONTAS), analisar: lista.includes(ANALISAR_CONTAS) };
      } catch {
        if (vivo) setErroDaFila("Não consegui carregar a fila.");
        return;
      }
      if (!vivo) return;
      setPode(quem);
      setAba(abasDe(quem)[0] ?? "fila");
      await carregarFila(tk, quem);
    }
    iniciar();
    return () => {
      vivo = false;
    };
  }, [carregarFila]);

  const esperandoAnalise = fila?.meus_envios.some((conta) => ESPERANDO_ANALISE.includes(conta.situacao)) ?? false;
  useEffect(() => {
    if (!token || !pode || !esperandoAnalise) return;
    const relogio = setInterval(() => carregarFila(token, pode), RELER_A_CADA_MS);
    return () => clearInterval(relogio);
  }, [token, pode, esperandoAnalise, carregarFila]);

  async function enviar(lista: FileList | File[] | null) {
    const arquivos = Array.from(lista ?? []);
    if (!token || !pode || arquivos.length === 0 || enviando !== null) return;
    const { aceitos, recusas } = separarArquivos(arquivos);
    setEnviando(aceitos.length);
    try {
      const resposta = aceitos.length > 0 ? await enviarEmLotes(aceitos, token) : null;
      setUltimo({
        envio_id: resposta?.envio_id ?? null,
        ultimo_envio: resposta?.ultimo_envio ?? [],
        recusas: [...recusas, ...(resposta?.recusas ?? [])],
      });
    } finally {
      setEnviando(null);
      if (seletor.current) seletor.current.value = "";
    }
    await carregarFila(token, pode);
  }

  /** Pergunta antes; confirmado, o servidor apaga a conta e os PDFs, e a lista se relê. */
  async function descartar(conta: ItemDaFila) {
    if (!token || !pode || !window.confirm(perguntaDoDescarte(conta))) return;
    setRecusaDoDescarte(null);
    try {
      const resposta = await fetch(rotaDoDescarte(conta.id), {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!resposta.ok) {
        const corpo = await resposta.json().catch(() => null);
        setRecusaDoDescarte(typeof corpo?.detail === "string" ? corpo.detail : "Não consegui descartar. Tente de novo.");
      }
    } catch {
      setRecusaDoDescarte("Não consegui descartar. Tente de novo.");
    }
    await carregarFila(token, pode);
  }

  /**
   * A conta volta para a fila e a lista se relê: o cartão passa para Na fila.
   * `assimMesmo` é a conta parada por folha escaneada ilegível (issue #1401).
   */
  async function analisarContaDeNovo(contaId: string, assimMesmo = false): Promise<string | null> {
    if (!token || !pode) return null;
    const recusa = await (assimMesmo ? analisarAssimMesmo : analisarDeNovo)(contaId, token);
    if (recusa === null) await carregarFila(token, pode);
    return recusa;
  }

  const contas = fila?.[aba];
  const abas = pode ? abasDe(pode) : [];
  // Sem nenhuma das duas permissões (o credenciamento), a tela fica só com os atalhos.
  const semListas = pode !== null && abas.length === 0;

  return (
    <div className="space-y-6">
      <div>
        <div className="flex items-center justify-between gap-3">
          <h1 className="flex-1 text-2xl font-bold text-slate-900">Contas médicas</h1>
          <LinkParaPainel />
          <LinkParaValidacao />
          <LinkParaCoordenacao />
          <LinkParaContratos />
          <LinkParaOperadoras />
          <LinkParaHabilitacao />
        </div>
        <p className="text-slate-500 text-sm mt-0.5">
          Envie a conta e o prontuário do MV e receba a lista do que corrigir antes de mandar para a operadora.
        </p>
      </div>

      {pode?.enviar && (
        <section
          aria-label="Envio de contas"
          onDragOver={(e) => {
            e.preventDefault();
            setArrastando(true);
          }}
          onDragLeave={() => setArrastando(false)}
          onDrop={(e) => {
            e.preventDefault();
            setArrastando(false);
            enviar(e.dataTransfer?.files ?? null);
          }}
          className={`rounded-2xl border-2 border-dashed p-8 text-center transition-colors ${
            arrastando ? "border-primary bg-primary/5" : "border-slate-300 bg-white"
          }`}
        >
          {enviando !== null ? (
            <p className="flex items-center justify-center gap-2 text-sm text-slate-600">
              <Loader2 className="w-4 h-4 animate-spin" aria-hidden="true" />
              Enviando {enviando === 1 ? "1 arquivo" : `${enviando} arquivos`} e lendo cada PDF
            </p>
          ) : (
            <>
              <Upload className="w-8 h-8 text-slate-400 mx-auto mb-3" aria-hidden="true" />
              <p className="text-sm font-medium text-slate-800">Arraste aqui a conta e o prontuário do MV</p>
              <p className="text-xs text-slate-500 mt-1">
                Vários de uma vez, sem renomear: o app lê o tipo e o atendimento dentro de cada PDF. Até 10
                atendimentos e 30 arquivos por envio, 100 MB por arquivo.
              </p>
              <button
                type="button"
                onClick={() => seletor.current?.click()}
                className="mt-4 inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-primary text-white text-sm font-medium"
              >
                Selecionar arquivos
              </button>
            </>
          )}
          <input
            ref={seletor}
            type="file"
            accept="application/pdf,.pdf"
            multiple
            hidden
            aria-label="Arquivos da conta e do prontuário"
            onChange={(e) => enviar(e.target.files)}
          />
        </section>
      )}

      {ultimo && <UltimoEnvio resposta={ultimo} />}

      {!semListas && (
        <div>
          <div className="flex gap-2 border-b border-border" role="tablist">
            {abas.map((id) => (

              <button
                key={id}
                type="button"
                role="tab"
                aria-selected={aba === id}
                onClick={() => setAba(id)}
                className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
                  aba === id ? "border-primary text-primary" : "border-transparent text-text-secondary hover:text-text"
                }`}
              >
                {`${rotuloDaAba(id, fila?.todas ?? false)} (${fila?.[id].length ?? 0})`}
              </button>
            ))}
          </div>

          {recusaDoDescarte && (
            <p role="alert" className="mt-4 flex items-center gap-2 text-sm text-red-700">
              <AlertCircle className="w-4 h-4" aria-hidden="true" /> {recusaDoDescarte}
            </p>
          )}

          <section aria-label="Fila de contas" className={`${CARTAO} mt-4`}>
            <div role="tabpanel">
              {erroDaFila ? (
                <p role="alert" className="flex items-center gap-2 p-6 text-sm text-red-700">
                  <AlertCircle className="w-4 h-4" aria-hidden="true" /> {erroDaFila}
                </p>
              ) : !fila ? (
                <p className="flex items-center gap-2 p-6 text-sm text-slate-500">
                  <Loader2 className="w-4 h-4 animate-spin" aria-hidden="true" /> Carregando a fila
                </p>
              ) : contas && contas.length > 0 && aba === "meus_envios" ? (
                <ul className="space-y-3 p-3">
                  {contas.map((conta) => (
                    <CartaoDoEnvio
                      key={conta.id}
                      conta={conta}
                      onEnviar={() => seletor.current?.click()}
                      onAnalisarDeNovo={() => analisarContaDeNovo(conta.id)}
                      onAnalisarAssimMesmo={() => analisarContaDeNovo(conta.id, true)}
                      onDescartar={() => descartar(conta)}
                    />
                  ))}
                </ul>
              ) : contas && contas.length > 0 ? (
                <ul className="divide-y divide-border">
                  {contas.map((conta) => (
                    <LinhaDaFila key={conta.id} conta={conta} onEnviarDeNovo={() => seletor.current?.click()} />
                  ))}
                </ul>
              ) : (
                <div className="p-10 text-center">
                  <ReceiptText className="w-8 h-8 text-slate-300 mx-auto mb-3" aria-hidden="true" />
                  <p className="text-slate-500 text-sm">{VAZIO[aba]}</p>
                </div>
              )}
            </div>
          </section>
        </div>
      )}
    </div>
  );
}
