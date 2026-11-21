import Link from "next/link";

/** Uma linha do trilho do Início (issue #1936): a próxima Reunião. */
export interface ItemDoTrilho {
  tipo: string;
  id: string;
  titulo: string;
  data: string;
  hora: string | null;
  papel: "facilitador" | "participante";
  destino: string;
}

/** Uma Rotina do ciclo de agora no trilho (issue #1944). */
export interface RotinaDoCiclo {
  id: string;
  titulo: string;
  ciclo_inicio: string;
  ciclo_fim: string;
  verificacao: "REALIZADA" | "NAO_REALIZADA" | null;
  destino: string;
}

const MARCA: Record<string, string> = { REALIZADA: "Realizada", NAO_REALIZADA: "Não realizada" };

/** "2026-11-29" vira "29/11", sem passar por fuso. */
function diaEMes(iso: string): string {
  const [, mes, dia] = iso.slice(0, 10).split("-");
  return `${dia}/${mes}`;
}

const DIAS_DA_SEMANA = ["dom", "seg", "ter", "qua", "qui", "sex", "sáb"];

/** "2026-11-20" e "14:00" viram "sex, 20/11, 14:00", sem passar por fuso. */
function quando(item: ItemDoTrilho, hoje: string): string {
  const [ano, mes, dia] = item.data.slice(0, 10).split("-").map(Number);
  const semana = item.data.slice(0, 10) === hoje ? "Hoje" : DIAS_DA_SEMANA[new Date(ano, mes - 1, dia).getDay()];
  const data = `${semana}, ${String(dia).padStart(2, "0")}/${String(mes).padStart(2, "0")}`;
  return item.hora ? `${data}, ${item.hora}` : data;
}

/**
 * As Rotinas do ciclo de agora (issue #1944), com quantas já têm Verificação.
 * Quem não é responsável de nenhuma não vê o bloco.
 */
function RotinasDoCicloNoTrilho({ rotinas }: { rotinas: RotinaDoCiclo[] }) {
  const marcadas = rotinas.filter((r) => r.verificacao !== null).length;
  return (
    <aside aria-label="Rotinas do ciclo" className="min-w-0">
      <p className="flex items-baseline justify-between gap-2 pb-2 border-b border-border text-xs text-text-secondary">
        <span aria-hidden className="etiqueta">
          Rotinas do ciclo
        </span>
        <span className="tabular-nums">
          {marcadas} de {rotinas.length} {rotinas.length === 1 ? "marcada" : "marcadas"}
        </span>
      </p>
      <ul>
        {rotinas.map((rotina) => (
          <li key={rotina.id} className="border-b border-border">
            <Link href={rotina.destino} className="block py-3 px-1 rounded-lg hover:bg-slate-50">
              <span className="block text-sm text-text leading-snug">{rotina.titulo}</span>
              <span className="block text-xs text-text-secondary mt-0.5 tabular-nums">
                {`Até ${diaEMes(rotina.ciclo_fim)}, ${rotina.verificacao ? MARCA[rotina.verificacao] : "falta marcar"}`}
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </aside>
  );
}

/**
 * O trilho, ao lado da Minha Fila: as próximas Reuniões da pessoa, com dia,
 * hora e o link para cada uma, e as Rotinas do ciclo. Não conta na frase nem
 * nos contadores.
 */
export function Trilho({
  itens,
  hoje,
  rotinas = [],
}: {
  itens: ItemDoTrilho[];
  hoje: string;
  rotinas?: RotinaDoCiclo[];
}) {
  return (
    <div className="min-w-0 space-y-8">
      <ProximasReunioes itens={itens} hoje={hoje} />
      {rotinas.length > 0 && <RotinasDoCicloNoTrilho rotinas={rotinas} />}
    </div>
  );
}

function ProximasReunioes({ itens, hoje }: { itens: ItemDoTrilho[]; hoje: string }) {
  return (
    <aside aria-label="Próximas Reuniões" className="min-w-0">
      <p aria-hidden className="etiqueta pb-2 border-b border-border text-xs text-text-secondary">
        Próximas Reuniões
      </p>
      {itens.length === 0 ? (
        <p className="py-3.5 text-sm text-text-secondary">Nenhuma Reunião marcada.</p>
      ) : (
        <ul>
          {itens.map((item) => (
            <li key={`${item.tipo}:${item.id}`} className="border-b border-border">
              <Link href={item.destino} className="block py-3 px-1 rounded-lg hover:bg-slate-50">
                <span className="block text-xs text-text-secondary tabular-nums">{quando(item, hoje)}</span>
                <span className="block text-sm text-text mt-0.5 leading-snug">{item.titulo}</span>
                <span className="block text-xs text-text-secondary mt-0.5">
                  {item.papel === "facilitador" ? "Você conduz" : "Você participa"}
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </aside>
  );
}
