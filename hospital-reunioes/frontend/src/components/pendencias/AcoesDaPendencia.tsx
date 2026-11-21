"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { History, Loader2, Paperclip } from "lucide-react";

import type { ComandoPendencia, EventoPendencia, HistoricoPendencia, Pendencia } from "@/types";

/**
 * As ações e o histórico da Pendência (issue #1862, ADR 0098, decisão 5).
 *
 * Toda ação pede uma anotação; repactuar e reabrir pedem também o prazo novo,
 * e ajustar uma contestação aceita o prazo novo e o responsável novo, sem
 * exigir nenhum dos dois (issue #1870).
 * Os botões são os que o backend devolve em `acoes_permitidas`: quem age sai do
 * vínculo com a Pendência, e a regra mora no servidor.
 */

const ROTULO_DO_BOTAO: Record<ComandoPendencia, string> = {
  iniciar: "Iniciar",
  anotar: "Anotar",
  concluir: "Concluir",
  repactuar: "Repactuar",
  cancelar: "Cancelar pendência",
  reabrir: "Reabrir",
  contestar: "Contestar",
  ajustar: "Ajustar",
  recusar: "Recusar contestação",
};

const ROTULO_DO_EVENTO: Record<EventoPendencia["comando"], string> = {
  nascimento: "Nasceu",
  iniciar: "Iniciou",
  anotar: "Anotou",
  concluir: "Concluiu",
  repactuar: "Repactuou",
  cancelar: "Cancelou",
  reabrir: "Reabriu",
  contestar: "Contestou",
  ajustar: "Ajustou a contestação",
  recusar: "Recusou a contestação",
  migracao: "Ajuste da migração",
};

const PEDE_PRAZO: ComandoPendencia[] = ["repactuar", "reabrir"];
// O ajuste da contestação pode trocar o prazo, ou não (o erro era outro).
const PRAZO_OPCIONAL: ComandoPendencia[] = ["ajustar"];
// Só o ajuste troca o responsável errado da ata (issue #1870).
const TROCA_RESPONSAVEL: ComandoPendencia[] = ["ajustar"];

interface Pessoa {
  id: string;
  nome_completo: string;
  cargo?: string | null;
}

// O anexo da conclusão (issue #1865): o mesmo teto e os mesmos tipos do
// backend (`app/services/pendencia_anexo.py`), que confere de novo.
const LIMITE_DO_ANEXO = 10 * 1024 * 1024;
const EXTENSOES_DO_ANEXO = [".jpg", ".jpeg", ".png", ".webp", ".pdf"];
const MOTIVO_TIPO = "O anexo precisa ser uma foto (JPG, PNG ou WEBP) ou um PDF. Escolha outro arquivo.";
const MOTIVO_GRANDE = "O anexo passa de 10 MB. Mande uma foto menor ou um PDF mais leve.";

function recusaDoAnexo(arquivo: File): string | null {
  const nome = arquivo.name.toLowerCase();
  if (!EXTENSOES_DO_ANEXO.some((ext) => nome.endsWith(ext))) return MOTIVO_TIPO;
  if (arquivo.size > LIMITE_DO_ANEXO) return MOTIVO_GRANDE;
  return null;
}

function dataBr(iso?: string | null): string {
  if (!iso) return "";
  const [ano, mes, dia] = iso.slice(0, 10).split("-");
  return `${dia}/${mes}/${ano}`;
}

