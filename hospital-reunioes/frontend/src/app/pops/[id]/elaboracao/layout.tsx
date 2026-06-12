import { requirePopsAccess } from "@/lib/pops/guard";

/**
 * Layout da tela dedicada de elaboração (issue #83): mesmo gate da área
 * /pops, sem o AppShell — a tela é full-screen no padrão da Ata Guiada
 * (ADR 0006), com header próprio. Quem decide se ESTE usuário pode
 * elaborar ESTE POP é o backend (403 só ao Elaborador designado).
 */
export default async function ElaboracaoLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  await requirePopsAccess();
  return <>{children}</>;
}
