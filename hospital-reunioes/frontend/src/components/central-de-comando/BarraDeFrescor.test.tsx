/**
 * @vitest-environment jsdom
 */

/**
 * A barra de frescor das telas da Central de Comando (issue #815, ADR 0058).
 *
 * Porte de `components/analytics/FreshnessBar.test.tsx` do repositório antigo:
 * o carimbo "Atualizado há X", o botão Atualizar agora, o "Atualizando…" e o
 * aviso calmo quando a atualização falhou, com a hora do último número bom. O
 * aviso de token do Instagram de lá virou o `motivo`, a frase da falha que o
 * backend manda. E o que a issue pede a mais: o tempo relativo anda sozinho,
 * a cada minuto, sem recarregar a página.
 */

import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { BarraDeFrescor } from "./BarraDeFrescor";

// 18/09/2026, 13h50 em Brasília, com os segundos zerados.
const AGORA = Date.parse("2026-09-18T16:50:00Z");
const HA_5_MINUTOS = "2026-09-18T16:45:00+00:00";

function frescor(
  parcial: { atualizado_em?: string | null; atualizacao_falhou?: boolean; motivo?: string | null } = {},
) {
  return {
    atualizado_em: parcial.atualizado_em === undefined ? HA_5_MINUTOS : parcial.atualizado_em,
    atualizacao_falhou: parcial.atualizacao_falhou ?? false,
    motivo: parcial.motivo ?? null,
  };
}

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

