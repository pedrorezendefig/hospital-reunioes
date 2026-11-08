"use client";

/**
 * A conversa da Operadora com o Auditor, na Memória da operadora (issue #1490, PRD #1484, ADR 0081).
 *
 * Quem tem "Regra contratual e tabelas" escreve a regra do jeito dele e o
 * Auditor devolve um lote de propostas já decididas, cada uma com o motivo,
 * os conflitos e a Prova da regra. "Ok, aplicar o lote" manda "ok", que grava
 * o lote inteiro numa versão nova da memória; "Corrigir o item N" manda
 * "corrige o item N: ...", e o Auditor refaz só aquele item. O servidor decide
 * tudo; a tela desenha a conversa e o lote como ele manda.
 *
 * A tabela de preço entra pelo atalho "Enviar tabela", o envio da tela
 * Operadoras já com a operadora escolhida.
 */

import { useState } from "react";
import Link from "next/link";
import { AlertCircle, Loader2, MessageSquare, Upload } from "lucide-react";

import { Ditar, juntarDitado } from "@/components/contas-medicas/Ditar";
import { type ProvaDaRegra, ProvaDaRegraNaTela } from "@/components/contas-medicas/ProvaDaRegra";
import { detalheDoErro } from "@/lib/contas-medicas/operadoras";

type ValorDoParametro = string | number | boolean | null | unknown[] | Record<string, unknown>;

interface Fala {
  id: string;
  autor: "PESSOA" | "AUDITOR";
  autor_nome: string | null;
  texto: string;
  criado_em: string | null;
  /** A versão da memória que a fala gerou, quando o lote dela foi aplicado. */
  versao: string | null;
}

interface PropostaDeRegra {
  secao: string;
  texto: string;
  tipo: string;
  origem: string | null;
  texto_anterior?: string;
}

interface PropostaDeParametro {
  chave: string;
  antes: ValorDoParametro;
  depois: ValorDoParametro;
}

interface ItemDoLote {
  numero: number;
  tipo: "REGRA_NOVA" | "REGRA_ALTERADA" | "PARAMETRO";
  regra_codigo: string | null;
  proposta: PropostaDeRegra | PropostaDeParametro;
  motivo: string | null;
  conflitos: { codigo: string; texto: string; resolucao: "JUNTAR" | "SUBSTITUIR" }[];
  prova: ProvaDaRegra | null;
}

interface Conversa {
  mensagens: Fala[];
  lote: { id: string; itens: ItemDoLote[] } | null;
}

export interface LoteAplicado {
  versao: string;
  regras: string[];
  contas_com_regra_nova: number;
}

const CARTAO = "bg-white rounded-2xl border border-border shadow-premium p-6";
const CAMPO =
  "w-full min-h-[38px] px-3 py-1.5 text-sm border border-slate-200 rounded-lg focus:outline-none focus:border-primary focus:ring-1 focus:ring-primary";
const BOTAO =
  "inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-primary text-white text-sm font-medium disabled:opacity-50";
const BOTAO_SECUNDARIO =
  "inline-flex items-center gap-2 px-4 py-2 rounded-lg border border-slate-200 bg-white text-sm text-slate-700 hover:border-slate-300 disabled:opacity-50";

const ROTULO_DO_TIPO: Record<ItemDoLote["tipo"], string> = {
  REGRA_NOVA: "Regra nova",
  REGRA_ALTERADA: "Regra alterada",
  PARAMETRO: "Parâmetro",
};

const ROTULO_DA_RESOLUCAO = { JUNTAR: "propõe juntar as duas", SUBSTITUIR: "propõe substituir" };

function valorLegivel(valor: ValorDoParametro): string {
  if (valor === null || valor === undefined) return "(sem valor)";
  if (typeof valor === "boolean") return valor ? "sim" : "não";
  if (typeof valor === "string") return valor;
  return JSON.stringify(valor);
}

