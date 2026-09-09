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

const BASE = "/api/admin/tecnologia";

export function TecnologiaModulo() {
  const { token, loading: carregandoAuth } = useAuth();

  const [aba, setAba] = useState<AbaId>("quadro");
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

  const carregar = useCallback(async () => {
    if (!token) return;
    setCarregando(true);
    try {
      const [respProdutos, respPessoas] = await Promise.all([
        fetch(`${BASE}/produtos`, { headers: autorizacao() }),
        fetch(`${BASE}/pessoas`, { headers: autorizacao() }),
      ]);
      if (!respProdutos.ok || !respPessoas.ok) {
        setErro("Não foi possível carregar os Produtos.");
        return;
      }
      setProdutos(await respProdutos.json());
      setPessoas(await respPessoas.json());
      setErro(null);
    } finally {
      setCarregando(false);
    }
  }, [token, autorizacao]);

  useEffect(() => {
    if (!carregandoAuth && token) carregar();
  }, [carregandoAuth, token, carregar]);

  /** Devolve `true` quando o servidor aceitou. O motivo da recusa vem dele. */
  async function enviar(url: string, metodo: string, corpo: unknown): Promise<boolean> {
    const resposta = await fetch(url, {
      method: metodo,
      headers: autorizacao(),
      body: JSON.stringify(corpo),
    });
    if (!resposta.ok) {
      setErro(await motivoDaRecusa(resposta));
      return false;
    }
    setErro(null);
    await carregar();
    return true;
  }

  async function criarProduto() {
    const criado = await enviar(`${BASE}/produtos`, "POST", {
      nome: nomeNovo,
      dono_id: donoNovo || null,
    });
    if (criado) {
      setNomeNovo("");
      setDonoNovo("");
    }
  }

  async function salvarNome(produto: Produto) {
    const salvo = await enviar(`${BASE}/produtos/${produto.id}`, "PATCH", { nome: nomeEditado });
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

      <div role="tabpanel" className="rounded-xl border border-border bg-surface p-6">
        <p className="text-sm text-text-secondary">
          A aba {ABAS.find((item) => item.id === aba)?.label} entra em uma próxima entrega.
        </p>
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

                <div className="w-[220px]">
                  <Select
                    label={`Dono de ${produto.nome}`}
                    value={produto.dono_id ?? ""}
                    onChange={(dono) =>
                      enviar(`${BASE}/produtos/${produto.id}`, "PATCH", { dono_id: dono })
                    }
                    options={
                      produto.dono_id && !opcoesDeDono.some((o) => o.value === produto.dono_id)
                        ? [
                            ...opcoesDeDono,
                            {
                              value: produto.dono_id,
                              label: produto.dono_nome ?? produto.dono_id,
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
                    enviar(`${BASE}/produtos/${produto.id}`, "PATCH", { ativo: !produto.ativo })
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

async function motivoDaRecusa(resposta: Response): Promise<string> {
  try {
    const corpo = await resposta.json();
    if (typeof corpo?.detail === "string") return corpo.detail;
    if (corpo?.detail) return JSON.stringify(corpo.detail);
  } catch {
    // Resposta sem corpo JSON: sobra o status.
  }
  return `Não foi possível salvar (${resposta.status}).`;
}
