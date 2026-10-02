import { requireSuperAdminNaCentral } from "@/lib/central-de-comando/guard";

/**
 * O gate da seção Central de Comando, no servidor (ADR 0058, decisão 1).
 *
 * O layout do /admin já checou login e papel nas Reuniões, e deixa passar
 * secretária e facilitador (o Dados do Atendimento é deles). Este checa Super
 * admin, antes de qualquer tela da seção existir: quem digita o endereço sem
 * ser Super admin volta para o início. O `AppShell` vem do layout do /admin.
 *
 * Este gate roda na entrada da seção, não a cada tela: na navegação entre as
 * telas daqui, o Partial Rendering do App Router renderiza só a página e não
 * reexecuta este layout (lição da primeira onda, #859). Por isso nenhum Server
 * Component da seção busca dado sensível confiando só nele. Hoje as páginas só
 * leem o endereço, e os números vêm do backend com o token da sessão, pelo
 * `require_super_admin` do router da Central. Página que um dia buscar dado no
 * servidor chama o `requireSuperAdminNaCentral` ela mesma.
 */
export default async function CentralDeComandoLayout({ children }: { children: React.ReactNode }) {
  await requireSuperAdminNaCentral();
  return <>{children}</>;
}
