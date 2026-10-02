import { Instagram } from "@/components/central-de-comando/Instagram";
import { PERIODOS_DO_INSTAGRAM, lerPeriodo } from "@/lib/central-de-comando/periodo";

/**
 * O Instagram da Central de Comando (issue #819, ADR 0058).
 *
 * O período mora no endereço (`?periodo=`), só 7 e 28 dias: o que se digita
 * fora disso (90 dias, por exemplo) vira o padrão de 28, sem tela de erro. Esta
 * página só lê o endereço; os números vêm do backend, pela tela, com o token
 * da sessão.
 */
export default async function InstagramPage({
  searchParams,
}: {
  searchParams: Promise<{ periodo?: string | string[] }>;
}) {
  const { periodo } = await searchParams;
  return <Instagram periodo={lerPeriodo(periodo, PERIODOS_DO_INSTAGRAM)} />;
}
