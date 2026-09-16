"use client";

/**
 * A porta de entrada da Demanda (issue #727, PRD #726, ADR 0056, decisão 5).
 *
 * "Nova Demanda", no Quadro, traz para cá. A página hospeda os dois caminhos:
 * o Assistente de Tecnologia (o padrão) e o formulário de sempre, atrás do
 * "prefiro preencher à mão". Nenhum dos dois grava por conta própria: os dois
 * chamam a mesma rota de criação, no clique de quem está olhando.
 */

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { AlertCircle, ArrowLeft, Lock } from "lucide-react";

import { AssistenteDeTecnologia } from "@/components/tecnologia/AssistenteDeTecnologia";
import { FormularioNovaDemanda } from "@/components/tecnologia/FormularioNovaDemanda";
import { BASE_TECNOLOGIA, Demanda, linkDaDemanda, ProdutoDaEscolha, ROTA_TECNOLOGIA } from "@/components/tecnologia/demandas";
import { useAuth } from "@/hooks/useAuth";
import { useCurrentParticipante } from "@/hooks/useCurrentParticipante";
import { isSuperAdmin } from "@/lib/auth";

const SEM_ACESSO = "A aba Tecnologia é do Super admin. Fale com quem administra o aplicativo se você precisa entrar.";
const SEM_PRODUTOS = "Não foi possível carregar os Produtos. Recarregue a página e tente de novo.";

export default function NovaDemandaPage() {
  const router = useRouter();
  const { token, loading: carregandoAuth } = useAuth();
  const { participante, loading: carregandoPerfil } = useCurrentParticipante();
  const [produtos, setProdutos] = useState<ProdutoDaEscolha[]>([]);
  const [erro, setErro] = useState<string | null>(null);
  const [aMao, setAMao] = useState(false);
  /**
   * O aviso de que a Demanda nasceu mas o e-mail de atribuição não saiu.
   *
   * Quando ele existe, a página NÃO navega sozinha: a frase se perderia na
   * troca de tela, e quem criou a Demanda ficaria sem saber que o responsável
   * não foi avisado. O link para o card fica ao lado, à mão.
   */
  const [avisoDeEmail, setAvisoDeEmail] = useState<{ texto: string; link: string } | null>(null);

  useEffect(() => {
    if (carregandoAuth || !token) return;
    let vivo = true;
    fetch(`${BASE_TECNOLOGIA}/produtos`, { headers: { Authorization: `Bearer ${token}` } })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((lista: ProdutoDaEscolha[]) => vivo && setProdutos(lista))
      .catch((e) => {
        console.error("[admin/tecnologia] falha ao carregar os Produtos", e);
        if (vivo) setErro(SEM_PRODUTOS);
      });
    return () => {
      vivo = false;
    };
  }, [token, carregandoAuth]);

  const aoCriar = useCallback(
    (demanda: Demanda, aviso: string | null) => {
      const link = linkDaDemanda(demanda.id, "");
      if (aviso) {
        setAvisoDeEmail({ texto: aviso, link });
        return;
      }
      router.push(link);
    },
    [router],
  );

  // Enquanto o perfil não chegou, a tela NÃO é desenhada. Desenhar e esconder
  // depois deixaria a caixa de mensagem à mão de quem não é Super admin
  // durante as duas idas à rede do hook, que é justamente o que o gate existe
  // para impedir. O layout de `/admin` deixa entrar qualquer papel.
  if (carregandoPerfil) {
    return <p className="max-w-2xl mx-auto px-6 py-16 text-center text-sm text-text-secondary">Carregando...</p>;
  }

  if (!isSuperAdmin(participante)) {
    return (
      <div className="max-w-2xl mx-auto px-6 py-16 text-center space-y-3">
        <Lock className="w-8 h-8 mx-auto text-text-secondary" />
        <h1 className="text-lg font-bold text-text-primary">Sem acesso à aba Tecnologia</h1>
        <p className="text-sm text-text-secondary">{SEM_ACESSO}</p>
      </div>
    );
  }

  return (
    <div className="max-w-7xl mx-auto w-full px-6 py-6 space-y-5">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-3 min-w-0">
          <Link
            href={ROTA_TECNOLOGIA}
            className="p-2 rounded-lg hover:bg-slate-100 transition-colors text-text-secondary flex-shrink-0"
            title="Voltar ao Quadro"
          >
            <ArrowLeft className="w-4 h-4" />
          </Link>
          <div className="min-w-0">
            <h1 className="text-base font-bold text-text-primary truncate">Nova Demanda</h1>
            <p className="text-xs text-text-secondary">
              A Demanda nasce em Nova, com o dono do Produto como responsável.
            </p>
          </div>
        </div>
        <button
          type="button"
          onClick={() => setAMao(!aMao)}
          className="px-3 py-2 rounded-xl border border-border text-sm text-text-secondary hover:border-primary hover:text-primary transition-colors"
        >
          {aMao ? "voltar ao assistente" : "prefiro preencher à mão"}
        </button>
      </div>

      {erro && (
        <p role="alert" className="px-4 py-3 rounded-xl bg-red-50 border border-red-200 text-red-700 text-sm">
          {erro}
        </p>
      )}

      {avisoDeEmail ? (
        <div
          role="alert"
          className="flex flex-wrap items-center gap-3 px-4 py-3 rounded-xl bg-amber-50 border border-amber-200 text-amber-800 text-sm"
        >
          <AlertCircle className="w-4 h-4 shrink-0" />
          <span>{avisoDeEmail.texto}</span>
          <Link href={avisoDeEmail.link} className="font-semibold underline">
            Ver a Demanda no Quadro
          </Link>
        </div>
      ) : aMao ? (
        <FormularioNovaDemanda token={token} produtos={produtos} onCriada={aoCriar} />
      ) : (
        <AssistenteDeTecnologia token={token} produtos={produtos} onCriada={aoCriar} />
      )}
    </div>
  );
}
