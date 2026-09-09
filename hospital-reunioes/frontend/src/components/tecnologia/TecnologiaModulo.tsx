"use client";

/**
 * O módulo da aba Tecnologia (issue #636, PRD #634, ADR 0050).
 *
 * A fundação: as três abas (Quadro, Minha vez e Histórico) nascem como casca
 * vazia, e o que já funciona é a gestão de Produtos. O gate de verdade é o
 * `require_super_admin` do backend; a sidebar apenas esconde o item.
 */

import { useCallback, useEffect, useState } from "react";
import { AlertCircle, Cpu, Pencil, Plus, Power, PowerOff } from "lucide-react";

import { useAuth } from "@/hooks/useAuth";
import { Select } from "@/components/ui/Select";

import { QuadroDemandas } from "./QuadroDemandas";
import {
  BASE_TECNOLOGIA,
  FALHA_DE_CONEXAO,
  FiltrosDoQuadro,
  motivoDaRecusa,
  SEM_FILTRO,
} from "./demandas";

type Pessoa = { id: string; nome_completo: string; email: string };

type Produto = {
  id: string;
  nome: string;
  ativo: boolean;
  ordem: number;
  dono_id: string | null;
  dono_nome: string | null;
};

const ABAS = [
  { id: "quadro", label: "Quadro" },
  { id: "minha-vez", label: "Minha vez" },
  { id: "historico", label: "Histórico" },
] as const;

type AbaId = (typeof ABAS)[number]["id"];

/**
 * A frase de quando `useAuth` não devolve token.
 *
 * Ela NÃO manda entrar de novo, de propósito. O hook devolve `token: null`
 * tanto quando a sessão acabou quanto quando o `getUser()` dele falhou por
 * rede, e o componente não distingue as duas: mandar sair e entrar de novo
 * seria cobrar justo a ação que a pessoa não consegue fazer quando a causa é a
 * rede. A frase nomeia as duas causas possíveis e sugere recarregar, que é
 * possível nos dois casos e resolve os dois quando a causa passa.
 */
const SEM_SESSAO =
  "Não foi possível carregar os Produtos: a sessão não está ativa ou o servidor não respondeu. Tente recarregar a página.";

