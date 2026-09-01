"use client";

import { Suspense, useState } from "react";
import { useSearchParams } from "next/navigation";
import { login } from "@/app/actions/auth";
import { Mail, Lock, AlertTriangle, Eye, EyeOff } from "lucide-react";
import { Logo } from "@/components/ui/Logo";
import { PARAM_DESTINO, caminhoInternoOuNulo } from "@/lib/login/destino";

function FormularioDeLogin() {
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [showPassword, setShowPassword] = useState(false);

  // O destino original de quem chegou aqui por um link estando deslogado
  // (issue #477, RN-54). Ele viaja até o server action pelo campo escondido
  // abaixo, que é o único canal que a action enxerga.
  const destino = caminhoInternoOuNulo(useSearchParams().get(PARAM_DESTINO));

  async function handleSubmit(formData: FormData) {
    setLoading(true);
    setError(null);
    const result = await login(formData);
    if (result?.error) {
      setError(result.error);
      setLoading(false);
    }
  }

  return (
    <main className="min-h-screen flex bg-bg">
      {/* Left decorative panel */}
      <div className="hidden lg:flex lg:w-1/2 bg-surface relative overflow-hidden items-center justify-center border-r border-border">
        <div className="absolute inset-0 opacity-10">
          <div className="absolute top-20 left-20 w-72 h-72 rounded-full border border-white/30" />
          <div className="absolute bottom-32 right-16 w-48 h-48 rounded-full border border-white/20" />
          <div className="absolute top-1/2 left-1/3 w-96 h-96 rounded-full border border-white/10" />
        </div>
        <div className="relative text-center text-white space-y-6 p-12 animate-fade-in-up">
          <div className="flex items-center justify-center mx-auto mb-8 p-10 bg-white/50 backdrop-blur-sm rounded-3xl shadow-sm border border-white/20">
            <Logo variant="default" size="lg" />
          </div>
          <p className="text-text-secondary max-w-sm mx-auto leading-relaxed text-lg font-medium">
            Gestão automatizada de atas e decisões com inteligência artificial.
          </p>
        </div>
      </div>

      {/* Right form panel */}
      <div className="flex-1 flex items-center justify-center p-8">
        <div className="w-full max-w-md animate-fade-in-up">
          {/* Mobile logo */}
          <div className="text-center mb-8 lg:hidden">
            <div className="flex items-center justify-center mx-auto mb-6">
              <Logo variant="default" size="sm" />
            </div>
          </div>

          <div className="mb-8">
            <h1 className="text-2xl font-bold text-text">Bem-vindo de volta</h1>
            <p className="text-text-secondary text-sm mt-1">
              Acesse o painel de gestão de reuniões
            </p>
          </div>

          <form action={handleSubmit} className="space-y-4">
            {destino && <input type="hidden" name={PARAM_DESTINO} value={destino} />}

            <div>
              <label className="block text-sm font-medium text-text mb-1.5">
                Email
              </label>
              <div className="relative">
                <Mail className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-text-secondary/50" />
                <input
                  id="email"
                  name="email"
                  type="email"
                  placeholder="seu@email.com"
                  required
                  autoComplete="email"
                  className="w-full pl-10 pr-4 py-3 rounded-xl border border-border bg-surface text-text placeholder:text-text-secondary/40 focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary transition-all"
                />
              </div>
            </div>

            <div>
              <label className="block text-sm font-medium text-text mb-1.5">
                Senha
              </label>
              <div className="relative">
                <Lock className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-text-secondary/50" />
                <input
                  id="password"
                  name="password"
                  type={showPassword ? "text" : "password"}
                  placeholder="••••••••"
                  required
                  autoComplete="current-password"
                  className="w-full pl-10 pr-11 py-3 rounded-xl border border-border bg-surface text-text placeholder:text-text-secondary/40 focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary transition-all"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  aria-label={showPassword ? "Ocultar senha" : "Mostrar senha"}
                  className="absolute right-3.5 top-1/2 -translate-y-1/2 text-text-secondary/50 hover:text-text-secondary transition-colors cursor-pointer"
                >
                  {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
              <div className="mt-1.5 text-right">
                <a
                  href="/reset-password"
                  className="text-sm text-primary hover:underline"
                >
                  Esqueci minha senha
                </a>
              </div>
            </div>

            {error && (
              <div className="flex items-center gap-2 px-4 py-3 rounded-xl bg-error/10 border border-error/20 text-error text-sm">
                <AlertTriangle className="w-4 h-4 flex-shrink-0" />
                {error}
              </div>
            )}

            <button
              type="submit"
              disabled={loading}
              className="w-full py-3 bg-gradient-to-r from-primary to-primary-dark text-white rounded-xl font-medium hover:shadow-premium-strong hover:-translate-y-0.5 transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:shadow-none disabled:hover:translate-y-0 cursor-pointer"
            >
              {loading ? "Entrando..." : "Entrar"}
            </button>
          </form>
        </div>
      </div>
    </main>
  );
}

/**
 * O `useSearchParams` do formulário exige limite de Suspense, e o padrão desta
 * casa é o mesmo do formulário público da Ouvidoria: componente interno com o
 * hook, invólucro exportado com o `fallback`.
 */
export default function LoginPage() {
  return (
    <Suspense fallback={<main className="min-h-screen bg-bg" />}>
      <FormularioDeLogin />
    </Suspense>
  );
}
