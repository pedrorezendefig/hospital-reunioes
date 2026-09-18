import { VisaoGeral } from "@/components/central-de-comando/VisaoGeral";
import { lerPeriodo } from "@/lib/central-de-comando/periodo";

/**
 * A Visão Geral da Central de Comando (issue #814, ADR 0058).
 *
 * O período mora no endereço (`?periodo=`): o link guardado abre no mesmo
 * período, e o que se digita errado vira o padrão de 28 dias.
 */
export default async function VisaoGeralPage({
  searchParams,
}: {
  searchParams: Promise<{ periodo?: string | string[] }>;
}) {
  const { periodo } = await searchParams;
  return <VisaoGeral periodo={lerPeriodo(periodo)} />;
}