export function TecnologiaModulo() {
  const { token, loading: carregandoAuth } = useAuth();

  const [aba, setAba] = useState<AbaId>("quadro");
  /**
   * Os filtros do Quadro moram aqui, e não dentro dele (issue #639).
   *
   * Trocar de aba desmonta o painel, então um estado guardado lá dentro
   * voltaria ao zero na volta, que é justo o que o critério de aceite proíbe.
   * Aqui em cima eles atravessam a troca de aba e ficam à mão das abas que
   * ainda vêm (Minha vez e Histórico).
   *
   * Não vão para o `localStorage` de propósito: um filtro escolhido ontem
   * voltaria calado no dia seguinte, escondendo Demandas de quem nem lembra
   * de tê-lo posto, e a leitura do storage ainda pode lançar em navegador com
   * dados de site bloqueados. O critério pede a travessia de aba, não a
   * travessia de sessão.
   */
  const [filtros, setFiltros] = useState<FiltrosDoQuadro>(SEM_FILTRO);
  const [produtos, setProdutos] = useState<Produto[]>([]);
  const [pessoas, setPessoas] = useState<Pessoa[]>([]);
  const [carregando, setCarregando] = useState(true);
  const [erro, setErro] = useState<string | null>(null);

  const [nomeNovo, setNomeNovo] = useState("");
  const [donoNovo, setDonoNovo] = useState("");
  const [editando, setEditando] = useState<string | null>(null);
  const [nomeEditado, setNomeEditado] = useState("");

  const autorizacao = useCallback(
    () => ({ Authorization: `Bearer ${token}`, "Content-Type": "application/json" }),
    [token],
  );

  /**
   * Carrega Produtos e pessoas.
   *
   * A falha de rede tem que virar AVISO, não lista vazia: sem o `catch`, o
   * backend fora do ar desenharia a tela calada e sem Produto nenhum, que é
   * indistinguível de "o seed da migration não rodou". Molde do
   * `app/admin/usuarios/page.tsx`, que já trata assim.
   */
  const carregar = useCallback(async () => {
    if (!token) return;
    setCarregando(true);
    try {
      const [respProdutos, respPessoas] = await Promise.all([
        fetch(`${BASE_TECNOLOGIA}/produtos`, { headers: autorizacao() }),
        fetch(`${BASE_TECNOLOGIA}/pessoas`, { headers: autorizacao() }),
      ]);
      if (!respProdutos.ok || !respPessoas.ok) {
        setErro("Não foi possível carregar os Produtos.");
        return;
      }
      setProdutos(await respProdutos.json());
      setPessoas(await respPessoas.json());
      setErro(null);
    } catch (e) {
      console.error("[admin/tecnologia] falha ao carregar", e);
      setErro(FALHA_DE_CONEXAO);
    } finally {
      setCarregando(false);
    }
  }, [token, autorizacao]);

  useEffect(() => {
    if (carregandoAuth) return;
    if (!token) {
      // Sem token a tela ficaria em "Carregando Produtos..." para sempre,
      // porque `carregar` desiste na primeira linha e ninguém desliga a
      // espera. Dizer o que aconteceu é melhor do que girar sem fim.
      setCarregando(false);
      setErro(SEM_SESSAO);
      return;
    }
    carregar();
  }, [carregandoAuth, token, carregar]);

  /** Devolve `true` quando o servidor aceitou. O motivo da recusa vem dele. */
  async function enviar(url: string, metodo: string, corpo: unknown): Promise<boolean> {
    let resposta: Response;
    try {
      resposta = await fetch(url, {
        method: metodo,
        headers: autorizacao(),
        body: JSON.stringify(corpo),
      });
    } catch (e) {
      console.error("[admin/tecnologia] falha ao salvar", e);
      setErro(FALHA_DE_CONEXAO);
      return false;
    }
    if (!resposta.ok) {
      setErro(await motivoDaRecusa(resposta));
      return false;
    }
    setErro(null);
    await carregar();
    return true;
  }

  async function criarProduto() {
    const criado = await enviar(`${BASE_TECNOLOGIA}/produtos`, "POST", {
      nome: nomeNovo,
      dono_id: donoNovo || null,
    });
    if (criado) {
      setNomeNovo("");
      setDonoNovo("");
    }
  }

  async function salvarNome(produto: Produto) {
    const salvo = await enviar(`${BASE_TECNOLOGIA}/produtos/${produto.id}`, "PATCH", { nome: nomeEditado });
    if (salvo) setEditando(null);
  }

  const opcoesDeDono = pessoas.map((p) => ({ value: p.id, label: p.nome_completo }));

  return (
    <div className="animate-fade-in-up space-y-6">
      <div className="flex items-center gap-3">
        <div className="p-2 rounded-xl bg-primary/10 text-primary">
          <Cpu className="w-6 h-6" />
        </div>
        <div>
          <h1 className="text-2xl font-bold text-text">Tecnologia</h1>
          <p className="text-sm text-text-secondary">
            As Demandas entre o hospital e a Vitta sobre os sistemas.
          </p>
        </div>
      </div>

      <div className="flex gap-2 border-b border-border" role="tablist">
        {ABAS.map((item) => (
          <button
            key={item.id}
            role="tab"
            aria-selected={aba === item.id}
            onClick={() => setAba(item.id)}
            className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
              aba === item.id
                ? "border-primary text-primary"
                : "border-transparent text-text-secondary hover:text-text"
            }`}
          >
            {item.label}
          </button>
        ))}
      </div>

      <div role="tabpanel">
        {aba === "quadro" ? (
          <QuadroDemandas
            token={token}
            carregandoAuth={carregandoAuth}
            produtos={produtos}
            pessoas={pessoas}
            filtros={filtros}
            onFiltrosChange={setFiltros}
          />
        ) : (
          <div className="rounded-xl border border-border bg-surface p-6">
            <p className="text-sm text-text-secondary">
              A aba {ABAS.find((item) => item.id === aba)?.label} entra em uma próxima entrega.
            </p>
          </div>
        )}
      </div>

      <section aria-labelledby="titulo-produtos" className="space-y-4">
        <div>
          <h2 id="titulo-produtos" className="text-lg font-semibold text-text">
            Produtos
          </h2>
          <p className="text-sm text-text-secondary">
            Cada coisa que a Vitta mantém para o hospital, com o dono que responde por ela.
          </p>
        </div>

        {erro && (
          <p
            role="alert"
            className="flex items-start gap-2 px-4 py-3 rounded-xl bg-red-50 border border-red-200 text-red-700 text-sm"
          >
            <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
            <span>{erro}</span>
          </p>
        )}

        <div className="grid grid-cols-1 md:grid-cols-[1fr_240px_auto] gap-3 items-start">
          <input
            type="text"
            aria-label="Nome do Produto"
            placeholder="Nome do Produto"
            value={nomeNovo}
            onChange={(e) => setNomeNovo(e.target.value)}
            className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg outline-none focus:border-primary focus:ring-1 focus:ring-primary bg-white"
          />
          <Select
            label="Dono do Produto novo"
            value={donoNovo}
            onChange={setDonoNovo}
            options={opcoesDeDono}
            placeholder="Escolha o dono"
          />
          <button
            onClick={criarProduto}
            disabled={!nomeNovo.trim()}
            className="flex items-center gap-2 px-4 py-2 rounded-xl bg-gradient-to-r from-primary to-primary-light text-white text-sm font-semibold shadow-md hover:shadow-lg transition-all disabled:opacity-50"
          >
            <Plus className="w-4 h-4" />
            Novo Produto
          </button>
        </div>

        {carregando ? (
          <p className="text-sm text-text-secondary">Carregando Produtos...</p>
        ) : (
          <ul className="divide-y divide-border rounded-xl border border-border bg-surface">
            {produtos.map((produto) => (
              <li key={produto.id} className="flex flex-wrap items-center gap-3 px-4 py-3">
                <div className="flex-1 min-w-[180px]">
                  {editando === produto.id ? (
                    <input
                      type="text"
                      aria-label={`Novo nome de ${produto.nome}`}
                      value={nomeEditado}
                      onChange={(e) => setNomeEditado(e.target.value)}
                      className="w-full px-3 py-1.5 text-sm border border-slate-200 rounded-lg outline-none focus:border-primary focus:ring-1 focus:ring-primary bg-white"
                    />
                  ) : (
                    <span className="font-medium text-text">{produto.nome}</span>
                  )}
                </div>

                <span
                  className={`inline-flex px-2 py-0.5 rounded text-xs font-medium ${
                    produto.ativo
                      ? "bg-emerald-50 text-emerald-600"
                      : "bg-slate-100 text-slate-500"
                  }`}
                >
                  {produto.ativo ? "Ativo" : "Inativo"}
                </span>

                {/* Os sete Produtos do seed nascem ativos e sem dono. A API não
                    recusa renomear um deles (não foi essa edição que os deixou
                    assim), então quem cobra o dono é esta marca. */}
                {produto.ativo && !produto.dono_id && (
                  <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium bg-amber-50 text-amber-700">
                    <AlertCircle className="w-3 h-3" />
                    Falta dono
                  </span>
                )}

                <div className="w-[220px]">
                  <Select
                    label={`Dono de ${produto.nome}`}
                    value={produto.dono_id ?? ""}
                    onChange={(dono) =>
                      enviar(`${BASE_TECNOLOGIA}/produtos/${produto.id}`, "PATCH", { dono_id: dono })
                    }
                    options={
                      produto.dono_id && !opcoesDeDono.some((o) => o.value === produto.dono_id)
                        ? [
                            ...opcoesDeDono,
                            {
                              value: produto.dono_id,
                              // A marca é o par na tela do carimbo do backend:
                              // a API recusa abrir Demanda neste Produto e manda
                              // trocar o dono aqui. Sem ela, quem chega vê um
                              // nome normal e não descobre qual é o problema.
                              label: `${produto.dono_nome ?? produto.dono_id} (sem acesso à aba)`,
                            },
                          ]
                        : opcoesDeDono
                    }
                    placeholder="Sem dono definido"
                  />
                </div>

                {editando === produto.id ? (
                  <button
                    onClick={() => salvarNome(produto)}
                    className="px-3 py-1.5 rounded-lg text-sm font-medium text-primary hover:bg-primary/5 transition-colors"
                  >
                    Salvar nome
                  </button>
                ) : (
                  <button
                    onClick={() => {
                      setEditando(produto.id);
                      setNomeEditado(produto.nome);
                    }}
                    title={`Renomear ${produto.nome}`}
                    aria-label={`Renomear ${produto.nome}`}
                    className="p-1.5 rounded-lg text-slate-500 hover:text-primary hover:bg-primary/5 transition-colors"
                  >
                    <Pencil className="w-4 h-4" />
                  </button>
                )}

                <button
                  onClick={() =>
                    enviar(`${BASE_TECNOLOGIA}/produtos/${produto.id}`, "PATCH", { ativo: !produto.ativo })
                  }
                  aria-label={`${produto.ativo ? "Desativar" : "Reativar"} ${produto.nome}`}
                  className="p-1.5 rounded-lg text-slate-500 hover:text-text hover:bg-primary/5 transition-colors"
                >
                  {produto.ativo ? (
                    <PowerOff className="w-4 h-4" />
                  ) : (
                    <Power className="w-4 h-4" />
                  )}
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
