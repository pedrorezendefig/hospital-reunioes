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
 *
 * A issue #483 (PRD #469, RN-59) reorganizou a tela na ordem que faz a resposta
 * sair rápido: gravidade, prazo, protocolo e setor, os três blocos de leitura
 * do ADR 0041, o campo único e os dois botões da RN-62. Quem abre este link é o
 * usuário menos treinado do módulo, e a hierarquia é o que substitui o
 * treinamento. Tudo que a Ouvidoria preencheu aparece como leitura.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { useParams } from "next/navigation";
import {
  AlertCircle,
  CalendarClock,
  CheckCircle2,
  Clock,
  Loader2,
  Lock,
  Paperclip,
  X,
} from "lucide-react";
import { Logo } from "@/components/ui/Logo";
import {
  blocosDoCaso,
  cartaoDeProrrogacaoTemConteudo,
  classeDoBloco,
  mensagemDoPortal,
  MINIMO_DA_RESPOSTA,
  montarFormularioDeResposta,
  pedidoDeProrrogacaoValido,
  respostaDoSetorValida,
  rotuloDePrazoDoPortal,
  situacaoDoPedido,
  type CasoDoPortal,
} from "@/lib/ouvidoria/setor";
import { CLASSE_GRAVIDADE, LABEL_GRAVIDADE, type Gravidade } from "@/lib/ouvidoria/validacao";

/**
 * O que o responsável lê antes de escrever, no lugar de um treinamento que ele
 * não teve. O exemplo é real de propósito: resposta sem "o que", "quando" e
 * "quem" volta para a área como devolução por insuficiência.
 */
const ORIENTACAO_DA_RESPOSTA =
  `Conte o que foi FEITO para corrigir, com pelo menos ${MINIMO_DA_RESPOSTA} caracteres. ` +
  "A apuração do motivo fica com a Ouvidoria.";

