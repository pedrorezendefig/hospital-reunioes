"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { createClient } from "@/lib/supabase/client";
import { useToast } from "@/components/ui/Toast";
import { isSuperAdmin } from "@/lib/auth";
import type { StatusPendencia, TipoReuniao } from "@/types";
import {
  FileUp,
  Upload,
  ArrowLeft,
  Loader2,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  Clock4,
  Eye,
  X,
  Trash2,
  ShieldAlert,
  Link2,
  User,
  Briefcase,
  Calendar,
  Target,
  Plus,
  Users,
  Sparkles,
} from "lucide-react";

const TIPOS_REUNIAO: TipoReuniao[] = [
  "Diretoria",
  "Gerencial",
  "Coordenação",
  "Mensal",
  "Extraordinária",
];

const STATUS_PENDENCIA: StatusPendencia[] = [
  "PENDENTE",
  "EM_PROGRESSO",
  "CONCLUIDO",
  "ATRASADO",
  "CANCELADO",
  "REPACTUADA",
];

// ──────────────────────────────────────────
// Types sincronizados com backend
// ──────────────────────────────────────────
type MetadadosImportacao = {
  titulo: string;
  tipo: TipoReuniao;
  data: string; // ISO YYYY-MM-DD
  hora_inicio?: string | null;
  hora_fim?: string | null;
  facilitador_id?: string | null;
  assunto?: string | null;
  objetivo?: string | null;
};

type ParticipanteMatchedPreview = {
  nome: string;
  participante_id: string;
  cargo?: string | null;
};

type ParticipanteExternoPreview = {
  nome: string;
  cargo: string;
  setor?: string | null;
  email?: string | null;
};

type PendenciaImportacao = {
  acao: string;
  responsavel_nome: string;
  responsavel_id?: string | null;
  responsavel_externo_idx?: number | null;
  cargo?: string | null;
  prazo?: string | null;
  prazo_original?: string | null;
  meta_entregavel?: string | null;
  status: StatusPendencia;
  co_responsavel_id?: string | null;
};

type ResponsavelTarget =
  | { tipo: "interno"; id: string; nome: string; cargo?: string | null }
  | { tipo: "externo"; idx: number; nome: string }
  | { tipo: "novo-externo"; nome: string };

type ParticipanteOption = {
  id: string;
  nome: string;
  cargo: string | null;
  isExterno: boolean;
};

type AtaMigradaPreview = {
  arquivo_hash: string;
  documento_id_origem?: string | null;
  nome_arquivo_original: string;
  metadados: MetadadosImportacao;
  participantes_matched: ParticipanteMatchedPreview[];
  participantes_externos: ParticipanteExternoPreview[];
  pendencias: PendenciaImportacao[];
  registro_narrativo?: string | null;
  resumo_executivo?: string | null;
  paginas: number;
  is_mock: boolean;
};

type DuplicataInfo = {
  id_reuniao: string;
  titulo?: string;
  data?: string;
  motivo?: string;
};

type FileMeta = {
  name: string;
  size: number;
};

type ItemFila = {
  id: string;
  file: File | null;
  fileMeta: FileMeta;
  status: "na_fila" | "processando" | "pronto" | "duplicado" | "erro" | "importado";
  preview?: AtaMigradaPreview;
  duplicata?: DuplicataInfo;
  erro?: string;
  id_reuniao_criada?: string;
};

type ParticipanteInterno = {
  id: string;
  nome_completo: string;
  email: string;
  cargo?: string;
  setor?: string;
  is_externo?: boolean;
};

type HistoricoItem = {
  id_reuniao: string;
  titulo?: string | null;
  data?: string | null;
  documento_id_origem?: string | null;
  nome_arquivo_original?: string | null;
  total_pendencias: number;
  importado_por_id?: string | null;
  importado_por_nome?: string | null;
  importado_em?: string | null;
};

// ──────────────────────────────────────────
// Helpers
// ──────────────────────────────────────────
function uuid(): string {
  return `${Math.random().toString(36).slice(2)}${Date.now().toString(36)}`;
}

function formatBytes(b: number): string {
  if (b < 1024) return `${b} B`;
  if (b < 1024 * 1024) return `${(b / 1024).toFixed(1)} KB`;
  return `${(b / 1024 / 1024).toFixed(1)} MB`;
}

// SHA-256 do conteúdo do PDF (hex, igual ao que o backend calcula com hashlib).
async function sha256Hex(file: File): Promise<string> {
  const buf = await file.arrayBuffer();
  const hash = await crypto.subtle.digest("SHA-256", buf);
  return [...new Uint8Array(hash)]
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

// ──────────────────────────────────────────
// Persistência do rascunho da fila em localStorage (sobrevive a navegação).
// Grava apenas itens com preview pronto — descarta File (não serializa).
// Ao voltar à página, rehidrata; para confirmar, usuário re-anexa o PDF.
// ──────────────────────────────────────────
const RASCUNHO_LS_KEY = "hospital:importacao:rascunhos:v1";

type ItemFilaSerializado = Omit<ItemFila, "file"> & { _hasFile: false };

function serializarFila(fila: ItemFila[]): ItemFilaSerializado[] {
  return fila
    .filter((i) => i.status === "pronto" && !!i.preview)
    .map((i) => ({
      id: i.id,
      fileMeta: i.fileMeta,
      status: i.status,
      preview: i.preview,
      duplicata: i.duplicata,
      erro: i.erro,
      id_reuniao_criada: i.id_reuniao_criada,
      _hasFile: false,
    }));
}

function carregarRascunhos(): ItemFila[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(RASCUNHO_LS_KEY);
    if (!raw) return [];
    const items = JSON.parse(raw) as ItemFilaSerializado[];
    return items.map<ItemFila>((it) => ({
      id: it.id,
      file: null,
      fileMeta: it.fileMeta,
      status: it.status,
      preview: it.preview,
      duplicata: it.duplicata,
      erro: it.erro,
      id_reuniao_criada: it.id_reuniao_criada,
    }));
  } catch {
    return [];
  }
}

function persistirRascunhos(fila: ItemFila[]) {
  if (typeof window === "undefined") return;
  try {
    const payload = serializarFila(fila);
    if (payload.length === 0) {
      window.localStorage.removeItem(RASCUNHO_LS_KEY);
    } else {
      window.localStorage.setItem(RASCUNHO_LS_KEY, JSON.stringify(payload));
    }
  } catch {
    // localStorage indisponível — ignore
  }
}

