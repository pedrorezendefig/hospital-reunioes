"use client";

import { useState } from "react";
import { Mail, AlertTriangle, CheckCircle } from "lucide-react";
import { Logo } from "@/components/ui/Logo";
import { createClient } from "@/lib/supabase/client";

export default function ResetPasswordPage() {
  const [loading, setLoading] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setLoading(true);
    setError(null);

    const form = new FormData(e.currentTarget);
    const email = form.get("email") as string;

    try {
      // O template recovery.html constrói o link manualmente usando {{ .SiteURL }}/reset-password/update?token_hash={{ .TokenHash }}&type=recovery,
      // então redirectTo não é necessário — o Supabase preenche SiteURL do config e o token_hash diretamente no email.
      const supabase = createClient();
      const { error: supabaseError } = await supabase.auth.resetPasswordForEmail(email);

      if (supabaseError) {
        setError("Erro ao enviar email. Tente novamente.");
        setLoading(false);
        return;
      }

      setSubmitted(true);
    } catch {
      setError("Erro de conexão. Verifique sua internet e tente novamente.");
    } finally {
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

          {submitted ? (
            <div className="space-y-6">
              <div className="flex flex-col items-center text-center space-y-4">
                <div className="w-16 h-16 rounded-full bg-green-100 flex items-center justify-center">
                  <CheckCircle className="w-8 h-8 text-green-600" />
                </div>
                <div>
                  <h1 className="text-2xl font-bold text-text">Verifique seu email</h1>
                  <p className="text-text-secondary text-sm mt-2 leading-relaxed">
                    Se o email existir no sistema, você receberá um link para redefinir sua senha.
                  </p>
                </div>
              </div>
              <a
                href="/login"
                className="block w-full py-3 text-center bg-gradient-to-r from-primary to-primary-dark text-white rounded-xl font-medium hover:shadow-premium-strong hover:-translate-y-0.5 transition-all duration-200"
              >
                Voltar ao login
              </a>
            </div>
          ) : (
            <>
              <div className="mb-8">
                <h1 className="text-2xl font-bold text-text">Esqueci minha senha</h1>
                <p className="text-text-secondary text-sm mt-1">
                  Informe seu email para receber o link de redefinição de senha.
                </p>
              </div>

              <form onSubmit={handleSubmit} className="space-y-4">
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
                  {loading ? "Enviando..." : "Enviar link de redefinição"}
                </button>

                <p className="text-center text-sm text-text-secondary">
                  Lembrou a senha?{" "}
                  <a href="/login" className="text-primary font-medium hover:underline">
                    Voltar ao login
                  </a>
                </p>
              </form>
            </>
          )}
        </div>
      </div>
    </main>
  );
}
