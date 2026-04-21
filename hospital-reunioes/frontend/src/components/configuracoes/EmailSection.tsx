"use client";

import { Mail } from "lucide-react";

export default function EmailSection({ token: _token }: { token: string | null }) {
  return (
    <div className="bg-surface border border-border rounded-xl p-6">
      <div className="flex items-center gap-3 mb-3">
        <div className="p-2 rounded-lg bg-primary/10">
          <Mail className="w-5 h-5 text-primary" />
        </div>
        <h2 className="text-lg font-semibold text-text">Configurações de Email</h2>
      </div>
      <p className="text-sm text-text-secondary">
        Preferências pessoais de email em breve.
      </p>
    </div>
  );
}
