import { redirect } from "next/navigation";

/**
 * Raiz do painel admin — redireciona para a tela default (Usuarios).
 * A verificacao de super_admin e feita pelo layout.
 */
export default function AdminRootPage() {
  redirect("/admin/usuarios");
}
