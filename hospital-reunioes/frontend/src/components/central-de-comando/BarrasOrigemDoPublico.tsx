import { formatarFatia, formatarInteiro } from "@/lib/central-de-comando/formato";
import { COR_DA_BARRA, COR_DA_BARRA_DO_RESTO, COR_DO_TRILHO } from "@/lib/central-de-comando/graficos";

/**
 * Uma origem do bloco `origem_do_publico` do payload de Dados do Google: as
 * Visitas do período que chegaram por ela, o rótulo da tela e a fatia em
 * pontos percentuais. O backend manda só as que tiveram Visita, na ordem da
 * tela (Outros e Não identificado no fim), com cada fatia arredondada sozinha,
 * como na Central antiga: abaixo de 1% vem 0 ponto, que a tela escreve "<1%".
 */
export type OrigemDoPayload = {
  chave: string;
  rotulo: string;
  visitas: number;
  percentual: number;
};

/** O resto: o que o Google não classificou, ou as origens pequenas somadas. */
const RESTO = new Set(["outros", "nao-identificado"]);

/**
 * As barras da Origem do público de Dados do Google (issue #818, ADR 0058).
 *
 * Porte da divisão por origem da Central antiga em Tailwind puro: cada origem
 * com o rótulo, a barra com a largura da fatia, a fatia e as Visitas. O resto
 * (Outros e Não identificado) fica em cinza, e, quando aparece, uma nota diz
 * o que ele é: a tela nunca mostra o termo cru da fonte.
 */
export function BarrasOrigemDoPublico({ origens }: { origens: OrigemDoPayload[] }) {
  if (origens.length === 0) {
    return (
      <p className="py-10 text-center text-sm text-text-secondary">Sem dados de Origem do público para este período.</p>
    );
  }

  const temResto = origens.some((origem) => RESTO.has(origem.chave));

  return (
    <div className="space-y-4">
      <ul aria-label="Visitas por Origem do público" className="space-y-3">
        {origens.map((origem) => {
          const resto = RESTO.has(origem.chave);
          return (
            <li key={origem.chave} className="space-y-1.5">
              <div className="flex items-baseline gap-3 text-sm">
                <span className={resto ? "text-text-secondary" : "font-medium text-text"}>{origem.rotulo}</span>
                <span className="ml-auto font-semibold tabular-nums text-text">{formatarFatia(origem.percentual)}</span>
                <span className="w-24 text-right text-xs tabular-nums text-text-secondary">
                  {formatarInteiro(origem.visitas)} {origem.visitas === 1 ? "visita" : "visitas"}
                </span>
              </div>
              <div
                aria-hidden="true"
                className="h-2 overflow-hidden rounded-full"
                style={{ backgroundColor: COR_DO_TRILHO }}
              >
                <div
                  data-testid="barra"
                  className="h-full min-w-0.5 rounded-full"
                  style={{
                    width: `${origem.percentual}%`,
                    backgroundColor: resto ? COR_DA_BARRA_DO_RESTO : COR_DA_BARRA,
                  }}
                />
              </div>
            </li>
          );
        })}
      </ul>
      {temResto && (
        <p className="border-t border-border pt-3 text-xs text-text-secondary">
          <b className="font-semibold text-text">Outros</b> soma as demais origens, cada uma pequena.{" "}
          <b className="font-semibold text-text">Não identificado</b> são as Visitas que o Google não classificou
          ou omitiu para proteger a privacidade.
        </p>
      )}
    </div>
  );
}
