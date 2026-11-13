"use client";

import { isValidElement, type ReactNode } from "react";
import ReactMarkdown, { type Components } from "react-markdown";

import { enderecoDaImagem } from "@/lib/manual/paginas";
import { Fluxograma } from "./fluxograma/Fluxograma";

/**
 * O Markdown de uma página do manual no visual do app (issue #1718, ADR 0094):
 * a fonte da casa e os tokens de cor do `globals.css`. Os títulos curtos saem
 * em Caixa alta (ADR 0080): o `h3` pela regra base, o `h4` pela classe
 * `uppercase`, porque a regra base só alcança `h1`, `h2` e `h3`. O texto
 * corrido fica como foi escrito.
 *
 * O bloco `fluxograma` vira o Fluxograma do app (emenda da ADR 0094, issue
 * #1719), ligado aqui pela primeira página que traz um (issue #1723).
 */
function componentes(pasta: string): Components {
  return {
    h1: ({ children }) => <h3 className="text-lg font-bold text-primary mt-8 mb-3">{children}</h3>,
    h2: ({ children }) => <h3 className="text-lg font-bold text-primary mt-8 mb-3">{children}</h3>,
    h3: ({ children }) => <h4 className="text-base font-semibold text-primary mt-6 mb-2 uppercase tracking-[0.02em]">{children}</h4>,
    p: ({ children }) => <p className="text-[15px] text-text leading-relaxed mb-3">{children}</p>,
    strong: ({ children }) => <strong className="font-semibold text-text">{children}</strong>,
    ul: ({ children }) => <ul className="list-disc pl-6 mb-3 space-y-1.5 text-[15px] text-text">{children}</ul>,
    ol: ({ children }) => <ol className="list-decimal pl-6 mb-3 space-y-1.5 text-[15px] text-text">{children}</ol>,
    li: ({ children }) => <li className="leading-relaxed pl-1">{children}</li>,
    blockquote: ({ children }) => (
      <blockquote className="my-4 rounded-xl bg-primary/5 border-l-[3px] border-primary px-4 py-3 text-text [&>p]:mb-0">
        {children}
      </blockquote>
    ),
    a: ({ children, href }) => (
      <a href={href} className="text-primary underline">
        {children}
      </a>
    ),
    img: ({ src, alt }) => (
      // eslint-disable-next-line @next/next/no-img-element -- print estático do manual, sem otimização
      <img
        src={enderecoDaImagem(pasta, typeof src === "string" ? src : "")}
        alt={alt ?? ""}
        loading="lazy"
        className="block max-w-full h-auto my-4 rounded-xl border border-border shadow-premium"
      />
    ),
    pre: ({ children }) => {
      const bloco = isValidElement<{ className?: string; children?: ReactNode }>(children)
        ? children.props
        : null;
      if (bloco?.className === "language-fluxograma") {
        return <Fluxograma fonte={String(bloco.children ?? "")} />;
      }
      return (
        <pre className="my-4 overflow-x-auto rounded-xl border border-border bg-bg px-4 py-3 text-[13px] font-mono text-text-secondary">
          {children}
        </pre>
      );
    },
    code: ({ children }) => (
      <code className="rounded bg-primary/5 px-1.5 py-0.5 text-[13px] font-mono text-text">{children}</code>
    ),
  };
}

export function MarkdownDoManual({ pasta, children }: { pasta: string; children: string }) {
  return <ReactMarkdown components={componentes(pasta)}>{children}</ReactMarkdown>;
}
