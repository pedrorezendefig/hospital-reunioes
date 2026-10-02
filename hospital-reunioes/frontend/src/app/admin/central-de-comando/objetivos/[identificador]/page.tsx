import { LenteDoObjetivo } from "@/components/central-de-comando/LenteDoObjetivo";
import { lerPeriodo } from "@/lib/central-de-comando/periodo";

/**
 * A lente de um Objetivo (issue #820). Lê o identificador e o período do
 * endereço. Quais períodos cada lente tem é o backend quem diz, no payload
 * (issue #847): aqui só o que não é período nenhum vira o padrão de 28. O
 * período que a lente não tem (90 dias no Instagram) cai no padrão dentro da
 * `LenteDoObjetivo`, também sem tela de erro.
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
  return <LenteDoObjetivo identificador={identificador} periodo={lerPeriodo(periodo)} />;
}
