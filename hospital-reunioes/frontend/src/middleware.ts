import { NextResponse, type NextRequest } from "next/server";
import { createServerClient, type CookieOptions } from "@supabase/ssr";

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

/**
 * Casa ÁREA, não prefixo de texto (issue #439).
 *
 * Com `startsWith` puro, uma rota futura chamada `/admin-publico` ou
 * `/perfil-do-hospital` virava rota protegida sem ninguém pedir, porque o
 * nome dela começa com o nome de uma área. O limite é o fim do segmento: ou o
 * caminho É a área, ou ele desce dentro dela.
 */
export function isProtectedPath(pathname: string): boolean {
  return protectedPaths.some((p) => pathname === p || pathname.startsWith(`${p}/`));
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

  // Rotas de cadastro e reset de senha — públicas (não requerem autenticação)
  if (pathname.startsWith("/signup") || pathname.startsWith("/reset-password")) {
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
