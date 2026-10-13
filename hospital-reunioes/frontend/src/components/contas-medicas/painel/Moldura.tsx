import { useId, type ReactNode } from "react";

/**
 * A moldura de um cartão ou de um bloco do Painel (issue #1137): o título dá
 * o nome da região, para quem lê a tela pelo leitor e para o teste achar cada
 * cartão pelo nome.
 */
export function Moldura({
  titulo,
  subtitulo,
  className = "",
  children,
}: {
  titulo: string;
  subtitulo?: string;
  className?: string;
  children: ReactNode;
}) {
  const id = useId();
  return (
    <section aria-labelledby={id} className={`bg-white rounded-2xl border border-border shadow-premium p-5 ${className}`}>
      <h2 id={id} className="text-sm font-semibold text-slate-700">
        {titulo}
      </h2>
      {subtitulo && <p className="text-xs text-slate-500 mt-0.5">{subtitulo}</p>}
      <div className="mt-3">{children}</div>
    </section>
  );
}

/** O número grande de um cartão: a cor primária, sem faixa de cor por valor. */
export function Numero({ children }: { children: ReactNode }) {
  return <p className="text-3xl font-bold tabular-nums text-primary">{children}</p>;
}

/** A linha de apoio embaixo do número. */
export function Apoio({ children }: { children: ReactNode }) {
  return <p className="mt-1 text-xs text-slate-500 tabular-nums">{children}</p>;
}