export function ConversaDaOperadora({
  sigla,
  token,
  aoAplicar,
}: {
  sigla: string;
  token: string | null;
  aoAplicar: (aplicado: LoteAplicado) => Promise<void>;
}) {
  const [aberta, setAberta] = useState(false);
  const [conversa, setConversa] = useState<Conversa>({ mensagens: [], lote: null });
  const [texto, setTexto] = useState("");
  const [ocupado, setOcupado] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const rota = `/api/contas-medicas/operadoras/${encodeURIComponent(sigla)}/conversa`;

  async function abrir() {
    setAberta(true);
    if (!token) return;
    try {
      const res = await fetch(rota, { headers: { Authorization: `Bearer ${token}` } });
      if (!res.ok) {
        setErro(await detalheDoErro(res, "Não foi possível abrir a conversa com o auditor."));
        return;
      }
      setConversa(await res.json());
    } catch {
      setErro("Não foi possível abrir a conversa com o auditor.");
    }
  }

  /** Manda uma mensagem ao Auditor; devolve se deu certo. */
  async function mandar(mensagem: string): Promise<boolean> {
    if (!token || !mensagem.trim()) return false;
    setOcupado(true);
    setErro(null);
    try {
      const res = await fetch(rota, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
        body: JSON.stringify({ texto: mensagem.trim() }),
      });
      if (!res.ok) {
        setErro(await detalheDoErro(res, `Não foi possível falar com o auditor (HTTP ${res.status}).`));
        return false;
      }
      const corpo: Conversa & { aplicado: LoteAplicado | null } = await res.json();
      setConversa({ mensagens: corpo.mensagens, lote: corpo.lote });
      if (corpo.aplicado) await aoAplicar(corpo.aplicado);
      return true;
    } catch {
      setErro("Não foi possível falar com o auditor.");
      return false;
    } finally {
      setOcupado(false);
    }
  }

  async function enviar(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (await mandar(texto)) setTexto("");
  }

  if (!aberta) {
    return (
      <div>
        <button type="button" onClick={abrir} className={BOTAO}>
          <MessageSquare className="w-4 h-4" aria-hidden="true" /> Falar com o auditor
        </button>
      </div>
    );
  }

  return (
    <section aria-label="Falar com o auditor" className={CARTAO}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold text-slate-900">Falar com o auditor</h2>
          <p className="text-sm text-slate-500 mt-0.5">
            Escreva a regra do seu jeito. O Auditor devolve as mudanças num lote, cada uma com a prova. Responda
            &quot;ok&quot; para aplicar tudo ou corrija só o item que discordar. A conversa fica guardada, mas só o que
            você aplica muda a análise das contas.
          </p>
        </div>
        <Link href={`/contas-medicas/operadoras?tabela=${encodeURIComponent(sigla)}`} className={BOTAO_SECUNDARIO}>
          <Upload className="w-4 h-4" aria-hidden="true" /> Enviar tabela
        </Link>
      </div>

      {conversa.mensagens.length > 0 && (
        <ul aria-label="Conversa com o auditor" className="mt-4 space-y-2">
          {conversa.mensagens.map((fala) => (
            <li
              key={fala.id}
              className={`rounded-lg px-3 py-2 text-sm ${
                fala.autor === "AUDITOR" ? "bg-[#EEEEF6] border border-border" : "bg-slate-50 border border-slate-200"
              }`}
            >
              <p className="text-xs font-semibold text-primary">
                {fala.autor === "AUDITOR" ? "Auditor" : (fala.autor_nome ?? "Você")}
              </p>
              <p className="text-slate-700 whitespace-pre-line break-words">{fala.texto}</p>
              {fala.versao && <p className="text-xs text-slate-500 mt-1">Gerou a versão {fala.versao} da memória.</p>}
            </li>
          ))}
        </ul>
      )}

      {conversa.lote && <LoteDoAuditor lote={conversa.lote} ocupado={ocupado} aoMandar={mandar} />}

      <form aria-label="Escrever ao auditor" onSubmit={enviar} className="mt-4 space-y-3">
        <label className="flex flex-col gap-1.5 text-xs font-medium text-slate-500 uppercase">
          Mensagem para o auditor
          <textarea
            value={texto}
            onChange={(e) => setTexto(e.target.value)}
            rows={3}
            maxLength={4000}
            placeholder="Por exemplo: na ASSIM a seringa de limpeza pronta não é paga."
            className={`${CAMPO} normal-case font-normal text-slate-800 bg-white`}
          />
        </label>
        <Ditar campo="Mensagem para o auditor" aoTranscrever={(ditado) => setTexto((atual) => juntarDitado(atual, ditado))} />
        {erro && (
          <p role="alert" className="flex items-start gap-2 text-sm text-red-700">
            <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" aria-hidden="true" /> {erro}
          </p>
        )}
        <div className="flex flex-wrap items-center gap-2">
          <button type="submit" disabled={!texto.trim() || ocupado} className={BOTAO}>
            {ocupado && <Loader2 className="w-4 h-4 animate-spin" aria-hidden="true" />}
            Enviar ao auditor
          </button>
          {ocupado && (
            <p aria-live="polite" className="text-xs text-slate-500">
              O Auditor está lendo e provando as regras nas últimas contas. Pode levar alguns minutos.
            </p>
          )}
        </div>
      </form>
    </section>
  );
}

