/**
 * O depoimento da Apuração do Canal de Conduta (issue #1830; especificação,
 * seções 7.1 e 7.2): os tipos que a API devolve no cartão e as chamadas que
 * enviam e abrem os arquivos.
 *
 * Arquivo nenhum tem URL: a tela pede ao backend, com o login, e recebe o
 * arquivo já decifrado, que vira um endereço local do navegador só enquanto a
 * tela está aberta.
 */
import { createClient } from "@/lib/supabase/client";

export type Papel = "acusado" | "testemunha" | "denunciante";
export type TipoDeArquivo = "transcricao" | "audio" | "termo_assinado";
export type EstadoDoItem = "feito" | "pendente" | "nao_se_aplica";

export interface PaginaDoArquivo {
  id: string;
  content_type: string;
  tamanho_bytes: number;
}

export interface VersaoDoArquivo {
  versao: number;
  enviado_em: string;
  enviado_por: string;
  paginas: PaginaDoArquivo[];
}

export interface ItemDaLista {
  item: string;
  rotulo: string;
  automatico: boolean;
  estado: EstadoDoItem;
  marcado_por?: string;
  marcado_em?: string;
  motivo?: string | null;
}

export interface Depoimento {
  id: string;
  nome: string;
  cargo: string;
  papel: Papel;
  situacao: string;
  arquivos: Record<TipoDeArquivo, VersaoDoArquivo[]>;
  sem_gravacao: { motivo: string; pontos: string; registrado_por: string } | null;
  lista: ItemDaLista[];
  bloqueio_da_conclusao: string | null;
  concluido_em: string | null;
  concluido_por: string | null;
}

export const PAPEIS: { valor: Papel; rotulo: string }[] = [
  { valor: "acusado", rotulo: "Acusado" },
  { valor: "testemunha", rotulo: "Testemunha" },
  { valor: "denunciante", rotulo: "Denunciante identificado" },
];

/** O áudio de um depoimento de duas horas cabe com folga (ADR 0097). */
export const LIMITE_DO_AUDIO = 300 * 1024 * 1024;

/** Cada botão envia para o seu endereço: o tipo é o botão, sem seletor. */
export const BOTOES: Record<TipoDeArquivo, { caminho: string; botao: string; aceita: string; titulo: string }> = {
  transcricao: {
    caminho: "transcricao",
    botao: "ANEXAR TRANSCRIÇÃO DO DEPOIMENTO",
    aceita: ".txt,.vtt,.docx,.pdf",
    titulo: "Transcrição (automática, não revisada)",
  },
  audio: {
    caminho: "audio",
    botao: "ANEXAR ÁUDIO DO DEPOIMENTO",
    aceita: ".mp3,.m4a,.ogg,audio/mpeg,audio/mp4,audio/ogg",
    titulo: "Áudio",
  },
  termo_assinado: {
    caminho: "termo-assinado",
    botao: "ANEXAR TERMO ASSINADO",
    aceita: ".pdf,.jpg,.jpeg,.png,.webp,.heic,.heif,application/pdf,image/*",
    titulo: "Termo assinado",
  },
};

export function rotuloDoPapel(papel: Papel): string {
  return PAPEIS.find((p) => p.valor === papel)?.rotulo ?? papel;
}

/** A data e a hora no relógio do hospital. */
export function dataEHora(iso: string): string {
  return new Date(iso).toLocaleString("pt-BR", {
    timeZone: "America/Sao_Paulo",
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

async function cabecalho(): Promise<Record<string, string>> {
  const {
    data: { session },
  } = await createClient().auth.getSession();
  return { Authorization: `Bearer ${session?.access_token ?? ""}` };
}

async function falha(res: Response): Promise<Error> {
  const corpo = await res.json().catch(() => null);
  if (res.status === 413 && typeof corpo?.detail !== "string") return new Error("O arquivo é grande demais.");
  return new Error(typeof corpo?.detail === "string" ? corpo.detail : "Não foi possível concluir. Tente de novo.");
}

/** Envia os arquivos de um botão. O termo assinado pode ir em várias páginas. */
export async function enviarArquivos(casoId: string, depoimentoId: string, tipo: TipoDeArquivo, arquivos: File[]) {
  const corpo = new FormData();
  for (const arquivo of arquivos) corpo.append("arquivo", arquivo);
  const res = await fetch(`/api/comite-de-conduta/casos/${casoId}/depoimentos/${depoimentoId}/${BOTOES[tipo].caminho}`, {
    method: "POST",
    headers: await cabecalho(),
    body: corpo,
  });
  if (!res.ok) throw await falha(res);
}

/** O arquivo decifrado pelo backend, como endereço local do navegador. Quem
 * chama solta o endereço (`URL.revokeObjectURL`) quando fecha. */
export async function abrirArquivo(casoId: string, depoimentoId: string, arquivoId: string): Promise<string> {
  const res = await fetch(`/api/comite-de-conduta/casos/${casoId}/depoimentos/${depoimentoId}/arquivos/${arquivoId}`, {
    headers: await cabecalho(),
  });
  if (!res.ok) throw await falha(res);
  return URL.createObjectURL(await res.blob());
}
