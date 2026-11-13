"use client";

import type { ComponentProps } from "react";
import type { ExtraProps } from "react-markdown";

import { Fluxograma } from "./Fluxograma";

type NoDoMarkdown = NonNullable<ExtraProps["node"]>;
type FilhoDoNo = NoDoMarkdown["children"][number];

function textoDe(no: FilhoDoNo): string {
  if (no.type === "text") return no.value;
  if (no.type === "element") return no.children.map(textoDe).join("");
  return "";
}

/** O texto do bloco quando o `<pre>` embrulha um ```fluxograma; senão, null. */
function fonteDoFluxograma(node: ExtraProps["node"]): string | null {
  const codigo = node?.children.find((c) => c.type === "element" && c.tagName === "code");
  if (!codigo || codigo.type !== "element") return null;
  const classes = codigo.properties.className;
  const lista = Array.isArray(classes) ? classes : [classes];
  if (!lista.includes("language-fluxograma")) return null;
  return textoDe(codigo);
}

/**
 * O `<pre>` do Markdown do manual (issue #1719): o bloco ```fluxograma vira o
 * Fluxograma do app; qualquer outro bloco de código continua código. A página
 * pluga assim: `<ReactMarkdown components={{ pre: PreDoManual }}>`.
 */
export function PreDoManual({ node, ...props }: ComponentProps<"pre"> & ExtraProps) {
  const fonte = fonteDoFluxograma(node);
  if (fonte !== null) return <Fluxograma fonte={fonte} />;
  return <pre {...props} />;
}
