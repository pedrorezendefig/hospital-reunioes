"use client";

/**
 * A barra de atalhos do topo da Ouvidoria (issue #496, PRD #471, RN-77, D-16).
 *
 * No computador é uma linha de pílulas com rótulo curto, e nenhuma delas
 * quebra: o nome inteiro fica no nome acessível, que é quem o leitor de tela
 * anuncia. No celular a linha inteira não caberia de jeito nenhum, então ela
 * colapsa num gatilho único, e o menu que ele abre tem largura para escrever
 * os nomes por extenso.
 *
 * As duas versões saem da MESMA lista (`lib/ouvidoria/atalhos`): quem
 * acrescentar uma porta amanhã não tem como acrescentá-la só no computador.
 */

import { useRef, useState } from "react";
import Link from "next/link";
import {
  LayoutDashboard,
  MapPin,
  Menu,
  SlidersHorizontal,
  Star,
  UsersRound,
} from "lucide-react";

import { useFecharFlutuante } from "@/hooks/useFecharFlutuante";
import { atalhosDoPerfil, type ChaveDeAtalho } from "@/lib/ouvidoria/atalhos";

const ICONE_DO_ATALHO: Record<ChaveDeAtalho, typeof MapPin> = {
  painel: LayoutDashboard,
  nota_externa: Star,
  pontos: MapPin,
  responsaveis: UsersRound,
  prazos: SlidersHorizontal,
};

/**
 * 44px, o piso de alvo de toque do WCAG 2.5.5 e o mesmo do botão de menu do
 * cabeçalho da casa (`components/layout/Header`). Vale só no celular: no
 * computador o ponteiro acerta a pílula compacta sem esforço.
 */
const TOQUE = "min-h-[44px] md:min-h-0";

export function AtalhosDaOuvidoria({ perfil }: { perfil: string | null | undefined }) {
  const atalhos = atalhosDoPerfil(perfil);
  const [aberto, setAberto] = useState(false);
  const caixa = useRef<HTMLDivElement>(null);
  useFecharFlutuante(aberto, caixa, () => setAberto(false));

  // Quem está fora da Ouvidoria também abre esta tela, e para ele não sobra
  // porta nenhuma: sem esta saída, o gatilho do celular apareceria abrindo um
  // menu vazio.
  if (atalhos.length === 0) return null;

  return (
    <>
      {/* Uma linha só, sem `flex-wrap`: o que garante que ela caiba é o rótulo
          curto, e não a permissão de quebrar (RN-77). */}
      <nav aria-label="Atalhos da Ouvidoria" className="hidden md:flex items-center gap-2">
        {atalhos.map((atalho) => {
          const Icone = ICONE_DO_ATALHO[atalho.chave];
          return (
            <Link
              key={atalho.chave}
              href={atalho.href}
              // O rótulo curto é o que se lê; o nome inteiro é o que se ouve.
              aria-label={atalho.nome}
              title={atalho.nome}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-sm font-medium whitespace-nowrap bg-slate-100 text-slate-700 hover:bg-slate-200 transition-colors"
            >
              <Icone className="w-4 h-4 shrink-0" />
              {atalho.rotulo}
            </Link>
          );
        })}
      </nav>

      <div className="relative md:hidden" ref={caixa}>
        <button
          type="button"
          aria-haspopup="true"
          aria-expanded={aberto}
          onClick={() => setAberto((antes) => !antes)}
          className={`inline-flex items-center gap-1.5 px-3 rounded-full text-sm font-medium whitespace-nowrap bg-slate-100 text-slate-700 hover:bg-slate-200 transition-colors ${TOQUE}`}
        >
          <Menu className="w-4 h-4 shrink-0" />
          Atalhos
        </button>
        {aberto && (
          // Sem `role="menu"`, pelo mesmo motivo do menu de ações da linha: um
          // menu ARIA espera filhos `menuitem`, e o papel explícito apagaria o
          // que estas portas são de verdade, links.
          <div
            aria-label="Atalhos da Ouvidoria"
            className="absolute left-0 top-12 z-20 min-w-[15rem] py-1 rounded-xl border border-border bg-white shadow-premium"
          >
            {atalhos.map((atalho) => {
              const Icone = ICONE_DO_ATALHO[atalho.chave];
              return (
                <Link
                  key={atalho.chave}
                  href={atalho.href}
                  onClick={() => setAberto(false)}
                  className={`flex items-center gap-2 px-3 py-2 text-sm text-slate-700 hover:bg-slate-50 ${TOQUE}`}
                >
                  <Icone className="w-4 h-4 shrink-0" />
                  {atalho.nome}
                </Link>
              );
            })}
          </div>
        )}
      </div>
    </>
  );
}
