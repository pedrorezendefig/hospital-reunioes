"use client";

import { useEffect, useState } from "react";

import { montarRetrato } from "@/lib/manual/retrato";
import { createClient } from "@/lib/supabase/client";

type Estado = { tipo: "carregando" } | { tipo: "pronto"; url: string } | { tipo: "desligado" };

const ROTA = "/api/admin/manual/ana/retrato";

/**
 * A aba Ana do manual: o Retrato da Ana, como ele está na branch principal do
 * repositório da Ana (issue #1720, ADR 0094, decisão 3).
 *
 * A tela busca o Retrato pela rota do backend, com o login do app, e o mostra
 * num quadro isolado: `sandbox="allow-scripts"` roda o script do Retrato, mas
 * sem a origem do app, então o Retrato não lê o login, o armazenamento nem a
 * página do manual. O quadro carrega a página montada por endereço `blob:`,
 * e não por `srcdoc`, porque o Retrato grava a aba aberta no `#` do endereço
 * e um `srcdoc` recusa essa troca.
 */
export function RetratoDaAna() {
  const [estado, setEstado] = useState<Estado>({ tipo: "carregando" });

  useEffect(() => {
    let cancelado = false;
    let url: string | null = null;

    async function carregar() {
      const {
        data: { session },
      } = await createClient().auth.getSession();
      const token = session?.access_token;
      if (!token) throw new Error("sem login");
      const html = await montarRetrato((caminho) =>
        fetch(`${ROTA}/${caminho.split("/").map(encodeURIComponent).join("/")}`, {
          headers: { Authorization: `Bearer ${token}` },
        }),
      );
      if (cancelado) return;
      url = URL.createObjectURL(new Blob([html], { type: "text/html" }));
      setEstado({ tipo: "pronto", url });
    }

    carregar().catch(() => {
      if (!cancelado) setEstado({ tipo: "desligado" });
    });

    return () => {
      cancelado = true;
      if (url) URL.revokeObjectURL(url);
    };
  }, []);

  if (estado.tipo === "pronto") {
    return (
      <iframe
        title="Retrato da Ana"
        src={estado.url}
        sandbox="allow-scripts"
        referrerPolicy="no-referrer"
        className="block w-full h-[calc(100vh-14rem)] min-h-[32rem] rounded-2xl border border-border bg-white shadow-premium"
      />
    );
  }

  return (
    <div className="rounded-2xl border border-border bg-surface p-8 text-center">
      <p className="text-base font-semibold text-text">
        {estado.tipo === "carregando" ? "Abrindo o Retrato da Ana" : "O Retrato da Ana ainda não está ligado"}
      </p>
      {estado.tipo === "desligado" && (
        <p className="mt-1 text-sm text-text-secondary">
          Quando o repositório da Ana estiver ligado ao aplicativo, esta aba mostra como a Ana funciona por dentro.
        </p>
      )}
    </div>
  );
}