function quando(iso: string): string {
  return new Date(iso).toLocaleString("pt-BR", {
    timeZone: "America/Sao_Paulo",
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

interface Props {
  idAcao: string;
  token: string | null;
  /** A ação que o arrasto no kanban sugeriu; abre o formulário se for permitida. */
  acaoInicial?: ComandoPendencia | null;
  onAtualizada: (pendencia: Pendencia) => void;
}

export function AcoesDaPendencia({ idAcao, token, acaoInicial, onAtualizada }: Props) {
  const [historico, setHistorico] = useState<HistoricoPendencia | null>(null);
  const [acao, setAcao] = useState<ComandoPendencia | null>(null);
  const [anotacao, setAnotacao] = useState("");
  const [prazo, setPrazo] = useState("");
  const [anexo, setAnexo] = useState<File | null>(null);
  const [erroDoAnexo, setErroDoAnexo] = useState<string | null>(null);
  const [erroDoLink, setErroDoLink] = useState<string | null>(null);
  const [busca, setBusca] = useState("");
  const [encontradas, setEncontradas] = useState<Pessoa[]>([]);
  const [responsavel, setResponsavel] = useState<Pessoa | null>(null);
  const ultimaBusca = useRef("");
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  const carregar = useCallback(async () => {
    const res = await fetch(`/api/pendencias/${idAcao}/historico`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    if (!res.ok) return setHistorico({ eventos: [], acoes_permitidas: [] });
    const dados = await res.json();
    setHistorico({
      eventos: dados?.eventos ?? [],
      acoes_permitidas: dados?.acoes_permitidas ?? [],
      pode_abrir_anexos: dados?.pode_abrir_anexos === true,
    });
  }, [idAcao, token]);

  useEffect(() => {
    carregar().catch(() => setHistorico({ eventos: [], acoes_permitidas: [] }));
  }, [carregar]);

  // O arrasto sugere a ação uma vez: o histórico recarregado depois de uma
  // ação não reabre o formulário (senão um clique grava a ação de novo).
  const sugestaoAplicada = useRef<string | null>(null);
  useEffect(() => {
    if (!acaoInicial || !historico) return;
    const chave = `${idAcao}:${acaoInicial}`;
    if (sugestaoAplicada.current === chave) return;
    sugestaoAplicada.current = chave;
    if (historico.acoes_permitidas.includes(acaoInicial)) setAcao(acaoInicial);
  }, [idAcao, acaoInicial, historico]);

  function abrir(comando: ComandoPendencia) {
    setAcao(comando);
    setAnotacao("");
    setPrazo("");
    setAnexo(null);
    setErroDoAnexo(null);
    setBusca("");
    setEncontradas([]);
    setResponsavel(null);
    setErro(null);
  }

  async function buscarPessoa(texto: string) {
    setBusca(texto);
    setResponsavel(null);
    ultimaBusca.current = texto;
    if (texto.trim().length < 2) return setEncontradas([]);
    try {
      const res = await fetch(`/api/participantes?nome=${encodeURIComponent(texto.trim())}&limit=8`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      const dados = res.ok ? await res.json() : [];
      // A resposta de uma busca antiga não cobre a da última letra digitada.
      if (ultimaBusca.current === texto) setEncontradas(Array.isArray(dados) ? dados : []);
    } catch {
      if (ultimaBusca.current === texto) setEncontradas([]);
    }
  }

  function escolher(pessoa: Pessoa) {
    setResponsavel(pessoa);
    setBusca(pessoa.nome_completo);
    setEncontradas([]);
  }

  function escolherAnexo(arquivo: File | null) {
    setAnexo(arquivo);
    setErroDoAnexo(arquivo ? recusaDoAnexo(arquivo) : null);
  }

  const pedePrazo = acao !== null && PEDE_PRAZO.includes(acao);
  const aceitaPrazo = pedePrazo || (acao !== null && PRAZO_OPCIONAL.includes(acao));
  const trocaResponsavel = acao !== null && TROCA_RESPONSAVEL.includes(acao);
  const aceitaAnexo = acao === "concluir";
  const pronto = anotacao.trim().length > 0 && (!pedePrazo || prazo !== "") && !erroDoAnexo;

  function enviar(comando: ComandoPendencia): Promise<Response> {
    const autorizacao: Record<string, string> = token ? { Authorization: `Bearer ${token}` } : {};
    if (comando === "concluir" && anexo) {
      // A conclusão com anexo (issue #1865): anotação e arquivo juntos.
      const corpo = new FormData();
      corpo.append("anotacao", anotacao.trim());
      corpo.append("arquivo", anexo);
      return fetch(`/api/pendencias/${idAcao}/conclusao`, { method: "POST", headers: autorizacao, body: corpo });
    }
    const corpo: Record<string, string> = { comando, anotacao: anotacao.trim() };
    if (aceitaPrazo && prazo !== "") corpo.prazo = prazo;
    if (trocaResponsavel && responsavel) corpo.responsavel_id = responsavel.id;
    return fetch(`/api/pendencias/${idAcao}/acoes`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...autorizacao },
      body: JSON.stringify(corpo),
    });
  }

  async function abrirAnexo(anexoId: number) {
    setErroDoLink(null);
    // A aba abre no clique, antes do fetch: depois dele o navegador a trataria
    // como pop-up (como nos Documentos do Núcleo).
    const aba = window.open("", "_blank");
    if (aba) aba.opener = null;
    try {
      const res = await fetch(`/api/pendencias/${idAcao}/anexos/${anexoId}/link`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      const dados = await res.json().catch(() => ({}));
      if (res.ok && typeof dados.url === "string" && aba) {
        aba.location.href = dados.url;
        return;
      }
      aba?.close();
      setErroDoLink(
        typeof dados.detail === "string" ? dados.detail : "Libere os pop-ups deste site para abrir o anexo."
      );
    } catch {
      aba?.close();
      setErroDoLink("Sem conexão. Tente de novo.");
    }
  }

  async function confirmar() {
    if (!acao || !pronto) return;
    setEnviando(true);
    setErro(null);
    try {
      const res = await enviar(acao);
      const dados = await res.json().catch(() => ({}));
      if (!res.ok) {
        setErro(typeof dados.detail === "string" ? dados.detail : "Não foi possível registrar a ação. Tente de novo.");
        return;
      }
      onAtualizada(dados as Pendencia);
      setAcao(null);
      setAnotacao("");
      setPrazo("");
      setAnexo(null);
      setBusca("");
      setResponsavel(null);
      await carregar();
    } catch {
      setErro("Sem conexão. Tente de novo.");
    } finally {
      setEnviando(false);
    }
  }

  if (!historico) {
    return (
      <div className="flex items-center gap-2 text-xs text-slate-400">
        <Loader2 className="w-4 h-4 animate-spin" /> Carregando o histórico...
      </div>
    );
  }

  return (
    <section className="space-y-4">
      {historico.acoes_permitidas.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {historico.acoes_permitidas.map((comando) => (
            <button
              key={comando}
              type="button"
              onClick={() => abrir(comando)}
              className={`px-3 py-1.5 rounded-lg text-sm font-semibold border transition-colors ${
                acao === comando
                  ? "bg-primary text-white border-primary"
                  : "bg-white text-slate-700 border-slate-200 hover:bg-slate-50"
              }`}
            >
              {ROTULO_DO_BOTAO[comando]}
            </button>
          ))}
        </div>
      )}

      {acao && (
        <div className="p-4 rounded-xl border border-primary/30 bg-primary/5 space-y-3">
          <label className="block">
            <span className="text-xs font-semibold text-slate-600">Anotação (obrigatória)</span>
            <textarea
              value={anotacao}
              onChange={(e) => setAnotacao(e.target.value)}
              placeholder="Conte o que foi feito ou por que esta ação."
              className="mt-1 w-full min-h-[80px] rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm outline-none focus:border-primary focus:ring-1 focus:ring-primary"
            />
          </label>
          {aceitaPrazo && (
            <label className="block">
              <span className="text-xs font-semibold text-slate-600">
                {pedePrazo ? "Prazo novo" : "Prazo novo (opcional)"}
              </span>
              <input
                type="date"
                value={prazo}
                onChange={(e) => setPrazo(e.target.value)}
                className="mt-1 block rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm outline-none focus:border-primary"
              />
            </label>
          )}
          {aceitaAnexo && (
            <label className="block">
              <span className="text-xs font-semibold text-slate-600">Anexo (opcional)</span>
              <input
                type="file"
                aria-label="Anexo (opcional)"
                accept={EXTENSOES_DO_ANEXO.join(",")}
                onChange={(e) => escolherAnexo(e.target.files?.[0] ?? null)}
                className="mt-1 block w-full text-sm text-slate-600 file:mr-3 file:rounded-lg file:border-0 file:bg-white file:px-3 file:py-1.5 file:text-sm file:font-semibold file:text-slate-700"
              />
              <span className="mt-1 block text-xs text-slate-500">
                Foto ou PDF de até 10 MB, como prova da entrega. Não anexe foto com paciente nem documento interno
                sensível.
              </span>
              {erroDoAnexo && (
                <span role="alert" className="mt-1 block text-sm text-red-600">
                  {erroDoAnexo}
                </span>
              )}
            </label>
          )}
          {trocaResponsavel && (
            <div>
              <label className="block">
                <span className="text-xs font-semibold text-slate-600">Responsável novo (opcional)</span>
                <input
                  type="text"
                  value={busca}
                  onChange={(e) => buscarPessoa(e.target.value)}
                  placeholder="Digite o nome da pessoa certa"
                  className="mt-1 block w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm outline-none focus:border-primary"
                />
              </label>
              {encontradas.length > 0 && (
                <ul className="mt-1 rounded-lg border border-slate-200 bg-white divide-y divide-slate-100">
                  {encontradas.map((pessoa) => (
                    <li key={pessoa.id}>
                      <button
                        type="button"
                        onClick={() => escolher(pessoa)}
                        className="w-full text-left px-3 py-2 text-sm hover:bg-slate-50"
                      >
                        {pessoa.nome_completo}
                        {pessoa.cargo ? <span className="text-slate-400">, {pessoa.cargo}</span> : null}
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
          {erro && <p className="text-sm text-red-600">{erro}</p>}
          <div className="flex gap-2">
            <button
              type="button"
              onClick={confirmar}
              disabled={!pronto || enviando}
              className="px-4 py-2 rounded-lg bg-primary text-white text-sm font-semibold disabled:opacity-40 disabled:cursor-not-allowed"
            >
              {enviando ? "Registrando..." : "Confirmar"}
            </button>
            <button
              type="button"
              onClick={() => setAcao(null)}
              className="px-4 py-2 rounded-lg text-sm font-medium text-slate-600 hover:bg-slate-100"
            >
              Voltar
            </button>
          </div>
        </div>
      )}

      <div>
        <div className="flex items-center gap-1.5 mb-2">
          <History className="w-3.5 h-3.5 text-slate-400" />
          <span className="text-xs font-bold text-slate-500 uppercase tracking-wider">Histórico</span>
        </div>
        {erroDoLink && <p className="mb-2 text-sm text-red-600">{erroDoLink}</p>}
        {historico.eventos.length === 0 ? (
          <p className="text-sm text-slate-400">Nenhuma ação registrada ainda.</p>
        ) : (
          <ol aria-label="Histórico da pendência" className="space-y-3">
            {historico.eventos.map((evento) => (
              <li key={evento.id} className="p-3 rounded-xl bg-slate-50 border border-slate-100">
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <span className="text-sm font-semibold text-slate-800">
                    {ROTULO_DO_EVENTO[evento.comando] ?? evento.comando}, por {evento.autor_nome}
                  </span>
                  <span className="text-[11px] text-slate-400">{quando(evento.criado_em)}</span>
                </div>
                {evento.prazo_depois && evento.prazo_depois !== evento.prazo_antes && (
                  <p className="text-xs text-slate-500 mt-1">Prazo novo: {dataBr(evento.prazo_depois)}</p>
                )}
                {evento.responsavel_depois && (
                  <p className="text-xs text-slate-500 mt-1">
                    Responsável novo: {evento.responsavel_depois}
                    {evento.responsavel_antes ? ` (era ${evento.responsavel_antes})` : ""}
                  </p>
                )}
                {evento.conta_atraso && <p className="text-xs text-red-600 mt-1">Depois do vencimento</p>}
                <p className="text-sm text-slate-600 mt-1 whitespace-pre-wrap break-words">{evento.anotacao}</p>
                {evento.anexo && (
                  <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-slate-500">
                    <Paperclip className="w-3.5 h-3.5" />
                    <span className="break-all">Anexo: {evento.anexo.nome}</span>
                    {historico.pode_abrir_anexos ? (
                      <button
                        type="button"
                        onClick={() => abrirAnexo(evento.anexo!.id)}
                        className="px-2 py-1 rounded-md border border-slate-200 bg-white font-semibold text-slate-700 hover:bg-slate-50"
                      >
                        Abrir anexo
                      </button>
                    ) : (
                      <span>(abrem o responsável, o facilitador e quem administra o aplicativo)</span>
                    )}
                  </div>
                )}
              </li>
            ))}
          </ol>
        )}
      </div>
    </section>
  );
}
