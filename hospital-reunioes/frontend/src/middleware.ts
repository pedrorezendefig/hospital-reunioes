import { NextResponse, type NextRequest } from "next/server";
import { createServerClient, type CookieOptions } from "@supabase/ssr";

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
  // A Ouvidoria entrou aqui na issue #344: a área inteira exige sessão, e o
  // painel em tempo real exige ainda o perfil da Ouvidoria, no layout dele.
  const protectedPaths = ["/dashboard", "/reunioes", "/pendencias", "/perfil", "/configuracoes", "/admin", "/ouvidoria"];
  // Casa a área, não o prefixo do texto: `/ouvidoria-setor` é o portal que o
  // gestor abre pelo link do email, sem login, e um `startsWith` cru o mandaria
  // para a tela de entrada.
  const isProtected = protectedPaths.some((p) => pathname === p || pathname.startsWith(`${p}/`));

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
    "/ouvidoria/:path*",
    "/ouvidoria",
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
