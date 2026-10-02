import { ArrowRight, BarChart3, Camera, type LucideIcon, Target } from "lucide-react";
import Link from "next/link";

import { CAMINHO_INSTAGRAM } from "./Instagram";
import { CAMINHO_OBJETIVOS } from "./Objetivos";

/** O caminho da tela Dados do Google, o terceiro atalho. */
const CAMINHO_DADOS_DO_GOOGLE = "/admin/central-de-comando/dados-do-google";

type Atalho = { titulo: string; descricao: string; href: string; icone: LucideIcon };

// As três outras telas da Central (o menu tem quatro; a Visão Geral é esta).
const ATALHOS: readonly Atalho[] = [
  {
    titulo: "Objetivos",
    descricao: "As direções da diretoria, cada uma com os números que importam.",
    href: CAMINHO_OBJETIVOS,
    icone: Target,
  },
  {
    titulo: "Dados do Google",
    descricao: "Visitas por dia, Áreas do site, Origem do público e Contatos gerados.",
    href: CAMINHO_DADOS_DO_GOOGLE,
    icone: BarChart3,
  },
  {
    titulo: "Instagram",
    descricao: "Seguidores, Alcance, engajamento e as publicações que mais renderam.",
    href: CAMINHO_INSTAGRAM,
    icone: Camera,
  },
];

/** Os atalhos para as outras três telas da Central de Comando. */
export function Atalhos() {
  return (
    <section aria-labelledby="central-atalhos" className="space-y-4">
      <h2 id="central-atalhos" className="text-lg font-bold text-text">
        Ir para
      </h2>
      <ul className="grid gap-4 sm:grid-cols-3">
        {ATALHOS.map((atalho) => {
          const Icone = atalho.icone;
          return (
            <li key={atalho.href}>
              <Link
                href={atalho.href}
                className="flex h-full items-start gap-3 rounded-2xl border border-border bg-white p-5 shadow-premium transition-colors hover:border-primary/40 hover:bg-primary/5"
              >
                <span
                  aria-hidden
                  className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary"
                >
                  <Icone className="h-4 w-4" />
                </span>
                <div className="min-w-0 flex-1 space-y-1">
                  <p className="flex items-center gap-1 font-semibold text-text">
                    {atalho.titulo}
                    <ArrowRight aria-hidden className="h-4 w-4 text-text-secondary" />
                  </p>
                  <p className="text-xs text-text-secondary">{atalho.descricao}</p>
                </div>
              </Link>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
