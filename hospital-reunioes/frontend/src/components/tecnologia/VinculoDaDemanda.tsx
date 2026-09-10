"use client";

/**
 * Os controles do Vínculo com o desenvolvimento (issue #674, ADR 0054).
 *
 * O que é da Vitta e fica atrás do login no GitHub: o campo "Vincular issue",
 * o botão "Desvincular" e o link "Abrir no GitHub" (decisão 9). Quem não tem
 * login não vê nada disto, e a API nem manda o número na resposta da Demanda,
 * então esconder aqui não é a proteção: é o par na tela de uma regra que o
 * backend já cumpre com 403.
 *
 * A tela não pergunta "quem sou eu" ao `useAuth`: ele carrega o id do Supabase
 * Auth, e não o `participantes.id`. Quem responde é o `GET /eu` da aba, que
 * também diz se a integração está configurada no servidor.
 */

import { useState } from "react";
import { AlertCircle, ExternalLink, Link2, Unlink } from "lucide-react";

import { BASE_TECNOLOGIA, Demanda, ETAPA_ROTULO, EtapaDemanda, EuNaAba, momentoLegivel } from "./demandas";

type Props = {
  demanda: Demanda;
  eu: EuNaAba;
  /** Manda o pedido e devolve `true` quando o servidor aceitou. */
  onEnviar: (url: string, corpo?: unknown) => Promise<boolean>;
};

/**
 * O aviso de integração desligada.
 *
 * Diz a CAUSA (falta configuração, não é falha passageira) sem NOMEAR as
 * variáveis de ambiente. O gate `if (!eu.tem_github_login) return null` é de
 * runtime: a string vive no bundle JS, que é servido a qualquer um que abra a
 * página, com sessão ou sem. O backend já acertou nisso (o
 * `MOTIVO_INTEGRACAO_DESLIGADA` fala de configuração e não cita variável), e a
 * tela segue o mesmo critério.
 *
 * Quem precisa saber QUAIS variáveis são lê o corpo do PR e o `.env.example`,
 * que é onde essa informação pertence.
 */
export const AVISO_SEM_INTEGRACAO =
  "A integração com o GitHub não está configurada neste ambiente: " +
  "vincular e desvincular ficam indisponíveis até alguém configurá-la no servidor.";

export const AJUDA_DO_CAMPO = "Número da issue-raiz (o PRD, ou a issue de correção). As fatias entram como partes dela.";

export function VinculoDaDemanda({ demanda, eu, onEnviar }: Props) {
  const [numero, setNumero] = useState("");

  // A porta é o login, e nada mais: sem ele, nem o bloco existe.
  if (!eu.tem_github_login) return null;

  const desligada = !eu.integracao_configurada;
  const vinculo = demanda.vinculo ?? null;

  async function vincular() {
    const limpo = numero.trim();
    if (!limpo) return;
    // Vai como número: o backend recusa o resto, mas mandar texto faria a
    // recusa vir do pydantic, em lista, e a tela mostraria o JSON cru.
    if (await onEnviar(`${BASE_TECNOLOGIA}/demandas/${demanda.id}/vincular`, { numero: Number(limpo) })) {
      setNumero("");
    }
  }

  return (
    <section aria-labelledby={`vinculo-${demanda.id}`} className="pt-4 border-t border-border space-y-3">
      <div>
        <h3 id={`vinculo-${demanda.id}`} className="text-xs font-medium text-text-secondary uppercase">
          Vínculo com o desenvolvimento
        </h3>
        <p className="mt-1 text-xs text-text-secondary">
          {vinculo
            ? `Etapa: ${ETAPA_ROTULO[demanda.etapa as EtapaDemanda] ?? "sem etapa"}${
                demanda.github_sincronizado_em
                  ? `, conferida em ${momentoLegivel(demanda.github_sincronizado_em)}`
                  : ""
              }`
            : "Esta Demanda ainda não está ligada a nenhuma issue."}
        </p>
      </div>

      {desligada && (
        <p
          role="status"
          className="flex items-start gap-2 px-3 py-2 rounded-lg bg-amber-50 border border-amber-200 text-amber-800 text-xs"
        >
          <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
          <span>{AVISO_SEM_INTEGRACAO}</span>
        </p>
      )}

      {vinculo ? (
        <div className="flex flex-wrap items-center gap-3">
          {/* Sem endereço na foto guardada, o número vira TEXTO e o link some.
              Um `href="#"` seria um clique morto: o cursor vira mãozinha, a
              pessoa clica e nada acontece, e ela conclui que a página quebrou.
              O número continua à vista, que é o que ela precisa para achar a
              issue à mão. */}
          {vinculo.url ? (
            <a
              href={vinculo.url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1.5 text-sm font-medium text-primary hover:underline"
            >
              <ExternalLink className="w-4 h-4" />
              Abrir no GitHub (#{vinculo.numero})
            </a>
          ) : (
            <span className="text-sm text-text-secondary">Issue #{vinculo.numero}</span>
          )}
          <button
            type="button"
            // Desabilitado por cima da guarda do backend, não no lugar dela.
            // Desvincular não precisa do GitHub, mas o botão acompanha o bloco:
            // ver "Desvincular" ativo ao lado de um aviso de indisponibilidade
            // seria contraditório.
            disabled={desligada}
            onClick={() => onEnviar(`${BASE_TECNOLOGIA}/demandas/${demanda.id}/desvincular`)}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-border text-sm text-text hover:border-primary hover:text-primary transition-colors disabled:opacity-50 disabled:hover:border-border disabled:hover:text-text"
          >
            <Unlink className="w-4 h-4" />
            Desvincular
          </button>
        </div>
      ) : (
        <div className="flex flex-wrap items-end gap-2">
          <label className="block">
            <span className="text-xs font-medium text-text-secondary">Vincular issue</span>
            <input
              type="number"
              min={1}
              aria-label="Vincular issue"
              aria-describedby={`ajuda-vinculo-${demanda.id}`}
              placeholder="673"
              value={numero}
              disabled={desligada}
              onChange={(e) => setNumero(e.target.value)}
              className="mt-1 w-32 px-3 py-2 text-sm border border-slate-200 rounded-lg outline-none focus:border-primary focus:ring-1 focus:ring-primary bg-white disabled:bg-slate-50 disabled:text-slate-400"
            />
          </label>
          <button
            type="button"
            disabled={desligada || !numero.trim()}
            onClick={vincular}
            className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg border border-border text-sm text-text hover:border-primary hover:text-primary transition-colors disabled:opacity-50 disabled:hover:border-border disabled:hover:text-text"
          >
            <Link2 className="w-4 h-4" />
            Vincular
          </button>
          <p id={`ajuda-vinculo-${demanda.id}`} className="w-full text-xs text-text-secondary">
            {AJUDA_DO_CAMPO}
          </p>
        </div>
      )}
    </section>
  );
}
