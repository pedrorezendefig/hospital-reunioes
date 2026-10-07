/**
 * O selo de Etapa do card (issue #674, PRD #673, ADR 0054).
 *
 * Um componente só, usado em todo lugar onde a Demanda aparece como card (o
 * Quadro e os três blocos do Painel). Cópias do mesmo `<span>` divergiriam na
 * primeira mudança de rótulo, e é justamente o rótulo que o diretor lê.
 *
 * Demanda sem Vínculo não tem selo: "Registrada" é a ausência dele
 * (ADR 0054, decisão 9), e é o `temSelo` que decide isso, aqui dentro. Quem
 * chama não precisa repetir a condição, e por isso não pode esquecê-la.
 */

import { Demanda, ETAPA_CLASSE, EtapaDemanda, temSelo, textoDoSelo } from "./demandas";

export function SeloDeEtapa({ demanda }: { demanda: Demanda }) {
  if (!temSelo(demanda)) return null;

  return (
    <span
      // O nome é o par na tela do que o backend derivou: quem lê com leitor de
      // tela precisa saber que este texto é a etapa da entrega, e não mais uma
      // marca solta na fileira de marcas do card.
      aria-label={`Etapa: ${textoDoSelo(demanda)}`}
      className={`px-2 py-0.5 rounded font-medium ${ETAPA_CLASSE[demanda.etapa as EtapaDemanda]}`}
    >
      {textoDoSelo(demanda)}
    </span>
  );
}
