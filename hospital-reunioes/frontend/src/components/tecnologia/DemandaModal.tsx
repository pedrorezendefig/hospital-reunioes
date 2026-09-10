"use client";

/**
 * O modal da Demanda (issue #637, PRD #634, ADR 0050).
 *
 * Três coisas na mesma janela: os campos editáveis, as portas de movimento
 * (mover de coluna e trocar responsável) e a Conversa em ordem cronológica.
 *
 * As portas são separadas do "Salvar" de propósito, e não por gosto de tela:
 * mover e atribuir gravam linha automática no fio, e o backend tem endpoint
 * próprio para cada um. Um "Salvar" que mandasse tudo junto esconderia dentro
 * de uma edição de texto uma mudança que o quadro inteiro precisa ver.
 *
 * A Conversa, com o fio e as duas portas de escrita, mora no
 * `ConversaDaDemanda` (issue #638). Quem carrega o fio continua sendo o modal,
 * porque mover e atribuir também acrescentam linha nele.
 */

import { useCallback, useEffect, useState } from "react";
import { AlertCircle, Save } from "lucide-react";

import { AdminModal } from "@/components/admin/AdminModal";
import { Select } from "@/components/ui/Select";

import { ConversaDaDemanda } from "./ConversaDaDemanda";
import { CopiarDaDemanda } from "./CopiarDaDemanda";
import { OQueMudaDaDemanda } from "./OQueMudaDaDemanda";
import { TipoIcone } from "./TipoIcone";
import { VinculoDaDemanda } from "./VinculoDaDemanda";
import {
  avisoPorEmail,
  BASE_TECNOLOGIA,
  Demanda,
  destinosDe,
  ESTADO_ROTULO,
  EstadoDemanda,
  EuNaAba,
  FALHA_DE_CONEXAO,
  LinhaDaConversa,
  motivoDaRecusa,
  PessoaDaAba,
  PRIORIDADE_ROTULO,
  PRIORIDADES,
  PrioridadeDemanda,
  ProdutoDaEscolha,
  TIPO_ROTULO,
  TIPOS,
  TipoDemanda,
} from "./demandas";

type Props = {
  demanda: Demanda;
  produtos: ProdutoDaEscolha[];
  pessoas: PessoaDaAba[];
  token: string | null;
  /** Quem está olhando, do ponto de vista do Vínculo (issue #674). */
  eu: EuNaAba;
  onFechar: () => void;
  onMudou: () => void | Promise<void>;
};

function camposDa(demanda: Demanda) {
  return {
    titulo: demanda.titulo,
    descricao: demanda.descricao ?? "",
    tipo: demanda.tipo,
    produto_id: demanda.produto_id,
    prioridade: demanda.prioridade,
    prazo: demanda.prazo ?? "",
  };
}

