import {
  CalendarCheck,
  MessageCircle,
  MessageSquareText,
  MousePointerClick,
  Phone,
  type LucideIcon,
} from "lucide-react";

import { formatarInteiro } from "@/lib/central-de-comando/formato";

/**
 * Um canal do bloco `contatos_gerados` do payload de Dados do Google, com o
 * estado honesto dele. Só o medido traz `cliques`: em construção (o Site
 * ainda não avisa o Google quando o clique acontece) e não medido (não há
 * clique para contar) não trazem número nenhum, nem zero. O backend manda os
 * quatro canais, na ordem da tela.
 */
export type ContatoDoPayload =
  | { chave: string; rotulo: string; estado: "medido"; cliques: number }
  | { chave: string; rotulo: string; estado: "em-construcao" | "nao-medido" };

/** Um ícone por canal; canal que a tela ainda não conhece ganha o genérico. */
const ICONE_DO_CANAL: Record<string, LucideIcon> = {
  agendar: CalendarCheck,
  whatsapp: MessageCircle,
  "fale-conosco": MessageSquareText,
  telefone: Phone,
};

const SELO_SEM_NUMERO: Record<"em-construcao" | "nao-medido", string> = {
  "em-construcao": "em construção",
  "nao-medido": "não medido",
};

/**
 * Os Contatos gerados de Dados do Google (issue #818, ADR 0058).
 *
 * Porte dos cartões de contato da Central antiga em Tailwind puro: um cartão
 * por canal, com o número de cliques e o selo de medido quando o canal é
 * medido, ou o selo "em construção" ou "não medido", sem número, quando não
 * é. Honestidade do dado: zero nunca aparece no lugar de "não medimos".
 */
export function CanaisDeContato({ contatos }: { contatos: ContatoDoPayload[] }) {
  return (
    <div className="space-y-4">
      <ul aria-label="Contatos gerados por canal" className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {contatos.map((contato) => {
          const Icone = ICONE_DO_CANAL[contato.chave] ?? MousePointerClick;
          const medido = contato.estado === "medido";
          return (
            <li
              key={contato.chave}
              className={`flex flex-col rounded-xl border p-4 ${
                medido ? "border-border bg-white" : "border-dashed border-border bg-bg"
              }`}
            >
              <span
                aria-hidden="true"
                className={`mb-3 flex h-9 w-9 items-center justify-center rounded-lg ${
                  medido ? "bg-primary text-white" : "bg-border text-text-secondary"
                }`}
              >
                <Icone className="h-4 w-4" />
              </span>
              <div className="flex min-h-9 items-center">
                {contato.estado === "medido" ? (
                  <span className="text-2xl font-bold tabular-nums text-text">{formatarInteiro(contato.cliques)}</span>
                ) : (
                  <span className="rounded-full border border-amber-200 bg-amber-50 px-2.5 py-1 text-xs font-semibold text-amber-800">
                    {SELO_SEM_NUMERO[contato.estado]}
                  </span>
                )}
              </div>
              <span data-testid="rotulo" className={`mt-1 text-xs ${medido ? "text-text-secondary" : "font-medium text-text"}`}>
                {contato.rotulo}
              </span>
              {medido && (
                <span className="mt-3 self-start rounded-full border border-emerald-200 bg-emerald-50 px-2 py-0.5 text-xs font-semibold text-emerald-700">
                  medido
                </span>
              )}
            </li>
          );
        })}
      </ul>
      <p className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-xs text-amber-900">
        <b className="font-semibold">Como ler:</b> medido é o clique que o Site avisa ao Google, hoje o do WhatsApp e o
        envio do Fale Conosco. Em construção é o clique que o Google ainda não recebe, como o de marcar consulta ou
        exame. Não medido é o contato sem clique para contar, como a ligação. Os dois últimos nunca aparecem como zero.
      </p>
    </div>
  );
}
