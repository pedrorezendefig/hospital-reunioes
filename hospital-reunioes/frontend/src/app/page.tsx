import Link from "next/link";
import { ArrowRight, LogIn, Activity } from "lucide-react";
import { Logo } from "@/components/ui/Logo";

export default function Home() {
  return (
    <main className="min-h-screen flex items-center justify-center bg-bg relative overflow-hidden">
      {/* Background decoration */}
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <div className="absolute -top-40 -right-40 w-[500px] h-[500px] rounded-full bg-gradient-to-br from-primary/8 to-primary-light/5 blur-3xl" />
        <div className="absolute -bottom-40 -left-40 w-[400px] h-[400px] rounded-full bg-gradient-to-tr from-secondary/6 to-primary/4 blur-3xl" />
      </div>

      <div className="text-center space-y-8 p-8 relative z-10 animate-fade-in-up">
        <Logo size="lg" className="mx-auto" />

        <div className="space-y-3">
          <h1 className="text-4xl font-bold text-text tracking-tight sr-only">
            Hospital Reuniões
          </h1>
          <p className="text-text-secondary text-lg max-w-md mx-auto leading-relaxed">
            Sistema de gestão automatizada do ciclo de vida de reuniões
            corporativas hospitalares.
          </p>
        </div>

        <div className="flex gap-4 justify-center">
          <Link
            href="/dashboard"
            className="group flex items-center gap-2 px-6 py-3 bg-gradient-to-r from-primary to-primary-dark text-white rounded-xl font-medium hover:shadow-premium-strong hover:-translate-y-0.5 transition-all duration-200 cursor-pointer"
          >
            Acessar Painel
            <ArrowRight className="w-4 h-4 group-hover:translate-x-0.5 transition-transform" />
          </Link>
          <Link
            href="/login"
            className="flex items-center gap-2 px-6 py-3 border border-border text-text rounded-xl font-medium hover:bg-surface hover:shadow-premium hover:-translate-y-0.5 transition-all duration-200 cursor-pointer"
          >
            <LogIn className="w-4 h-4" />
            Fazer Login
          </Link>
        </div>

        <div className="pt-8 flex gap-10 justify-center text-sm text-text-secondary">
          <div className="text-center">
            <div className="text-2xl font-bold text-primary">v0.1</div>
            <div className="mt-0.5">Protótipo</div>
          </div>
          <div className="text-center">
            <div className="flex items-center justify-center gap-1.5">
              <Activity className="w-5 h-5 text-success" />
              <span className="relative flex h-2.5 w-2.5">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-success/60" />
                <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-success" />
              </span>
            </div>
            <div className="mt-0.5">Sistema Online</div>
          </div>
        </div>
      </div>
    </main>
  );
}
