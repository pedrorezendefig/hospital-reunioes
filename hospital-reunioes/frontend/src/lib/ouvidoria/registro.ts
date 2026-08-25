/**
 * Registro manual da manifestação (issue #321, ADR 0034).
 *
 * O que o formulário do ouvidor monta antes de mandar para a API. A regra do
 * anonimato mora aqui, e não no JSX: apagar nome e contato é decisão de
 * domínio, não detalhe de tela.
 */

export type CanalManual = "telefone" | "presencial" | "email";

export const CANAIS: { valor: CanalManual; rotulo: string }[] = [
  { valor: "telefone", rotulo: "Telefone" },
  { valor: "presencial", rotulo: "Presencial (balcão)" },
  { valor: "email", rotulo: "Email" },
];

export const VINCULOS = [
  { valor: "paciente", rotulo: "Paciente" },
  { valor: "acompanhante", rotulo: "Acompanhante" },
  { valor: "colaborador", rotulo: "Colaborador" },
  { valor: "terceiro", rotulo: "Terceiro" },
  { valor: "outro", rotulo: "Outro" },
];

/**
 * O que o seletor de arquivo oferece. Espelha a lista que o backend aceita
 * (`app/services/ouvidoria_anexos.py`): filtrar já no diálogo evita o ouvidor
 * escolher um .zip e só descobrir a recusa depois de o caso existir.
 */
export const EXTENSOES_ACEITAS =
  ".jpg,.jpeg,.png,.webp,.heic,.pdf,.mp3,.m4a,.ogg,.wav,.doc,.docx,.odt,.txt";

export interface FormularioRegistro {
  canal: CanalManual;
  /** Valor de um input datetime-local: "2026-08-14T16:50", hora de Brasília. */
  contatoEm: string;
  categoria: string;
  setor: string;
  resumo: string;
  relatoIntegral: string;
  manifestanteNome: string;
  manifestanteContato: string;
  manifestanteVinculo: string;
  anonimo: boolean;
}

export interface RegistroManual {
  canal: CanalManual;
  contato_em: string;
  categoria: string;
  setor: string;
  resumo: string;
  relato_integral: string;
  manifestante_nome: string | null;
  manifestante_contato: string | null;
  manifestante_vinculo: string | null;
  anonimo: boolean;
}

function textoOuNulo(valor: string): string | null {
  const limpo = valor.trim();
  return limpo === "" ? null : limpo;
}

/**
 * Monta o corpo do POST. O T0 vai como o ouvidor digitou (hora do contato
 * real, não do clique) e o backend o interpreta em horário de Brasília.
 */
export function montarRegistro(form: FormularioRegistro): RegistroManual {
  const identificado = !form.anonimo;
  return {
    canal: form.canal,
    contato_em: form.contatoEm,
    categoria: form.categoria.trim(),
    setor: form.setor.trim(),
    resumo: form.resumo.trim(),
    relato_integral: form.relatoIntegral.trim(),
    manifestante_nome: identificado ? textoOuNulo(form.manifestanteNome) : null,
    manifestante_contato: identificado ? textoOuNulo(form.manifestanteContato) : null,
    manifestante_vinculo: identificado ? textoOuNulo(form.manifestanteVinculo) : null,
    anonimo: form.anonimo,
  };
}

/**
 * Valor inicial do campo de data e hora: agora, no relógio local, no formato
 * que o input datetime-local aceita. O ouvidor corrige para o momento real do
 * contato quando registra depois.
 */
export function agoraParaCampoLocal(agora: Date = new Date()): string {
  const doisDigitos = (n: number) => String(n).padStart(2, "0");
  return (
    `${agora.getFullYear()}-${doisDigitos(agora.getMonth() + 1)}-${doisDigitos(agora.getDate())}` +
    `T${doisDigitos(agora.getHours())}:${doisDigitos(agora.getMinutes())}`
  );
}
