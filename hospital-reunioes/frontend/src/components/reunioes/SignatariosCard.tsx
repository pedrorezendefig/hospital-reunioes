"use client";

import { useCallback, useEffect, useState } from "react";
import { AlertCircle, CheckCircle2, Clock, ExternalLink, Mail, PenLine, RefreshCw, RotateCw } from "lucide-react";
import { createClient } from "@/lib/supabase/client";
import { useToast } from "@/components/ui/Toast";
import { usePolling } from "@/hooks/usePolling";
import { getErrorMessage } from "@/lib/errors";

interface Signatario {
  signer_id: string | null;
  nome: string;
  email: string;
  status: "signed" | "pending";
  signed_at: string | null;
}

interface SignatariosResponse {
  total: number;
  assinaram: number;
  envelope_id: string | null;
  signatarios: Signatario[];
  pendencias_criadas?: number;
  total_acoes?: number;
  modo_interno?: boolean;
  legacy_warning?: string;
  clicksign_url?: string;
}

interface Props {
  idReuniao: string;
  envelopeKey: string;
  enabled: boolean;
  pollIntervalMs?: number;
  /** Chamado quando a sincronização muda o desfecho da Reunião (finalizada ou modo interno). */
  onDesfecho?: () => void | Promise<void>;
}

const POLL_DEFAULT_MS = 30_000;
const REMIND_COOLDOWN_MS = 60_000;
// Espelha o cooldown curto do backend (endpoint sincronizar, issue #279)
const SYNC_COOLDOWN_MS = 60_000;

async function getToken(): Promise<string | undefined> {
  const supabase = createClient();
  const { data: { session } } = await supabase.auth.getSession();
  return session?.access_token;
}

function formatDateTime(iso: string | null): string {
  if (!iso) return "-";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const dia = d.toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" });
  const hora = d.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
  return `${dia} ${hora}`;
}

function formatRelative(d: Date): string {
  const diffSec = Math.floor((Date.now() - d.getTime()) / 1000);
  if (diffSec < 30) return "agora";
  if (diffSec < 60) return `${diffSec}s atrás`;
  if (diffSec < 3600) return `${Math.floor(diffSec / 60)}min atrás`;
  return `${Math.floor(diffSec / 3600)}h atrás`;
}

