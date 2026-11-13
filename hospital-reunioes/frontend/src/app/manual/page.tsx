import { Manual } from "@/components/manual/Manual";
import { carregarPaginasDoManual } from "@/lib/manual/carregar";

/**
 * O manual (issue #1718, ADR 0094). O servidor lê as páginas de
 * `public/manual/` e a tela escolhe, pelo menu da pessoa, as que ela vê.
 */
export default async function ManualPage() {
  return <Manual paginas={carregarPaginasDoManual()} />;
}
