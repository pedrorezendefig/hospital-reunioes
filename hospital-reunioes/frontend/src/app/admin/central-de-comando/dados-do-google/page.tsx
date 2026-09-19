import { DadosDoGoogle } from "@/components/central-de-comando/DadosDoGoogle";
import { lerPeriodo } from "@/lib/central-de-comando/periodo";

/**
 * Os Dados do Google da Central de Comando (issue #817, ADR 0058).
 *
 * O período mora no endereço (`?periodo=`): o link guardado abre no mesmo
 * período, e o que se digita errado vira o padrão de 28 dias. Esta página só
 * lê o endereço: os números vêm do backend, pela tela, com o token da sessão.
 */
export default async function DadosDoGooglePage({
  searchParams,
}: {
  searchParams: Promise<{ periodo?: string | string[] }>;
}) {
  const { periodo } = await searchParams;
  return <DadosDoGoogle periodo={lerPeriodo(periodo)} />;
}
