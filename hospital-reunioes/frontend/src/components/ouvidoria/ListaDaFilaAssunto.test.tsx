/**
 * @vitest-environment jsdom
 */

/**
 * A fila mostra o assunto (issue #1624, ADR 0087).
 *
 * O agente de triagem escreve um assunto de uma linha, sem nome de ninguém, e
 * a fila o mostra no lugar do começo do relato. O resumo do canal aberto é
 * recorte literal do que a pessoa escreveu, e é por ali que o nome do paciente
 * aparecia na fila. Quando o agente não gerou o assunto, a linha diz isso. Para
 * quem está fora da Ouvidoria o assunto nem chega, e a linha fica sem texto,
 * como já ficava sem o resumo.
 */

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import type { ManifestacaoIndice } from "@/lib/ouvidoria/fila";

import { ListaDaFila } from "./ListaDaFila";

const RESUMO_COM_NOME = "Minha mãe Maria Aparecida Souza caiu do leito no quarto 204";

function caso(extra: Partial<ManifestacaoIndice>): ManifestacaoIndice {
  return {
    id: "uuid-7",
    numero: 7,
    protocolo: "2026-0007",
    data_abertura: "2026-11-12",
    prazo_resposta: "2026-11-19",
    status: "em_classificacao",
    tipo_manifestacao: null,
    sigilo_reforcado: true,
    categoria: "A classificar",
    setor: "A definir",
    conversa_id: "",
    gravidade: null,
    prazo_area_em: null,
    prazo_estourado: false,
    rotulo_prazo: "",
    minutos_uteis_restantes: null,
    tem_novidade: false,
    ...extra,
  };
}

function desenhar(m: ManifestacaoIndice) {
  const nada = () => {};
  render(
    <ListaDaFila
      itens={[m]}
      hoje="2026-11-13"
      responsaveis={[]}
      podeAbrirDossie
      cobrancas={{}}
      onValidar={nada}
      onEncerrar={nada}
      onCobrar={nada}
      onRedirecionar={nada}
      onArquivar={nada}
      onDesarquivar={nada}
    />,
  );
}

afterEach(cleanup);

describe("a linha da fila", () => {
  it("mostra o assunto do agente e não o começo do relato", () => {
    desenhar(caso({ resumo: RESUMO_COM_NOME, assunto: "Queda do leito na internação" }));

    expect(screen.getByText("Queda do leito na internação")).toBeTruthy();
    expect(document.body.textContent).not.toContain("Maria Aparecida Souza");
  });

  it("diz Assunto não gerado quando o agente não escreveu", () => {
    desenhar(caso({ resumo: RESUMO_COM_NOME, assunto: null }));

    expect(screen.getByText("Assunto não gerado")).toBeTruthy();
    expect(document.body.textContent).not.toContain("Maria Aparecida Souza");
  });

  it("fica sem texto para quem não recebe o assunto", () => {
    desenhar(caso({ sigilo_reforcado: false }));

    expect(screen.queryByText("Assunto não gerado")).toBeNull();
  });
});
