"use client";

import { useEffect, useState, Suspense } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import Link from "next/link";
import { CheckCircle2, AlertTriangle, Loader2 } from "lucide-react";
import { Logo } from "@/components/ui/Logo";

type Status = "loading" | "success" | "error";

function ConfirmarContent() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const token = searchParams.get("token");

  const [status, setStatus] = useState<Status>("loading");
  const [message, setMessage] = useState("");

  useEffect(() => {
    if (!token) {
      setStatus("error");
      setMessage("Link de confirmação inválido. Verifique o link recebido por email.");
      return;
    }

    const confirm = async () => {
      try {
        const res = await fetch(`/api/signup/verify/${token}`);
        const data = await res.json();

        if (res.ok && data.success) {
          setStatus("success");
          setMessage(data.message || "Conta criada com sucesso!");
          // Redirecionar para login após 3 segundos
          setTimeout(() => router.push("/login"), 3000);
        } else {
          setStatus("error");
          setMessage(data.detail || "Erro ao confirmar email. O link pode ter expirado.");
        }
      } catch {
        setStatus("error");
        setMessage("Erro de conexão. Verifique sua internet e tente novamente.");
      }
    };

    confirm();
  }, [token, router]);

  return (
    <main className="min-h-screen flex items-center justify-center bg-bg p-8">
      <div className="w-full max-w-md text-center animate-fade-in-up">
        {/* Logo */}
        <div className="flex justify-center mb-8">
          <Logo variant="default" size="sm" />
        </div>

        {status === "loading" && (
          <>
            <div className="flex justify-center mb-6">
              <div className="w-20 h-20 rounded-full bg-primary/10 flex items-center justify-center">
                <Loader2 className="w-10 h-10 text-primary animate-spin" />
              </div>
            </div>
            <h1 className="text-2xl font-bold text-text mb-3">Confirmando seu email...</h1>
            <p className="text-text-secondary text-sm">Por favor, aguarde um momento.</p>
          </>
        )}

        {status === "success" && (
          <>
            <div className="flex justify-center mb-6">
              <div className="w-20 h-20 rounded-full bg-success/10 flex items-center justify-center">
                <CheckCircle2 className="w-10 h-10 text-success" />
              </div>
            </div>
            <h1 className="text-2xl font-bold text-text mb-3">Conta criada!</h1>
            <p className="text-text-secondary text-sm leading-relaxed mb-6">
              {message}
              <br />
              <span className="text-primary font-medium">
                Você será redirecionado para o login em instantes...
              </span>
            </p>
            <Link
              href="/login"
              className="inline-block py-3 px-8 bg-gradient-to-r from-primary to-primary-dark text-white rounded-xl font-medium hover:shadow-premium-strong hover:-translate-y-0.5 transition-all duration-200"
            >
              Ir para o Login
            </Link>
          </>
        )}

        {status === "error" && (
          <>
            <div className="flex justify-center mb-6">
              <div className="w-20 h-20 rounded-full bg-error/10 flex items-center justify-center">
                <AlertTriangle className="w-10 h-10 text-error" />
              </div>
            </div>
            <h1 className="text-2xl font-bold text-text mb-3">Erro na confirmação</h1>
            <p className="text-text-secondary text-sm leading-relaxed mb-6">{message}</p>
            <div className="flex flex-col gap-3">
              <Link
                href="/signup"
                className="inline-block py-3 px-8 bg-gradient-to-r from-primary to-primary-dark text-white rounded-xl font-medium hover:shadow-premium-strong hover:-translate-y-0.5 transition-all duration-200"
              >
                Tentar novo cadastro
              </Link>
              <Link
                href="/login"
                className="text-sm text-text-secondary hover:text-primary transition-colors"
              >
                Voltar para o login
              </Link>
            </div>
          </>
        )}
      </div>
    </main>
  );
}

export default function ConfirmarPage() {
  return (
    <Suspense fallback={<div className="min-h-screen flex items-center justify-center bg-bg" />}>
      <ConfirmarContent />
    </Suspense>
  );
}
