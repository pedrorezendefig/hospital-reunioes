"use client";

import ReactMarkdown from "react-markdown";
import remarkBreaks from "remark-breaks";
import type { Components } from "react-markdown";

/**
 * Renderiza o conteúdo markdown de uma seção de texto do POP (negrito, listas,
 * blocos, espaçamento) reaproveitando a linguagem visual da Ata (ADR 0016,
 * Fatia 2): negrito forte, títulos em navy, listas com marcador, citação em
 * caixa azul clara. Espelha o que o PDF gera no servidor (markdown_secao_html),
 * para o preview ao vivo e o documento ficarem coerentes.
 *
 * `remark-breaks` faz a quebra simples de linha virar <br>, igual ao `nl2br` do
 * backend, preservando a sensação de quebras que o Elaborador digita em prosa.
 */
const componentes: Components = {
  p: ({ children }) => <p className="text-sm text-slate-700 leading-relaxed mb-2 last:mb-0">{children}</p>,
  strong: ({ children }) => <strong className="font-bold text-slate-900">{children}</strong>,
  em: ({ children }) => <em className="italic">{children}</em>,
  ul: ({ children }) => <ul className="list-disc pl-5 my-2 space-y-1 text-sm text-slate-700">{children}</ul>,
  ol: ({ children }) => <ol className="list-decimal pl-5 my-2 space-y-1 text-sm text-slate-700">{children}</ol>,
  li: ({ children }) => <li className="leading-relaxed">{children}</li>,
  h1: ({ children }) => <h3 className="text-sm font-bold text-primary mt-3 mb-1.5">{children}</h3>,
  h2: ({ children }) => <h3 className="text-sm font-bold text-primary mt-3 mb-1.5">{children}</h3>,
  h3: ({ children }) => <h3 className="text-sm font-bold text-primary mt-3 mb-1.5">{children}</h3>,
  h4: ({ children }) => <h4 className="text-sm font-semibold text-primary mt-2.5 mb-1">{children}</h4>,
  blockquote: ({ children }) => (
    <blockquote className="my-2 rounded-md bg-blue-50 px-3 py-2 text-sm text-blue-900 [&>p]:text-blue-900 [&>p]:mb-0">
      {children}
    </blockquote>
  ),
  code: ({ children }) => (
    <code className="rounded bg-slate-100 px-1.5 py-0.5 text-[13px] font-mono text-slate-800">{children}</code>
  ),
  a: ({ children, href }) => (
    <a href={href} className="text-primary underline" target="_blank" rel="noopener noreferrer">
      {children}
    </a>
  ),
};

export default function SecaoMarkdown({ children }: { children: string }) {
  return (
    <div className="space-y-0">
      <ReactMarkdown remarkPlugins={[remarkBreaks]} components={componentes}>
        {children}
      </ReactMarkdown>
    </div>
  );
}
