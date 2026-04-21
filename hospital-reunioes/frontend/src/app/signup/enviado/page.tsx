"use client";

import { Suspense } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import { Mail, CheckCircle2 } from "lucide-react";
import { Logo } from "@/components/ui/Logo";

function EnviadoContent() {
  const searchParams = useSearchParams();
  const email = searchParams.get("email") || "seu email";

  return (
    <main className="min-h-screen flex items-center justify-center bg-bg p-8">
      <div className="w-full max-w-md text-center animate-fade-in-up">
        {/* Logo */}
        <div className="flex justify-center mb-8">
          <Logo variant="default" size="sm" />
        </div>

        {/* Icon */}
        <div className="flex justify-center mb-6">
          <div className="w-20 h-20 rounded-full bg-primary/10 flex items-center justify-center">
            <Mail className="w-10 h-10 text-primary" />
          </div>
        </div>

        {/* Title */}
        <h1 className="text-2xl font-bold text-text mb-3">
          Verifique seu email!
        </h1>

        <p className="text-text-secondary text-sm leading-relaxed mb-6">
          Enviamos um link de confirmação para{" "}
          <strong className="text-text">{email}</strong>.
          <br />
          Clique no link para ativar sua conta e fazer login.
        </p>

        {/* Info box */}
        <div className="rounded-xl border border-border bg-surface p-4 space-y-2 text-left mb-8">
          <div className="flex items-start gap-2">
            <CheckCircle2 className="w-4 h-4 text-primary flex-shrink-0 mt-0.5" />
            <p className="text-sm text-text-secondary">
              O link expira em <strong className="text-text">24 horas</strong>.
            </p>
          </div>
          <div className="flex items-start gap-2">
            <CheckCircle2 className="w-4 h-4 text-primary flex-shrink-0 mt-0.5" />
            <p className="text-sm text-text-secondary">
              Verifique também a pasta de <strong className="text-text">Spam</strong> ou Lixo Eletrônico.
            </p>
          </div>
          <div className="flex items-start gap-2">
            <CheckCircle2 className="w-4 h-4 text-primary flex-shrink-0 mt-0.5" />
            <p className="text-sm text-text-secondary">
              Não recebeu? Aguarde alguns minutos e tente se{" "}
              <Link href="/signup" className="text-primary hover:underline font-medium">
                cadastrar novamente
              </Link>
              .
            </p>
          </div>
        </div>

        <Link
          href="/login"
          className="text-sm text-text-secondary hover:text-primary transition-colors"
        >
          Voltar para o login
        </Link>
      </div>
    </main>
  );
}

export default function EnviadoPage() {
  return (
    <Suspense fallback={<div className="min-h-screen flex items-center justify-center bg-bg" />}>
      <EnviadoContent />
    </Suspense>
  );
}
