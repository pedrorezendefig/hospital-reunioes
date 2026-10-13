"use client";

/**
 * A aba Cenários da tela Coordenação (issue #1143): a lista, o cenário novo
 * (a pessoa escreve, a IA preenche os campos e a pessoa confere os códigos),
 * editar, ativar e desativar. Só aparece para quem tem "incluir regra
 * operacional"; o servidor recusa os outros de novo.
 */

import { useCallback, useEffect, useState } from "react";
import { AlertCircle, Loader2, Plus, Sparkles, Trash2 } from "lucide-react";

import { Ditar, juntarDitado } from "@/components/contas-medicas/Ditar";
import {
  type AbaDeCenarios,
  type CamposDoCenario,
  type Cenario,
  ROTA_CENARIOS,
  cenarioVazio,
} from "@/lib/contas-medicas/coordenacao";

// Sem largura: a linha do insumo dá a de cada campo; os outros ocupam a linha toda.
const CAMPO_SEM_LARGURA =
  "min-h-[38px] px-3 py-1.5 text-sm border border-slate-200 rounded-lg bg-white focus:outline-none focus:border-primary focus:ring-1 focus:ring-primary";
const CAMPO = `w-full ${CAMPO_SEM_LARGURA}`;
const BOTAO =
  "inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-primary text-white text-sm font-medium disabled:opacity-50";
const BOTAO_CLARO =
  "inline-flex items-center gap-2 px-3 py-1.5 rounded-lg border border-slate-200 bg-white text-sm text-slate-700 hover:border-slate-300 disabled:opacity-50";

interface Edicao {
  id: string | null;
  campos: CamposDoCenario;
}

/** O que vai ao servidor: os campos conferidos, sem a marca de tabela da proposta. */
function corpoDoCenario(campos: CamposDoCenario): CamposDoCenario {
  return {
    ...campos,
    insumos: campos.insumos.map(({ codigo, descricao, quantidade }) => ({
      codigo: codigo.trim(),
      descricao: descricao?.trim() || null,
      quantidade: Number(quantidade) || 1,
    })),
  };
}

function camposDe(cenario: Cenario): CamposDoCenario {
  const { nome, operadora_sigla, gatilho_texto, orientacao, ativo, insumos } = cenario;
  return { nome, operadora_sigla, gatilho_texto, orientacao, ativo, insumos };
}

async function detalheDoErro(res: Response, padrao: string): Promise<string> {
  try {
    const corpo = await res.json();
    if (typeof corpo?.detail === "string") return corpo.detail;
  } catch {
    // resposta sem JSON (ex.: 500 do proxy)
  }
  return padrao;
}