export function SignatariosCard({
  idReuniao,
  envelopeKey,
  enabled,
  pollIntervalMs = POLL_DEFAULT_MS,
  onDesfecho,
}: Props) {
  const { toast } = useToast();
  const [data, setData] = useState<SignatariosResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdate, setLastUpdate] = useState<Date | null>(null);
  const [remindingId, setRemindingId] = useState<string | null>(null);
  const [recentlyReminded, setRecentlyReminded] = useState<Record<string, number>>({});
  const [syncing, setSyncing] = useState(false);
  const [lastSyncAt, setLastSyncAt] = useState<number | null>(null);
  const [nowTick, setNowTick] = useState(0);

  // Tick a cada 10s só pra atualizar o texto "atualizado HHs atrás" e os cooldowns visuais.
  useEffect(() => {
    const id = setInterval(() => setNowTick((n) => n + 1), 10_000);
    return () => clearInterval(id);
  }, []);

  const fetchStatus = useCallback(
    async (manual: boolean) => {
      if (manual) setRefreshing(true);
      try {
        const token = await getToken();
        const res = await fetch(`/api/reunioes/${idReuniao}/signatarios/status`, {
          headers: token ? { Authorization: `Bearer ${token}` } : {},
        });
        if (!res.ok) {
          const body = await res.json().catch(() => ({}));
          throw new Error(body.detail || `HTTP ${res.status}`);
        }
        const fresh = (await res.json()) as SignatariosResponse;
        setData(fresh);
        setError(null);
        setLastUpdate(new Date());
      } catch (e) {
        setError(getErrorMessage(e) || "Não foi possível atualizar o status dos signatários.");
      } finally {
        setLoading(false);
        if (manual) setRefreshing(false);
      }
    },
    [idReuniao],
  );

  // Fetch inicial
  useEffect(() => {
    void fetchStatus(false);
  }, [fetchStatus]);

  // Polling automático
  usePolling(() => fetchStatus(false), pollIntervalMs, enabled);

  async function handleLembrar(signer: Signatario) {
    if (!signer.signer_id) return;
    setRemindingId(signer.signer_id);
    try {
      const token = await getToken();
      const res = await fetch(
        `/api/reunioes/${idReuniao}/signatarios/${signer.signer_id}/lembrar`,
        {
          method: "POST",
          headers: token ? { Authorization: `Bearer ${token}` } : {},
        },
      );
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        toast(body.detail || "Erro ao enviar lembrete", "error");
        return;
      }
      toast(`Lembrete enviado para ${signer.nome || signer.email}`, "success");
      setRecentlyReminded((prev) => ({ ...prev, [signer.signer_id!]: Date.now() }));
    } catch (e) {
      toast(getErrorMessage(e) || "Erro ao enviar lembrete", "error");
    } finally {
      setRemindingId(null);
    }
  }

  // Botão "Sincronizar" (issue #279, ADR 0030): força a reconciliação com a
  // ClickSign na hora. Documento fechado finaliza a ata; cancelado abre a
  // coleta interna de aceites. Mesmo fluxo do job diário, idempotente.
  async function handleSincronizar() {
    setSyncing(true);
    try {
      const token = await getToken();
      const res = await fetch(`/api/reunioes/${idReuniao}/signatarios/sincronizar`, {
        method: "POST",
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) {
        toast(body.detail || "Erro ao sincronizar com a ClickSign", "error");
        return;
      }
      setLastSyncAt(Date.now());
      if (body.desfecho === "finalizada") {
        toast("Documento fechado na ClickSign: ata finalizada.", "success");
        await onDesfecho?.();
      } else if (body.desfecho === "modo_interno") {
        toast("Envelope cancelado na ClickSign: o sistema passa a colher os aceites por dentro.", "success");
        await onDesfecho?.();
      } else {
        toast("Tudo em dia: o documento segue aguardando assinaturas na ClickSign.", "success");
      }
      await fetchStatus(false);
    } catch (e) {
      toast(getErrorMessage(e) || "Erro ao sincronizar com a ClickSign", "error");
    } finally {
      setSyncing(false);
    }
  }

  const isOnCooldown = (signerId: string): boolean => {
    const sentAt = recentlyReminded[signerId];
    if (!sentAt) return false;
    return Date.now() - sentAt < REMIND_COOLDOWN_MS;
  };

  const cooldownSentAt = (signerId: string): Date | null => {
    const sentAt = recentlyReminded[signerId];
    return sentAt ? new Date(sentAt) : null;
  };

  const total = data?.total ?? 0;
  const assinaram = data?.assinaram ?? 0;
  const modoInterno = Boolean(data?.modo_interno);
  // Modo interno: Envelope morto, nada a sincronizar na ClickSign
  const podeSincronizar = Boolean(data) && !modoInterno && !data?.legacy_warning;
  const syncOnCooldown = lastSyncAt !== null && Date.now() - lastSyncAt < SYNC_COOLDOWN_MS;
  // nowTick força re-render pro texto relativo atualizar sem mudar a referência do data
  void nowTick;

  return (
    <div className="bg-white rounded-2xl border border-border shadow-premium">
      <div className="flex items-center gap-3 px-6 py-4 border-b border-slate-100">
        <div
          className={`w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0 ${
            modoInterno ? "bg-amber-100" : "bg-blue-100"
          }`}
        >
          <PenLine className={`w-5 h-5 ${modoInterno ? "text-amber-600" : "text-blue-600"}`} />
        </div>
        <div className="flex-1 min-w-0">
          <h2 className="font-semibold text-slate-900">
            {modoInterno ? "Coleta interna de aceites" : "Aguardando assinatura digital"}
          </h2>
          {!loading && (
            <p className="text-xs text-slate-500 mt-0.5">
              <span className="font-medium text-slate-700">
                {assinaram} de {total}
              </span>{" "}
              {modoInterno
                ? total === 1
                  ? "firmou compromisso"
                  : "firmaram compromisso"
                : total === 1
                ? "assinou"
                : "assinaram"}
              {typeof data?.pendencias_criadas === "number" && typeof data?.total_acoes === "number" && (
                <span>
                  {" · "}Pendências criadas:{" "}
                  <span className="font-medium text-slate-700">
                    {data.pendencias_criadas} de {data.total_acoes}
                  </span>
                </span>
              )}
              {lastUpdate && (
                <span className="text-slate-400"> · atualizado {formatRelative(lastUpdate)}</span>
              )}
            </p>
          )}
        </div>
        {podeSincronizar && (
          <button
            type="button"
            onClick={() => void handleSincronizar()}
            disabled={syncing || syncOnCooldown || loading}
            aria-label="Sincronizar com a ClickSign"
            title={
              syncOnCooldown
                ? "Sincronizado há pouco. Aguarde um instante para conferir de novo."
                : "Conferir agora na ClickSign se o documento foi fechado ou cancelado"
            }
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-slate-600 hover:text-slate-900 hover:bg-slate-100 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <RotateCw className={`w-3.5 h-3.5 ${syncing ? "animate-spin" : ""}`} />
            {syncOnCooldown ? "Sincronizado" : "Sincronizar"}
          </button>
        )}
        <button
          type="button"
          onClick={() => void fetchStatus(true)}
          disabled={refreshing || loading}
          aria-label="Atualizar status dos signatários"
          className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-slate-600 hover:text-slate-900 hover:bg-slate-100 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${refreshing ? "animate-spin" : ""}`} />
          Atualizar
        </button>
      </div>

      <div className="px-6 py-4">
        {modoInterno && (
          <div className="mb-3 flex items-start gap-2 text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2">
            <AlertCircle className="w-3.5 h-3.5 flex-shrink-0 mt-0.5" />
            <span>
              O envelope de assinatura no ClickSign foi encerrado. O que já foi firmado continua valendo e o
              sistema segue colhendo o aceite dos demais por dentro, sem reenvio ao ClickSign.
            </span>
          </div>
        )}

        {loading ? (
          <SkeletonRows />
        ) : data?.signatarios.length === 0 ? (
          <p className="text-sm text-slate-400 italic">Nenhum signatário cadastrado.</p>
        ) : (
          <ul className="space-y-2">
            {data?.signatarios.map((s, i) => (
              <SignerRow
                key={s.signer_id || s.email || `idx-${i}`}
                signer={s}
                onLembrar={() => void handleLembrar(s)}
                reminding={remindingId === s.signer_id}
                onCooldown={s.signer_id ? isOnCooldown(s.signer_id) : false}
                cooldownSentAt={s.signer_id ? cooldownSentAt(s.signer_id) : null}
                legacy={Boolean(data?.legacy_warning)}
                modoInterno={modoInterno}
              />
            ))}
          </ul>
        )}

        {data?.legacy_warning && (
          <div className="mt-3 flex items-start gap-2 text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2">
            <AlertCircle className="w-3.5 h-3.5 flex-shrink-0 mt-0.5" />
            <div className="flex flex-col gap-1.5">
              <span>{data.legacy_warning}</span>
              {data.clicksign_url && (
                <a
                  href={data.clicksign_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1 w-fit font-medium text-amber-800 hover:text-amber-900 underline underline-offset-2"
                >
                  <ExternalLink className="w-3 h-3" />
                  Abrir no ClickSign
                </a>
              )}
            </div>
          </div>
        )}

        {error && (
          <div className="mt-3 flex items-start gap-2 text-xs text-slate-600 bg-slate-50 border border-slate-200 rounded-lg px-3 py-2">
            <AlertCircle className="w-3.5 h-3.5 flex-shrink-0 mt-0.5" />
            <span>{error}</span>
          </div>
        )}
      </div>

      <div className="px-6 py-3 border-t border-slate-100">
        <p className="text-[10px] text-slate-400 font-mono truncate" title={envelopeKey}>
          Envelope: {envelopeKey || "-"}
        </p>
      </div>
    </div>
  );
}

interface SignerRowProps {
  signer: Signatario;
  onLembrar: () => void;
  reminding: boolean;
  onCooldown: boolean;
  cooldownSentAt: Date | null;
  legacy: boolean;
  modoInterno: boolean;
}

function SignerRow({ signer, onLembrar, reminding, onCooldown, cooldownSentAt, legacy, modoInterno }: SignerRowProps) {
  const isSigned = signer.status === "signed";
  const initial = (signer.nome || signer.email || "?").charAt(0).toUpperCase();
  // Modo interno (ADR 0030): Envelope morto, nenhuma ação via ClickSign
  const podeLembrar = !isSigned && Boolean(signer.signer_id) && !legacy && !modoInterno;
  const lembrarDisabled = reminding || onCooldown;

  return (
    <li className="flex items-center gap-3 px-3 py-2 rounded-xl bg-slate-50 hover:bg-slate-100/70 transition-colors">
      <div
        className={`w-8 h-8 rounded-full flex items-center justify-center text-xs font-semibold flex-shrink-0 ${
          isSigned
            ? "bg-gradient-to-br from-emerald-200 to-emerald-300 text-emerald-800"
            : "bg-gradient-to-br from-amber-200 to-amber-300 text-amber-800"
        }`}
      >
        {initial}
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-slate-800 truncate">{signer.nome || "-"}</p>
        <p className="text-xs text-slate-400 truncate">{signer.email || "-"}</p>
      </div>

      {podeLembrar && (
        <button
          type="button"
          onClick={onLembrar}
          disabled={lembrarDisabled}
          aria-label={`Reenviar email de lembrete para ${signer.nome || signer.email}`}
          title={
            onCooldown && cooldownSentAt
              ? `Lembrete enviado às ${cooldownSentAt.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" })}`
              : legacy
              ? "Indisponível para reuniões enviadas antes da atualização"
              : "Reenviar email de assinatura"
          }
          className="flex items-center gap-1 px-2 py-1 text-[11px] font-medium text-slate-600 border border-slate-200 rounded-lg hover:bg-white hover:text-slate-900 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex-shrink-0"
        >
          {reminding ? (
            <RefreshCw className="w-3 h-3 animate-spin" />
          ) : (
            <Mail className="w-3 h-3" />
          )}
          {onCooldown ? "Enviado" : "Lembrar"}
        </button>
      )}

      {isSigned ? (
        <span
          aria-label={`Assinou em ${formatDateTime(signer.signed_at)}`}
          className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200 text-[11px] font-medium flex-shrink-0"
        >
          <CheckCircle2 className="w-3 h-3" />
          {formatDateTime(signer.signed_at)}
        </span>
      ) : (
        <span
          aria-label={modoInterno ? "Aguardando aceite" : "Pendente"}
          className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-amber-50 text-amber-700 border border-amber-200 text-[11px] font-medium flex-shrink-0"
        >
          <Clock className="w-3 h-3" />
          {modoInterno ? "Aguardando aceite" : "Pendente"}
        </span>
      )}
    </li>
  );
}

function SkeletonRows() {
  return (
    <ul className="space-y-2">
      {[0, 1, 2].map((i) => (
        <li key={i} className="flex items-center gap-3 px-3 py-2 rounded-xl bg-slate-50 animate-pulse">
          <div className="w-8 h-8 rounded-full bg-slate-200" />
          <div className="flex-1 space-y-1.5">
            <div className="h-3 bg-slate-200 rounded w-3/4" />
            <div className="h-2 bg-slate-200 rounded w-1/2" />
          </div>
          <div className="h-5 w-16 bg-slate-200 rounded-full" />
        </li>
      ))}
    </ul>
  );
}

export default SignatariosCard;
