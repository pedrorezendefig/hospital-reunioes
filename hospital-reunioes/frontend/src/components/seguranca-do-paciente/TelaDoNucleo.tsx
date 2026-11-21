"use client";

import { useEffect, useState, type ReactNode } from "react";
import { FileSignature, Inbox, Lock } from "lucide-react";

import { useCurrentParticipante } from "@/hooks/useCurrentParticipante";
import { chamarNsp } from "@/lib/seguranca-do-paciente/membros";

const CARTAO = "bg-white rounded-2xl border border-border shadow-premium";

interface MeuTermo {
  pendente: boolean;
  documento_url: string | null;
}

/** O Termo pendente de quem não tem a tela liberada (issue #1768). */
function useMeuTermo(perguntar: boolean): MeuTermo | null {
  const [termo, setTermo] = useState<MeuTermo | null>(null);
  useEffect(() => {
    if (!perguntar) return;
    let vivo = true;
    chamarNsp<MeuTermo>("/api/nsp/meu-termo")
      .then((corpo) => vivo && setTermo(corpo))
      .catch(() => vivo && setTermo(null));
    return () => {
      vivo = false;
    };
  }, [perguntar]);
  return termo;
}

/** A faixa das telas bloqueadas para quem ainda não assinou o Termo. */
function FaixaDoTermo({ documentoUrl }: { documentoUrl: string | null }) {
  return (
    <div className="rounded-2xl border border-amber-200 bg-amber-50 flex flex-col sm:flex-row gap-3 sm:items-center px-4 py-4">
      <FileSignature className="w-5 h-5 shrink-0 text-amber-700" aria-hidden />
      <div className="min-w-0 flex-1">
        <p className="text-sm font-semibold text-amber-900">Assine o Termo de Adesão para liberar este acesso</p>
        <p className="text-sm text-amber-800 mt-0.5">
          {documentoUrl
            ? "O link para assinar foi para o seu e-mail."
            : "O documento ainda não saiu. Fale com a Presidência do Núcleo."}
        </p>
      </div>
      {documentoUrl && (
        <a
          href={documentoUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center justify-center rounded-xl bg-amber-600 px-4 py-2 text-sm font-semibold text-white hover:bg-amber-700"
        >
          Abrir o Termo de Adesão
        </a>
      )}
    </div>
  );
}

interface Props {
  titulo: string;
  /** A linha no topo dizendo o que fazer ali (seção 17 da especificação). */
  orientacao: string;
  /** O recurso da permissão efetiva que abre a tela (ADR 0095). */
  recurso: string;
  /** O conteúdo da tela. Sem ele, o estado vazio. */
  children?: ReactNode;
  /** A tela de duas colunas (a triagem, issue #1992) ocupa mais largura. */
  larga?: boolean;
}

/**
 * A moldura de toda tela de Segurança do Paciente (issue #1765): título,
 * linha de orientação e o conteúdo, ou o estado vazio enquanto a fatia da tela
 * não chega.
 *
 * Quem decide o acesso é o servidor: o layout já barrou quem não entra no
 * módulo, e cada rota da API barra o recurso dela. Aqui a tela só deixa de se
 * mostrar a quem não tem o recurso (o membro sem Termo, por exemplo, não abre
 * Membros), em vez de mostrar uma tela que a API vai recusar. Quem ainda não
 * assinou o Termo vê, no lugar da recusa, a faixa com o documento pendente
 * (issue #1768).
 */
export function TelaDoNucleo({ titulo, orientacao, recurso, children, larga = false }: Props) {
  const { participante } = useCurrentParticipante();
  const liberada = participante?.recursos_nsp?.includes(recurso) ?? false;
  const meuTermo = useMeuTermo(Boolean(participante) && !liberada);

  return (
    <div className={`p-4 md:p-8 ${larga ? "max-w-6xl" : "max-w-3xl"} mx-auto w-full`}>
      <h1 className="text-2xl font-bold text-slate-900">{titulo}</h1>
      <p className="text-slate-500 text-sm mt-0.5 mb-5">{orientacao}</p>

      {participante && !liberada && meuTermo?.pendente ? (
        <FaixaDoTermo documentoUrl={meuTermo.documento_url} />
      ) : participante && !liberada ? (
        <div className={`${CARTAO} flex gap-3 items-start px-4 py-4`}>
          <Lock className="w-5 h-5 shrink-0 text-slate-400" aria-hidden />
          <div className="min-w-0">
            <p className="text-sm font-semibold text-slate-900">Esta tela ainda não está liberada para você.</p>
            <p className="text-sm text-slate-600 mt-0.5">
              Quem está no Núcleo libera as telas ao assinar o Termo de Adesão.
            </p>
          </div>
        </div>
      ) : (
        (children ?? (
          <div className={`${CARTAO} flex flex-col items-center text-center gap-2 px-4 py-10`}>
            <Inbox className="w-8 h-8 text-slate-300" aria-hidden />
            <p className="text-sm font-semibold text-slate-900">Nada por aqui ainda.</p>
            <p className="text-sm text-slate-600">Esta tela chega nas próximas entregas do módulo.</p>
          </div>
        ))
      )}
    </div>
  );
}
