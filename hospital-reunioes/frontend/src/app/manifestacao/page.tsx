"use client";

/**
 * Formulário público da Ouvidoria (issue #323, ADR 0034 decisão 9).
 *
 * Sem login. É a página que o QR setorial abre (com o setor pré-preenchido pelo
 * servidor) e a que o site do hospital linka. Feita para o celular primeiro:
 * o caso de uso principal é a pessoa apontando a câmera para o cartaz.
 */

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { AlertCircle, CheckCircle2, Loader2, MapPin, Send } from "lucide-react";
import { Logo } from "@/components/ui/Logo";
import {
  NATUREZAS_INFORMADAS,
  montarEnvio,
  relatoEstaVazio,
  type NaturezaInformada,
} from "@/lib/ouvidoria/publico";

interface Recibo {
  protocolo: string;
  data_abertura: string;
  prazo_resposta: string;
  status: string;
}

const LIMITE_RELATO = 10000;

function formatarData(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(`${iso}T12:00:00`);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString("pt-BR", {
    day: "2-digit",
    month: "long",
    year: "numeric",
  });
}

function FormularioPublico() {
  const searchParams = useSearchParams();
  // A URL traz só o código do cartaz, e nada mais (ADR 0036, decisão 10). O que
  // a página EXIBE vem do servidor, que resolve o código contra o cadastro: não
  // há mais texto de origem vindo do cliente para renderizar, que é o que fecha
  // o item 9 da #375 em definitivo.
  const codigoDoCartaz = searchParams.get("p");
  const [setorExibido, setSetorExibido] = useState<string | null>(null);

  useEffect(() => {
    // Sem código na URL não há o que perguntar, e a ida ao servidor seria gasto
    // puro: a maioria absoluta chega pelo link do site.
    if (!codigoDoCartaz) return;
    let vivo = true;
    fetch(`/api/ouvidoria/publico/pontos/${encodeURIComponent(codigoDoCartaz)}`)
      .then((res) => (res.ok ? res.json() : null))
      .then((cartaz) => {
        // Cartaz aposentado ou código que ninguém cadastrou: a página não
        // mostra origem nenhuma, e o formulário segue igual.
        if (vivo) setSetorExibido(cartaz?.setor ?? null);
      })
      // Falha aqui só tira o chip de origem da tela. O formulário, que é o
      // que a pessoa veio fazer, continua de pé.
      .catch(() => {
        if (vivo) setSetorExibido(null);
      });
    return () => {
      vivo = false;
    };
  }, [codigoDoCartaz]);

  const [relato, setRelato] = useState("");
  // A natureza que a pessoa marcou (issue #473, RN-88). Começa sem escolha e
  // pode voltar a ficar sem: é sugestão dela, não obrigação.
  const [natureza, setNatureza] = useState<NaturezaInformada | null>(null);
  const [nome, setNome] = useState("");
  const [contato, setContato] = useState("");
  const [anonimo, setAnonimo] = useState(false);
  const [armadilha, setArmadilha] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [recibo, setRecibo] = useState<Recibo | null>(null);

  const vazio = relatoEstaVazio(relato);

  async function handleEnviar(evento: React.FormEvent) {
    evento.preventDefault();
    if (vazio || enviando) return;
    setEnviando(true);
    setErro(null);
    try {
      const res = await fetch("/api/ouvidoria/publico/manifestacoes", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ...montarEnvio({ relato, nome, contato, anonimo, p: codigoDoCartaz, natureza }),
          assunto_alternativo: armadilha,
        }),
      });
      if (res.status === 429) {
        setErro(
          "Recebemos muitos envios deste aparelho agora há pouco. Aguarde um minuto e tente de novo."
        );
        return;
      }
      if (res.status === 422 || res.status === 400) {
        // Recusa definitiva: pedir para "tentar de novo em instantes" mandaria
        // a pessoa repetir algo que nunca vai passar.
        setErro(
          "Não conseguimos ler sua manifestação. Reescreva o relato com palavras e envie de novo."
        );
        return;
      }
      if (!res.ok) {
        setErro(
          "Não foi possível registrar sua manifestação agora. Tente novamente em instantes."
        );
        return;
      }
      setRecibo((await res.json()) as Recibo);
    } catch {
      setErro(
        "Não foi possível falar com o hospital agora. Verifique sua conexão e tente de novo."
      );
    } finally {
      setEnviando(false);
    }
  }

  if (recibo) {
    return (
      <div className="bg-white rounded-2xl border border-emerald-200 shadow-premium px-5 py-8 text-center space-y-4">
        <CheckCircle2 className="w-12 h-12 text-emerald-500 mx-auto" />
        <div className="space-y-1">
          <p className="text-slate-600 text-sm">
            Sua manifestação foi registrada. Guarde o número do protocolo:
          </p>
          <p className="text-3xl font-bold tracking-tight text-slate-900 tabular-nums">
            {recibo.protocolo}
          </p>
        </div>
        <p className="text-sm text-slate-500">
          Registrada em {formatarData(recibo.data_abertura)}. A Ouvidoria vai
          analisar e encaminhar ao setor responsável.
        </p>
      </div>
    );
  }

  return (
    <form
      onSubmit={handleEnviar}
      className="bg-white rounded-2xl border border-border shadow-premium px-5 py-6 space-y-5"
    >
      {setorExibido && (
        <div className="flex items-start gap-2 rounded-xl bg-slate-50 border border-border px-3 py-2.5">
          <MapPin className="w-4 h-4 text-slate-500 mt-0.5 shrink-0" />
          <p className="text-sm text-slate-600">
            Você leu o QR de{" "}
            <span className="font-semibold text-slate-800">{setorExibido}</span>.
            <span className="block text-xs text-slate-400">
              A Ouvidoria define o setor responsável depois de ler seu relato.
            </span>
          </p>
        </div>
      )}

      {/*
        As quatro naturezas do cartaz (RN-88, ADR 0040 decisão 3). Igual
        destaque para as quatro, com o elogio na frente: quem chega achando que
        ouvidoria é só queixa vê logo que o canal também serve para agradecer.
        A escolha é sugestão de quem manifesta, e a Ouvidoria classifica depois.
      */}
      <div className="space-y-1.5">
        <p id="rotulo-natureza" className="block text-sm font-semibold text-slate-700">
          O que você quer registrar?{" "}
          <span className="font-normal text-slate-400">(opcional)</span>
        </p>
        <div
          role="group"
          aria-labelledby="rotulo-natureza"
          className="grid grid-cols-2 gap-2"
        >
          {NATUREZAS_INFORMADAS.map(({ valor, rotulo }) => {
            const escolhido = natureza === valor;
            return (
              <button
                key={valor}
                type="button"
                aria-pressed={escolhido}
                // Clicar no que já está marcado desmarca: quem tocou por engano
                // não fica preso a uma natureza que não é a dele.
                onClick={() => setNatureza(escolhido ? null : valor)}
                className={`rounded-xl border px-3 py-4 text-base font-semibold transition-colors ${
                  escolhido
                    ? "border-primary bg-primary/10 text-primary"
                    : "border-border bg-white text-slate-600 hover:border-primary/40"
                }`}
              >
                {rotulo}
              </button>
            );
          })}
        </div>
        <p className="text-xs text-slate-400">
          Não precisa escolher. A Ouvidoria confirma isso ao ler seu relato.
        </p>
      </div>

      <div className="space-y-1.5">
        <label htmlFor="relato" className="block text-sm font-semibold text-slate-700">
          O que aconteceu?
        </label>
        <textarea
          id="relato"
          value={relato}
          onChange={(e) => setRelato(e.target.value)}
          maxLength={LIMITE_RELATO}
          rows={7}
          required
          autoFocus
          placeholder="Conte com suas palavras o que você quer registrar: uma reclamação, um elogio ou uma sugestão."
          className="w-full rounded-xl border border-border px-3 py-2.5 text-base text-slate-800 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary resize-y"
        />
        <p className="text-xs text-slate-400 text-right tabular-nums">
          {relato.length} / {LIMITE_RELATO}
        </p>
      </div>

      <label className="flex items-start gap-2.5 cursor-pointer select-none">
        <input
          type="checkbox"
          checked={anonimo}
          onChange={(e) => setAnonimo(e.target.checked)}
          className="mt-0.5 w-4 h-4 rounded border-border text-primary focus:ring-primary/30"
        />
        <span className="text-sm text-slate-600">
          Quero registrar de forma anônima.
          <span className="block text-xs text-slate-400">
            Sem identificação não conseguimos dar retorno individual a você.
          </span>
        </span>
      </label>

      {!anonimo && (
        <div className="space-y-4">
          <div className="space-y-1.5">
            <label htmlFor="nome" className="block text-sm font-semibold text-slate-700">
              Seu nome <span className="font-normal text-slate-400">(opcional)</span>
            </label>
            <input
              id="nome"
              type="text"
              value={nome}
              onChange={(e) => setNome(e.target.value)}
              maxLength={200}
              autoComplete="name"
              className="w-full rounded-xl border border-border px-3 py-2.5 text-base text-slate-800 focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary"
            />
          </div>
          <div className="space-y-1.5">
            <label htmlFor="contato" className="block text-sm font-semibold text-slate-700">
              Telefone ou email <span className="font-normal text-slate-400">(opcional)</span>
            </label>
            <input
              id="contato"
              type="text"
              value={contato}
              onChange={(e) => setContato(e.target.value)}
              maxLength={200}
              inputMode="email"
              autoComplete="email"
              className="w-full rounded-xl border border-border px-3 py-2.5 text-base text-slate-800 focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary"
            />
            <p className="text-xs text-slate-400">
              É por aqui que a Ouvidoria fala com você sobre este caso.
            </p>
          </div>
        </div>
      )}

      {/* Armadilha para robô: pessoa nenhuma vê nem alcança este campo. */}
      <div aria-hidden="true" className="hidden">
        <label htmlFor="assunto-alternativo">Não preencha este campo</label>
        <input
          id="assunto-alternativo"
          type="text"
          tabIndex={-1}
          autoComplete="off"
          value={armadilha}
          onChange={(e) => setArmadilha(e.target.value)}
        />
      </div>

      {erro && (
        <div className="flex items-start gap-2 rounded-xl bg-amber-50 border border-amber-200 px-3 py-2.5">
          <AlertCircle className="w-4 h-4 text-amber-500 mt-0.5 shrink-0" />
          <p className="text-sm text-amber-800">{erro}</p>
        </div>
      )}

      <button
        type="submit"
        disabled={vazio || enviando}
        className="w-full flex items-center justify-center gap-2 rounded-xl bg-primary px-4 py-3 text-base font-semibold text-white shadow-premium transition-colors hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed"
      >
        {enviando ? (
          <>
            <Loader2 className="w-4 h-4 animate-spin" />
            Registrando...
          </>
        ) : (
          <>
            <Send className="w-4 h-4" />
            Enviar manifestação
          </>
        )}
      </button>
      <p className="text-xs text-slate-400 text-center">
        Ao enviar, você recebe o número do protocolo nesta tela.
      </p>
    </form>
  );
}

export default function ManifestacaoPage() {
  return (
    <main className="min-h-screen bg-bg">
      <div className="max-w-lg mx-auto px-4 py-8 space-y-5">
        <div className="flex items-center justify-center">
          <Logo variant="default" size="sm" />
        </div>
        <div className="text-center space-y-1">
          <h1 className="text-xl font-bold text-slate-900">Ouvidoria</h1>
          <p className="text-sm text-slate-500">
            Reclamação, elogio ou sugestão: conte para a gente e receba seu
            protocolo na hora.
          </p>
        </div>
        <Suspense
          fallback={
            <div className="flex items-center justify-center gap-2 py-16 text-slate-500">
              <Loader2 className="w-5 h-5 animate-spin" />
              <span className="text-sm">Carregando o formulário...</span>
            </div>
          }
        >
          <FormularioPublico />
        </Suspense>
      </div>
    </main>
  );
}