function LoteDoAuditor({
  lote,
  ocupado,
  aoMandar,
}: {
  lote: { id: string; itens: ItemDoLote[] };
  ocupado: boolean;
  aoMandar: (mensagem: string) => Promise<boolean>;
}) {
  // Prova antes do ok (ADR 0081, decisão 7): o servidor recusa o ok com item de regra sem prova.
  const semProva = lote.itens.filter((item) => item.tipo !== "PARAMETRO" && !item.prova).map((item) => item.numero);
  return (
    <section aria-label="Lote do Auditor" className="mt-4 rounded-xl border border-slate-200 bg-slate-50 p-4 space-y-3">
      <h3 className="text-xs font-semibold text-slate-500 uppercase">
        Lote do Auditor, {lote.itens.length === 1 ? "1 item" : `${lote.itens.length} itens`}
      </h3>
      {lote.itens.map((item) => (
        <ItemDoLoteNaTela key={`${lote.id}-${item.numero}`} item={item} ocupado={ocupado} aoMandar={aoMandar} />
      ))}
      <p className="text-xs text-slate-500">
        Nada vale antes do ok. O ok aplica o lote inteiro numa versão nova da memória, com o seu nome e a data.
      </p>
      {semProva.length > 0 && (
        <p className="text-xs text-amber-700">
          O ok fica travado enquanto {semProva.length === 1 ? "o item" : "os itens"} {semProva.join(", ")}{" "}
          {semProva.length === 1 ? "estiver" : "estiverem"} sem prova.
        </p>
      )}
      <button type="button" disabled={ocupado || semProva.length > 0} onClick={() => aoMandar("ok")} className={BOTAO}>
        Ok, aplicar o lote
      </button>
    </section>
  );
}

function ItemDoLoteNaTela({
  item,
  ocupado,
  aoMandar,
}: {
  item: ItemDoLote;
  ocupado: boolean;
  aoMandar: (mensagem: string) => Promise<boolean>;
}) {
  const [corrigindo, setCorrigindo] = useState(false);
  const [correcao, setCorrecao] = useState("");
  const rotulo = `Item ${item.numero}`;

  async function corrigir(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (await aoMandar(`corrige o item ${item.numero}: ${correcao.trim()}`)) {
      setCorrigindo(false);
      setCorrecao("");
    }
  }

  return (
    <article aria-label={rotulo} className="rounded-lg bg-white border border-slate-200 p-3 text-sm space-y-2">
      <p className="font-semibold text-slate-900">
        {rotulo}, {ROTULO_DO_TIPO[item.tipo]}
        {item.regra_codigo && (
          <>
            {" "}
            <span className="font-mono text-xs text-slate-500">{item.regra_codigo}</span>
          </>
        )}
      </p>
      {item.tipo === "PARAMETRO" ? (
        <ParametroDoItem proposta={item.proposta as PropostaDeParametro} />
      ) : (
        <RegraDoItem proposta={item.proposta as PropostaDeRegra} alterada={item.tipo === "REGRA_ALTERADA"} />
      )}
      {item.motivo && <p className="text-slate-600">{item.motivo}</p>}
      {item.conflitos.map((c) => (
        <p key={c.codigo} className="text-amber-700">
          <span className="font-medium">
            Conflita com {c.codigo}, {ROTULO_DA_RESOLUCAO[c.resolucao]}:
          </span>{" "}
          {c.texto}
        </p>
      ))}
      {item.prova && <ProvaDaRegraNaTela prova={item.prova} />}
      {!item.prova && item.tipo !== "PARAMETRO" && (
        <p className="text-amber-700">A prova não rodou agora. Corrija o item para provar de novo.</p>
      )}
      {corrigindo ? (
        <form aria-label={`Corrigir o item ${item.numero}`} onSubmit={corrigir} className="space-y-2">
          <label className="flex flex-col gap-1.5 text-xs font-medium text-slate-500 uppercase">
            O que corrigir no item {item.numero}
            <textarea
              value={correcao}
              onChange={(e) => setCorrecao(e.target.value)}
              rows={2}
              maxLength={3900}
              className={`${CAMPO} normal-case font-normal text-slate-800 bg-white`}
            />
          </label>
          <div className="flex flex-wrap gap-2">
            <button type="submit" disabled={!correcao.trim() || ocupado} className={BOTAO}>
              Mandar a correção
            </button>
            <button type="button" onClick={() => setCorrigindo(false)} className={BOTAO_SECUNDARIO}>
              Cancelar
            </button>
          </div>
        </form>
      ) : (
        <button
          type="button"
          disabled={ocupado}
          onClick={() => setCorrigindo(true)}
          className="text-sm font-medium text-primary hover:underline disabled:opacity-50"
        >
          Corrigir o item {item.numero}
        </button>
      )}
    </article>
  );
}

function RegraDoItem({ proposta, alterada }: { proposta: PropostaDeRegra; alterada: boolean }) {
  if (!alterada) return <p className="text-slate-800">{proposta.texto}</p>;
  return (
    <>
      <p className="text-slate-600">Antes: {proposta.texto_anterior ?? ""}</p>
      <p className="text-slate-800">Depois: {proposta.texto}</p>
    </>
  );
}

function ParametroDoItem({ proposta }: { proposta: PropostaDeParametro }) {
  return (
    <p className="text-slate-800">
      <span className="font-mono text-xs normal-case">{proposta.chave}</span>: de {valorLegivel(proposta.antes)} para{" "}
      {valorLegivel(proposta.depois)}
    </p>
  );
}
