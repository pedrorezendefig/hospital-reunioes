// Selo discreto "N de M assinaram" (issue #275, ADR 0030).
// A contagem e persistida pelo backend no fechamento real do Envelope
// (close/auto_close/deadline). Null = sem selo: 100% ClickSign, contagem
// ausente (Reuniao legada) ou valores invalidos. O visual atual do banner
// de ASSINADA fica intacto nesses casos.
export function seloAssinaturas(assinaram?: number | null, total?: number | null): string | null {
  if (typeof assinaram !== "number" || typeof total !== "number") return null;
  if (total <= 0 || assinaram < 0 || assinaram >= total) return null;
  return `${assinaram} de ${total} assinaram`;
}
