import { requireSuperAdminNaCentral } from "@/lib/central-de-comando/guard";

/**
 * O gate da seção Central de Comando, no servidor (ADR 0058, decisão 1).
 *
 * O layout do /admin já checou login e papel nas Reuniões, e deixa passar
 * secretária e facilitador (o Dados do Atendimento é deles). Este checa Super
 * admin, antes de qualquer tela da seção existir: quem digita o endereço sem
 * ser Super admin volta para o início. O `AppShell` vem do layout do /admin.
 */
export default async function CentralDeComandoLayout({ children }: { children: React.ReactNode }) {
  await requireSuperAdminNaCentral();
  return <>{children}</>;
}
