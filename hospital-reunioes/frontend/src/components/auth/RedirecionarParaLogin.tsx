"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

import { urlDeLoginCom } from "@/lib/login/destino";

/**
 * A ida ao login carregando o destino original (issue #477, RN-54, PRD #468).
 *
 * Quem decide que não há sessão continua sendo o servidor: o layout da área da
 * Ouvidoria checa o usuário e, sem ele, devolve ESTE componente no lugar dos
 * filhos. Nada da tela protegida chega ao navegador.
 *
 * O que o servidor não tem é o endereço pedido. No App Router, layout não
 * recebe pathname nem searchParams, e o middleware, que teria o `NextRequest`
 * com tudo, é justamente de onde a área da Ouvidoria foi mantida fora de
 * propósito: ele roda ANTES dos rewrites, e alcançá-la levaria junto o
 * `/ouvidoria/qr` do cartaz colado na parede da Recepção, que é público (ADR
 * 0034 decisão 9, ADR 0036, issue #344). Cartaz na parede não se corrige com
 * deploy.
 *
 * Então quem lê o endereço é o único que o tem inteiro: o navegador. A decisão
 * segue no servidor, a leitura do destino é do cliente.
 */
export function RedirecionarParaLogin() {
  const router = useRouter();

  useEffect(() => {
    router.replace(urlDeLoginCom(window.location.pathname + window.location.search));
  }, [router]);

  return (
    <main className="min-h-screen flex items-center justify-center bg-bg p-8">
      <div className="text-center space-y-2">
        <p className="text-text-secondary text-sm">Redirecionando para o login...</p>
        <a href="/login" className="text-primary text-sm hover:underline">
          Ir para o login
        </a>
      </div>
    </main>
  );
}