const EXEMPLO_DA_RESPOSTA =
  "Ex.: Conversamos com a equipe da recepção em 02/09 e passamos a abrir o segundo guichê " +
  "às 7h. A coordenadora Ana Paula acompanha a fila diariamente.";

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
  // Uma condição só para o parágrafo do motivo e para o `aria-describedby` do
  // botão: se as duas divergirem, o botão aponta para um id que não existe.
  const motivoDaProrrogacaoAVista = Boolean(
    prorrogacao && !prorrogacao.permitida && !prorrogacao.pedido && prorrogacao.motivo
  );

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
        {/* 1 a 3 da RN-59: gravidade, prazo, e a linha que confirma que o caso
            é meu. Nesta ordem porque é ela que faz a leitura render: o peso do
            caso e a urgência chegam antes de qualquer texto. */}
        <div
          data-testid="cabecalho-do-caso"
          className="bg-white rounded-2xl border border-slate-200 shadow-premium overflow-hidden"
        >
          <div
            data-testid="faixa-de-gravidade"
            className={`px-6 py-2.5 border-b text-xs font-bold uppercase tracking-wide ${
              CLASSE_GRAVIDADE[caso.gravidade as Gravidade] ??
              "bg-slate-100 text-slate-600 border-slate-200"
            }`}
          >
            Gravidade {LABEL_GRAVIDADE[caso.gravidade as Gravidade] ?? caso.gravidade ?? "a definir"}
          </div>

          <div className="p-6">
            {/* A identidade do hospital não é um dos nove elementos da RN-59,
                mas a página é pública e aberta a partir de um email: sem ela,
                quem recebe o link não tem como saber que a tela é mesmo do
                hospital. Fica numa linha só, entre a faixa e o prazo, para
                custar o mínimo de altura no celular. */}
            <div data-testid="identidade-do-hospital" className="flex items-center gap-2 mb-3">
              <Logo />
              <h1 className="text-sm font-bold text-slate-900">Demanda da Ouvidoria</h1>
            </div>

            <div
              data-testid="prazo-regressivo"
              className={`flex items-start gap-2 rounded-xl border px-3 py-2.5 ${
                caso.prazo_estourado
                  ? "bg-red-50 border-red-200 text-red-700"
                  : "bg-slate-50 border-slate-200 text-slate-700"
              }`}
            >
              <Clock className="w-4 h-4 mt-0.5 shrink-0" />
              {/* A frase sai da tela quando o calendário de feriados não pôde
                  ser lido: prazo em dias úteis contado sem os feriados sai mais
                  curto do que é, e aqui está quem tem que cumprir (issue #449). */}
              <p className="text-sm font-semibold">
                Prazo de resposta: {rotuloDePrazoDoPortal(caso)}
              </p>
            </div>

            <div
              data-testid="linha-secundaria"
              className="mt-3 flex flex-wrap items-center gap-x-2 gap-y-1 text-sm text-slate-500"
            >
              <span className="font-mono font-bold text-slate-700">{caso.protocolo}</span>
              <span className="text-slate-300">|</span>
              <span className="font-semibold text-slate-700">{caso.setor}</span>
              <span className="text-slate-300">|</span>
              <span>{caso.categoria}</span>
            </div>

            <dl className="mt-3 flex justify-between gap-3 text-sm">
              <dt className="text-slate-500">Quem manifestou</dt>
              <dd className="font-semibold text-slate-800 text-right">
                {caso.identificacao ?? "Sem identificação"}
              </dd>
            </dl>
          </div>
        </div>

        {/* 4 a 6 da RN-59: os três blocos do ADR 0041, nunca fundidos nem com a
            mesma formatação (RN-60). A tela mostra o que o servidor montou: no
            caso protegido a lista chega com um bloco só, e o aviso explica por
            quê. Quem distingue as variantes lê a chave, nunca a posição. */}
        <div
          data-testid="leitura-do-caso"
          className="bg-white rounded-2xl border border-slate-200 shadow-premium p-6 space-y-4"
        >
          {caso.aviso && (
            <p
              data-testid="aviso-do-caso"
              className="flex items-start gap-2 text-sm text-amber-800 bg-amber-50 border border-amber-200 rounded-xl px-3 py-2.5 leading-relaxed"
            >
              <Lock className="w-4 h-4 mt-0.5 shrink-0" />
              <span>{caso.aviso}</span>
            </p>
          )}

          {blocosDoCaso(caso).map((bloco) => (
            <div key={bloco.chave} className="space-y-1.5">
              <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">
                {bloco.rotulo}
              </p>
              <p data-testid={`bloco-${bloco.chave}`} className={classeDoBloco(bloco.chave)}>
                {bloco.texto}
              </p>
            </div>
          ))}
        </div>

        {caso.aceita_resposta ? (
          <form
            onSubmit={handleEnviar}
            className="bg-white rounded-2xl border border-slate-200 shadow-premium p-6 space-y-4"
          >
            {/* 7 da RN-59: o campo único. O rótulo é a pergunta que o
                responsável tem que responder, a orientação é fixa e o
                placeholder traz um exemplo real (RN-61). */}
            <div className="space-y-1.5">
              <label
                htmlFor="resposta"
                className="block text-sm font-bold uppercase tracking-wide text-slate-700"
              >
                O que foi feito
              </label>
              <p data-testid="orientacao-da-resposta" className="text-xs text-slate-500 leading-relaxed">
                {ORIENTACAO_DA_RESPOSTA}
              </p>
              <textarea
                id="resposta"
                value={resposta}
                onChange={(e) => setResposta(e.target.value)}
                rows={6}
                required
                placeholder={EXEMPLO_DA_RESPOSTA}
                className="w-full rounded-xl border border-slate-200 px-3 py-2.5 text-base text-slate-800 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary resize-y"
              />
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
              Responder à Ouvidoria
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

          {/* O motivo vem ANTES do botão, e ligado a ele pelo aria-describedby:
              `disabled` tira o botão da ordem de foco, então quem navega por
              teclado nunca chegaria nele para ouvir a explicação, e um motivo
              depois do botão é lido tarde demais por quem já desistiu. */}
          {motivoDaProrrogacaoAVista && (
            <p id="motivo-da-prorrogacao" className="text-xs text-slate-500 leading-relaxed">
              {prorrogacao?.motivo}
            </p>
          )}

          {/* 9 da RN-59, segundo botão: ele fica na tela mesmo quando o pedido
              não cabe mais, desabilitado e com o motivo acima. Sumir com o
              botão deixaria o responsável procurando um recurso que existe e
              não está disponível (issue #483, RN-62). */}
          {!pedindoPrazo && (
            <button
              type="button"
              onClick={() => setPedindoPrazo(true)}
              disabled={!prorrogacao?.permitida}
              aria-describedby={motivoDaProrrogacaoAVista ? "motivo-da-prorrogacao" : undefined}
              className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm font-semibold bg-slate-100 text-slate-700 hover:bg-slate-200 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              <CalendarClock className="w-4 h-4" />
              Solicitar prorrogação de prazo
            </button>
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
