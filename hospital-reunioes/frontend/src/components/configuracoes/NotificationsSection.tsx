"use client";

import { useState, useEffect, useCallback } from "react";
import { Bell, Loader2 } from "lucide-react";
import { useToast } from "@/components/ui/Toast";

// ─── Types ────────────────────────────────────────────────────────────────────

interface NotificacoesPrefs {
  mencao: boolean;
  prazo_proximo: boolean;
  comentario: boolean;
  responsavel_atribuido: boolean;
}

interface ToggleConfig {
  key: keyof NotificacoesPrefs;
  title: string;
  description: string;
}

const TOGGLES: ToggleConfig[] = [
  {
    key: "mencao",
    title: "Menções em comentários",
    description: "Receba notificações quando alguém mencionar você em um comentário",
  },
  {
    key: "prazo_proximo",
    title: "Prazos próximos",
    description: "Seja avisado quando uma pendência estiver perto do prazo",
  },
  {
    key: "comentario",
    title: "Novos comentários",
    description: "Notificações sobre novos comentários em reuniões que você participa",
  },
  {
    key: "responsavel_atribuido",
    title: "Atribuição de pendências",
    description: "Seja notificado quando uma pendência for atribuída a você",
  },
];

const DEFAULTS: NotificacoesPrefs = {
  mencao: true,
  prazo_proximo: true,
  comentario: true,
  responsavel_atribuido: true,
};

// ─── Component ────────────────────────────────────────────────────────────────

export default function NotificationsSection({ token }: { token: string | null }) {
  const { toast } = useToast();
  const [prefs, setPrefs] = useState<NotificacoesPrefs>(DEFAULTS);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  // Fetch current preferences
  useEffect(() => {
    if (!token) return;

    async function fetchPrefs() {
      try {
        const res = await fetch("/api/configuracoes", {
          headers: { Authorization: `Bearer ${token}` },
        });

        if (res.ok) {
          const data = await res.json();
          if (data.notificacoes) {
            setPrefs({ ...DEFAULTS, ...data.notificacoes });
          }
        }
      } catch {
        // Keep defaults
      } finally {
        setLoading(false);
      }
    }

    fetchPrefs();
  }, [token]);

  // Save preferences
  const savePrefs = useCallback(
    async (updated: NotificacoesPrefs) => {
      if (!token) return;
      setSaving(true);

      try {
        const res = await fetch("/api/configuracoes", {
          method: "PATCH",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${token}`,
          },
          body: JSON.stringify({ notificacoes: updated }),
        });

        if (!res.ok) {
          toast("Erro ao salvar preferências.", "error");
          return;
        }

        toast("Preferências salvas!", "success");
      } catch {
        toast("Erro ao salvar preferências.", "error");
      } finally {
        setSaving(false);
      }
    },
    [token, toast]
  );

  function handleToggle(key: keyof NotificacoesPrefs) {
    const updated = { ...prefs, [key]: !prefs[key] };
    setPrefs(updated);
    savePrefs(updated);
  }

  // ─── Loading ────────────────────────────────────────────────────────────

  if (loading) {
    return (
      <div className="bg-white rounded-2xl border border-border shadow-premium p-6 animate-fade-in-up">
        <div className="flex items-center justify-center py-12">
          <Loader2 className="w-6 h-6 text-primary animate-spin" />
        </div>
      </div>
    );
  }

  // ─── Render ─────────────────────────────────────────────────────────────

  return (
    <div className="bg-white rounded-2xl border border-border shadow-premium p-6 animate-fade-in-up">
      {/* Header */}
      <div className="flex items-center gap-3 mb-1">
        <div className="p-2 rounded-xl bg-primary/10">
          <Bell className="w-5 h-5 text-primary" />
        </div>
        <div className="flex items-center gap-3">
          <h2 className="text-lg font-bold text-text">Notificações</h2>
          {saving && <Loader2 className="w-4 h-4 text-primary animate-spin" />}
        </div>
      </div>
      <p className="text-text-secondary text-sm mb-6 ml-[44px]">
        Controle quais notificações você deseja receber no sistema
      </p>

      {/* Toggles */}
      <div className="space-y-1">
        {TOGGLES.map((toggle, idx) => (
          <div
            key={toggle.key}
            className={`flex items-center justify-between py-4 px-2 ${
              idx < TOGGLES.length - 1 ? "border-b border-border/50" : ""
            }`}
          >
            <div>
              <p className="text-sm font-medium text-text">{toggle.title}</p>
              <p className="text-xs text-text-secondary mt-0.5">
                {toggle.description}
              </p>
            </div>
            <ToggleSwitch
              checked={prefs[toggle.key]}
              onChange={() => handleToggle(toggle.key)}
            />
          </div>
        ))}
      </div>
    </div>
  );
}

// ─── Toggle Switch ────────────────────────────────────────────────────────────

function ToggleSwitch({
  checked,
  onChange,
}: {
  checked: boolean;
  onChange: () => void;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      onClick={onChange}
      className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors duration-200 focus:outline-none focus:ring-2 focus:ring-primary/20 cursor-pointer ${
        checked ? "bg-primary" : "bg-slate-200"
      }`}
    >
      <span
        className={`inline-block h-4 w-4 rounded-full bg-white shadow-sm transition-transform duration-200 ${
          checked ? "translate-x-6" : "translate-x-1"
        }`}
      />
    </button>
  );
}
