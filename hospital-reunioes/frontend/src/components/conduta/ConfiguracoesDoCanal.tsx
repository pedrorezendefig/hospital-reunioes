"use client";

import { useCallback, useEffect, useState } from "react";
import { Lock } from "lucide-react";

import {
  ErroDoCanal,
  ROTA_DAS_CONFIGURACOES,
  chamarConduta,
  linhaDaVersao,
  type ItemDaConfiguracao,
} from "@/lib/conduta/configuracoes";

const CARTAO = "bg-white rounded-2xl border border-border shadow-premium";

function CartaoDoItem({ item, aoSalvar }: { item: ItemDaConfiguracao; aoSalvar: () => Promise<void> }) {
  const [vigente, ...anteriores] = item.versoes;
  const [editando, setEditando] = useState(false);
  const [texto, setTexto] = useState("");
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const idDoCampo = `config-${item.chave}`;

  function editar() {
    setTexto(vigente?.texto ?? "");
    setErro(null);
    setEditando(true);
  }

  async function salvar() {
    setSalvando(true);
    setErro(null);
    try {
      await chamarConduta(`${ROTA_DAS_CONFIGURACOES}/${item.chave}`, { method: "POST", body: { texto } });
      setEditando(false);
      await aoSalvar();
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Não foi possível salvar. Tente de novo.");
    } finally {
      setSalvando(false);
    }
  }

  const igualAVigente = texto.trim() === (vigente?.texto ?? "").trim();

  return (
    <article className={`${CARTAO} px-4 py-4`}>
      <div className="flex items-start justify-between gap-3">
        <h3 className="text-sm font-semibold text-slate-900">{item.rotulo}</h3>
        {!editando && (
          <button
            type="button"
            onClick={editar}
            className="shrink-0 rounded-xl border border-border px-3 py-1.5 text-sm font-semibold text-slate-700 hover:bg-slate-50"
          >
            Editar
          </button>
        )}
      </div>

      {editando ? (
        <div className="mt-3 flex flex-col gap-2">
          <label htmlFor={idDoCampo} className="sr-only">
            {item.rotulo}
          </label>
          <textarea
            id={idDoCampo}
            value={texto}
            onChange={(e) => setTexto(e.target.value)}
            rows={4}
            maxLength={5000}
            className="w-full rounded-xl border border-border px-3 py-2 text-sm text-slate-900"
          />
          <p className="text-xs text-slate-500">A versão de agora continua guardada.</p>
          {erro && <p className="text-sm text-red-700">{erro}</p>}
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={salvar}
              disabled={salvando || !texto.trim() || igualAVigente}
              className="rounded-xl bg-primary px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
            >
              Salvar nova versão
            </button>
            <button
              type="button"
              onClick={() => setEditando(false)}
              className="rounded-xl border border-border px-4 py-2 text-sm font-semibold text-slate-700"
            >
              Cancelar
            </button>
          </div>
        </div>
      ) : vigente ? (
        <div className="mt-2">
          <p className="whitespace-pre-wrap text-sm text-slate-700">{vigente.texto}</p>
          <p className="mt-1 text-xs text-slate-500">{linhaDaVersao(vigente)}</p>
        </div>
      ) : (
        <p className="mt-2 text-sm text-slate-500">Ainda não preenchido.</p>
      )}

      {anteriores.length > 0 && (
        <details className="mt-3">
          <summary className="cursor-pointer text-sm font-semibold text-slate-600">
            Versões anteriores ({anteriores.length})
          </summary>
          <ol className="mt-2 flex flex-col gap-2">
            {anteriores.map((v) => (
              <li key={v.id} className="rounded-xl bg-slate-50 px-3 py-2">
                <p className="whitespace-pre-wrap text-sm text-slate-700">{v.texto}</p>
                <p className="mt-1 text-xs text-slate-500">{linhaDaVersao(v)}</p>
              </li>
            ))}
          </ol>
        </details>
      )}
    </article>
  );
}

/**
 * A tela Configurações do Canal de Conduta (issue #1826, especificação seção
 * 15): os contatos e os textos das telas públicas, e o que o Comitê usa. Cada
 * salvamento é uma versão nova; as anteriores ficam para consulta. Só a
 * coordenação abre: quem decide é a API, e a tela mostra a recusa.
 */
export function ConfiguracoesDoCanal() {
  const [itens, setItens] = useState<ItemDaConfiguracao[] | null>(null);
  const [recusado, setRecusado] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  const carregar = useCallback(async () => {
    try {
      const corpo = await chamarConduta<{ itens: ItemDaConfiguracao[] }>(ROTA_DAS_CONFIGURACOES);
      setItens(corpo.itens);
    } catch (e) {
      if (e instanceof ErroDoCanal && e.status === 403) setRecusado(true);
      else setErro(e instanceof Error ? e.message : "Não foi possível carregar. Tente de novo.");
    }
  }, []);

  useEffect(() => {
    void carregar();
  }, [carregar]);

  if (recusado) {
    return (
      <div className={`${CARTAO} flex gap-3 items-start px-4 py-4`}>
        <Lock className="w-5 h-5 shrink-0 text-slate-400" aria-hidden />
        <p className="text-sm font-semibold text-slate-900">Esta tela é só da coordenação do Comitê.</p>
      </div>
    );
  }
  if (erro) return <p className="text-sm text-red-700">{erro}</p>;
  if (!itens) return <p className="text-sm text-slate-500">Carregando...</p>;

  const grupos = [...new Set(itens.map((item) => item.grupo))];
  return (
    <div className="flex flex-col gap-6">
      {grupos.map((grupo) => (
        <section key={grupo} className="flex flex-col gap-3">
          <h2 className="text-base font-bold text-slate-900">{grupo}</h2>
          {itens
            .filter((item) => item.grupo === grupo)
            .map((item) => (
              <CartaoDoItem key={item.chave} item={item} aoSalvar={carregar} />
            ))}
        </section>
      ))}
    </div>
  );
}
