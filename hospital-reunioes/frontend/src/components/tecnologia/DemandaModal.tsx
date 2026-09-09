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
 * Responder no fio é da issue #638: aqui a Conversa é só leitura.
 */

import { useCallback, useEffect, useState } from "react";
import { AlertCircle, Save } from "lucide-react";

import { AdminModal } from "@/components/admin/AdminModal";
import { Select } from "@/components/ui/Select";

import { TipoIcone } from "./TipoIcone";
import {
  BASE_TECNOLOGIA,
  Demanda,
  destinosDe,
  ESTADO_ROTULO,
  EstadoDemanda,
  FALHA_DE_CONEXAO,
  LinhaDaConversa,
  momentoLegivel,
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

export function DemandaModal({ demanda, produtos, pessoas, token, onFechar, onMudou }: Props) {
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
    setErro(null);
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

  const opcoesDeProduto = produtos
    .filter((p) => p.ativo || p.id === demanda.produto_id)
    .map((p) => ({ value: p.id, label: p.ativo ? p.nome : `${p.nome} (inativo)` }));

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
          className="flex items-center gap-2 px-4 py-2 rounded-xl bg-gradient-to-r from-primary to-primary-light text-white text-sm font-semibold shadow-md hover:shadow-lg transition-all"
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
              options={pessoas.map((p) => ({ value: p.id, label: p.nome_completo }))}
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

        <section aria-labelledby="titulo-conversa" className="pt-4 border-t border-border">
          <h3 id="titulo-conversa" className="text-sm font-semibold text-text">
            Conversa
          </h3>
          {conversa.length === 0 ? (
            <p className="mt-2 text-sm text-text-secondary">Nada aconteceu nesta Demanda ainda.</p>
          ) : (
            <ol className="mt-2 space-y-2">
              {conversa.map((linha) => (
                <li
                  key={linha.id}
                  className={`px-3 py-2 rounded-lg text-sm ${
                    linha.linha === "movimento" ? "bg-slate-50 text-text-secondary" : "bg-white border border-border"
                  }`}
                >
                  <span className="block">
                    {linha.autor_nome ? <strong className="font-medium text-text">{linha.autor_nome}: </strong> : null}
                    {linha.texto}
                  </span>
                  <span className="block mt-0.5 text-xs text-slate-400">{momentoLegivel(linha.criado_em)}</span>
                </li>
              ))}
            </ol>
          )}
        </section>
      </div>
    </AdminModal>
  );
}
