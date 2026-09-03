/**
 * @vitest-environment jsdom
 */

/**
 * O campo do desfecho mudou de público (issue #494, RN-80, ADR 0042).
 *
 * `desfecho_descricao` sempre foi o texto que o ouvidor escreve PARA quem
 * manifestou (RN-64), mas até esta fatia ele nunca saía do hospital: ficava no
 * Dossiê e na linha do tempo, atrás do gate da Ouvidoria. Agora ele viaja por
 * email ao manifestante.
 *
 * A tela é a única coisa entre o ouvidor e esse email. Se ela continuar
 * apresentando o campo como registro interno, o ouvidor escreve nome de
 * colaborador e medida disciplinar achando que é nota de processo, e isso sai
 * assinado pelo domínio do hospital, contra a letra do ADR 0042. Estes testes
 * são o que impede o aviso de ser removido "por ser feio" sem ninguém notar.
 */

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { EncerrarModal } from "./EncerrarModal";

function montar() {
  render(
    <EncerrarModal
      manifestacao={{ id: "uuid-12", protocolo: "2026-0012" }}
      token="token-de-teste"
      onClose={vi.fn()}
      onEncerrada={vi.fn()}
    />
  );
}

describe("o desfecho é texto que sai do hospital (issue #494)", () => {
  afterEach(() => {
    cleanup();
  });

  it("o rótulo do campo nomeia o destinatário", () => {
    montar();

    // "Descrição do desfecho" descrevia um registro; "Desfecho para o
    // manifestante" nomeia quem vai ler. É a diferença entre o ouvidor achar
    // que documenta o caso e saber que está escrevendo uma carta.
    expect(screen.getByLabelText(/Desfecho para o manifestante/)).toBeTruthy();
    expect(screen.queryByLabelText(/Descrição do desfecho/)).toBeNull();
  });

  it("avisa que o texto sai do hospital por email, antes de a pessoa escrever", () => {
    montar();

    const aviso = screen.getByText(/Este texto sai do hospital/);
    expect(aviso).toBeTruthy();
    // Antes do campo no DOM, e não numa nota de rodapé: quem já escreveu o
    // texto não volta para reler.
    const campo = screen.getByLabelText(/Desfecho para o manifestante/);
    expect(aviso.compareDocumentPosition(campo) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("diz o que não pode ir no texto", () => {
    montar();

    // O aviso genérico ("cuidado com o que escreve") não muda comportamento
    // nenhum. O que muda é nomear as duas coisas que o ADR 0042 proíbe no
    // corpo destes emails.
    expect(screen.getByText(/nome de colaborador/)).toBeTruthy();
    expect(screen.getByText(/medida disciplinar/)).toBeTruthy();
  });

  it("diz que caso anônimo ou sem email não recebe", () => {
    montar();

    // Sem isto, o ouvidor de um caso anônimo escreveria para uma pessoa que
    // nunca vai ler, e o silêncio do sistema pareceria falha de envio.
    expect(screen.getByText(/Caso anônimo ou sem email no contato não/)).toBeTruthy();
  });

  it("o placeholder fala com a pessoa, não com o processo", () => {
    montar();

    expect(screen.getByPlaceholderText(/dito para quem reclamou/)).toBeTruthy();
  });
});
