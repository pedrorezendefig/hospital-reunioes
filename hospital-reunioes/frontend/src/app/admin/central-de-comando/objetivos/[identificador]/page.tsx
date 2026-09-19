import { LenteDoObjetivo } from "@/components/central-de-comando/LenteDoObjetivo";
import { lerPeriodo, PERIODOS, PERIODOS_DO_INSTAGRAM } from "@/lib/central-de-comando/periodo";

/**
 * A lente de um Objetivo (issue #820). Lê o identificador e o período do
 * endereço; os Objetivos do Instagram só têm 7 e 28 dias, então 90 dias no
 * endereço vira o padrão de 28, sem tela de erro.
 */
export default async function LenteDoObjetivoPage({
  params,
  searchParams,
}: {
  params: Promise<{ identificador: string }>;
  searchParams: Promise<{ periodo?: string | string[] }>;
}) {
  const { identificador } = await params;
  const { periodo } = await searchParams;
  const permitidos = identificador.startsWith("instagram") ? PERIODOS_DO_INSTAGRAM : PERIODOS;
  return <LenteDoObjetivo identificador={identificador} periodo={lerPeriodo(periodo, permitidos)} />;
}
