"use client";

/**
 * A galeria dos Objetivos da Central de Comando (issue #820, PRD #809, ADR 0058).
 *
 * Pede ao backend a lista dos seis Objetivos com o numero de hoje dos que tem
 * montador, e desenha os cards: os quatro navegaveis levam a lente; os dois em
 * construcao aparecem esmaecidos, sem numero e sem destino. A conta e do
 * backend; a tela so escreve.
 *
 * Honestidade do dado, como nas outras telas: sem credencial (503 com a frase
 * do backend) ou com a fonte fora e nada guardado (502), a galeria diz o que
 * houve e nao inventa numero.
 */

import Link from "next/link";
import {
  AlertTriangle,
  Building2,
  Globe,
  Heart,
  type LucideIcon,
  Loader2,
  Phone,
  PlugZap,
  Star,
  Target,
  Users,
} from "lucide-react";
import { useEffect, useState } from "react";

import { getAuthToken } from "@/hooks/useAuth";
import { BASE_CENTRAL, FALHA_DE_CONEXAO, type Frescor, lerRecusa, SEM_SESSAO } from "@/lib/central-de-comando/api";
import { formatarInteiro } from "@/lib/central-de-comando/formato";

export const CAMINHO_OBJETIVOS = "/admin/central-de-comando/objetivos";

/** O numero de hoje de um Objetivo na galeria (o primeiro numero da lente). */
export type NumeroDaGaleria = {
  chave: string;
  rotulo: string;
  valor: number;
};

/** Um Objetivo na galeria: os metadados e o numero de hoje (ou nada). */
export type ObjetivoDaGaleria = {
  id: string;
  nome: string;
  descricao: string;
  em_construcao: boolean;
  numero: NumeroDaGaleria | null;
};

/** O que `GET /api/admin/central-de-comando/objetivos` devolve. */
export type GaleriaPayload = {
  objetivos: ObjetivoDaGaleria[];
  frescor: Frescor;
};

type Estado =
  | { tipo: "carregando" }
  | { tipo: "pronto"; dados: GaleriaPayload }
  | { tipo: "nao-configurado"; mensagem: string }
  | { tipo: "falhou"; mensagem: string }
  | { tipo: "sem-conexao"; mensagem: string };

// O icone de cada Objetivo: escolha de tela, mora aqui (o backend nao manda
// icone). Objetivo fora do mapa cai no alvo, para nunca faltar icone.
const ICONE_DO_OBJETIVO: Record<string, LucideIcon> = {
  "site-visitantes": Globe,
  "instagram-seguidores": Users,
  "instagram-engajamento": Heart,
  "site-area": Building2,
  contatos: Phone,
  "google-reputacao": Star,
};

