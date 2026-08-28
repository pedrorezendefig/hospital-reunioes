"use client";

/**
 * Portal do setor por link tokenizado (issue #326, ADR 0034 decisão 4).
 *
 * O titular chega pelo link do email de acionamento, sem senha: o token opaco
 * de uso único é a credencial, no padrão do Aceite interno. A página mostra o
 * extrato necessário do caso (sem identificação quando sigiloso), o prazo em
 * linguagem natural, e colhe o que o setor FEZ para corrigir, com anexos
 * opcionais. Mobile-first: o responsável responde do celular.
 *
 * Desde a issue #333 a mesma página pede prorrogação de prazo, com as regras
 * à vista: uma vez só, antes do vencimento, com justificativa.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { useParams } from "next/navigation";
import {
  AlertCircle,
  CalendarClock,
  CheckCircle2,
  Clock,
  Loader2,
  Megaphone,
  Paperclip,
  X,
} from "lucide-react";
import { Logo } from "@/components/ui/Logo";
import {
  cartaoDeProrrogacaoTemConteudo,
  mensagemDoPortal,
  montarFormularioDeResposta,
  pedidoDeProrrogacaoValido,
  respostaDoSetorValida,
  situacaoDoPedido,
  type CasoDoPortal,
} from "@/lib/ouvidoria/setor";

export default function PortalDoSetorPage() {
  const params = useParams();
  const token = params.token as string;

  const [caso, setCaso] = useState<CasoDoPortal | null>(null);
  const [loading, setLoading] = useState(true);
  const [erro, setErro] = useState<string | null>(null);
  const [erroDoEnvio, setErroDoEnvio] = useState<string | null>(null);
  const [resposta, setResposta] = useState("");
  const [arquivos, setArquivos] = useState<File[]>([]);
  const [enviando, setEnviando] = useState(false);
  const [recibo, setRecibo] = useState<{
    protocolo: string;
    anexosEnviados: number;
    anexosGravados: number;
  } | null>(null);
  const inputArquivos = useRef<HTMLInputElement>(null);
  // Prorrogação (issue #333): o formulário só abre quando o responsável
  // decide pedir, para a ação principal continuar sendo responder.
  const [pedindoPrazo, setPedindoPrazo] = useState(false);
  const [justificativa, setJustificativa] = useState("");
  const [diasPedidos, setDiasPedidos] = useState(5);
  const [enviandoPedido, setEnviandoPedido] = useState(false);
  const [erroDoPedido, setErroDoPedido] = useState<string | null>(null);

  const carregar = useCallback(async () => {
    try {
      const res = await fetch(`/api/ouvidoria-setor/${encodeURIComponent(token)}`);
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        setErro(mensagemDoPortal(res.status, body.detail));
        return;
      }
      setCaso((await res.json()) as CasoDoPortal);
    } catch {
      setErro("Não foi possível carregar este link agora. Tente novamente.");
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    void carregar();
  }, [carregar]);

  async function handleEnviar(e: React.FormEvent) {
    e.preventDefault();
    if (!caso || !respostaDoSetorValida(resposta)) return;
    setEnviando(true);
    setErroDoEnvio(null);
    try {
      const res = await fetch(`/api/ouvidoria-setor/${encodeURIComponent(token)}/responder`, {
        method: "POST",
        body: montarFormularioDeResposta(resposta, arquivos),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        setErroDoEnvio(mensagemDoPortal(res.status, body.detail));
        return;
      }
      const corpo = await res.json().catch(() => ({}));
      setRecibo({
        protocolo: caso.protocolo,
        anexosEnviados: arquivos.length,
        anexosGravados: typeof corpo.anexos_gravados === "number" ? corpo.anexos_gravados : arquivos.length,
      });
    } catch {
      setErroDoEnvio("Não foi possível enviar a resposta agora. Tente novamente.");
    } finally {
      setEnviando(false);
    }
  }

  function removerArquivo(indice: number) {
    setArquivos((atuais) => atuais.filter((_, i) => i !== indice));
  }

  /**
   * O pedido de mais prazo. As três regras (uma vez, antes do vencimento, com
   * justificativa) são aplicadas pelo backend, que recusa sozinho; a tela
   * recarrega o caso depois para mostrar o estado novo em vez de adivinhá-lo.
   */
  async function handlePedirPrazo(e: React.FormEvent) {
    e.preventDefault();
    if (!caso) return;
    if (!pedidoDeProrrogacaoValido(justificativa, diasPedidos, maxDiasDaProrrogacao)) return;
    setEnviandoPedido(true);
    setErroDoPedido(null);
    try {
      const res = await fetch(`/api/ouvidoria-setor/${encodeURIComponent(token)}/prorrogacao`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ justificativa: justificativa.trim(), dias_uteis: diasPedidos }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        setErroDoPedido(mensagemDoPortal(res.status, body.detail));
        return;
      }
      setPedindoPrazo(false);
      setJustificativa("");
      await carregar();
    } catch {
      setErroDoPedido("Não foi possível enviar o pedido agora. Tente novamente.");
    } finally {
      setEnviandoPedido(false);
    }
  }

  if (loading) {
    return (
      <main className="min-h-screen bg-slate-50 flex items-center justify-center p-4">
        <Loader2 className="w-8 h-8 text-primary animate-spin" />
      </main>
    );
  }

  if (erro || !caso) {
    return (
      <main className="min-h-screen bg-slate-50 flex items-center justify-center p-4">
        <div className="w-full max-w-lg bg-white rounded-2xl border border-slate-200 shadow-premium p-8 text-center">
          <div className="flex justify-center mb-6">
            <Logo />
          </div>
          <AlertCircle className="w-10 h-10 text-amber-500 mx-auto mb-4" />
          <h1 className="text-lg font-bold text-slate-900">Este link não abre o caso</h1>
          <p className="text-slate-600 text-sm leading-relaxed mt-3">{erro}</p>
          <p className="text-slate-400 text-xs leading-relaxed mt-4">
            Se você é responsável de setor e precisa responder uma demanda, fale com a Ouvidoria
            para receber um novo link.
          </p>
        </div>
      </main>
    );
  }

  // O bloco de prorrogação é lido com guarda: a página é pública, aberta do
  // celular por gente de fora, e um backend uma versão atrás (ou uma resposta
  // em cache) não pode deixar o titular numa tela em branco. O `caso` já está
  // garantido pelo early return acima, então aqui não cabe `?.` nele.
  const prorrogacao = caso.prorrogacao;
  const regrasDaProrrogacao = prorrogacao?.regras ?? [];
  const maxDiasDaProrrogacao = prorrogacao?.max_dias_uteis ?? 30;

  if (recibo) {
    return (
      <main className="min-h-screen bg-slate-50 flex items-center justify-center p-4">
        <div className="w-full max-w-lg bg-white rounded-2xl border border-emerald-200 shadow-premium p-8 text-center space-y-4">
          <div className="flex justify-center">
            <Logo />
          </div>
          <CheckCircle2 className="w-12 h-12 text-emerald-500 mx-auto" />
          <div className="space-y-1">
            <p className="text-slate-600 text-sm">Resposta registrada na manifestação</p>
            <p className="text-2xl font-bold tracking-tight text-slate-900 tabular-nums">
              {recibo.protocolo}
            </p>
          </div>
          {recibo.anexosGravados < recibo.anexosEnviados && (
            <p className="flex items-start gap-2 text-left text-sm text-amber-700 bg-amber-50 border border-amber-200 rounded-xl px-3 py-2.5">
              <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
              <span>
                A resposta entrou, mas {recibo.anexosGravados} de {recibo.anexosEnviados} anexos
                foram gravados. Envie os demais diretamente à Ouvidoria, citando o protocolo.
              </span>
            </p>
          )}
          <p className="text-sm text-slate-500">
            A Ouvidoria vai conferir a resposta e encerrar o caso. Este link era de uso único e não
            abre mais.
          </p>
        </div>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-slate-50 py-6 px-4">
      <div className="w-full max-w-lg mx-auto space-y-4">
        <div className="bg-white rounded-2xl border border-slate-200 shadow-premium p-6">
          <div className="flex justify-center mb-5">
            <Logo />
          </div>
          <div className="flex items-center gap-3">
            <div className="w-11 h-11 rounded-xl bg-primary/10 flex items-center justify-center shrink-0">
              <Megaphone className="w-5.5 h-5.5 text-primary" strokeWidth={1.5} />
            </div>
            <div>
              <h1 className="text-lg font-bold text-slate-900 leading-tight">
                Demanda da Ouvidoria
              </h1>
              <p className="font-mono text-sm font-bold text-slate-700">{caso.protocolo}</p>
            </div>
          </div>

          <dl className="mt-5 space-y-3 text-sm">
            <div className="flex justify-between gap-3">
              <dt className="text-slate-500">Setor acionado</dt>
              <dd className="font-semibold text-slate-800 text-right">{caso.setor}</dd>
            </div>
            <div className="flex justify-between gap-3">
              <dt className="text-slate-500">Categoria</dt>
              <dd className="font-semibold text-slate-800 text-right">{caso.categoria}</dd>
            </div>
            <div className="flex justify-between gap-3">
              <dt className="text-slate-500">Quem manifestou</dt>
              <dd className="font-semibold text-slate-800 text-right">
                {caso.identificacao ?? "Sem identificação"}
              </dd>
            </div>
          </dl>

          <div
            className={`mt-4 flex items-start gap-2 rounded-xl border px-3 py-2.5 ${
              caso.prazo_estourado
                ? "bg-red-50 border-red-200 text-red-700"
                : "bg-slate-50 border-slate-200 text-slate-700"
            }`}
          >
            <Clock className="w-4 h-4 mt-0.5 shrink-0" />
            <p className="text-sm font-semibold">Prazo de resposta: {caso.rotulo_prazo}</p>
          </div>

          <div className="mt-4">
            <p className="text-xs font-semibold uppercase tracking-wide text-slate-400 mb-1.5">
              O que aconteceu
            </p>
            <p className="text-sm text-slate-700 leading-relaxed whitespace-pre-wrap rounded-xl bg-slate-50 border border-slate-200 px-3 py-2.5">
              {caso.extrato}
            </p>
          </div>
        </div>

        {caso.aceita_resposta ? (
          <form
            onSubmit={handleEnviar}
            className="bg-white rounded-2xl border border-slate-200 shadow-premium p-6 space-y-4"
          >
            <div className="space-y-1.5">
              <label htmlFor="resposta" className="block text-sm font-semibold text-slate-700">
                O que o setor fez para corrigir?
              </label>
              <textarea
                id="resposta"
                value={resposta}
                onChange={(e) => setResposta(e.target.value)}
                rows={6}
                required
                placeholder="Descreva as providências tomadas: o que foi feito, quando e por quem."
                className="w-full rounded-xl border border-slate-200 px-3 py-2.5 text-base text-slate-800 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary resize-y"
              />
              <p className="text-xs text-slate-400">
                Conte o que foi FEITO. A apuração do motivo fica com a Ouvidoria.
              </p>
            </div>

            <div className="space-y-2">
              <button
                type="button"
                onClick={() => inputArquivos.current?.click()}
                className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm font-semibold bg-slate-100 text-slate-700 hover:bg-slate-200 transition-colors"
              >
                <Paperclip className="w-4 h-4" />
                Anexar arquivos (opcional)
              </button>
              <input
                ref={inputArquivos}
                type="file"
                multiple
                className="hidden"
                onChange={(e) => {
                  setArquivos((atuais) => [...atuais, ...Array.from(e.target.files ?? [])]);
                  e.target.value = "";
                }}
              />
              {arquivos.length > 0 && (
                <ul className="space-y-1">
                  {arquivos.map((arquivo, i) => (
                    <li
                      key={`${arquivo.name}-${i}`}
                      className="flex items-center justify-between gap-2 rounded-lg bg-slate-50 border border-slate-200 px-3 py-1.5 text-sm text-slate-700"
                    >
                      <span className="truncate">{arquivo.name}</span>
                      <button
                        type="button"
                        onClick={() => removerArquivo(i)}
                        aria-label={`Remover ${arquivo.name}`}
                        className="text-slate-400 hover:text-slate-600 shrink-0"
                      >
                        <X className="w-4 h-4" />
                      </button>
                    </li>
                  ))}
                </ul>
              )}
              <p className="text-xs text-slate-400">
                Imagem, PDF, áudio ou documento, até 20 MB por arquivo.
              </p>
            </div>

            {erroDoEnvio && (
              <p className="flex items-start gap-2 text-sm text-red-600">
                <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
                {erroDoEnvio}
              </p>
            )}

            <button
              type="submit"
              disabled={enviando || !respostaDoSetorValida(resposta)}
              className="w-full inline-flex items-center justify-center gap-2 px-4 py-3 rounded-xl text-sm font-semibold bg-primary text-white hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {enviando && <Loader2 className="w-4 h-4 animate-spin" />}
              Enviar resposta à Ouvidoria
            </button>
          </form>
        ) : (
          <div className="bg-white rounded-2xl border border-slate-200 shadow-premium p-6 text-center">
            <p className="text-sm text-slate-600">
              Este caso não está mais aguardando resposta do setor. Se precisar complementar,
              fale diretamente com a Ouvidoria citando o protocolo acima.
            </p>
          </div>
        )}

        {/* Prorrogação de prazo (issue #333). As regras ficam à vista mesmo
            quando o pedido não cabe mais: contar com um recurso que não existe
            é pior do que não ter o recurso. Sem nada disso, o cartão não
            aparece: vazio ele era só título e lista sem itens (issue #375). */}
        {cartaoDeProrrogacaoTemConteudo(prorrogacao) && (
        <div className="bg-white rounded-2xl border border-slate-200 shadow-premium p-6 space-y-3">
          <div className="flex items-center gap-2">
            <CalendarClock className="w-4 h-4 text-slate-400 shrink-0" />
            <h2 className="text-sm font-bold text-slate-800">Precisa de mais prazo?</h2>
          </div>

          <ul className="space-y-1.5">
            {regrasDaProrrogacao.map((regra) => (
              <li key={regra} className="flex items-start gap-2 text-xs text-slate-500 leading-relaxed">
                <span className="mt-1.5 w-1 h-1 rounded-full bg-slate-300 shrink-0" />
                {regra}
              </li>
            ))}
          </ul>

          {prorrogacao?.pedido && (
            <div className="rounded-xl bg-slate-50 border border-slate-200 px-3 py-2.5 space-y-1">
              <p className="text-sm font-semibold text-slate-700">
                {situacaoDoPedido(prorrogacao.pedido)}
              </p>
              <p className="text-xs text-slate-500 leading-relaxed">
                Pedido de {prorrogacao.pedido.dias_uteis_pedidos} dia(s) útil(eis) por{" "}
                {prorrogacao.pedido.solicitante_nome}.
              </p>
              {prorrogacao.pedido.decisao_justificativa && (
                <p className="text-xs text-slate-500 leading-relaxed">
                  Ouvidoria: {prorrogacao.pedido.decisao_justificativa}
                </p>
              )}
            </div>
          )}

          {prorrogacao?.permitida && !pedindoPrazo && (
            <button
              type="button"
              onClick={() => setPedindoPrazo(true)}
              className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm font-semibold bg-slate-100 text-slate-700 hover:bg-slate-200 transition-colors"
            >
              <CalendarClock className="w-4 h-4" />
              Pedir prorrogação de prazo
            </button>
          )}

          {prorrogacao && !prorrogacao.permitida && !prorrogacao.pedido && prorrogacao.motivo && (
            <p className="text-xs text-slate-500 leading-relaxed">{prorrogacao.motivo}</p>
          )}

          {prorrogacao?.permitida && pedindoPrazo && (
            <form onSubmit={handlePedirPrazo} className="space-y-3 pt-1">
              <div className="space-y-1.5">
                <label htmlFor="dias" className="block text-sm font-semibold text-slate-700">
                  Quantos dias úteis a mais?
                </label>
                <input
                  id="dias"
                  type="number"
                  min={1}
                  max={maxDiasDaProrrogacao}
                  value={diasPedidos}
                  onChange={(e) => setDiasPedidos(Number(e.target.value))}
                  className="w-28 rounded-xl border border-slate-200 px-3 py-2.5 text-base text-slate-800 focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary"
                />
              </div>

              <div className="space-y-1.5">
                <label htmlFor="justificativa" className="block text-sm font-semibold text-slate-700">
                  Por que o setor precisa de mais prazo?
                </label>
                <textarea
                  id="justificativa"
                  value={justificativa}
                  onChange={(e) => setJustificativa(e.target.value)}
                  rows={4}
                  required
                  placeholder="Explique o que impede a resposta dentro do prazo atual."
                  className="w-full rounded-xl border border-slate-200 px-3 py-2.5 text-base text-slate-800 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary resize-y"
                />
                <p className="text-xs text-slate-400">
                  A Ouvidoria lê esta justificativa para aprovar ou negar o pedido.
                </p>
              </div>

              {erroDoPedido && (
                <p className="flex items-start gap-2 text-sm text-red-600">
                  <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
                  {erroDoPedido}
                </p>
              )}

              <div className="flex gap-2">
                <button
                  type="submit"
                  disabled={
                    enviandoPedido ||
                    !pedidoDeProrrogacaoValido(justificativa, diasPedidos, maxDiasDaProrrogacao)
                  }
                  className="inline-flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl text-sm font-semibold bg-primary text-white hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                >
                  {enviandoPedido && <Loader2 className="w-4 h-4 animate-spin" />}
                  Enviar pedido
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setPedindoPrazo(false);
                    setErroDoPedido(null);
                  }}
                  className="px-4 py-2.5 rounded-xl text-sm font-semibold text-slate-600 hover:bg-slate-100 transition-colors"
                >
                  Cancelar
                </button>
              </div>
            </form>
          )}
        </div>
        )}
      </div>
    </main>
  );
}