describe("BarraDeFrescor", () => {
  it("mostra há quanto tempo os números foram atualizados e o botão", () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.setSystemTime(AGORA);

    render(<BarraDeFrescor frescor={frescor()} atualizando={false} onAtualizar={() => {}} />);

    expect(screen.getByText("Atualizado há 5 minutos")).toBeTruthy();
    expect(screen.getByRole("button", { name: /Atualizar agora/ })).toBeTruthy();
  });

  it("chama a atualização ao clicar", () => {
    const onAtualizar = vi.fn();
    render(<BarraDeFrescor frescor={frescor()} atualizando={false} onAtualizar={onAtualizar} />);

    fireEvent.click(screen.getByRole("button", { name: /Atualizar agora/ }));

    expect(onAtualizar).toHaveBeenCalledTimes(1);
  });

  it("enquanto atualiza, diz 'Atualizando…' e desliga o botão", () => {
    render(<BarraDeFrescor frescor={frescor()} atualizando={true} onAtualizar={() => {}} />);

    const botao = screen.getByRole("button", { name: /Atualizando/ }) as HTMLButtonElement;
    expect(botao.disabled).toBe(true);
    expect(screen.queryByText("Atualizar agora")).toBeNull();
  });

  it("quando a atualização falhou, avisa com calma e diz de que horas são os números", () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.setSystemTime(AGORA);

    render(
      <BarraDeFrescor
        frescor={frescor({
          atualizado_em: "2026-09-18T16:45:00+00:00",
          atualizacao_falhou: true,
          motivo: "O Google Analytics respondeu HTTP 500.",
        })}
        atualizando={false}
        onAtualizar={() => {}}
      />,
    );

    const aviso = screen.getByRole("status");
    expect(aviso.textContent).toContain("Não foi possível atualizar agora");
    expect(aviso.textContent).toContain("Mostrando os números de 13h45");
    expect(aviso.textContent).toContain("O Google Analytics respondeu HTTP 500.");
    expect(screen.queryByText(/^Atualizado/)).toBeNull();
    expect(screen.getByRole("button", { name: /Atualizar agora/ })).toBeTruthy();
  });

  it("número bom de outro dia diz o dia, e não só a hora", () => {
    // O Google fora desde ontem: "os números de 13h45" leria como de hoje.
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.setSystemTime(AGORA);

    render(
      <BarraDeFrescor
        frescor={frescor({ atualizado_em: "2026-09-17T16:45:00+00:00", atualizacao_falhou: true })}
        atualizando={false}
        onAtualizar={() => {}}
      />,
    );

    expect(screen.getByRole("status").textContent).toContain("Mostrando os números de 17/09/2026 às 13h45");
  });

  it("sem hora registrada, não inventa tempo nenhum", () => {
    // O contrato do backend admite `atualizado_em` nulo (frescor de chaves que
    // nunca foram lidas). A barra não escreve "há NaN horas" nem hora falsa.
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.setSystemTime(AGORA);

    const { rerender } = render(
      <BarraDeFrescor frescor={frescor({ atualizado_em: null })} atualizando={false} onAtualizar={() => {}} />,
    );

    expect(screen.queryByText(/NaN/)).toBeNull();
    expect(screen.queryByText(/Atualizado há/)).toBeNull();
    expect(screen.getByRole("button", { name: /Atualizar agora/ })).toBeTruthy();

    rerender(
      <BarraDeFrescor
        frescor={frescor({ atualizado_em: null, atualizacao_falhou: true, motivo: "O Google caiu." })}
        atualizando={false}
        onAtualizar={() => {}}
      />,
    );

    const aviso = screen.getByRole("status").textContent ?? "";
    expect(aviso).toContain("Não foi possível atualizar agora");
    expect(aviso).toContain("O Google caiu.");
    expect(aviso).not.toMatch(/NaN|Mostrando os números de/);
  });

  it("sem carimbo nenhum, não diz 'Atualizado' nem pinta o ponto verde (issue #848)", () => {
    // A Visão Geral com as duas fontes fora (ou sem configurar) e nada guardado:
    // o backend manda `{atualizado_em: null, atualizacao_falhou: false}`. Nenhum
    // bloco deu número, então nada foi atualizado: a barra fica neutra.
    render(<BarraDeFrescor frescor={frescor({ atualizado_em: null })} atualizando={false} onAtualizar={() => {}} />);

    expect(screen.queryByText(/Atualizado/)).toBeNull();
    expect(screen.getByText("Nenhum número disponível agora.")).toBeTruthy();
    expect(document.querySelector(".bg-emerald-500")).toBeNull();
    expect(screen.getByRole("button", { name: /Atualizar agora/ })).toBeTruthy();
  });

  it("falha sem motivo mantém a frase de sempre", () => {
    render(
      <BarraDeFrescor
        frescor={frescor({ atualizado_em: "2026-06-21T16:45:00+00:00", atualizacao_falhou: true })}
        atualizando={false}
        onAtualizar={() => {}}
      />,
    );

    expect(screen.getByRole("status").textContent).toContain("Não foi possível atualizar agora");
  });

  it("o Atualizar agora que não deu certo aparece como aviso, sem tirar o carimbo", () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.setSystemTime(AGORA);

    render(
      <BarraDeFrescor
        frescor={frescor()}
        atualizando={false}
        aviso="Muitas atualizações em pouco tempo. Espere um minuto e tente de novo."
        onAtualizar={() => {}}
      />,
    );

    expect(screen.getByText("Atualizado há 5 minutos")).toBeTruthy();
    expect(screen.getByRole("status").textContent).toBe(
      "Muitas atualizações em pouco tempo. Espere um minuto e tente de novo.",
    );
  });

  it("o tempo anda sozinho, a cada minuto, sem recarregar a página", () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.setSystemTime(AGORA);
    render(<BarraDeFrescor frescor={frescor()} atualizando={false} onAtualizar={() => {}} />);
    expect(screen.getByText("Atualizado há 5 minutos")).toBeTruthy();

    act(() => {
      vi.advanceTimersByTime(60_000);
    });

    expect(screen.getByText("Atualizado há 6 minutos")).toBeTruthy();

    act(() => {
      vi.advanceTimersByTime(55 * 60_000);
    });

    expect(screen.getByText("Atualizado há 1 hora")).toBeTruthy();
  });
});
