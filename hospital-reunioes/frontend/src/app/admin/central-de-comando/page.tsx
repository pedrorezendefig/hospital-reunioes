import { redirect } from "next/navigation";

/**
 * A raiz da seção Central de Comando leva à Visão Geral.
 *
 * A Visão Geral tem endereço próprio, e não esta raiz, porque o menu marca o
 * item ativo por prefixo: na raiz, ele ficaria aceso em todas as telas.
 */
export default function CentralDeComandoPage() {
  redirect("/admin/central-de-comando/visao-geral");
}