// ──────────────────────────────────────────
// Main Page
// ──────────────────────────────────────────
export default function ImportarAtasPage() {
  const router = useRouter();
  const { toast } = useToast();

  const [token, setToken] = useState<string | null>(null);
  const [userEmail, setUserEmail] = useState<string | null>(null);
  const [isChecking, setIsChecking] = useState(true);
  const [isSuper, setIsSuper] = useState(false);
  const [participantesInternos, setParticipantesInternos] = useState<ParticipanteInterno[]>([]);
  const [participantesTodos, setParticipantesTodos] = useState<ParticipanteInterno[]>([]);

  const [fila, setFila] = useState<ItemFila[]>([]);
  const [ativo, setAtivo] = useState<string | null>(null); // id do ItemFila em preview
  const [dragging, setDragging] = useState(false);
  const [confirmando, setConfirmando] = useState(false);
  const [historico, setHistorico] = useState<HistoricoItem[]>([]);
  const [historicoLoading, setHistoricoLoading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const fetchHistorico = useCallback(async (jwt: string | null) => {
    if (!jwt) return;
    setHistoricoLoading(true);
    try {
      const res = await fetch("/api/reunioes/importacao/historico?limit=20", {
        headers: { Authorization: `Bearer ${jwt}` },
      });
      if (!res.ok) return;
      const data: HistoricoItem[] = await res.json();
      setHistorico(data);
    } catch {
      // histórico é auxiliar: falha silenciosa não bloqueia importação
    } finally {
      setHistoricoLoading(false);
    }
  }, []);

  // Fetch session + participante atual (is_super_admin) + lista participantes
  useEffect(() => {
    async function init() {
      const supabase = createClient();
      const {
        data: { session },
      } = await supabase.auth.getSession();
      if (!session) {
        router.replace("/login");
        return;
      }
      setToken(session.access_token);
      setUserEmail(session.user.email ?? null);

      // Fetch participantes (inclui o user atual p/ checar is_super_admin)
      try {
        const res = await fetch("/api/participantes", {
          headers: { Authorization: `Bearer ${session.access_token}` },
        });
        if (!res.ok) throw new Error("Falha ao carregar participantes");
        const all: Array<ParticipanteInterno & { is_super_admin?: boolean }> = await res.json();
        setParticipantesInternos(all.filter((p) => !p.is_externo));
        setParticipantesTodos(all);
        const me = all.find((p) => p.email === session.user.email);
        setIsSuper(isSuperAdmin(me ?? null));
      } catch (err) {
        console.error(err);
        toast("Não foi possível verificar suas permissões.", "error");
      } finally {
        setIsChecking(false);
      }
    }
    init();
  }, [router, toast]);

  // Se não for super admin, redireciona após check concluir
  useEffect(() => {
    if (!isChecking && !isSuper) {
      toast("Apenas super admins podem importar ATAs.", "error");
      const t = setTimeout(() => router.replace("/reunioes"), 1200);
      return () => clearTimeout(t);
    }
  }, [isChecking, isSuper, router, toast]);

  // Busca o histórico de importações quando o token e a permissão estão prontos
  useEffect(() => {
    if (!token || !isSuper) return;
    void fetchHistorico(token);
  }, [token, isSuper, fetchHistorico]);

  // Rehidrata rascunhos de extração persistidos em localStorage ao montar.
  // Itens rehidratados têm file=null — usuário precisa re-anexar o PDF para confirmar.
  useEffect(() => {
    const restaurados = carregarRascunhos();
    if (restaurados.length === 0) return;
    setFila((prev) => {
      const existentes = new Set(prev.map((i) => i.id));
      return [...prev, ...restaurados.filter((r) => !existentes.has(r.id))];
    });
    setAtivo((cur) => cur ?? restaurados[0]?.id ?? null);
  }, []);

  // Persiste a fila a cada mudança (serializa apenas itens em "pronto" com preview).
  useEffect(() => {
    persistirRascunhos(fila);
  }, [fila]);

  // ─────── Drop handlers ───────
  const addFiles = useCallback((fs: File[]) => {
    const pdfs = fs.filter((f) => f.name.toLowerCase().endsWith(".pdf"));
    if (pdfs.length === 0) {
      toast("Apenas arquivos PDF são aceitos.", "error");
      return;
    }
    setFila((prev) => [
      ...prev,
      ...pdfs.map<ItemFila>((f) => ({
        id: uuid(),
        file: f,
        fileMeta: { name: f.name, size: f.size },
        status: "na_fila",
      })),
    ]);
  }, [toast]);

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragging(false);
    addFiles(Array.from(e.dataTransfer.files));
  };

  const onFileInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files ? Array.from(e.target.files) : [];
    addFiles(files);
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  // ─────── Processar item (chamar /preparar) ───────
  const processarItem = useCallback(
    async (itemId: string) => {
      if (!token) return;
      setFila((prev) => prev.map((i) => (i.id === itemId ? { ...i, status: "processando" } : i)));

      const item = fila.find((i) => i.id === itemId);
      const file = item?.file;
      if (!file) return;

      try {
        const fd = new FormData();
        fd.append("file", file);
        const res = await fetch("/api/reunioes/importacao/preparar", {
          method: "POST",
          headers: { Authorization: `Bearer ${token}` },
          body: fd,
        });

        if (res.status === 409) {
          const body = await res.json().catch(() => ({}));
          const detail = body?.detail ?? {};
          setFila((prev) =>
            prev.map((i) =>
              i.id === itemId
                ? {
                    ...i,
                    status: "duplicado",
                    duplicata: {
                      id_reuniao: detail.id_reuniao_existente,
                      titulo: detail.titulo,
                      data: detail.data,
                      motivo: detail.motivo,
                    },
                  }
                : i,
            ),
          );
          return;
        }

        if (!res.ok) {
          const body = await res.json().catch(() => ({}));
          const msg = typeof body?.detail === "string"
            ? body.detail
            : `HTTP ${res.status}`;
          setFila((prev) =>
            prev.map((i) => (i.id === itemId ? { ...i, status: "erro", erro: msg } : i)),
          );
          return;
        }

        const preview: AtaMigradaPreview = await res.json();
        setFila((prev) =>
          prev.map((i) => (i.id === itemId ? { ...i, status: "pronto", preview } : i)),
        );
        // Se nenhum ainda estava ativo, abre este automaticamente
        setAtivo((cur) => cur ?? itemId);
      } catch (err) {
        const msg = err instanceof Error ? err.message : "Erro desconhecido";
        setFila((prev) =>
          prev.map((i) => (i.id === itemId ? { ...i, status: "erro", erro: msg } : i)),
        );
      }
    },
    [fila, token],
  );

  // Fila sequencial: processa 1 por vez
  useEffect(() => {
    if (!token || !isSuper) return;
    const estaProcessando = fila.some((i) => i.status === "processando");
    if (estaProcessando) return;
    const proximo = fila.find((i) => i.status === "na_fila");
    if (!proximo) return;
    processarItem(proximo.id);
  }, [fila, token, isSuper, processarItem]);

  // ─────── Atualizar preview editado ───────
  const atualizarPreview = (itemId: string, patch: Partial<AtaMigradaPreview>) => {
    setFila((prev) =>
      prev.map((i) =>
        i.id === itemId && i.preview
          ? { ...i, preview: { ...i.preview, ...patch } }
          : i,
      ),
    );
  };

  const atualizarMetadados = (itemId: string, patch: Partial<MetadadosImportacao>) => {
    setFila((prev) =>
      prev.map((i) =>
        i.id === itemId && i.preview
          ? {
              ...i,
              preview: { ...i.preview, metadados: { ...i.preview.metadados, ...patch } },
            }
          : i,
      ),
    );
  };

  // Editar um externo sincroniza o responsavel_nome nas pendências que o referenciam,
  // assim o usuário corrige o nome uma vez e a pendência atualiza junto.
  const atualizarExterno = (
    itemId: string,
    idx: number,
    patch: Partial<ParticipanteExternoPreview>,
  ) => {
    setFila((prev) =>
      prev.map((i) => {
        if (i.id !== itemId || !i.preview) return i;
        const externos = i.preview.participantes_externos.map((e, k) =>
          k === idx ? { ...e, ...patch } : e,
        );
        const pendencias =
          patch.nome !== undefined
            ? i.preview.pendencias.map((p) =>
                p.responsavel_externo_idx === idx
                  ? { ...p, responsavel_nome: patch.nome ?? "" }
                  : p,
              )
            : i.preview.pendencias;
        return {
          ...i,
          preview: { ...i.preview, participantes_externos: externos, pendencias },
        };
      }),
    );
  };

  const atualizarPendencia = (
    itemId: string,
    idx: number,
    patch: Partial<PendenciaImportacao>,
  ) => {
    setFila((prev) =>
      prev.map((i) => {
        if (i.id !== itemId || !i.preview) return i;
        const pendencias = i.preview.pendencias.map((p, k) =>
          k === idx ? { ...p, ...patch } : p,
        );
        return { ...i, preview: { ...i.preview, pendencias } };
      }),
    );
  };

  const adicionarExterno = (itemId: string) => {
    setFila((prev) =>
      prev.map((i) => {
        if (i.id !== itemId || !i.preview) return i;
        return {
          ...i,
          preview: {
            ...i.preview,
            participantes_externos: [
              ...i.preview.participantes_externos,
              { nome: "", cargo: "", email: null },
            ],
          },
        };
      }),
    );
  };

  // Remove um externo e normaliza as pendências que o referenciavam:
  //   idx igual → vira null (cai em "não identificado")
  //   idx maior → decrementa (indices deslocam para a esquerda)
  const removerExterno = (itemId: string, idx: number) => {
    setFila((prev) =>
      prev.map((i) => {
        if (i.id !== itemId || !i.preview) return i;
        const externos = i.preview.participantes_externos.filter((_, k) => k !== idx);
        const pendencias = i.preview.pendencias.map((p) => {
          const ref = p.responsavel_externo_idx;
          if (ref == null) return p;
          if (ref === idx) return { ...p, responsavel_externo_idx: null };
          if (ref > idx) return { ...p, responsavel_externo_idx: ref - 1 };
          return p;
        });
        return {
          ...i,
          preview: { ...i.preview, participantes_externos: externos, pendencias },
        };
      }),
    );
  };

  const reassignarResponsavel = (
    itemId: string,
    pendIdx: number,
    target: ResponsavelTarget,
  ) => {
    setFila((prev) =>
      prev.map((i) => {
        if (i.id !== itemId || !i.preview) return i;

        if (target.tipo === "novo-externo") {
          const novosExternos = [
            ...i.preview.participantes_externos,
            { nome: target.nome, cargo: "", email: null },
          ];
          const novoIdx = novosExternos.length - 1;
          const pendencias = i.preview.pendencias.map((p, k) =>
            k === pendIdx
              ? {
                  ...p,
                  responsavel_nome: target.nome,
                  responsavel_id: null,
                  responsavel_externo_idx: novoIdx,
                }
              : p,
          );
          return {
            ...i,
            preview: {
              ...i.preview,
              participantes_externos: novosExternos,
              pendencias,
            },
          };
        }

        const pendencias = i.preview.pendencias.map((p, k) => {
          if (k !== pendIdx) return p;
          if (target.tipo === "interno") {
            return {
              ...p,
              responsavel_nome: target.nome,
              responsavel_id: target.id,
              responsavel_externo_idx: null,
              cargo: p.cargo || target.cargo || null,
              // Backend só aceita co-resp quando responsável é externo
              co_responsavel_id: null,
            };
          }
          return {
            ...p,
            responsavel_nome: target.nome,
            responsavel_id: null,
            responsavel_externo_idx: target.idx,
          };
        });
        return { ...i, preview: { ...i.preview, pendencias } };
      }),
    );
  };

  // ─────── Remover / cancelar item ───────
  const removerItem = (itemId: string) => {
    setFila((prev) => prev.filter((i) => i.id !== itemId));
    if (ativo === itemId) setAtivo(null);
  };

  const retryItem = (itemId: string) => {
    setFila((prev) =>
      prev.map((i) =>
        i.id === itemId ? { ...i, status: "na_fila", erro: undefined } : i,
      ),
    );
  };

  // Anexar PDF a um rascunho rehidratado sem arquivo.
  // Valida SHA-256 localmente contra o preview antes de aceitar, para evitar
  // arquivo errado ser confirmado e trocar a ATA.
  const anexarArquivoRascunho = useCallback(
    async (itemId: string, file: File) => {
      const item = fila.find((i) => i.id === itemId);
      if (!item?.preview) return;
      try {
        const hash = await sha256Hex(file);
        if (hash !== item.preview.arquivo_hash) {
          toast(
            "Este PDF não bate com a extração salva. Anexe o mesmo arquivo original.",
            "error",
          );
          return;
        }
        setFila((prev) =>
          prev.map((i) =>
            i.id === itemId
              ? { ...i, file, fileMeta: { name: file.name, size: file.size } }
              : i,
          ),
        );
        toast("PDF anexado. Agora você pode confirmar.", "success");
      } catch (err) {
        const msg = err instanceof Error ? err.message : "Erro ao validar arquivo";
        toast(msg, "error");
      }
    },
    [fila, toast],
  );

  // ─────── Confirmar (persiste) ───────
  const confirmar = async (itemId: string) => {
    const item = fila.find((i) => i.id === itemId);
    if (!item?.preview || !token) return;
    if (!item.file) {
      toast(
        "Este rascunho precisa do PDF original anexado antes de confirmar.",
        "error",
      );
      return;
    }

    setConfirmando(true);
    try {
      const fd = new FormData();
      fd.append("file", item.file);
      fd.append("payload", JSON.stringify(item.preview));

      const res = await fetch("/api/reunioes/importacao/confirmar", {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        body: fd,
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        const msg = typeof body?.detail === "string"
          ? body.detail
          : body?.detail?.erro ?? `HTTP ${res.status}`;
        throw new Error(msg);
      }
      const data: {
        id_reuniao: string;
        total_pendencias: number;
        total_externos_criados: number;
        total_externos_stub?: number;
        pendencias_ignoradas?: Array<{ acao: string; motivo: string }>;
      } = await res.json();

      setFila((prev) =>
        prev.map((i) =>
          i.id === itemId
            ? { ...i, status: "importado", id_reuniao_criada: data.id_reuniao }
            : i,
        ),
      );

      // Escolhe próximo arquivo pronto automaticamente
      setAtivo((cur) => {
        if (cur !== itemId) return cur;
        const proximoPronto = fila.find((i) => i.status === "pronto" && i.id !== itemId);
        return proximoPronto?.id ?? null;
      });

      const stubs = data.total_externos_stub ?? 0;
      const ignoradas = data.pendencias_ignoradas?.length ?? 0;
      const partes = [
        `ATA migrada para ${data.id_reuniao}: ${data.total_pendencias} pendências`,
        `${data.total_externos_criados} externos novos`,
      ];
      if (stubs > 0) partes.push(`${stubs} externos sem email (stub)`);
      if (ignoradas > 0) partes.push(`${ignoradas} pendências ignoradas (veja console)`);
      toast(partes.join(" · "), ignoradas > 0 ? "info" : "success");
      if (ignoradas > 0) {
        console.warn(
          "[importacao] Pendências ignoradas:",
          data.pendencias_ignoradas,
        );
      }
      // Atualiza histórico persistido para o usuário ver a ATA recém-importada
      void fetchHistorico(token);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Erro ao confirmar";
      toast(msg, "error");
    } finally {
      setConfirmando(false);
    }
  };

  // ─────── Anexar PDF em rascunhos (usa um único input escondido global) ───────
  const anexarInputRef = useRef<HTMLInputElement>(null);
  const [pendingAnexarId, setPendingAnexarId] = useState<string | null>(null);
  const abrirAnexar = (itemId: string) => {
    setPendingAnexarId(itemId);
    anexarInputRef.current?.click();
  };
  const onAnexarInputChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    const targetId = pendingAnexarId;
    if (anexarInputRef.current) anexarInputRef.current.value = "";
    setPendingAnexarId(null);
    if (!file || !targetId) return;
    if (!file.name.toLowerCase().endsWith(".pdf")) {
      toast("Apenas PDF é aceito.", "error");
      return;
    }
    await anexarArquivoRascunho(targetId, file);
  };

  // ─────── Derived ───────
  const itemAtivo = useMemo(() => fila.find((i) => i.id === ativo), [fila, ativo]);
  const resumoFila = useMemo(() => {
    return {
      total: fila.length,
      naFila: fila.filter((i) => i.status === "na_fila").length,
      processando: fila.filter((i) => i.status === "processando").length,
      prontos: fila.filter((i) => i.status === "pronto").length,
      duplicados: fila.filter((i) => i.status === "duplicado").length,
      erros: fila.filter((i) => i.status === "erro").length,
      importados: fila.filter((i) => i.status === "importado").length,
    };
  }, [fila]);

  const internosOptions = useMemo(
    () =>
      participantesInternos
        .map((p) => ({ id: p.id, nome: p.nome_completo }))
        .sort((a, b) => a.nome.localeCompare(b.nome)),
    [participantesInternos],
  );

  const participantesTodosOptions = useMemo<ParticipanteOption[]>(
    () =>
      participantesTodos
        .map((p) => ({
          id: p.id,
          nome: p.nome_completo,
          cargo: p.cargo ?? null,
          isExterno: !!p.is_externo,
        }))
        .sort((a, b) => a.nome.localeCompare(b.nome)),
    [participantesTodos],
  );

  // ─────── Render ───────
  if (isChecking) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <Loader2 className="w-6 h-6 animate-spin text-primary" />
      </div>
    );
  }

  if (!isSuper) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[60vh] gap-3 text-center">
        <ShieldAlert className="w-10 h-10 text-amber-500" />
        <p className="text-slate-700">Esta página é restrita a super admins.</p>
        <p className="text-xs text-slate-500">Redirecionando para /reunioes…</p>
      </div>
    );
  }

  return (
    <div className="space-y-6 animate-fade-in-up">
      {/* Input escondido pra re-anexar PDF em rascunhos persistidos */}
      <input
        ref={anexarInputRef}
        type="file"
        accept=".pdf,application/pdf"
        className="hidden"
        onChange={onAnexarInputChange}
      />
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <div className="flex items-center gap-2 text-sm text-slate-500 mb-1">
            <Link href="/reunioes" className="hover:text-primary inline-flex items-center gap-1">
              <ArrowLeft className="w-3.5 h-3.5" />
              Reuniões
            </Link>
            <span>/</span>
            <span>Importar ATA</span>
          </div>
          <h1 className="text-2xl font-bold text-slate-900">Importar ATA</h1>
          <p className="text-slate-500 text-sm mt-0.5">
            Faça upload de PDFs de ATAs já assinadas no sistema antigo. A IA extrai
            participantes e pendências; você revisa e confirma antes de criar a reunião MIGRADA.
            <span className="ml-1 text-slate-400">{userEmail}</span>
          </p>
        </div>
      </div>

      {/* Dropzone */}
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        onClick={() => fileInputRef.current?.click()}
        className={`relative border-2 border-dashed rounded-2xl p-6 text-center transition-all cursor-pointer ${
          dragging
            ? "border-primary bg-primary/5"
            : "border-slate-200 hover:border-primary/40 hover:bg-slate-50"
        }`}
      >
        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf,application/pdf"
          multiple
          className="hidden"
          onChange={onFileInputChange}
        />
        <Upload className="w-8 h-8 mx-auto mb-2 text-slate-400" strokeWidth={1.5} />
        <p className="text-sm text-slate-600">
          Arraste PDFs de ATAs aqui ou{" "}
          <span className="text-primary font-medium">clique para selecionar</span>
        </p>
        <p className="text-xs text-slate-400 mt-1">
          Múltiplos arquivos suportados — processamento sequencial. Máx 15 MB por arquivo.
        </p>
      </div>

      {/* Fila */}
      {fila.length > 0 && (
        <div className="bg-white rounded-2xl border border-border shadow-premium overflow-hidden">
          <div className="px-5 py-3 border-b border-slate-100 bg-slate-50/60 flex items-center justify-between">
            <h2 className="text-sm font-semibold text-slate-700">
              Fila de importação · {resumoFila.total} arquivo(s)
            </h2>
            <span className="text-xs text-slate-500">
              {resumoFila.importados} concluído(s) · {resumoFila.prontos} aguardando revisão ·{" "}
              {resumoFila.processando} processando · {resumoFila.duplicados} duplicado(s) ·{" "}
              {resumoFila.erros} erro(s)
            </span>
          </div>
          <ul className="divide-y divide-slate-50">
            {fila.map((item) => (
              <ItemFilaRow
                key={item.id}
                item={item}
                isActive={item.id === ativo}
                onView={() => setAtivo(item.id)}
                onRetry={() => retryItem(item.id)}
                onRemove={() => removerItem(item.id)}
                onAnexar={() => abrirAnexar(item.id)}
              />
            ))}
          </ul>
        </div>
      )}

      {/* Importações recentes (persistido no banco) */}
      <section className="bg-white rounded-2xl border border-border shadow-premium overflow-hidden">
        <div className="px-5 py-3 border-b border-slate-100 bg-slate-50/60 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-slate-700">
            Importações recentes
            {historico.length > 0 && (
              <span className="ml-2 text-xs font-normal text-slate-500">
                · {historico.length} última{historico.length === 1 ? "" : "s"}
              </span>
            )}
          </h2>
          {historicoLoading && <Loader2 className="w-4 h-4 animate-spin text-slate-400" />}
        </div>
        {historico.length === 0 ? (
          <div className="px-5 py-6 text-sm text-slate-500 text-center">
            Nenhuma ATA importada ainda. Os PDFs confirmados aparecem aqui e ficam disponíveis mesmo após você sair da página.
          </div>
        ) : (
          <ul className="divide-y divide-slate-50">
            {historico.map((h) => {
              const dataFmt = h.data
                ? new Date(`${h.data}T00:00:00`).toLocaleDateString("pt-BR")
                : "—";
              const importadoFmt = h.importado_em
                ? new Date(h.importado_em).toLocaleString("pt-BR", {
                    day: "2-digit",
                    month: "2-digit",
                    year: "numeric",
                    hour: "2-digit",
                    minute: "2-digit",
                  })
                : null;
              return (
                <li key={h.id_reuniao} className="px-5 py-3 hover:bg-slate-50/60 transition-colors">
                  <div className="flex items-center justify-between gap-4">
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2 flex-wrap">
                        <Link
                          href={`/reunioes/${h.id_reuniao}`}
                          className="text-sm font-medium text-slate-800 hover:text-primary truncate"
                        >
                          {h.titulo || h.id_reuniao}
                        </Link>
                        <span className="inline-flex items-center gap-1 text-[10px] font-semibold px-1.5 py-0.5 rounded-full bg-amber-50 text-amber-700">
                          MIGRADA
                        </span>
                        {h.documento_id_origem && (
                          <span className="inline-flex items-center gap-1 text-[10px] text-slate-500 font-mono">
                            <Link2 className="w-3 h-3" />
                            {h.documento_id_origem}
                          </span>
                        )}
                      </div>
                      <div className="text-xs text-slate-500 mt-0.5 flex items-center gap-3 flex-wrap">
                        <span>Data da reunião: {dataFmt}</span>
                        <span>·</span>
                        <span>{h.total_pendencias} pendência{h.total_pendencias === 1 ? "" : "s"}</span>
                        {h.nome_arquivo_original && (
                          <>
                            <span>·</span>
                            <span className="truncate max-w-[240px]" title={h.nome_arquivo_original}>
                              {h.nome_arquivo_original}
                            </span>
                          </>
                        )}
                      </div>
                      {(h.importado_por_nome || importadoFmt) && (
                        <div className="text-[11px] text-slate-400 mt-0.5">
                          Importada{importadoFmt ? ` em ${importadoFmt}` : ""}
                          {h.importado_por_nome ? ` por ${h.importado_por_nome}` : ""}
                        </div>
                      )}
                    </div>
                    <Link
                      href={`/reunioes/${h.id_reuniao}`}
                      className="text-xs text-primary font-medium hover:underline whitespace-nowrap"
                    >
                      Abrir →
                    </Link>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </section>

      {/* Preview editável */}
      {itemAtivo?.preview && itemAtivo.status !== "importado" && (
        <PreviewEditor
          item={itemAtivo}
          internosOptions={internosOptions}
          participantesTodos={participantesTodosOptions}
          confirmando={confirmando}
          onMetadados={(patch) => atualizarMetadados(itemAtivo.id, patch)}
          onExterno={(idx, patch) => atualizarExterno(itemAtivo.id, idx, patch)}
          onAdicionarExterno={() => adicionarExterno(itemAtivo.id)}
          onRemoverExterno={(idx) => removerExterno(itemAtivo.id, idx)}
          onPendencia={(idx, patch) => atualizarPendencia(itemAtivo.id, idx, patch)}
          onReassignarResponsavel={(pendIdx, target) =>
            reassignarResponsavel(itemAtivo.id, pendIdx, target)
          }
          onPreviewField={(patch) => atualizarPreview(itemAtivo.id, patch)}
          onCancelar={() => removerItem(itemAtivo.id)}
          onConfirmar={() => confirmar(itemAtivo.id)}
          onAnexar={() => abrirAnexar(itemAtivo.id)}
        />
      )}
    </div>
  );
}

// ──────────────────────────────────────────
// Componentes internos
// ──────────────────────────────────────────
function ItemFilaRow({
  item,
  isActive,
  onView,
  onRetry,
  onRemove,
  onAnexar,
}: {
  item: ItemFila;
  isActive: boolean;
  onView: () => void;
  onRetry: () => void;
  onRemove: () => void;
  onAnexar: () => void;
}) {
  const statusIcon = {
    na_fila: <Clock4 className="w-4 h-4 text-slate-400" />,
    processando: <Loader2 className="w-4 h-4 text-blue-500 animate-spin" />,
    pronto: <CheckCircle2 className="w-4 h-4 text-emerald-500" />,
    duplicado: <AlertTriangle className="w-4 h-4 text-amber-500" />,
    erro: <XCircle className="w-4 h-4 text-red-500" />,
    importado: <CheckCircle2 className="w-4 h-4 text-emerald-600" />,
  }[item.status];

  const statusLabel = {
    na_fila: "Na fila",
    processando: "Processando…",
    pronto: "Revisar preview",
    duplicado: "Duplicada",
    erro: "Erro",
    importado: "Importada",
  }[item.status];

  return (
    <li
      className={`px-5 py-3 flex items-center gap-3 transition-colors ${
        isActive ? "bg-primary/5" : "hover:bg-slate-50"
      }`}
    >
      <span className="flex-shrink-0">{statusIcon}</span>
      <div className="flex-1 min-w-0">
        <div className="text-sm font-medium text-slate-800 truncate">{item.fileMeta.name}</div>
        <div className="text-xs text-slate-500 flex items-center gap-2 mt-0.5">
          <span>{formatBytes(item.fileMeta.size)}</span>
          <span>·</span>
          <span>{statusLabel}</span>
          {item.status === "pronto" && !item.file && (
            <>
              <span>·</span>
              <span className="text-amber-700">
                PDF não anexado — anexe o arquivo original para confirmar
              </span>
            </>
          )}
          {item.status === "duplicado" && item.duplicata && (
            <>
              <span>·</span>
              <Link
                href={`/reunioes/${item.duplicata.id_reuniao}`}
                className="text-amber-700 hover:underline inline-flex items-center gap-1"
              >
                <Link2 className="w-3 h-3" />
                {item.duplicata.id_reuniao}
              </Link>
              {item.duplicata.motivo && <span>({item.duplicata.motivo})</span>}
            </>
          )}
          {item.status === "erro" && item.erro && (
            <span className="text-red-600 truncate">· {item.erro}</span>
          )}
          {item.status === "importado" && item.id_reuniao_criada && (
            <Link
              href={`/reunioes/${item.id_reuniao_criada}`}
              className="text-emerald-700 hover:underline inline-flex items-center gap-1"
            >
              <Link2 className="w-3 h-3" />
              {item.id_reuniao_criada}
            </Link>
          )}
        </div>
      </div>
      <div className="flex items-center gap-1.5">
        {item.status === "pronto" && !item.file && (
          <button
            onClick={onAnexar}
            className="flex items-center gap-1 px-3 py-1.5 rounded-lg bg-amber-50 text-amber-700 hover:bg-amber-100 text-xs font-medium cursor-pointer"
          >
            <Upload className="w-3.5 h-3.5" />
            Anexar PDF
          </button>
        )}
        {item.status === "pronto" && (
          <button
            onClick={onView}
            className="flex items-center gap-1 px-3 py-1.5 rounded-lg bg-primary/10 text-primary hover:bg-primary/15 text-xs font-medium cursor-pointer"
          >
            <Eye className="w-3.5 h-3.5" />
            {isActive ? "Visível" : "Revisar"}
          </button>
        )}
        {item.status === "erro" && (
          <button
            onClick={onRetry}
            className="px-3 py-1.5 rounded-lg bg-red-50 text-red-700 hover:bg-red-100 text-xs font-medium cursor-pointer"
          >
            Tentar novamente
          </button>
        )}
        {item.status !== "importado" && (
          <button
            onClick={onRemove}
            className="p-1.5 rounded-lg text-slate-400 hover:text-red-500 hover:bg-red-50 cursor-pointer"
            title="Remover da fila"
          >
            <Trash2 className="w-3.5 h-3.5" />
          </button>
        )}
      </div>
    </li>
  );
}

function PreviewEditor({
  item,
  internosOptions,
  participantesTodos,
  confirmando,
  onMetadados,
  onExterno,
  onAdicionarExterno,
  onRemoverExterno,
  onPendencia,
  onReassignarResponsavel,
  onPreviewField,
  onCancelar,
  onConfirmar,
  onAnexar,
}: {
  item: ItemFila;
  internosOptions: { id: string; nome: string }[];
  participantesTodos: ParticipanteOption[];
  confirmando: boolean;
  onMetadados: (patch: Partial<MetadadosImportacao>) => void;
  onExterno: (idx: number, patch: Partial<ParticipanteExternoPreview>) => void;
  onAdicionarExterno: () => void;
  onRemoverExterno: (idx: number) => void;
  onPendencia: (idx: number, patch: Partial<PendenciaImportacao>) => void;
  onReassignarResponsavel: (pendIdx: number, target: ResponsavelTarget) => void;
  onPreviewField: (patch: Partial<AtaMigradaPreview>) => void;
  onCancelar: () => void;
  onConfirmar: () => void;
  onAnexar: () => void;
}) {
  const p = item.preview!;
  const semArquivo = !item.file;
  const pendenciasNaoIdentificadas = p.pendencias.reduce(
    (acc, pend) =>
      !pend.responsavel_id &&
      (pend.responsavel_externo_idx === null ||
        pend.responsavel_externo_idx === undefined) &&
      pend.responsavel_nome?.trim()
        ? acc + 1
        : acc,
    0,
  );

  return (
    <div className="bg-white rounded-2xl border border-border shadow-premium overflow-hidden">
      {/* Sub-header */}
      <div className="px-5 py-3 border-b border-slate-100 bg-slate-50/60 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <FileUp className="w-4 h-4 text-amber-500" />
          <div>
            <div className="text-sm font-semibold text-slate-800">{item.fileMeta.name}</div>
            <div className="text-xs text-slate-500">
              {p.paginas} página(s) · hash {p.arquivo_hash.slice(0, 10)}…
              {p.documento_id_origem && (
                <>
                  {" · "}doc origem <span className="font-mono">{p.documento_id_origem}</span>
                </>
              )}
              {p.is_mock && <span className="ml-2 text-amber-600">[MOCK — sem OpenAI key]</span>}
            </div>
          </div>
        </div>
      </div>

      {/* Metadados */}
      <section className="p-5 space-y-3 border-b border-slate-100">
        <h3 className="text-sm font-semibold text-slate-700">Metadados</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <LabeledInput
            label="Título"
            value={p.metadados.titulo}
            onChange={(v) => onMetadados({ titulo: v })}
          />
          <LabeledSelect
            label="Tipo"
            value={p.metadados.tipo}
            options={TIPOS_REUNIAO.map((t) => ({ value: t, label: t }))}
            onChange={(v) => onMetadados({ tipo: v as TipoReuniao })}
          />
          <LabeledInput
            label="Data"
            type="date"
            value={p.metadados.data}
            onChange={(v) => onMetadados({ data: v })}
          />
          <div className="grid grid-cols-2 gap-3">
            <LabeledInput
              label="Hora início"
              type="time"
              value={p.metadados.hora_inicio ?? ""}
              onChange={(v) => onMetadados({ hora_inicio: v || null })}
            />
            <LabeledInput
              label="Hora fim"
              type="time"
              value={p.metadados.hora_fim ?? ""}
              onChange={(v) => onMetadados({ hora_fim: v || null })}
            />
          </div>
          <LabeledInput
            label="Assunto"
            value={p.metadados.assunto ?? ""}
            onChange={(v) => onMetadados({ assunto: v || null })}
          />
          <LabeledInput
            label="Objetivo"
            value={p.metadados.objetivo ?? ""}
            onChange={(v) => onMetadados({ objetivo: v || null })}
          />
        </div>
      </section>

      {/* Participantes */}
      <section className="p-5 space-y-4 border-b border-slate-100">
        <div className="flex items-center justify-between flex-wrap gap-2">
          <h3 className="text-sm font-semibold text-slate-700">
            Participantes
            <span className="ml-2 text-xs font-normal text-slate-400">
              {p.participantes_matched.length} cadastrado
              {p.participantes_matched.length === 1 ? "" : "s"} ·{" "}
              {p.participantes_externos.length} externo
              {p.participantes_externos.length === 1 ? "" : "s"}
            </span>
          </h3>
        </div>

        {p.participantes_matched.length > 0 && (
          <div className="rounded-xl border border-emerald-100 bg-emerald-50/40 p-3">
            <div className="text-xs text-emerald-700 font-medium mb-2">
              Cadastrados identificados
            </div>
            <ul className="space-y-1 text-sm text-slate-700">
              {p.participantes_matched.map((m) => (
                <li
                  key={m.participante_id}
                  className="flex items-center justify-between gap-2"
                >
                  <span className="truncate">
                    {m.nome}
                    <span className="text-slate-400 ml-1 text-xs">
                      {m.cargo ?? "—"}
                    </span>
                  </span>
                  <CheckCircle2 className="w-4 h-4 text-emerald-500 shrink-0" />
                </li>
              ))}
            </ul>
          </div>
        )}

        <div className="rounded-xl border border-amber-200 bg-amber-50/40 p-3 space-y-3">
          <div className="flex items-start justify-between gap-2 flex-wrap">
            <div>
              <div className="text-xs font-medium text-amber-900">
                Participantes não cadastrados ({p.participantes_externos.length})
              </div>
              <div className="text-[11px] text-slate-500 mt-0.5 max-w-prose">
                Serão criados automaticamente ao confirmar a ATA. Se tiver o
                email, o participante recebe convite para se autenticar.
              </div>
            </div>
            <button
              type="button"
              onClick={onAdicionarExterno}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-amber-300 bg-white text-amber-800 text-xs font-medium hover:bg-amber-50 cursor-pointer"
            >
              <Plus className="w-3.5 h-3.5" />
              Adicionar externo
            </button>
          </div>

          {p.participantes_externos.length === 0 ? (
            <div className="text-xs text-slate-500 italic">
              Nenhum externo nesta ATA ainda.
            </div>
          ) : (
            <div className="space-y-2">
              {p.participantes_externos.map((e, idx) => (
                <ExternoRow
                  key={idx}
                  externo={e}
                  onChange={(patch) => onExterno(idx, patch)}
                  onRemove={() => onRemoverExterno(idx)}
                />
              ))}
            </div>
          )}
        </div>
      </section>

      {/* Pendências */}
      <section className="p-5 space-y-3 border-b border-slate-100">
        <div className="flex items-center justify-between flex-wrap gap-2">
          <h3 className="text-sm font-semibold text-slate-700">
            Pendências
            <span className="ml-2 text-xs font-normal text-slate-400">
              {p.pendencias.length} ação
              {p.pendencias.length === 1 ? "" : "ões"}
            </span>
          </h3>
          {pendenciasNaoIdentificadas > 0 && (
            <div className="inline-flex items-center gap-1.5 text-xs text-rose-700 bg-rose-50 border border-rose-200 rounded-full px-2.5 py-1">
              <AlertTriangle className="w-3.5 h-3.5" />
              {pendenciasNaoIdentificadas} com responsável não identificado
            </div>
          )}
        </div>
        <div className="space-y-3">
          {p.pendencias.map((pend, idx) => (
            <PendenciaCard
              key={idx}
              numero={idx + 1}
              pend={pend}
              internosOptions={internosOptions}
              externosDaAta={p.participantes_externos}
              participantesTodos={participantesTodos}
              onPatch={(patch) => onPendencia(idx, patch)}
              onReassignar={(target) => onReassignarResponsavel(idx, target)}
            />
          ))}
        </div>
      </section>

      {/* Resumo narrativo */}
      <section className="p-5 space-y-3 border-b border-slate-100">
        <h3 className="text-sm font-semibold text-slate-700">Resumo (editável)</h3>
        <LabeledTextarea
          label="Resumo executivo"
          value={p.resumo_executivo ?? ""}
          rows={3}
          onChange={(v) => onPreviewField({ resumo_executivo: v || null })}
        />
        <LabeledTextarea
          label="Registro narrativo"
          value={p.registro_narrativo ?? ""}
          rows={5}
          onChange={(v) => onPreviewField({ registro_narrativo: v || null })}
        />
      </section>

      {/* Actions */}
      <div className="px-5 py-4 bg-slate-50/60 flex items-center justify-between gap-3">
        <button
          onClick={onCancelar}
          className="flex items-center gap-2 px-4 py-2 border border-slate-200 text-slate-700 rounded-xl text-sm font-medium hover:bg-white cursor-pointer"
        >
          <X className="w-4 h-4" />
          Cancelar este arquivo
        </button>
        <div className="flex items-center gap-3">
          {semArquivo && (
            <>
              <span className="text-xs text-amber-700 inline-flex items-center gap-1">
                <AlertTriangle className="w-3.5 h-3.5" />
                PDF não anexado
              </span>
              <button
                onClick={onAnexar}
                className="flex items-center gap-2 px-3 py-2 border border-amber-200 bg-amber-50 text-amber-800 rounded-xl text-xs font-medium hover:bg-amber-100 cursor-pointer"
              >
                <Upload className="w-3.5 h-3.5" />
                Anexar PDF
              </button>
            </>
          )}
          <button
            onClick={onConfirmar}
            disabled={confirmando || semArquivo}
            title={semArquivo ? "Anexe o PDF original para confirmar" : undefined}
            className="flex items-center gap-2 px-4 py-2 bg-gradient-to-r from-primary to-primary-dark text-white rounded-xl text-sm font-medium hover:shadow-premium-strong disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
          >
            {confirmando ? <Loader2 className="w-4 h-4 animate-spin" /> : <CheckCircle2 className="w-4 h-4" />}
            Confirmar importação
          </button>
        </div>
      </div>
    </div>
  );
}

// ──────────────────────────────────────────
// UI helpers
// ──────────────────────────────────────────
type IconType = React.ComponentType<{ className?: string }>;

function FieldLabel({
  label,
  icon: Icon,
  required,
}: {
  label: string;
  icon?: IconType;
  required?: boolean;
}) {
  return (
    <label className="flex items-center gap-1.5 text-xs font-medium text-slate-600 mb-1">
      {Icon && <Icon className="w-3.5 h-3.5 text-slate-400" />}
      <span>{label}</span>
      {required && (
        <span className="text-rose-500 leading-none" aria-hidden="true">
          *
        </span>
      )}
    </label>
  );
}

function LabeledInput({
  label,
  value,
  onChange,
  type = "text",
  highlight,
  icon,
  required,
  helperText,
  placeholder,
  autoFocus,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  type?: string;
  highlight?: boolean;
  icon?: IconType;
  required?: boolean;
  helperText?: React.ReactNode;
  placeholder?: string;
  autoFocus?: boolean;
}) {
  return (
    <div>
      <FieldLabel label={label} icon={icon} required={required} />
      <input
        type={type}
        value={value}
        autoFocus={autoFocus}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
        className={`w-full px-3 py-2 border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary/30 ${
          highlight ? "border-amber-400 bg-amber-50/40" : "border-slate-200"
        }`}
      />
      {helperText && <div className="mt-1 text-xs text-slate-500">{helperText}</div>}
    </div>
  );
}

function LabeledTextarea({
  label,
  value,
  onChange,
  rows = 3,
  icon,
  required,
  helperText,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  rows?: number;
  icon?: IconType;
  required?: boolean;
  helperText?: React.ReactNode;
}) {
  return (
    <div>
      <FieldLabel label={label} icon={icon} required={required} />
      <textarea
        value={value}
        rows={rows}
        onChange={(e) => onChange(e.target.value)}
        className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary/30 resize-none"
      />
      {helperText && <div className="mt-1 text-xs text-slate-500">{helperText}</div>}
    </div>
  );
}

function LabeledSelect({
  label,
  value,
  options,
  onChange,
  icon,
  required,
  helperText,
}: {
  label: string;
  value: string;
  options: { value: string; label: string }[];
  onChange: (v: string) => void;
  icon?: IconType;
  required?: boolean;
  helperText?: React.ReactNode;
}) {
  return (
    <div>
      <FieldLabel label={label} icon={icon} required={required} />
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary/30 bg-white"
      >
        {options.map((opt) => (
          <option key={opt.value} value={opt.value}>
            {opt.label}
          </option>
        ))}
      </select>
      {helperText && <div className="mt-1 text-xs text-slate-500">{helperText}</div>}
    </div>
  );
}

// ──────────────────────────────────────────
// Badge + combobox + helpers específicos da importação
// ──────────────────────────────────────────

type BadgeVariant =
  | "neutral"
  | "externo"
  | "nao-identificado"
  | "status-PENDENTE"
  | "status-EM_PROGRESSO"
  | "status-CONCLUIDO"
  | "status-ATRASADO"
  | "status-CANCELADO"
  | "status-REPACTUADA";

const BADGE_STYLES: Record<BadgeVariant, string> = {
  neutral: "bg-slate-100 text-slate-700 border-slate-200",
  externo: "bg-amber-50 text-amber-800 border-amber-200",
  "nao-identificado": "bg-rose-50 text-rose-700 border-rose-200",
  "status-PENDENTE": "bg-slate-100 text-slate-700 border-slate-200",
  "status-EM_PROGRESSO": "bg-blue-50 text-blue-700 border-blue-200",
  "status-CONCLUIDO": "bg-emerald-50 text-emerald-700 border-emerald-200",
  "status-ATRASADO": "bg-rose-50 text-rose-700 border-rose-200",
  "status-CANCELADO": "bg-slate-100 text-slate-500 border-slate-200",
  "status-REPACTUADA": "bg-indigo-50 text-indigo-700 border-indigo-200",
};

function Badge({
  variant = "neutral",
  children,
  icon: Icon,
}: {
  variant?: BadgeVariant;
  children: React.ReactNode;
  icon?: IconType;
}) {
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-medium ${BADGE_STYLES[variant]}`}
    >
      {Icon && <Icon className="w-3 h-3" />}
      {children}
    </span>
  );
}

// Tenta converter "27/04/2026" → "2026-04-27" para botão "Usar esta data".
// Retorna null se o formato não bate com a máscara exata.
function tryParseBrazilianDate(raw: string | null | undefined): string | null {
  if (!raw) return null;
  const match = raw.trim().match(/^(\d{2})\/(\d{2})\/(\d{4})$/);
  if (!match) return null;
  const [, dd, mm, yyyy] = match;
  const day = Number(dd);
  const month = Number(mm);
  const year = Number(yyyy);
  if (month < 1 || month > 12 || day < 1 || day > 31) return null;
  return `${yyyy}-${mm}-${dd}`;
}

type ComboItem =
  | { kind: "header"; label: string }
  | { kind: "item-interno"; option: ParticipanteOption }
  | { kind: "item-externo-banco"; option: ParticipanteOption }
  | { kind: "item-externo-ata"; idx: number; nome: string; cargo: string }
  | { kind: "item-novo"; nome: string };

function ResponsavelCombobox({
  valueNome,
  responsavelId,
  responsavelExternoIdx,
  externosDaAta,
  todos,
  onSelect,
  autoOpen,
}: {
  valueNome: string;
  responsavelId: string | null | undefined;
  responsavelExternoIdx: number | null | undefined;
  externosDaAta: ParticipanteExternoPreview[];
  todos: ParticipanteOption[];
  onSelect: (target: ResponsavelTarget) => void;
  autoOpen?: boolean;
}) {
  const [query, setQuery] = useState(valueNome);
  const [open, setOpen] = useState(!!autoOpen);
  const [activeIdx, setActiveIdx] = useState(0);
  const [userTyping, setUserTyping] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  // Quando a prop externa muda (e o usuário não está digitando) refletimos no input.
  useEffect(() => {
    if (!userTyping) setQuery(valueNome);
  }, [valueNome, userTyping]);

  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (!containerRef.current?.contains(e.target as Node)) {
        setOpen(false);
        setUserTyping(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  const naoIdentificado =
    !responsavelId &&
    (responsavelExternoIdx === null || responsavelExternoIdx === undefined) &&
    !!valueNome.trim();

  const items = useMemo<ComboItem[]>(() => {
    const q = query.trim().toLowerCase();
    const matches = (s: string) => q === "" || s.toLowerCase().includes(q);

    const internos = todos
      .filter((p) => !p.isExterno && matches(p.nome))
      .slice(0, 20);
    const externosAtaList = externosDaAta
      .map((e, idx) => ({ e, idx }))
      .filter(({ e }) => matches(e.nome || ""));
    const externosBanco = todos
      .filter((p) => p.isExterno && matches(p.nome))
      .slice(0, 10);

    const out: ComboItem[] = [];
    if (internos.length > 0) {
      out.push({ kind: "header", label: "Cadastrados internos" });
      internos.forEach((p) => out.push({ kind: "item-interno", option: p }));
    }
    if (externosAtaList.length > 0) {
      out.push({ kind: "header", label: "Externos desta ATA" });
      externosAtaList.forEach(({ e, idx }) =>
        out.push({ kind: "item-externo-ata", idx, nome: e.nome, cargo: e.cargo }),
      );
    }
    if (externosBanco.length > 0) {
      out.push({ kind: "header", label: "Externos já cadastrados" });
      externosBanco.forEach((p) => out.push({ kind: "item-externo-banco", option: p }));
    }

    const nomeNormalizado = query.trim();
    if (nomeNormalizado) {
      const bateExato = out.some((it) => {
        if (it.kind === "item-interno" || it.kind === "item-externo-banco")
          return it.option.nome.toLowerCase() === q;
        if (it.kind === "item-externo-ata") return (it.nome || "").toLowerCase() === q;
        return false;
      });
      if (!bateExato) out.push({ kind: "item-novo", nome: nomeNormalizado });
    }

    return out;
  }, [query, todos, externosDaAta]);

  const selectableIdxs = useMemo(
    () =>
      items
        .map((it, i) => (it.kind === "header" ? -1 : i))
        .filter((i) => i >= 0),
    [items],
  );

  useEffect(() => {
    if (selectableIdxs.length === 0) return;
    if (!selectableIdxs.includes(activeIdx)) setActiveIdx(selectableIdxs[0]);
  }, [selectableIdxs, activeIdx]);

  const handleSelect = (item: ComboItem) => {
    if (item.kind === "header") return;
    if (item.kind === "item-interno" || item.kind === "item-externo-banco") {
      onSelect({
        tipo: "interno",
        id: item.option.id,
        nome: item.option.nome,
        cargo: item.option.cargo,
      });
    } else if (item.kind === "item-externo-ata") {
      onSelect({ tipo: "externo", idx: item.idx, nome: item.nome });
    } else {
      onSelect({ tipo: "novo-externo", nome: item.nome });
    }
    setOpen(false);
    setUserTyping(false);
  };

  const moveActive = (direction: 1 | -1) => {
    if (selectableIdxs.length === 0) return;
    const pos = selectableIdxs.indexOf(activeIdx);
    const next =
      pos === -1
        ? selectableIdxs[0]
        : selectableIdxs[
            (pos + direction + selectableIdxs.length) % selectableIdxs.length
          ];
    setActiveIdx(next);
  };

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setOpen(true);
      moveActive(1);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setOpen(true);
      moveActive(-1);
    } else if (e.key === "Enter") {
      if (open && items[activeIdx]) {
        e.preventDefault();
        handleSelect(items[activeIdx]);
      }
    } else if (e.key === "Escape") {
      setOpen(false);
      setUserTyping(false);
    }
  };

  return (
    <div className="relative" ref={containerRef}>
      <div
        className={`flex items-center gap-2 px-3 py-2 border rounded-lg text-sm bg-white focus-within:ring-2 focus-within:ring-primary/30 ${
          naoIdentificado ? "border-rose-300" : "border-slate-200"
        }`}
      >
        <User className="w-3.5 h-3.5 text-slate-400 shrink-0" />
        <input
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setUserTyping(true);
            setOpen(true);
          }}
          onFocus={() => setOpen(true)}
          onKeyDown={onKeyDown}
          placeholder="Buscar ou digitar um nome…"
          role="combobox"
          aria-expanded={open}
          aria-autocomplete="list"
          className="w-full outline-none bg-transparent placeholder:text-slate-400"
        />
      </div>
      {open && items.length > 0 && (
        <div
          className="absolute z-20 mt-1 w-full max-h-64 overflow-auto rounded-xl border border-slate-200 bg-white shadow-premium"
          role="listbox"
        >
          {items.map((item, i) => {
            if (item.kind === "header") {
              return (
                <div
                  key={`h-${i}`}
                  className="text-[11px] uppercase tracking-wide text-slate-400 px-3 pt-2 pb-1"
                >
                  {item.label}
                </div>
              );
            }
            const active = activeIdx === i;
            if (item.kind === "item-novo") {
              return (
                <button
                  key={`novo-${i}`}
                  type="button"
                  onClick={() => handleSelect(item)}
                  onMouseEnter={() => setActiveIdx(i)}
                  className={`w-full text-left px-3 py-2 text-sm border-t border-slate-100 flex items-center gap-2 cursor-pointer text-primary font-medium ${
                    active ? "bg-primary/5" : "hover:bg-primary/5"
                  }`}
                >
                  <Plus className="w-3.5 h-3.5" />
                  Adicionar &quot;{item.nome}&quot; como externo
                </button>
              );
            }
            const nome =
              item.kind === "item-externo-ata" ? item.nome : item.option.nome;
            const cargo =
              item.kind === "item-externo-ata" ? item.cargo : item.option.cargo;
            return (
              <button
                key={`it-${i}`}
                type="button"
                onClick={() => handleSelect(item)}
                onMouseEnter={() => setActiveIdx(i)}
                className={`w-full text-left px-3 py-1.5 text-sm flex items-center justify-between gap-2 cursor-pointer ${
                  active ? "bg-primary/5" : "hover:bg-primary/5"
                }`}
              >
                <span className="truncate">{nome || "(sem nome)"}</span>
                {cargo && (
                  <span className="text-xs text-slate-400 truncate">{cargo}</span>
                )}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

function ExternoRow({
  externo,
  onChange,
  onRemove,
}: {
  externo: ParticipanteExternoPreview;
  onChange: (patch: Partial<ParticipanteExternoPreview>) => void;
  onRemove: () => void;
}) {
  const [mostrarSetor, setMostrarSetor] = useState(!!externo.setor);
  return (
    <div className="bg-white border border-amber-100 rounded-lg p-3 space-y-2">
      <div className="grid grid-cols-1 md:grid-cols-[1fr_1fr_1.3fr_auto] gap-2 md:items-end">
        <LabeledInput
          label="Nome"
          icon={User}
          value={externo.nome}
          onChange={(v) => onChange({ nome: v })}
          placeholder="Nome completo"
        />
        <LabeledInput
          label="Cargo"
          icon={Briefcase}
          value={externo.cargo}
          onChange={(v) => onChange({ cargo: v })}
          placeholder="Cargo / função"
        />
        <LabeledInput
          label="Email (opcional)"
          type="email"
          value={externo.email ?? ""}
          onChange={(v) => onChange({ email: v || null })}
          placeholder="email@dominio.com"
        />
        <button
          type="button"
          onClick={onRemove}
          aria-label="Remover este externo"
          title="Remover externo"
          className="inline-flex items-center justify-center h-10 md:w-10 w-full rounded-lg border border-transparent text-slate-400 hover:text-rose-600 hover:bg-rose-50 hover:border-rose-100 cursor-pointer"
        >
          <Trash2 className="w-4 h-4" />
        </button>
      </div>
      {mostrarSetor ? (
        <LabeledInput
          label="Setor"
          value={externo.setor ?? ""}
          onChange={(v) => onChange({ setor: v || null })}
          placeholder="Setor / departamento"
        />
      ) : (
        <button
          type="button"
          onClick={() => setMostrarSetor(true)}
          className="inline-flex items-center gap-1 text-[11px] text-slate-500 hover:text-primary cursor-pointer"
        >
          <Plus className="w-3 h-3" />
          Informar setor
        </button>
      )}
    </div>
  );
}

function PendenciaCard({
  numero,
  pend,
  internosOptions,
  externosDaAta,
  participantesTodos,
  onPatch,
  onReassignar,
}: {
  numero: number;
  pend: PendenciaImportacao;
  internosOptions: { id: string; nome: string }[];
  externosDaAta: ParticipanteExternoPreview[];
  participantesTodos: ParticipanteOption[];
  onPatch: (patch: Partial<PendenciaImportacao>) => void;
  onReassignar: (target: ResponsavelTarget) => void;
}) {
  const isRespExterno = pend.responsavel_externo_idx != null;
  const naoIdentificado =
    !pend.responsavel_id &&
    (pend.responsavel_externo_idx === null ||
      pend.responsavel_externo_idx === undefined) &&
    !!pend.responsavel_nome?.trim();
  const prazoAmbiguo = !pend.prazo && !!pend.prazo_original;
  const prazoSugerido = prazoAmbiguo ? tryParseBrazilianDate(pend.prazo_original) : null;
  const [mostrarCoResp, setMostrarCoResp] = useState(!!pend.co_responsavel_id);

  const statusVariant = `status-${pend.status}` as BadgeVariant;

  return (
    <div className="rounded-2xl border border-slate-200 bg-white overflow-hidden shadow-premium">
      <div className="flex items-center justify-between gap-2 px-4 py-2.5 bg-slate-50 border-b border-slate-100 flex-wrap">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-xs font-semibold text-slate-500">#{numero}</span>
          {isRespExterno && <Badge variant="externo">Externo</Badge>}
          {naoIdentificado && (
            <Badge variant="nao-identificado" icon={AlertTriangle}>
              Não identificado
            </Badge>
          )}
        </div>
        <Badge variant={statusVariant}>{pend.status.replace("_", " ")}</Badge>
      </div>

      <div className="px-4 py-3 space-y-3">
        <LabeledTextarea
          label="Ação"
          value={pend.acao}
          rows={2}
          onChange={(v) => onPatch({ acao: v })}
        />

        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <div>
            <FieldLabel label="Responsável" icon={User} />
            <ResponsavelCombobox
              valueNome={pend.responsavel_nome}
              responsavelId={pend.responsavel_id}
              responsavelExternoIdx={pend.responsavel_externo_idx}
              externosDaAta={externosDaAta}
              todos={participantesTodos}
              onSelect={onReassignar}
              autoOpen={naoIdentificado}
            />
            {naoIdentificado && (
              <div className="mt-1 text-xs text-rose-700">
                A IA sugeriu &quot;{pend.responsavel_nome}&quot;, mas este nome
                não está cadastrado. Escolha uma pessoa ou crie como externo.
              </div>
            )}
          </div>
          <LabeledInput
            label="Cargo"
            icon={Briefcase}
            value={pend.cargo ?? ""}
            onChange={(v) => onPatch({ cargo: v || null })}
          />
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <div>
            <FieldLabel label="Prazo" icon={Calendar} />
            <input
              type="date"
              value={pend.prazo ?? ""}
              onChange={(ev) => onPatch({ prazo: ev.target.value || null })}
              className="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary/30"
            />
            {prazoAmbiguo && (
              <div className="mt-1 flex items-center gap-2 text-xs text-amber-700">
                <Sparkles className="w-3.5 h-3.5 shrink-0" />
                <span className="flex-1">
                  A ATA dizia &quot;{pend.prazo_original}&quot;
                  {prazoSugerido ? "" : " — defina uma data manualmente."}
                </span>
                {prazoSugerido && (
                  <button
                    type="button"
                    onClick={() => onPatch({ prazo: prazoSugerido })}
                    className="shrink-0 inline-flex items-center px-2 py-0.5 rounded-full border border-amber-300 bg-white text-amber-800 font-medium hover:bg-amber-50 cursor-pointer"
                  >
                    Usar esta data
                  </button>
                )}
              </div>
            )}
          </div>
          <LabeledSelect
            label="Status"
            value={pend.status}
            options={STATUS_PENDENCIA.map((s) => ({
              value: s,
              label: s.replace("_", " "),
            }))}
            onChange={(v) => onPatch({ status: v as StatusPendencia })}
          />
        </div>

        <LabeledInput
          label="Meta / Entregável"
          icon={Target}
          value={pend.meta_entregavel ?? ""}
          onChange={(v) => onPatch({ meta_entregavel: v || null })}
        />

        {isRespExterno && (
          <div>
            {mostrarCoResp || pend.co_responsavel_id ? (
              <div className="space-y-1">
                <FieldLabel label="Co-responsável" icon={Users} />
                <div className="flex gap-2">
                  <select
                    value={pend.co_responsavel_id ?? ""}
                    onChange={(ev) =>
                      onPatch({ co_responsavel_id: ev.target.value || null })
                    }
                    className="flex-1 px-3 py-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary/30 bg-white"
                  >
                    <option value="">Selecionar interno…</option>
                    {internosOptions.map((opt) => (
                      <option key={opt.id} value={opt.id}>
                        {opt.nome}
                      </option>
                    ))}
                  </select>
                  <button
                    type="button"
                    onClick={() => {
                      onPatch({ co_responsavel_id: null });
                      setMostrarCoResp(false);
                    }}
                    aria-label="Remover co-responsável"
                    title="Remover co-responsável"
                    className="inline-flex items-center justify-center w-10 rounded-lg border border-slate-200 text-slate-400 hover:text-slate-600 hover:bg-slate-100 cursor-pointer"
                  >
                    <X className="w-4 h-4" />
                  </button>
                </div>
              </div>
            ) : (
              <button
                type="button"
                onClick={() => setMostrarCoResp(true)}
                className="inline-flex items-center gap-1.5 text-xs text-slate-500 hover:text-primary cursor-pointer"
              >
                <Plus className="w-3.5 h-3.5" />
                Adicionar co-responsável
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
