"use client";

/**
 * O "?" da Ouvidoria (seção 4.11 e regra T1 da especificação da Diretoria):
 * uma linha visível e, no "?", a explicação completa.
 *
 * Nasceu no Painel e virou peça do módulo na issue #1629, quando os campos das
 * outras telas ganharam o mesmo "?". Botão de verdade, e não `title`: no
 * celular não há passar o mouse por cima.
 */

import { useState } from "react";
import { CircleHelp } from "lucide-react";

import { ALVO_DE_TOQUE } from "@/lib/toque";

export function Ajuda({ assunto, explicacao }: { assunto: string; explicacao: string }) {
  const [aberta, setAberta] = useState(false);
  return (
    <>
      <button
        type="button"
        aria-expanded={aberta}
        aria-label={`O que é: ${assunto}`}
        onClick={() => setAberta((antes) => !antes)}
        className={`inline-flex items-center justify-center shrink-0 rounded-full text-slate-400 hover:text-slate-600 ${ALVO_DE_TOQUE} md:w-6 md:h-6`}
      >
        <CircleHelp className="w-4 h-4" />
      </button>
      {aberta && <p className="basis-full text-xs text-slate-500 mt-1 normal-case tracking-normal">{explicacao}</p>}
    </>
  );
}

/**
 * O rótulo de um campo com o "?" ao lado. O botão fica FORA do `label`: dentro
 * dele, o nome do campo passaria a carregar o texto do botão, e clicar no "?"
 * mandaria o foco para o campo.
 */
export function RotuloComAjuda({
  htmlFor,
  rotulo,
  explicacao,
  className,
  children,
}: {
  htmlFor?: string;
  /** O nome do campo, que também nomeia o "?". */
  rotulo: string;
  explicacao: string;
  /** As classes do rótulo da tela, sem a margem de baixo, que é da linha. */
  className: string;
  /** O que vai depois do nome dentro do rótulo, como "(opcional)". */
  children?: React.ReactNode;
}) {
  return (
    <div className="flex flex-wrap items-center gap-x-1 mb-1">
      {htmlFor ? (
        <label className={className} htmlFor={htmlFor}>
          {rotulo}
          {children}
        </label>
      ) : (
        <span className={className}>
          {rotulo}
          {children}
        </span>
      )}
      <Ajuda assunto={rotulo} explicacao={explicacao} />
    </div>
  );
}
