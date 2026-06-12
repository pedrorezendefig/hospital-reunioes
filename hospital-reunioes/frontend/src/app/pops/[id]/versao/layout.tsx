import { requirePopsAccess } from "@/lib/pops/guard";

/**
 * Layout da leitura da Versão (issue #85): mesmo gate da área /pops, sem o
 * AppShell — tela full-screen com header próprio, como a elaboração. Quem
 * decide se ESTE usuário lê/age neste POP é o backend (designados + escopo
 * de Setor; aprovar/devolver só Revisor e Validador designados).
 */
export default async function VersaoLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  await requirePopsAccess();
  return <>{children}</>;
}
