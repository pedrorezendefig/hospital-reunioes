import { Construction, type LucideIcon } from "lucide-react";

interface EmConstrucaoProps {
  titulo: string;
  icone: LucideIcon;
  descricao: string;
}

/**
 * A tela da Central de Comando que ainda não chegou (issue #814).
 *
 * Existe só para a navegação da seção fechar durante a migração, com a seção
 * dormente em produção: cada fatia do PRD #809 troca a sua tela por esta. Não
 * é o "em breve" que o menu evita (ADR 0058, decisão 5): o que ainda não
 * existe de verdade (Blog, Editor do Site) vai para "O que vem por aí".
 */
export function EmConstrucao({ titulo, icone: Icone, descricao }: EmConstrucaoProps) {
  return (
    <div className="animate-fade-in-up space-y-6">
      <header className="flex items-center gap-3">
        <div className="rounded-xl bg-primary/10 p-2 text-primary">
          <Icone className="h-6 w-6" />
        </div>
        <div>
          <h1 className="text-2xl font-bold text-text">{titulo}</h1>
          <p className="text-sm text-text-secondary">{descricao}</p>
        </div>
      </header>
      <div
        role="status"
        className="flex items-center gap-3 rounded-2xl border border-dashed border-border bg-white p-6 text-sm text-text-secondary"
      >
        <Construction className="h-5 w-5 shrink-0" />
        Em construção nesta migração: esta tela da Central de Comando chega numa das próximas entregas.
      </div>
    </div>
  );
}
