/**
 * @vitest-environment jsdom
 */

/**
 * O aviso de encerramento na página do caso (issue #494, RN-80, ADR 0042).
 *
 * A régua de o que dizer vem pronta do servidor (`aviso_do_encerramento`), com
 * teste próprio em `test_ouvidoria_aviso_encerramento.py`. O que só existe aqui
 * é a fiação: a linha aparecer com o que o servidor mandou, ao lado da do
 * acuse, e as situações ficarem distintas na tela.
 *
 * A distinção que mais importa é a mesma da fatia irmã, e vale repeti-la: a
 * tela não pode afirmar que a pessoa soube do desfecho olhando o carimbo do
 * caso, que é gravado antes de o provedor responder. Quem manda é o status da
 * notificação (precedente da issue #373).
 */

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { Dossie } from "./Dossie";

const ENTRADA = "2026-08-14T19:00:00+00:00";

const ACUSE = {
  rotulo: "Acuse de recebimento",
  em: "2026-08-14T19:01:00+00:00",
  situacao: "enviado",
  nota: null,
};

function dossie(aviso: Record<string, unknown> | undefined) {
  return {
    id: "uuid-12",
    protocolo: "2026-0012",
    data_abertura: "2026-08-14",
    prazo_resposta: "2026-08-21",
    status: "encerrado",
    tipo_manifestacao: "reclamacao",
    categoria: "Reclamação",
    setor: "Recepção",
    resumo: "Paciente relata espera acima de duas horas.",
    relato_integral: "Cheguei as 8h e so fui atendido as 10h30.",
    manifestante_nome: "Joana da Silva",
    manifestante_contato: "joana@exemplo.com",
    manifestante_vinculo: "paciente",
    anonimo: false,
    sigilo_reforcado: false,
    dados_incompletos: false,
    desfecho: "procedente",
    desfecho_descricao: "A escala do setor foi reforçada a partir desta semana.",
    gravidade: "medio",
    prazo_area_em: null,
    validada_em: null,
    respondida_em: null,
    resposta_da_area: null,
    respondida_por_nome: null,
    encerrada_em: "2026-08-20T19:00:00+00:00",
    pausada_em: null,
    minutos_pausados: 0,
    reincidencia: false,
    reaberta_em: null,
    canal: "site",
    canal_setor: null,
    canal_ponto: null,
    natureza_informada: null,
    marcos: [
      {
        chave: "T0",
        rotulo: "Entrada",
        em: ENTRADA,
        pendente: false,
        trecho: null,
        minutos_uteis: null,
        em_curso: false,
        tramitacao_anterior_em: null,
      },
    ],
    prazos: [],
    acuse: ACUSE,
    aviso_encerramento: aviso,
    degradado: [],
  };
}

function respostaJson(body: unknown) {
  return { ok: true, json: async () => body } as Response;
}

function montar(caso: Record<string, unknown>) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      if (url.endsWith("/anexos")) return respostaJson({ anexos: [] });
      if (url.endsWith("/notificacoes")) return respostaJson({ notificacoes: [] });
      if (url.endsWith("/prorrogacoes")) return respostaJson({ prorrogacoes: [] });
      if (url.endsWith("/respostas")) return respostaJson({ respostas: [] });
      if (url.endsWith("/tentativas-contato")) return respostaJson({ tentativas: [] });
      return respostaJson(caso);
    })
  );
  render(<Dossie protocolo="2026-0012" token="token-de-teste" />);
}

describe("o aviso de encerramento na página do caso (issue #494)", () => {
  beforeEach(() => {
    vi.unstubAllGlobals();
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("mostra quando o desfecho foi ao manifestante", async () => {
    montar(
      dossie({
        rotulo: "Aviso de encerramento",
        em: "2026-08-20T19:00:00+00:00",
        situacao: "enviado",
        nota: null,
      })
    );

    expect(await screen.findByText("Aviso de encerramento")).toBeTruthy();
    // A situação e a data na mesma linha: a data sozinha aparece em outros
    // pontos da página, e casar com ela isolada provaria outra coisa.
    expect(screen.getByText(/Enviado ao manifestante, 20\/08\/2026/)).toBeTruthy();
  });

  it("não afirma envio quando o email falhou", async () => {
    montar(
      dossie({
        rotulo: "Aviso de encerramento",
        em: "2026-08-20T19:00:00+00:00",
        situacao: "falha_no_envio",
        nota: "O provedor de email recusou a mensagem nas tentativas previstas. Reenvie pelo registro de notificações deste caso.",
      })
    );

    expect(await screen.findByText(/Não entregue/)).toBeTruthy();
    // O acuse desta fixture está entregue: sem o recorte, "Enviado ao
    // manifestante" apareceria pela linha de cima e o teste ficaria vazio.
    expect(screen.getAllByText(/Enviado ao manifestante/)).toHaveLength(1);
    expect(screen.getByText(/Reenvie pelo registro de notificações/)).toBeTruthy();
  });

  it("o que ainda está na fila não vira envio confirmado", async () => {
    montar(
      dossie({
        rotulo: "Aviso de encerramento",
        em: "2026-08-20T19:00:00+00:00",
        situacao: "em_envio",
        nota: null,
      })
    );

    expect(await screen.findByText(/Na fila de envio/)).toBeTruthy();
    expect(screen.getAllByText(/Enviado ao manifestante/)).toHaveLength(1);
  });

  it("diz por que ninguém foi avisado quando não havia canal", async () => {
    montar(
      dossie({
        rotulo: "Aviso de encerramento",
        em: "2026-08-20T19:00:00+00:00",
        situacao: "sem_contato",
        nota: "Sem canal para avisar: o caso é anônimo ou o contato informado não tem email. O desfecho não foi enviado, e este caso fica fora do indicador de resposta conclusiva.",
      })
    );

    expect(await screen.findByText(/Não enviado/)).toBeTruthy();
    expect(screen.getByText(/fica fora do indicador de resposta conclusiva/)).toBeTruthy();
  });

  it("caso de backend antigo não quebra a página do caso", async () => {
    montar(dossie(undefined));

    expect(await screen.findByText("Marcos do caso")).toBeTruthy();
    expect(screen.queryByText("Aviso de encerramento")).toBeNull();
    // A linha irmã continua no lugar: a ausência é do campo novo, não do bloco.
    expect(screen.getByText("Acuse de recebimento")).toBeTruthy();
  });
});
