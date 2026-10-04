/**
 * @vitest-environment jsdom
 */

/**
 * O menu de reticências da linha da fila (issue #777).
 *
 * Ele abria `position: absolute` dentro da linha, e os dois cards que desenham
 * a fila fecham em `overflow-hidden` para clipar os filhos ao canto
 * arredondado. Recorte não olha `z-index`: o menu do caso destacado no topo
 * sumia inteiro atrás do bloco de manifestações listado logo abaixo, e o da
 * última linha de cada grupo saía pela metade.
 *
 * A suíte mira o bloco AGUARDANDO SEU ENCERRAMENTO porque é o card mais baixo
 * da tela, o que o diretor reportou: com uma linha só, não há altura nenhuma
 * dentro do card onde o menu pudesse caber.
 */

import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { BottomNav } from "@/components/layout/BottomNav";

import OuvidoriaPage from "./page";

vi.mock("next/navigation", () => ({
  usePathname: () => "/ouvidoria",
}));

vi.mock("@/lib/supabase/client", () => ({
  createClient: () => ({
    auth: {
      getSession: async () => ({ data: { session: { access_token: "token-de-teste" } } }),
    },
  }),
}));

vi.mock("@/hooks/useCurrentParticipante", () => ({
  useCurrentParticipante: () => ({
    participante: {
      id: "p1",
      nome_completo: "Marta Ouvidora",
      email: "marta@hsm",
      perfil_ouvidoria: "ouvidor",
    },
    loading: false,
  }),
}));

const BLOCO = /aguardando seu encerramento/i;
const PROTOCOLO = "2026-0007";

/** O caso respondido com novidade, que é o que sobe para o bloco do topo. */
const CASO = {
  id: "uuid-7",
  numero: 7,
  protocolo: PROTOCOLO,
  data_abertura: "2026-08-14",
  prazo_resposta: "2026-08-21",
  status: "respondido",
  tipo_manifestacao: "reclamacao",
  sigilo_reforcado: false,
  categoria: "Demora",
  setor: "Recepcao",
  resumo: "Esperei na consulta muito mais que o combinado.",
  conversa_id: "",
  gravidade: null,
  prazo_area_em: null,
  prazo_estourado: false,
  rotulo_prazo: "",
  minutos_uteis_restantes: null,
  tem_novidade: true,
};

function montar() {
  vi.stubGlobal(
    "fetch",
    vi.fn(
      async () =>
        ({
          ok: true,
          status: 200,
          json: async () => ({ protocolos: [CASO], degradado: [] }),
        }) as Response
    )
  );
  render(<OuvidoriaPage />);
}

/** Monta a tela e abre o menu pelo botão de reticências da linha do bloco. */
async function abrirOMenuDoBloco(): Promise<HTMLElement> {
  montar();
  const bloco = await screen.findByRole("region", { name: BLOCO });
  fireEvent.click(
    within(bloco).getByRole("button", { name: `Mais ações da manifestação ${PROTOCOLO}` })
  );
  return bloco;
}

/**
 * A camada declarada na classe, `z-50` ou `z-[150]`. jsdom não empilha nada,
 * então o que se trava é a causa: quem declara a camada maior.
 */
function camada(el: Element): number {
  const z = el.className.match(/(?:^|\s)z-(?:\[(\d+)\]|(\d+))(?:\s|$)/);
  if (!z) throw new Error(`sem z-index na classe: ${el.className}`);
  return Number(z[1] ?? z[2]);
}

function painel(): HTMLElement | null {
  return document.body.querySelector<HTMLElement>(`[aria-label="Ações da manifestação ${PROTOCOLO}"]`);
}

describe("menu de ações da fila (issue #777)", () => {
  beforeEach(() => {
    vi.unstubAllGlobals();
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("o painel aberto não fica dentro do card que recorta a fila", async () => {
    // O coração do bug. Enquanto o painel for descendente da seção, o
    // `overflow-hidden` dela o recorta, e nenhum `z-index` desfaz isso.
    const bloco = await abrirOMenuDoBloco();

    const aberto = painel();
    expect(aberto).not.toBeNull();
    expect(bloco.contains(aberto)).toBe(false);
    expect(document.body.contains(aberto)).toBe(true);
  });

  it("o gatilho continua na linha, junto do botão do estado", async () => {
    // Só o painel viaja. O botão de reticências fora da linha seria outro bug.
    const bloco = await abrirOMenuDoBloco();

    expect(
      within(bloco).getByRole("button", { name: `Mais ações da manifestação ${PROTOCOLO}` })
    ).toBeTruthy();
  });

  it("a ação escolhida no menu acontece", async () => {
    // Com o painel fora da caixa do gatilho, o `mousedown` de quem fecha o
    // flutuante ao clicar fora passa a enxergar o item do menu como "fora", e
    // desmonta o botão antes de o `click` chegar nele. O menu viraria enfeite.
    await abrirOMenuDoBloco();

    const redirecionar = within(painel()!).getByRole("button", { name: "Redirecionar" });
    fireEvent.mouseDown(redirecionar);
    fireEvent.click(redirecionar);

    expect(await screen.findByText("Redirecionar para a área nova")).toBeTruthy();
  });

  it("clicar fora fecha o menu", async () => {
    await abrirOMenuDoBloco();
    expect(painel()).not.toBeNull();

    fireEvent.mouseDown(document.body);

    expect(painel()).toBeNull();
  });

  it("Escape fecha o menu", async () => {
    await abrirOMenuDoBloco();
    expect(painel()).not.toBeNull();

    fireEvent.keyDown(document, { key: "Escape" });

    expect(painel()).toBeNull();
  });

  it("a rolagem fecha o menu", async () => {
    // Preso à janela, o painel não acompanha a linha que o abriu: rolando a
    // fila ele ficaria parado no ar, apontando para outro caso.
    await abrirOMenuDoBloco();
    expect(painel()).not.toBeNull();

    fireEvent.scroll(window);

    expect(painel()).toBeNull();
  });

  it("abrir leva o foco ao primeiro item do painel", async () => {
    // Portado para o fim do `body`, o painel deixou de vir logo depois do
    // gatilho no DOM: o Tab saía do botão de reticências para a linha seguinte,
    // o `main` rolava e a rolagem fechava o menu antes de o foco chegar nele.
    await abrirOMenuDoBloco();

    const primeiro = within(painel()!).getAllByRole("button")[0];
    expect(document.activeElement).toBe(primeiro);
  });

  it("Escape devolve o foco ao gatilho", async () => {
    // Sem isso o foco cai no `body` junto com o painel desmontado, e quem usa
    // teclado recomeça do topo da página.
    const bloco = await abrirOMenuDoBloco();

    fireEvent.keyDown(document.activeElement!, { key: "Escape" });

    expect(painel()).toBeNull();
    expect(document.activeElement).toBe(
      within(bloco).getByRole("button", { name: `Mais ações da manifestação ${PROTOCOLO}` })
    );
  });

  it("o painel fica acima da barra de baixo do celular", async () => {
    // A barra é `fixed bottom-0` e o painel desce quando cabe na janela
    // inteira: numa linha logo acima da barra, os últimos itens caíam atrás
    // dela. Painel numa camada abaixo da barra é a ação que não aparece de novo.
    render(<BottomNav />);
    await abrirOMenuDoBloco();

    const barra = screen.getByRole("navigation", { name: "Navegação principal" });
    expect(camada(painel()!)).toBeGreaterThan(camada(barra));
  });
});
