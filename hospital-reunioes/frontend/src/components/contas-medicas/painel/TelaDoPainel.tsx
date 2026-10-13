import type { Painel } from "@/lib/contas-medicas/painel";

import { BlocoCausaRaiz } from "./BlocoCausaRaiz";
import { BlocoCustoIa } from "./BlocoCustoIa";
import { BlocoItensQueFaltam } from "./BlocoItensQueFaltam";
import { BlocoNivelEvidencia } from "./BlocoNivelEvidencia";
import { BlocoNotaPorSemana } from "./BlocoNotaPorSemana";
import { BlocoProducao } from "./BlocoProducao";
import { CartaoContasConcluidas } from "./CartaoContasConcluidas";
import { CartaoCoordenacao } from "./CartaoCoordenacao";
import { CartaoNaoProcede } from "./CartaoNaoProcede";
import { CartaoNotaMedia } from "./CartaoNotaMedia";
import { CartaoValorApontado } from "./CartaoValorApontado";

/**
 * Os cartões e os blocos do Painel (issue #1137). Cada um aparece quando a
 * chave dele vem no payload: é o servidor quem decide o que cada pessoa vê, e
 * a faturista recebe só a produção. Cartão novo entra aqui, ao lado dos outros.
 */
export function TelaDoPainel({ painel }: { painel: Painel }) {
  const temCartoes =
    painel.nota_media || painel.contas_concluidas || painel.valor_apontado || painel.nao_procede || painel.coordenacao;
  return (
    <div className="space-y-4">
      {temCartoes && (
        <div className="grid gap-4 grid-cols-2 lg:grid-cols-4">
          {painel.nota_media && <CartaoNotaMedia nota={painel.nota_media} />}
          {painel.contas_concluidas && <CartaoContasConcluidas contas={painel.contas_concluidas} />}
          {painel.valor_apontado && <CartaoValorApontado valor={painel.valor_apontado} />}
          {painel.nao_procede && <CartaoNaoProcede naoProcede={painel.nao_procede} />}
          {painel.coordenacao && <CartaoCoordenacao coordenacao={painel.coordenacao} />}
        </div>
      )}
      <div className="grid gap-4 lg:grid-cols-2">
        {painel.nota_por_semana && <BlocoNotaPorSemana pontos={painel.nota_por_semana} />}
        {painel.causa_raiz && <BlocoCausaRaiz causas={painel.causa_raiz} />}
        {painel.itens_que_faltam && <BlocoItensQueFaltam itens={painel.itens_que_faltam} />}
        <BlocoProducao linhas={painel.producao} />
        {painel.nivel_evidencia && <BlocoNivelEvidencia semanas={painel.nivel_evidencia} />}
        {painel.custo_ia && <BlocoCustoIa custo={painel.custo_ia} />}
      </div>
    </div>
  );
}