export function DemandaModal({ demanda, produtos, pessoas, token, eu, onFechar, onMudou }: Props) {
  const [campos, setCampos] = useState(() => camposDa(demanda));
  const [conversa, setConversa] = useState<LinhaDaConversa[]>([]);
  const [erro, setErro] = useState<string | null>(null);

  const autorizacao = useCallback(
    () => ({ Authorization: `Bearer ${token}`, "Content-Type": "application/json" }),
    [token],
  );

  // Só quando o modal troca de Demanda: recarregar depois de mover não pode
  // apagar o que a pessoa acabou de digitar nos campos.
  useEffect(() => {
    setCampos(camposDa(demanda));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [demanda.id]);

  const carregarConversa = useCallback(async () => {
    if (!token) return;
    try {
      const resposta = await fetch(`${BASE_TECNOLOGIA}/demandas/${demanda.id}/conversa`, {
        headers: autorizacao(),
      });
      if (!resposta.ok) {
        setErro("Não foi possível carregar a Conversa desta Demanda.");
        return;
      }
      setConversa(await resposta.json());
    } catch (e) {
      console.error("[admin/tecnologia] falha ao carregar a Conversa", e);
      setErro(FALHA_DE_CONEXAO);
    }
  }, [token, demanda.id, autorizacao]);

  useEffect(() => {
    carregarConversa();
  }, [carregarConversa]);

  async function enviar(url: string, metodo: string, corpo: unknown): Promise<boolean> {
    let resposta: Response;
    try {
      resposta = await fetch(url, { method: metodo, headers: autorizacao(), body: JSON.stringify(corpo) });
    } catch (e) {
      console.error("[admin/tecnologia] falha ao salvar a Demanda", e);
      setErro(FALHA_DE_CONEXAO);
      return false;
    }
    if (!resposta.ok) {
      setErro(await motivoDaRecusa(resposta));
      return false;
    }
    // A ação valeu. O que pode ter faltado é o aviso por e-mail que ela
    // dispara (issue #642): trocar o responsável avisa quem recebeu a Demanda,
    // e quando esse aviso não sai quem trocou é a única pessoa que ainda pode
    // dar o recado por outro caminho. `null` quando não houve nada a avisar,
    // que é o mesmo estado de antes.
    setErro(await avisoPorEmail(resposta));
    await onMudou();
    await carregarConversa();
    return true;
  }

  const salvar = () =>
    enviar(`${BASE_TECNOLOGIA}/demandas/${demanda.id}`, "PATCH", {
      titulo: campos.titulo,
      descricao: campos.descricao,
      tipo: campos.tipo,
      produto_id: campos.produto_id,
      prioridade: campos.prioridade,
      // Campo de data apagado manda `null`: o vazio é "sem prazo", não um
      // texto vazio para o banco engolir.
      prazo: campos.prazo || null,
    });

  const mover = (estado: EstadoDemanda) =>
    enviar(`${BASE_TECNOLOGIA}/demandas/${demanda.id}/mover`, "POST", { estado });

  const atribuir = (responsavel_id: string) =>
    enviar(`${BASE_TECNOLOGIA}/demandas/${demanda.id}/atribuir`, "POST", { responsavel_id });

  /**
   * As duas portas do Vínculo passam pelo MESMO `enviar` das outras (issue
   * #674): quem diz o motivo da recusa (403 de quem não tem login, 503 da
   * integração desligada, 422 do número que não serve) é o servidor, e a frase
   * dele já aparece no alerta lá em cima. Um caminho de rede próprio para o
   * Vínculo repetiria esse tratamento e divergiria dele na primeira mudança.
   */
  const enviarDoVinculo = (url: string, corpo?: unknown) => enviar(url, "POST", corpo ?? {});

  const opcoesDeProduto = produtos
    .filter((p) => p.ativo || p.id === demanda.produto_id)
    .map((p) => ({ value: p.id, label: p.ativo ? p.nome : `${p.nome} (inativo)` }));

  const opcoesDeResponsavel = pessoas.map((p) => ({ value: p.id, label: p.nome_completo }));
  /**
   * O responsável de hoje entra na lista mesmo se saiu da aba.
   *
   * A API recusa criar e atribuir para quem perdeu o acesso, mas dado antigo
   * existe: o `Select` da casa cai no placeholder quando o valor não casa com
   * nenhuma opção, e o modal diria "Sem responsável" enquanto o card mostra o
   * nome. Mesmo remendo que a lista de Produtos já faz com o dono.
   */
  const opcoesComOAtual =
    demanda.responsavel_id && !pessoas.some((p) => p.id === demanda.responsavel_id)
      ? [
          ...opcoesDeResponsavel,
          {
            value: demanda.responsavel_id,
            label: `${demanda.responsavel_nome ?? demanda.responsavel_id} (sem acesso à aba)`,
          },
        ]
      : opcoesDeResponsavel;

  return (
    <AdminModal
      open
      onClose={onFechar}
      title={demanda.titulo}
      description={`${ESTADO_ROTULO[demanda.estado] ?? demanda.estado} · ${demanda.produto_nome ?? "sem Produto"}`}
      icon={<TipoIcone tipo={demanda.tipo} className="w-5 h-5 text-primary" />}
      size="xl"
      scrollable
      footer={
        <button
          type="button"
          onClick={salvar}
          // Por cima da guarda do backend, não no lugar dela: quem recusa
          // título vazio é o router, com frase de gente. Aqui só se evita o
          // clique que já se sabe que vai voltar recusado.
          disabled={!campos.titulo.trim()}
          className="flex items-center gap-2 px-4 py-2 rounded-xl bg-gradient-to-r from-primary to-primary-light text-white text-sm font-semibold shadow-md hover:shadow-lg transition-all disabled:opacity-50"
        >
          <Save className="w-4 h-4" />
          Salvar
        </button>
      }
    >
      <div className="space-y-5">
        {erro && (
          <p
            role="alert"
            className="flex items-start gap-2 px-4 py-3 rounded-xl bg-red-50 border border-red-200 text-red-700 text-sm"
          >
            <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
            <span>{erro}</span>
          </p>
        )}

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <label className="block md:col-span-2">
            <span className="text-xs font-medium text-text-secondary">Título</span>
            <input
              type="text"
              aria-label="Título"
              maxLength={200}
              value={campos.titulo}
              onChange={(e) => setCampos({ ...campos, titulo: e.target.value })}
              className="mt-1 w-full px-3 py-2 text-sm border border-slate-200 rounded-lg outline-none focus:border-primary focus:ring-1 focus:ring-primary bg-white"
            />
          </label>

          <label className="block md:col-span-2">
            <span className="text-xs font-medium text-text-secondary">Descrição</span>
            <textarea
              aria-label="Descrição"
              rows={3}
              value={campos.descricao}
              onChange={(e) => setCampos({ ...campos, descricao: e.target.value })}
              className="mt-1 w-full px-3 py-2 text-sm border border-slate-200 rounded-lg outline-none focus:border-primary focus:ring-1 focus:ring-primary bg-white"
            />
          </label>

          {/* Logo abaixo da descrição, e não junto dos controles do Vínculo
              (issue #676): a descrição é o que o hospital pediu, e o "O que
              muda" é o que a Vitta vai entregar em resposta. Quem lê o card
              lê os dois seguidos. Ele não é editável, e some inteiro quando não
              há Vínculo. */}
          <OQueMudaDaDemanda demanda={demanda} />

          <Select
            label="Tipo"
            value={campos.tipo}
            onChange={(tipo) => setCampos({ ...campos, tipo: tipo as TipoDemanda })}
            options={TIPOS.map((t) => ({ value: t, label: TIPO_ROTULO[t] }))}
          />

          <Select
            label="Produto"
            value={campos.produto_id}
            onChange={(produto_id) => setCampos({ ...campos, produto_id })}
            options={opcoesDeProduto}
          />

          <Select
            label="Prioridade"
            value={campos.prioridade}
            onChange={(prioridade) => setCampos({ ...campos, prioridade: prioridade as PrioridadeDemanda })}
            options={PRIORIDADES.map((p) => ({ value: p, label: PRIORIDADE_ROTULO[p] }))}
          />

          <label className="block">
            <span className="text-xs font-medium text-text-secondary">Prazo</span>
            <input
              type="date"
              aria-label="Prazo"
              value={campos.prazo}
              onChange={(e) => setCampos({ ...campos, prazo: e.target.value })}
              className="mt-1 w-full px-3 py-2 text-sm border border-slate-200 rounded-lg outline-none focus:border-primary focus:ring-1 focus:ring-primary bg-white"
            />
          </label>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-4 border-t border-border">
          <div>
            <Select
              label="Responsável"
              value={demanda.responsavel_id ?? ""}
              onChange={atribuir}
              options={opcoesComOAtual}
              placeholder="Sem responsável"
            />
            <p className="mt-1 text-xs text-text-secondary">
              Trocar o responsável vale na hora e entra na Conversa.
            </p>
          </div>

          <div>
            <span className="text-xs font-medium text-text-secondary">Mover para</span>
            <div className="mt-1 flex flex-wrap gap-2">
              {destinosDe(demanda.estado).map((destino) => (
                <button
                  key={destino}
                  type="button"
                  onClick={() => mover(destino)}
                  className="px-3 py-1.5 rounded-lg border border-border text-sm text-text hover:border-primary hover:text-primary transition-colors"
                >
                  {ESTADO_ROTULO[destino]}
                </button>
              ))}
            </div>
          </div>
        </div>

        <VinculoDaDemanda demanda={demanda} eu={eu} onEnviar={enviarDoVinculo} />

        <CopiarDaDemanda demanda={demanda} token={token} />

        <ConversaDaDemanda
          demandaId={demanda.id}
          linhas={conversa}
          pessoas={pessoas}
          token={token}
          onFioMudou={carregarConversa}
          onErro={setErro}
        />
      </div>
    </AdminModal>
  );
}
