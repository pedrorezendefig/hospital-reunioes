"use client";

import Link from "next/link";
import { ArrowLeft, Library } from "lucide-react";
import { BibliotecaPops } from "@/components/pops/BibliotecaPops";

/**
 * Biblioteca (issue #87) — o repositório oficial e único dos POPs com
 * Versão Publicada, organizado por Setor, com o PDF assinado para download.
 * O escopo do perfil é aplicado pelo backend.
 */
export default function BibliotecaPage() {
  return (
    <div className="animate-fade-in-up space-y-8">
      <div className="flex items-center gap-3">
        <div className="p-2 rounded-xl bg-primary/10 text-primary">
          <Library className="w-6 h-6" />
        </div>
        <div className="flex-1">
          <h1 className="text-2xl font-bold text-text">Biblioteca</h1>
          <p className="text-sm text-text-secondary">
            POPs publicados — a versão oficial e assinada de cada procedimento, por Setor
          </p>
        </div>
        <Link
          href="/pops"
          className="inline-flex items-center gap-2 text-sm font-medium text-text-secondary hover:text-primary"
        >
          <ArrowLeft className="w-4 h-4" />
          Gestão de POPs
        </Link>
      </div>

      <BibliotecaPops />
    </div>
  );
}
