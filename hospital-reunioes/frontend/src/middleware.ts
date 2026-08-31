import { NextResponse, type NextRequest } from "next/server";
import { createServerClient, type CookieOptions } from "@supabase/ssr";

/**
 * A régua do arquivo: casa ÁREA, não prefixo de texto (issue #439).
 *
 * O limite é o fim do segmento: ou o caminho É a área, ou ele desce dentro
 * dela. Com `startsWith` cru, uma rota futura chamada `/admin-publico` ou
 * `/reset-password-admin` seria tratada como se fosse a área vizinha, só
 * porque o nome dela começa igual.
 *
 * Hoje isso é defesa em profundidade, não conserto de bug alcançável: o
 * `config.matcher` também não alcança `/admin-publico`, então o middleware
 * nem roda para ela. O que a régua garante é que as duas guardas do arquivo
 * (a que protege e a que libera) parem de depender de coincidência de nome se
 * um dia o matcher ficar mais largo.
 */
function estaNaArea(pathname: string, areas: readonly string[]): boolean {
  return areas.some((a) => pathname === a || pathname.startsWith(`${a}/`));
}

// As áreas do staff que exigem sessão.
//
// A Ouvidoria NÃO entra aqui, e isso é decisão (issue #344): `/ouvidoria/qr`
// é o rewrite do cartaz colado na parede da Recepção, escaneado por paciente
// e visitante sem login (ADR 0034 decisão 9, ADR 0036). O middleware roda
// ANTES dos rewrites do next.config, então incluir a área aqui mandaria o
// celular de quem escaneia para a tela de login do staff. O que a área
// precisa ela já tem no servidor: `app/ouvidoria/layout.tsx` exige sessão, e
// `app/ouvidoria/painel/layout.tsx` exige o perfil da Ouvidoria.
const protectedPaths = ["/dashboard", "/reunioes", "/pendencias", "/perfil", "/configuracoes", "/admin"];

// Cadastro e reset de senha: públicas por decisão, e pela MESMA régua das
// protegidas. Esta é a direção perigosa (liberar demais), então deixá-la em
// `startsWith` cru enquanto a de cima ganhava limite de segmento seria a
// assimetria errada.
const publicPaths = ["/signup", "/reset-password"];

export function isProtectedPath(pathname: string): boolean {
  return estaNaArea(pathname, protectedPaths);
}

export async function middleware(request: NextRequest) {
  let supabaseResponse = NextResponse.next({ request });

  const supabase = createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      cookies: {
        getAll() {
          return request.cookies.getAll();
        },
        setAll(cookiesToSet: { name: string; value: string; options: CookieOptions }[]) {
          cookiesToSet.forEach(({ name, value }) =>
            request.cookies.set(name, value)
          );
          supabaseResponse = NextResponse.next({ request });
          cookiesToSet.forEach(({ name, value, options }) =>
            supabaseResponse.cookies.set(name, value, options)
          );
        },
      },
    }
  );

  const {
    data: { user },
  } = await supabase.auth.getUser();

  // Se há cookies de sessão mas o user é null (token expirado/inválido),
  // limpa os cookies para evitar erros de "Refresh Token Not Found" em loop
  if (!user) {
    const authCookies = request.cookies.getAll().filter(c => c.name.startsWith("sb-"));
    if (authCookies.length > 0) {
      authCookies.forEach(({ name }) => {
        supabaseResponse.cookies.set(name, "", { maxAge: 0, path: "/" });
      });
    }
  }

  const { pathname } = request.nextUrl;

  // Rotas de cadastro e reset de senha: públicas (não requerem autenticação)
  if (estaNaArea(pathname, publicPaths)) {
    return supabaseResponse;
  }

  // Redireciona para /login se tentar acessar rotas protegidas sem autenticação
  const isProtected = isProtectedPath(pathname);

  if (isProtected && !user) {
    return NextResponse.redirect(new URL("/login", request.url));
  }

  // Redireciona para /dashboard se já autenticado tentar acessar /login ou /signup
  if ((pathname === "/login" || pathname === "/signup") && user) {
    return NextResponse.redirect(new URL("/dashboard", request.url));
  }

  return supabaseResponse;
}

export const config = {
  matcher: [
    "/dashboard/:path*",
    "/reunioes/:path*",
    "/pendencias/:path*",
    "/perfil/:path*",
    "/perfil",
    "/configuracoes/:path*",
    "/configuracoes",
    "/admin/:path*",
    "/admin",
    "/signup/:path*",
    "/signup",
    "/login",
    "/reset-password",
    "/reset-password/:path*",
  ],
};
