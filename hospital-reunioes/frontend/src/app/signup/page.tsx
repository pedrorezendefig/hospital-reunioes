"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import {
  User,
  Mail,
  Lock,
  Briefcase,
  KeyRound,
  AlertTriangle,
  ChevronDown,
  Building2,
  Shield,
  Eye,
  EyeOff,
} from "lucide-react";
import { Logo } from "@/components/ui/Logo";
import { CARGOS_LIST, getCargoInfo, ROLE_LABELS, type CargoInfo } from "@/lib/onboarding-data";

export default function SignupPage() {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [preview, setPreview] = useState<CargoInfo | null>(null);
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);
  const [showPasse, setShowPasse] = useState(false);

  function handleCargoChange(e: React.ChangeEvent<HTMLSelectElement>) {
    const info = getCargoInfo(e.target.value);
    setPreview(info ?? null);
  }

  async function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setLoading(true);
    setError(null);

    const form = new FormData(e.currentTarget);
    const nome_completo = form.get("nome_completo") as string;
    const email = form.get("email") as string;
    const senha = form.get("senha") as string;
    const confirmar_senha = form.get("confirmar_senha") as string;
    const cargo = form.get("cargo") as string;
    const passe = form.get("passe") as string;

    if (senha !== confirmar_senha) {
      setError("As senhas não coincidem. Verifique e tente novamente.");
      setLoading(false);
      return;
    }

    if (senha.length < 8) {
      setError("A senha deve ter pelo menos 8 caracteres.");
      setLoading(false);
      return;
    }

    try {
      const res = await fetch("/api/signup/register", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ nome_completo, email, senha, cargo, passe }),
      });

      let data;
      try {
        data = await res.json();
      } catch {
        setError("Erro inesperado do servidor. Tente novamente.");
        setLoading(false);
        return;
      }

      if (!res.ok) {
        setError(data.detail || data.error || "Erro ao criar conta. Tente novamente.");
        setLoading(false);
        return;
      }

      // Sucesso — redirecionar para página de "verifique seu email"
      router.push(`/signup/enviado?email=${encodeURIComponent(email)}`);
    } catch (err) {
      setError("Erro de conexão. Verifique sua internet e tente novamente.");
      setLoading(false);
    }
  }

  return (
    <main className="min-h-screen flex bg-bg">
      {/* Left decorative panel */}
      <div className="hidden lg:flex lg:w-1/2 bg-gradient-to-br from-primary via-primary-dark to-secondary relative overflow-hidden items-center justify-center">
        <div className="absolute inset-0 opacity-10">
          <div className="absolute top-20 left-20 w-72 h-72 rounded-full border border-white/30" />
          <div className="absolute bottom-32 right-16 w-48 h-48 rounded-full border border-white/20" />
          <div className="absolute top-1/2 left-1/3 w-96 h-96 rounded-full border border-white/10" />
        </div>
        <div className="relative text-center text-white space-y-4 p-12 animate-fade-in-up">
          <div className="flex items-center justify-center mx-auto mb-8">
            <Logo variant="white" size="md" />
          </div>
          <h2 className="text-2xl font-bold">Crie sua conta</h2>
          <p className="text-white/80 max-w-sm mx-auto leading-relaxed text-base font-medium">
            Acesse a plataforma de gestão de atas e decisões do hospital.
          </p>
          <div className="mt-8 space-y-3 text-left max-w-xs mx-auto">
            {[
              "Gestão automatizada de atas",
              "Acompanhamento de pendências",
              "Acesso hierárquico por cargo",
            ].map((item) => (
              <div key={item} className="flex items-center gap-2 text-white/80 text-sm">
                <div className="w-5 h-5 rounded-full bg-white/20 flex items-center justify-center flex-shrink-0">
                  <span className="text-white text-xs">✓</span>
                </div>
                {item}
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Right form panel */}
      <div className="flex-1 flex items-center justify-center p-8 overflow-y-auto">
        <div className="w-full max-w-md animate-fade-in-up py-8">
          {/* Mobile logo */}
          <div className="text-center mb-6 lg:hidden">
            <Logo variant="default" size="sm" />
          </div>

          <div className="mb-6">
            <h1 className="text-2xl font-bold text-text">Criar nova conta</h1>
            <p className="text-text-secondary text-sm mt-1">
              Preencha os dados abaixo para solicitar acesso ao sistema.
            </p>
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            {/* Nome completo */}
            <div>
              <label className="block text-sm font-medium text-text mb-1.5">
                Nome completo
              </label>
              <div className="relative">
                <User className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-text-secondary/50" />
                <input
                  id="nome_completo"
                  name="nome_completo"
                  type="text"
                  placeholder="Seu nome completo"
                  required
                  autoComplete="name"
                  className="w-full pl-10 pr-4 py-3 rounded-xl border border-border bg-surface text-text placeholder:text-text-secondary/40 focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary transition-all"
                />
              </div>
            </div>

            {/* Email */}
            <div>
              <label className="block text-sm font-medium text-text mb-1.5">
                Email institucional
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

            {/* Senha */}
            <div>
              <label className="block text-sm font-medium text-text mb-1.5">
                Senha
              </label>
              <div className="relative">
                <Lock className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-text-secondary/50" />
                <input
                  id="senha"
                  name="senha"
                  type={showPassword ? "text" : "password"}
                  placeholder="Mínimo 8 caracteres"
                  required
                  autoComplete="new-password"
                  className="w-full pl-10 pr-11 py-3 rounded-xl border border-border bg-surface text-text placeholder:text-text-secondary/40 focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary transition-all"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3.5 top-1/2 -translate-y-1/2 text-text-secondary/50 hover:text-text-secondary transition-colors"
                >
                  {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
            </div>

            {/* Confirmar senha */}
            <div>
              <label className="block text-sm font-medium text-text mb-1.5">
                Confirmar senha
              </label>
              <div className="relative">
                <Lock className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-text-secondary/50" />
                <input
                  id="confirmar_senha"
                  name="confirmar_senha"
                  type={showConfirm ? "text" : "password"}
                  placeholder="Repita sua senha"
                  required
                  autoComplete="new-password"
                  className="w-full pl-10 pr-11 py-3 rounded-xl border border-border bg-surface text-text placeholder:text-text-secondary/40 focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary transition-all"
                />
                <button
                  type="button"
                  onClick={() => setShowConfirm(!showConfirm)}
                  className="absolute right-3.5 top-1/2 -translate-y-1/2 text-text-secondary/50 hover:text-text-secondary transition-colors"
                >
                  {showConfirm ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
            </div>

            {/* Cargo */}
            <div>
              <label htmlFor="cargo" className="block text-sm font-medium text-text mb-1.5">
                Cargo
              </label>
              <div className="relative">
                <Briefcase className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-text-secondary/50 pointer-events-none" />
                <select
                  id="cargo"
                  name="cargo"
                  required
                  defaultValue=""
                  onChange={handleCargoChange}
                  className="w-full pl-10 pr-10 py-3 rounded-xl border border-border bg-surface text-text focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary transition-all appearance-none cursor-pointer"
                >
                  <option value="" disabled>
                    Selecione seu cargo
                  </option>
                  {CARGOS_LIST.map((c) => (
                    <option key={c.label} value={c.label}>
                      {c.label}
                    </option>
                  ))}
                </select>
                <ChevronDown className="absolute right-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-text-secondary/50 pointer-events-none" />
              </div>
            </div>

            {/* Preview automático de setor/acesso */}
            {preview && (
              <div className="rounded-xl border border-primary/20 bg-primary/5 p-4 space-y-3 animate-fade-in-up">
                <p className="text-xs font-semibold text-primary uppercase tracking-wide">
                  Configurado automaticamente
                </p>
                <div className="flex items-center gap-3">
                  <Building2 className="w-4 h-4 text-text-secondary flex-shrink-0" />
                  <div>
                    <p className="text-xs text-text-secondary">Setor</p>
                    <p className="text-sm font-medium text-text">{preview.setor}</p>
                  </div>
                </div>
                <div className="flex items-center gap-3">
                  <Shield className="w-4 h-4 text-text-secondary flex-shrink-0" />
                  <div>
                    <p className="text-xs text-text-secondary">Nível de Acesso</p>
                    <p className="text-sm font-medium text-text">{ROLE_LABELS[preview.role]}</p>
                  </div>
                </div>
              </div>
            )}

            {/* Passe */}
            <div>
              <label className="block text-sm font-medium text-text mb-1.5">
                Código Passe{" "}
                <span className="text-text-secondary/60 font-normal text-xs">
                  (solicite ao administrador)
                </span>
              </label>
              <div className="relative">
                <KeyRound className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-text-secondary/50" />
                <input
                  id="passe"
                  name="passe"
                  type={showPasse ? "text" : "password"}
                  placeholder="Digite o código de acesso"
                  required
                  maxLength={10}
                  className="w-full pl-10 pr-11 py-3 rounded-xl border border-border bg-surface text-text placeholder:text-text-secondary/40 focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary transition-all"
                />
                <button
                  type="button"
                  onClick={() => setShowPasse(!showPasse)}
                  className="absolute right-3.5 top-1/2 -translate-y-1/2 text-text-secondary/50 hover:text-text-secondary transition-colors"
                >
                  {showPasse ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
            </div>

            {/* Error */}
            {error && (
              <div className="flex items-center gap-2 px-4 py-3 rounded-xl bg-error/10 border border-error/20 text-error text-sm">
                <AlertTriangle className="w-4 h-4 flex-shrink-0" />
                {error}
              </div>
            )}

            {/* Submit */}
            <button
              type="submit"
              disabled={loading || !preview}
              className="w-full py-3 bg-gradient-to-r from-primary to-primary-dark text-white rounded-xl font-medium hover:shadow-premium-strong hover:-translate-y-0.5 transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:shadow-none disabled:hover:translate-y-0 cursor-pointer mt-2"
            >
              {loading ? "Criando conta..." : "Criar Conta"}
            </button>

            <p className="text-center text-sm text-text-secondary">
              Já tem conta?{" "}
              <Link href="/login" className="text-primary font-medium hover:underline">
                Fazer login
              </Link>
            </p>
          </form>
        </div>
      </div>
    </main>
  );
}
