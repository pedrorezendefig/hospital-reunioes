/**
 * De onde o caso chegou, para o Dossiê (issue #375, itens 10 e 11).
 *
 * `canal_setor` e `canal_ponto` eram write-only: o canal aberto gravava os dois
 * e nenhuma tela lia, então o ouvidor nunca via de qual cartaz o caso veio.
 */

/**
 * O aviso que anda junto do canal "qr".
 *
 * Qualquer pessoa monta `/manifestacao?setor=Recepção&ponto=Poltrona 12` sem
 * nunca ter chegado perto do cartaz. O backend confere o setor contra a
 * taxonomia, mas não que existiu cartaz: "qr" diz de onde o link veio, não que
 * a pessoa esteve no lugar. Dizer isso na tela é o que impede o ouvidor de ler
 * o campo como evidência (decisão 4 da issue).
 */
export const QR_NAO_PROVA_PRESENCA =
  "Ler o QR não prova presença no local: o endereço do formulário pode ser aberto de qualquer lugar.";

export interface OrigemDoCaso {
  canal: string | null;
  canal_setor: string | null;
  canal_ponto: string | null;
}

export interface OrigemDescrita {
  titulo: string;
  /** O cartaz: setor e, quando houver, o ponto. Nulo quando não veio de um. */
  detalhe: string | null;
  aviso: string | null;
}

const TITULO_POR_CANAL: Record<string, string> = {
  qr: "Chegou pelo QR de um cartaz",
  site: "Chegou pelo formulário do site",
  ana: "Chegou pela conversa com a Ana",
  telefone: "Registrada pela Ouvidoria (telefone)",
  presencial: "Registrada pela Ouvidoria (presencial)",
  email: "Registrada pela Ouvidoria (email)",
  carta: "Registrada pela Ouvidoria (carta)",
};

export function descreverOrigem(caso: OrigemDoCaso): OrigemDescrita | null {
  if (!caso.canal) return null;
  const doCartaz = [caso.canal_setor, caso.canal_ponto].filter(
    (parte): parte is string => Boolean(parte?.trim())
  );
  return {
    titulo: TITULO_POR_CANAL[caso.canal] ?? `Chegou pelo canal ${caso.canal}`,
    detalhe: doCartaz.length ? doCartaz.join(", ") : null,
    aviso: caso.canal === "qr" ? QR_NAO_PROVA_PRESENCA : null,
  };
}
