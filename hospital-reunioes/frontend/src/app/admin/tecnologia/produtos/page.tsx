"use client";

/**
 * A tela de Produtos da aba Tecnologia (issue #1060, PRD #1056).
 *
 * A engrenagem ao lado de "Nova Demanda", no Quadro, traz para cá; a seta
 * volta ao Quadro. O cadastro é o de sempre (`ProdutosDaTecnologia`), que antes
 * morava no rodapé do Quadro. O gate de verdade é o `require_super_admin` do
 * backend; este daqui só evita desenhar botões que a API vai recusar.
 */

import Link from "next/link";
import { ArrowLeft, Lock } from "lucide-react";

import { ProdutosDaTecnologia } from "@/components/tecnologia/ProdutosDaTecnologia";
import { ROTA_TECNOLOGIA } from "@/components/tecnologia/demandas";
import { useCurrentParticipante } from "@/hooks/useCurrentParticipante";
import { isSuperAdmin } from "@/lib/auth";

const SEM_ACESSO = "A aba Tecnologia é do Super admin. Fale com quem administra o aplicativo se você precisa entrar.";

export default function ProdutosPage() {
  const { participante, loading: carregandoPerfil } = useCurrentParticipante();

  // Enquanto o perfil não chegou, o cadastro NÃO é desenhado: desenhar e
  // esconder depois deixaria os botões à mão de quem não é Super admin durante
  // as idas à rede do hook. O layout de `/admin` deixa entrar qualquer papel.
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
      <div className="flex items-center gap-3 min-w-0">
        <Link
          href={ROTA_TECNOLOGIA}
          aria-label="Voltar ao Quadro"
          title="Voltar ao Quadro"
          className="p-2 rounded-lg hover:bg-slate-100 transition-colors text-text-secondary flex-shrink-0"
        >
          <ArrowLeft className="w-4 h-4" />
        </Link>
        <div className="min-w-0">
          <h1 className="text-base font-bold text-text-primary truncate">Produtos</h1>
          <p className="text-xs text-text-secondary">
            Cada coisa que a Vitta mantém para o hospital, com o dono que responde por ela.
          </p>
        </div>
      </div>

      <ProdutosDaTecnologia />
    </div>
  );
}