export function Objetivos() {
  const [estado, setEstado] = useState<Estado>({ tipo: "carregando" });

  useEffect(() => {
    let vivo = true;

    async function carregar() {
      let token: string | undefined;
      try {
        token = await getAuthToken();
      } catch {
        token = undefined;
      }
      if (!token) {
        if (vivo) setEstado({ tipo: "sem-conexao", mensagem: SEM_SESSAO });
        return;
      }
      try {
        const resposta = await fetch(`${BASE_CENTRAL}/objetivos`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (!resposta.ok) {
          const recusa = await lerRecusa(resposta);
          if (vivo) setEstado(recusa);
          return;
        }
        const dados = (await resposta.json()) as GaleriaPayload;
        if (vivo) setEstado({ tipo: "pronto", dados });
      } catch {
        if (vivo) setEstado({ tipo: "sem-conexao", mensagem: FALHA_DE_CONEXAO });
      }
    }

    carregar();
    return () => {
      vivo = false;
    };
  }, []);

  return (
    <div className="animate-fade-in-up space-y-6">
      <header className="flex items-center gap-3">
        <div className="rounded-xl bg-primary/10 p-2 text-primary">
          <Target className="h-6 w-6" />
        </div>
        <div>
          <h1 className="text-2xl font-bold text-text">Objetivos</h1>
          <p className="text-sm text-text-secondary">
            Escolha onde a diretoria quer chegar e veja os números que importam para cada direção.
          </p>
        </div>
      </header>

      {estado.tipo === "carregando" && (
        <div
          role="status"
          className="flex items-center gap-2 rounded-2xl border border-border bg-white p-6 text-sm text-text-secondary shadow-premium"
        >
          <Loader2 className="h-4 w-4 animate-spin" />
          Carregando os Objetivos
        </div>
      )}

      {estado.tipo === "pronto" && (
        <ul aria-label="Objetivos" className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {estado.dados.objetivos.map((objetivo) => (
            <li key={objetivo.id}>
              <CardDoObjetivo objetivo={objetivo} />
            </li>
          ))}
        </ul>
      )}

      {estado.tipo === "nao-configurado" && (
        <div role="status" className="flex gap-3 rounded-2xl border border-amber-200 bg-amber-50 p-6 text-amber-900">
          <PlugZap className="mt-0.5 h-5 w-5 shrink-0" />
          <div className="space-y-1">
            <p className="font-semibold">Sem ligação com a fonte dos números</p>
            <p className="text-sm">{estado.mensagem}</p>
          </div>
        </div>
      )}

      {(estado.tipo === "falhou" || estado.tipo === "sem-conexao") && (
        <div role="alert" className="flex gap-3 rounded-2xl border border-red-200 bg-red-50 p-6 text-red-900">
          <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0" />
          <div className="space-y-1">
            <p className="font-semibold">Não foi possível carregar os Objetivos agora.</p>
            <p className="text-sm">{estado.mensagem}</p>
          </div>
        </div>
      )}
    </div>
  );
}

function CardDoObjetivo({ objetivo }: { objetivo: ObjetivoDaGaleria }) {
  const Icone = ICONE_DO_OBJETIVO[objetivo.id] ?? Target;

  if (objetivo.em_construcao) {
    return (
      <div className="flex h-full flex-col rounded-2xl border border-dashed border-border bg-bg p-5 text-text-secondary">
        <CabecalhoDoCard Icone={Icone} nome={objetivo.nome} descricao={objetivo.descricao} esmaecido />
        <span className="mt-4 inline-flex w-fit items-center rounded-lg bg-border/50 px-2.5 py-1 text-xs font-medium">
          Em construção
        </span>
      </div>
    );
  }

  return (
    <Link
      href={`${CAMINHO_OBJETIVOS}/${objetivo.id}`}
      className="flex h-full flex-col rounded-2xl border border-border bg-white p-5 shadow-premium transition-colors hover:border-primary/40 hover:bg-primary/5"
    >
      <CabecalhoDoCard Icone={Icone} nome={objetivo.nome} descricao={objetivo.descricao} />
      {objetivo.numero ? (
        <div className="mt-4">
          <p className="text-3xl font-bold tabular-nums text-text">{formatarInteiro(objetivo.numero.valor)}</p>
          <p className="text-xs text-text-secondary">{objetivo.numero.rotulo}</p>
        </div>
      ) : (
        <p className="mt-4 text-sm text-text-secondary">Ver os números</p>
      )}
    </Link>
  );
}

function CabecalhoDoCard({
  Icone,
  nome,
  descricao,
  esmaecido = false,
}: {
  Icone: LucideIcon;
  nome: string;
  descricao: string;
  esmaecido?: boolean;
}) {
  return (
    <div className="flex items-start gap-3">
      <span
        aria-hidden="true"
        className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-lg ${
          esmaecido ? "bg-border/50 text-text-secondary" : "bg-primary text-white"
        }`}
      >
        <Icone className="h-4 w-4" />
      </span>
      <div className="space-y-1">
        <h2 className="font-semibold text-text">{nome}</h2>
        <p className="text-xs text-text-secondary">{descricao}</p>
      </div>
    </div>
  );
}