export function AbaCenarios({ token }: { token: string }) {
  const [aba, setAba] = useState<AbaDeCenarios | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [edicao, setEdicao] = useState<Edicao | null>(null);
  const [texto, setTexto] = useState("");
  const [lendo, setLendo] = useState(false);
  const [salvando, setSalvando] = useState(false);
  const [fora, setFora] = useState<string[]>([]);
  const [aviso, setAviso] = useState<string | null>(null);

  const cabecalho = { Authorization: `Bearer ${token}`, "Content-Type": "application/json" };

  const carregar = useCallback(async () => {
    try {
      const res = await fetch(ROTA_CENARIOS, { headers: { Authorization: `Bearer ${token}` } });
      if (!res.ok) {
        setErro(await detalheDoErro(res, "Não foi possível carregar os cenários."));
        return;
      }
      setErro(null);
      setAba(await res.json());
    } catch {
      setErro("Não foi possível carregar os cenários.");
    }
  }, [token]);

  useEffect(() => {
    carregar();
  }, [carregar]);

  function mudar(campos: Partial<CamposDoCenario>) {
    setEdicao((atual) => (atual ? { ...atual, campos: { ...atual.campos, ...campos } } : atual));
  }

  function mudarInsumo(indice: number, campos: Partial<CamposDoCenario["insumos"][number]>) {
    if (!edicao) return;
    mudar({ insumos: edicao.campos.insumos.map((insumo, i) => (i === indice ? { ...insumo, ...campos } : insumo)) });
  }

  async function preencherComIa() {
    if (!edicao || !texto.trim()) return;
    setLendo(true);
    setErro(null);
    try {
      const res = await fetch(`${ROTA_CENARIOS}/proposta`, {
        method: "POST",
        headers: cabecalho,
        body: JSON.stringify({ texto: texto.trim() }),
      });
      if (!res.ok) {
        setErro(await detalheDoErro(res, "A IA não conseguiu ler o texto. Preencha os campos à mão."));
        return;
      }
      const proposta = await res.json();
      setEdicao({ ...edicao, campos: proposta.campos });
      setFora(proposta.codigos_fora_da_tabela ?? []);
    } catch {
      setErro("A IA não conseguiu ler o texto. Preencha os campos à mão.");
    } finally {
      setLendo(false);
    }
  }

  async function gravar(id: string | null, campos: CamposDoCenario): Promise<boolean> {
    setSalvando(true);
    setErro(null);
    try {
      const res = await fetch(id ? `${ROTA_CENARIOS}/${id}` : ROTA_CENARIOS, {
        method: id ? "PUT" : "POST",
        headers: cabecalho,
        body: JSON.stringify(corpoDoCenario(campos)),
      });
      if (!res.ok) {
        setErro(await detalheDoErro(res, "Não foi possível salvar o cenário."));
        return false;
      }
      const salvo = await res.json();
      const codigos: string[] = salvo.codigos_fora_da_tabela ?? [];
      setAviso(
        codigos.length > 0
          ? `Cenário salvo. Código fora da tabela da operadora: ${codigos.join(", ")}.`
          : "Cenário salvo.",
      );
      await carregar();
      return true;
    } catch {
      setErro("Não foi possível salvar o cenário.");
      return false;
    } finally {
      setSalvando(false);
    }
  }

  async function salvar() {
    if (edicao && (await gravar(edicao.id, edicao.campos))) {
      setEdicao(null);
      setFora([]);
      setTexto("");
    }
  }

  function abrirNovo() {
    setEdicao({ id: null, campos: cenarioVazio() });
    setTexto("");
    setFora([]);
    setAviso(null);
  }

  if (!aba && !erro) {
    return (
      <p className="flex items-center gap-2 text-sm text-slate-500">
        <Loader2 className="w-4 h-4 animate-spin" aria-hidden="true" /> Carregando os cenários
      </p>
    );
  }

  return (
    <div className="space-y-4">
      {erro && (
        <p role="alert" className="flex items-center gap-2 text-sm text-red-700">
          <AlertCircle className="w-4 h-4" aria-hidden="true" /> {erro}
        </p>
      )}
      {aviso && (
        <p role="status" className="text-sm text-slate-700">
          {aviso}
        </p>
      )}

      {edicao ? (
        <section aria-label={edicao.id ? "Editar cenário" : "Novo cenário"} className="space-y-3 rounded-xl border border-border bg-white p-4">
          <label className="block text-sm text-slate-700">
            Escreva o cenário
            <textarea
              value={texto}
              onChange={(e) => setTexto(e.target.value)}
              rows={3}
              maxLength={4000}
              placeholder="Sondagem vesical ou cirurgia com lidocaína gel: conferir lidocaína gel, sonda e coletor."
              className={`${CAMPO} mt-1`}
            />
          </label>
          <Ditar campo="Cenário" aoTranscrever={(ditado) => setTexto((atual) => juntarDitado(atual, ditado).slice(0, 4000))} />
          <button type="button" onClick={preencherComIa} disabled={lendo || !texto.trim()} className={BOTAO_CLARO}>
            {lendo ? (
              <Loader2 className="w-4 h-4 animate-spin" aria-hidden="true" />
            ) : (
              <Sparkles className="w-4 h-4" aria-hidden="true" />
            )}
            Preencher com a IA
          </button>

          {fora.length > 0 && (
            <p role="alert" className="flex items-center gap-2 text-sm text-amber-800">
              <AlertCircle className="w-4 h-4" aria-hidden="true" />
              Código fora da tabela da operadora: {fora.join(", ")}. Confira antes de salvar.
            </p>
          )}

          <div className="grid gap-3 sm:grid-cols-2">
            <label className="block text-sm text-slate-700">
              Nome
              <input value={edicao.campos.nome} onChange={(e) => mudar({ nome: e.target.value })} className={`${CAMPO} mt-1`} />
            </label>
            <label className="block text-sm text-slate-700">
              Operadora
              <select
                value={edicao.campos.operadora_sigla ?? ""}
                onChange={(e) => mudar({ operadora_sigla: e.target.value || null })}
                className={`${CAMPO} mt-1`}
              >
                <option value="">Todas as operadoras</option>
                {aba?.operadoras.map((operadora) => (
                  <option key={operadora.sigla} value={operadora.sigla}>
                    {operadora.sigla}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <label className="block text-sm text-slate-700">
            Quando dispara
            <textarea
              value={edicao.campos.gatilho_texto}
              onChange={(e) => mudar({ gatilho_texto: e.target.value })}
              rows={2}
              className={`${CAMPO} mt-1`}
            />
          </label>
          <label className="block text-sm text-slate-700">
            Orientação para a coordenadora
            <textarea
              value={edicao.campos.orientacao ?? ""}
              onChange={(e) => mudar({ orientacao: e.target.value || null })}
              rows={2}
              className={`${CAMPO} mt-1`}
            />
          </label>

          <fieldset className="space-y-2">
            <legend className="text-sm font-medium text-slate-700">Insumos a conferir</legend>
            {edicao.campos.insumos.map((insumo, i) => (
              <div key={i} className="flex flex-wrap items-center gap-2">
                <input
                  aria-label={`Código do insumo ${i + 1}`}
                  value={insumo.codigo}
                  onChange={(e) => mudarInsumo(i, { codigo: e.target.value, na_tabela: undefined })}
                  placeholder="Código"
                  className={`${CAMPO_SEM_LARGURA} w-32 font-mono ${insumo.na_tabela === false ? "border-amber-500" : ""}`}
                />
                <input
                  aria-label={`Descrição do insumo ${i + 1}`}
                  value={insumo.descricao ?? ""}
                  onChange={(e) => mudarInsumo(i, { descricao: e.target.value })}
                  placeholder="Descrição"
                  className={`${CAMPO_SEM_LARGURA} flex-1 min-w-[10rem]`}
                />
                <input
                  aria-label={`Quantidade do insumo ${i + 1}`}
                  type="number"
                  min={0}
                  step="any"
                  value={insumo.quantidade}
                  onChange={(e) => mudarInsumo(i, { quantidade: Number(e.target.value) })}
                  className={`${CAMPO_SEM_LARGURA} w-24`}
                />
                <button
                  type="button"
                  aria-label={`Tirar o insumo ${i + 1}`}
                  onClick={() => mudar({ insumos: edicao.campos.insumos.filter((_, j) => j !== i) })}
                  disabled={edicao.campos.insumos.length === 1}
                  className="p-2 text-slate-500 hover:text-red-700 disabled:opacity-30"
                >
                  <Trash2 className="w-4 h-4" aria-hidden="true" />
                </button>
              </div>
            ))}
            <button
              type="button"
              onClick={() => mudar({ insumos: [...edicao.campos.insumos, { codigo: "", descricao: "", quantidade: 1 }] })}
              className={BOTAO_CLARO}
            >
              <Plus className="w-4 h-4" aria-hidden="true" /> Adicionar insumo
            </button>
          </fieldset>

          <label className="flex items-center gap-2 text-sm text-slate-700">
            <input type="checkbox" checked={edicao.campos.ativo} onChange={(e) => mudar({ ativo: e.target.checked })} />
            Ativo
          </label>
          <div className="flex gap-2">
            <button type="button" onClick={salvar} disabled={salvando} className={BOTAO}>
              {salvando && <Loader2 className="w-4 h-4 animate-spin" aria-hidden="true" />} Salvar cenário
            </button>
            <button type="button" onClick={() => setEdicao(null)} className={BOTAO_CLARO}>
              Cancelar
            </button>
          </div>
        </section>
      ) : (
        <button type="button" onClick={abrirNovo} className={BOTAO}>
          <Plus className="w-4 h-4" aria-hidden="true" /> Novo cenário
        </button>
      )}

      {aba && aba.cenarios.length === 0 && (
        <p className="text-sm text-slate-500">Nenhum cenário cadastrado ainda.</p>
      )}
      <ul className="space-y-3">
        {aba?.cenarios.map((cenario) => (
          <li key={cenario.id}>
            <article
              aria-label={`${cenario.codigo} ${cenario.nome}`}
              className={`rounded-xl border px-4 py-3 space-y-1 ${cenario.ativo ? "border-border bg-white" : "border-slate-200 bg-slate-50"}`}
            >
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-mono text-xs text-primary">{cenario.codigo}</span>
                <span className="text-sm font-semibold text-slate-900">{cenario.nome}</span>
                <span className="text-xs text-slate-500">{cenario.operadora_sigla ?? "Todas as operadoras"}</span>
                {!cenario.ativo && (
                  <span className="rounded-full bg-slate-200 px-2 py-0.5 text-[11px] font-semibold text-slate-700">
                    Desativado
                  </span>
                )}
                <span className="ml-auto flex gap-2">
                  <button
                    type="button"
                    onClick={() => {
                      setEdicao({ id: cenario.id, campos: camposDe(cenario) });
                      setTexto("");
                      setFora([]);
                      setAviso(null);
                    }}
                    className={BOTAO_CLARO}
                  >
                    Editar
                  </button>
                  <button
                    type="button"
                    onClick={() => gravar(cenario.id, { ...camposDe(cenario), ativo: !cenario.ativo })}
                    disabled={salvando}
                    className={BOTAO_CLARO}
                  >
                    {cenario.ativo ? "Desativar" : "Ativar"}
                  </button>
                </span>
              </div>
              <p className="text-sm text-slate-700">Quando dispara: {cenario.gatilho_texto}</p>
              <p className="text-xs text-slate-500">
                Insumos:{" "}
                {cenario.insumos
                  .map((insumo) => `${insumo.codigo}${insumo.descricao ? ` ${insumo.descricao}` : ""} (${insumo.quantidade})`)
                  .join(", ")}
              </p>
            </article>
          </li>
        ))}
      </ul>
    </div>
  );
}
