"use client";

/**
 * A legenda das cores e dos estados da Ouvidoria (issue #1629, PRD #1527,
 * regra T8 da especificação da Diretoria).
 *
 * Nasce fechada: aberta todo dia, ela empurraria a lista para baixo e o olho
 * aprenderia a pular a região. Fechada, ela é um botão que a pessoa nova acha
 * e a experiente ignora. As cores saem das mesmas constantes que pintam o card
 * e a fila, para a legenda não contar uma cor que a tela já trocou.
 */

import { useState } from "react";
import { Info } from "lucide-react";

import { COR_DA_GRAVIDADE } from "@/components/ouvidoria/CardDeCaso";
import { ORDEM_DA_FILA, classeDoStatus, rotuloDoStatus } from "@/lib/ouvidoria/fila";
import type { StatusManifestacao } from "@/lib/ouvidoria/prazo";
import { ALTURA_DE_TOQUE } from "@/lib/toque";
import { AJUDA_GRAVIDADE, GRAVIDADES, LABEL_GRAVIDADE } from "@/lib/ouvidoria/validacao";

/** O que cada estado quer dizer, em uma frase. */
const SIGNIFICADO_DO_ESTADO: Record<StatusManifestacao, string> = {
  novo: "Registrada e ainda não aberta pela Ouvidoria.",
  em_classificacao: "A Ouvidoria confere tipo, setor e gravidade antes de enviar à área.",
  aguardando_area: "Enviado à área, com o prazo correndo.",
  aguardando_manifestante: "Parado, esperando quem manifestou responder.",
  respondido: "A área respondeu. Falta a Ouvidoria revisar e encerrar.",
  encerrado: "Desfecho registrado. O caso saiu do trabalho.",
};

export function Legenda() {
  const [aberta, setAberta] = useState(false);
  return (
    <div>
      <button
        type="button"
        aria-expanded={aberta}
        onClick={() => setAberta((antes) => !antes)}
        className={`inline-flex items-center gap-1.5 px-3 rounded-full text-sm font-medium normal-case tracking-normal whitespace-nowrap bg-slate-100 text-slate-700 hover:bg-slate-200 transition-colors ${ALTURA_DE_TOQUE}`}
      >
        <Info aria-hidden="true" className="w-4 h-4 shrink-0" />
        Legenda
      </button>
      {aberta && (
        <section
          aria-label="Legenda das cores e dos estados"
          className="mt-2 grid gap-4 sm:grid-cols-2 p-4 rounded-xl border border-border bg-white text-sm"
        >
          <div>
            <h3 id="legenda-gravidade" className="text-xs font-semibold uppercase tracking-wide text-slate-500 mb-2">
              Gravidade
            </h3>
            <ul aria-labelledby="legenda-gravidade" className="space-y-1.5">
              {GRAVIDADES.map((nivel) => (
                <li key={nivel} className="flex items-start gap-2">
                  <span
                    data-cor
                    aria-hidden="true"
                    className={`inline-block w-2.5 h-2.5 mt-1.5 shrink-0 rounded-full ${COR_DA_GRAVIDADE[nivel]}`}
                  />
                  <span className="text-slate-600">
                    <strong className="font-semibold text-slate-800">{LABEL_GRAVIDADE[nivel]}</strong>.{" "}
                    {AJUDA_GRAVIDADE[nivel]}
                  </span>
                </li>
              ))}
            </ul>
          </div>
          <div>
            <h3 id="legenda-estado" className="text-xs font-semibold uppercase tracking-wide text-slate-500 mb-2">
              Estado do caso
            </h3>
            <ul aria-labelledby="legenda-estado" className="space-y-1.5">
              {ORDEM_DA_FILA.map((status) => (
                <li key={status} className="flex flex-wrap items-baseline gap-x-2">
                  <strong
                    className={`shrink-0 px-2 py-0.5 rounded-full text-[11px] font-semibold uppercase tracking-wide ${classeDoStatus(status)}`}
                  >
                    {rotuloDoStatus(status)}
                  </strong>
                  <span className="text-slate-600">{SIGNIFICADO_DO_ESTADO[status]}</span>
                </li>
              ))}
            </ul>
          </div>
        </section>
      )}
    </div>
  );
}
