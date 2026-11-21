"use client";

import { useCallback, useEffect, useState } from "react";
import { AlertCircle, Check, Loader2 } from "lucide-react";

import { DepoimentosDaApuracao } from "@/components/conduta/DepoimentosDaApuracao";
import { OQueFazerAgora } from "@/components/conduta/OQueFazerAgora";
import {
  CATEGORIAS,
  DESTINOS,
  ESCOPOS,
  RITOS,
  chamarComite,
  rotuloDaEtapa,
  rotuloDoRito,
  textoDoPrazo,
  type CasoAberto,
  type Escopo,
  type Rito,
} from "@/lib/conduta/comite";

const CARTAO = "bg-white rounded-2xl border border-border shadow-premium";
const CAMPO = "w-full rounded-xl border border-border bg-white px-3 py-2 text-sm text-slate-900";
const BOTAO =
  "inline-flex items-center justify-center rounded-xl bg-[#282760] px-4 py-2.5 text-sm font-semibold text-white hover:bg-[#1f1e4d] disabled:bg-slate-300 w-full sm:w-auto";
const BOTAO_CLARO =
  "inline-flex items-center justify-center rounded-xl border border-[#282760] bg-white px-4 py-2.5 text-sm font-semibold text-[#282760] w-full sm:w-auto";

interface TriagemDoFormulario {
  escopo: Escopo | "";
  categoria: string;
  rito: Rito | "";
  destino: string;
}

const VAZIA: TriagemDoFormulario = { escopo: "", categoria: "", rito: "", destino: "" };

function rotulo(lista: { valor: string; rotulo: string }[], valor: string | null | undefined): string {
  return lista.find((item) => item.valor === valor)?.rotulo ?? "Não informado";
}

/** Os campos da triagem: dentro, fora ou misto, a categoria, o rito e o destino. */
function CamposDaTriagem({
  valor,
  aoMudar,
}: {
  valor: TriagemDoFormulario;
  aoMudar: (v: TriagemDoFormulario) => void;
}) {
  const fora = valor.escopo === "fora";
  return (
    <div className="grid grid-cols-1 gap-3">
      <fieldset className="space-y-1">
        <legend className="text-sm font-semibold text-slate-700">É do canal?</legend>
        <div className="flex flex-wrap gap-3">
          {ESCOPOS.map((e) => (
            <label key={e.valor} className="flex items-center gap-2 text-sm text-slate-800">
              <input
                type="radio"
                name="escopo"
                value={e.valor}
                checked={valor.escopo === e.valor}
                onChange={() =>
                  aoMudar({
                    ...valor,
                    escopo: e.valor,
                    rito: e.valor === "fora" ? "encaminhamento" : valor.rito === "encaminhamento" ? "" : valor.rito,
                    destino: e.valor === "dentro" ? "" : valor.destino,
                  })
                }
              />
              {e.rotulo}
            </label>
          ))}
        </div>
      </fieldset>
      <label className="text-sm font-semibold text-slate-700 space-y-1">
        <span>Categoria</span>
        <select className={CAMPO} value={valor.categoria} onChange={(e) => aoMudar({ ...valor, categoria: e.target.value })}>
          <option value="">Escolha</option>
          {CATEGORIAS.map((c) => (
            <option key={c.valor} value={c.valor}>
              {c.rotulo}
            </option>
          ))}
        </select>
      </label>
      <label className="text-sm font-semibold text-slate-700 space-y-1">
        <span>Rito</span>
        <select
          className={CAMPO}
          value={valor.rito}
          disabled={fora}
          onChange={(e) => aoMudar({ ...valor, rito: e.target.value as Rito })}
        >
          <option value="">Escolha</option>
          {RITOS.filter((r) => (fora ? r.valor === "encaminhamento" : r.valor !== "encaminhamento")).map((r) => (
            <option key={r.valor} value={r.valor}>
              {`${r.rotulo} (${r.prazo})`}
            </option>
          ))}
        </select>
      </label>
      {valor.escopo && valor.escopo !== "dentro" && (
        <label className="text-sm font-semibold text-slate-700 space-y-1">
          <span>Para onde vai o que não é do canal</span>
          <select className={CAMPO} value={valor.destino} onChange={(e) => aoMudar({ ...valor, destino: e.target.value })}>
            <option value="">Escolha</option>
            {DESTINOS.map((d) => (
              <option key={d.valor} value={d.valor}>
                {d.rotulo}
              </option>
            ))}
          </select>
        </label>
      )}
    </div>
  );
}

function corpoDaTriagem(t: TriagemDoFormulario) {
  return { escopo: t.escopo, categoria: t.categoria, rito: t.rito, destino: t.destino || null };
}

/**
 * A tela do caso do Comitê (issue #1824; especificação, seções 5.3, 6.1 e
 * 6.2): o trilho do rito no topo, o prazo sempre visível, a caixa "O QUE FAZER
 * AGORA" e o relato original. O servidor diz o que a pessoa pode fazer; a tela
 * mostra o formulário do passo quando o botão é tocado.
 */
export function TelaDoCaso({ casoId }: { casoId: string }) {
  const [caso, setCaso] = useState<CasoAberto | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);
  const [ocupado, setOcupado] = useState(false);
  const [passo, setPasso] = useState<string | null>(null);
  const [triagem, setTriagem] = useState<TriagemDoFormulario>(VAZIA);
  const [motivo, setMotivo] = useState("");
  const [justificativa, setJustificativa] = useState("");

  const carregar = useCallback(() => {
    chamarComite<CasoAberto>(`/casos/${casoId}`)
      .then((corpo) => {
        setCaso(corpo);
        setErro(null);
      })
      .catch((e: Error) => setErro(e.message));
  }, [casoId]);

  useEffect(() => {
    carregar();
  }, [carregar]);

  const enviar = async (caminho: string, body?: unknown) => {
    setOcupado(true);
    setAviso(null);
    try {
      await chamarComite(`/casos/${casoId}/${caminho}`, { method: "POST", body: body ?? {} });
      setPasso(null);
      setTriagem(VAZIA);
      setMotivo("");
      setJustificativa("");
      carregar();
    } catch (e) {
      setAviso((e as Error).message);
    } finally {
      setOcupado(false);
    }
  };

  const aoAgir = (acao: string) => {
    if (acao === "conferir_triagem") return void enviar("conferencia");
    if (acao === "enviar_orientacao") return void enviar("encaminhamento");
    setPasso(acao);
  };

  if (erro) {
    return (
      <div role="alert" className={`${CARTAO} flex gap-2 items-start px-4 py-4`}>
        <AlertCircle className="w-5 h-5 shrink-0 text-red-500" aria-hidden />
        <p className="text-sm text-red-700">{erro}</p>
      </div>
    );
  }
  if (caso === null) return <Loader2 className="w-5 h-5 animate-spin text-slate-400" aria-label="Carregando" />;

  const encerrado = caso.situacao === "encerrado";
  const triagemPronta = triagem.escopo && triagem.categoria && triagem.rito && (triagem.escopo === "dentro" || triagem.destino);

  return (
    <div className="space-y-5 min-w-0">
      <header className="space-y-1">
        <h1 className="text-2xl font-bold text-slate-900 tabular-nums">{caso.protocolo}</h1>
        <p className="text-sm text-slate-600">{`${rotuloDoRito(caso.rito)}, ${rotuloDaEtapa(caso.etapa).toLowerCase()}`}</p>
        <p
          aria-label="Prazo"
          className={`text-sm font-semibold ${caso.prazo_vencido && !encerrado ? "text-red-700" : "text-slate-800"}`}
        >
          {textoDoPrazo(caso.faltam_dias, encerrado)}
          {caso.prazo_vencido && <span className="ml-2 text-xs text-red-700">Prazo vencido registrado</span>}
        </p>
      </header>

      <ol aria-label="Trilho do rito" className="flex flex-wrap gap-2">
        {caso.trilho.map((etapa) => (
          <li
            key={etapa.nome}
            aria-current={etapa.estado === "atual" ? "step" : undefined}
            className={`flex items-center gap-1 rounded-full px-3 py-1 text-xs font-semibold ${
              etapa.estado === "atual"
                ? "bg-[#282760] text-white"
                : etapa.estado === "concluida"
                  ? "bg-emerald-100 text-emerald-800"
                  : "bg-slate-100 text-slate-500"
            }`}
          >
            {etapa.estado === "concluida" && <Check className="w-3 h-3" aria-label="concluída" />}
            {etapa.nome}
          </li>
        ))}
      </ol>

      <OQueFazerAgora caixa={caso.o_que_fazer_agora} aoAgir={aoAgir} ocupado={ocupado} />

      {aviso && (
        <p role="alert" className="text-sm text-red-700">
          {aviso}
        </p>
      )}

      {passo === "confirmar_triagem" && (
        <form
          aria-label="Confirmar a triagem"
          className={`${CARTAO} px-4 py-4 space-y-3`}
          onSubmit={(e) => {
            e.preventDefault();
            void enviar("triagem", corpoDaTriagem(triagem));
          }}
        >
          <CamposDaTriagem valor={triagem} aoMudar={setTriagem} />
          <button type="submit" className={BOTAO} disabled={!triagemPronta || ocupado}>
            CONFIRMAR TRIAGEM
          </button>
        </form>
      )}

      {caso.pode_contestar && passo !== "contestar" && (
        <button type="button" className={BOTAO_CLARO} onClick={() => setPasso("contestar")}>
          CONTESTAR TRIAGEM
        </button>
      )}
      {passo === "contestar" && (
        <form
          aria-label="Contestar a triagem"
          className={`${CARTAO} px-4 py-4 space-y-3`}
          onSubmit={(e) => {
            e.preventDefault();
            void enviar("contestacao", { ...corpoDaTriagem(triagem), motivo });
          }}
        >
          <p className="text-sm text-slate-700">A contestação vai à decisão dos três membros votantes.</p>
          <label className="text-sm font-semibold text-slate-700 space-y-1 block">
            <span>Motivo, em uma linha</span>
            <input className={CAMPO} value={motivo} maxLength={500} onChange={(e) => setMotivo(e.target.value)} />
          </label>
          <CamposDaTriagem valor={triagem} aoMudar={setTriagem} />
          <button type="submit" className={BOTAO} disabled={!triagemPronta || !motivo.trim() || ocupado}>
            CONTESTAR TRIAGEM
          </button>
        </form>
      )}

      {passo === "decidir_contestacao" && (
        <div className={`${CARTAO} px-4 py-4 space-y-3`}>
          <p className="text-sm text-slate-700">Vale o que dois dos três escolherem.</p>
          <div className="flex flex-col sm:flex-row gap-2">
            <button type="button" className={BOTAO} disabled={ocupado} onClick={() => void enviar("contestacao/decisao", { escolha: "manter" })}>
              MANTER A TRIAGEM DA COORDENAÇÃO
            </button>
            <button type="button" className={BOTAO_CLARO} disabled={ocupado} onClick={() => void enviar("contestacao/decisao", { escolha: "acatar" })}>
              ACATAR A CONTESTAÇÃO
            </button>
          </div>
        </div>
      )}

      <DepoimentosDaApuracao
        casoId={casoId}
        depoimentos={caso.depoimentos ?? []}
        emApuracao={caso.etapa === "apuracao" && !encerrado}
        bloqueioDoAvanco={caso.avanco_da_apuracao ?? null}
        adicionando={passo === "adicionar_pessoa"}
        aoFecharAdicionar={() => setPasso(null)}
        aoMudar={carregar}
      />

      {caso.triagem_em && (
        <section aria-label="Triagem" className={`${CARTAO} px-4 py-4 space-y-1`}>
          <h2 className="text-base font-semibold text-slate-900">Triagem</h2>
          <p className="text-sm text-slate-700">{rotulo(ESCOPOS, caso.escopo)}</p>
          <p className="text-sm text-slate-700">{rotulo(CATEGORIAS, caso.categoria)}</p>
          <p className="text-sm text-slate-700">{`Rito ${rotuloDoRito(caso.rito)}`}</p>
          {caso.destino && <p className="text-sm text-slate-700">{`Fora do canal: ${rotulo(DESTINOS, caso.destino)}`}</p>}
          <p className="text-xs text-slate-500">
            {caso.conferida_em ? "Conferida pelo segundo leitor" : "Ainda sem a conferência do segundo leitor"}
          </p>
        </section>
      )}

      {caso.contestacao && (
        <section aria-label="Contestação" className={`${CARTAO} px-4 py-4 space-y-1`}>
          <h2 className="text-base font-semibold text-slate-900">Contestação do segundo leitor</h2>
          <p className="text-sm text-slate-800">{caso.contestacao.motivo}</p>
          <p className="text-sm text-slate-700">
            {`Propõe: ${rotulo(ESCOPOS, caso.contestacao.escopo)}, ${rotulo(CATEGORIAS, caso.contestacao.categoria)}, rito ${rotuloDoRito(caso.contestacao.rito)}`}
          </p>
          <p className="text-xs text-slate-500">
            {caso.contestacao.resultado === "acatada"
              ? "Os três decidiram: vale a contestação."
              : caso.contestacao.resultado === "mantida"
                ? "Os três decidiram: vale a triagem da coordenação."
                : `${caso.contestacao.votos} de 3 já decidiram.`}
          </p>
        </section>
      )}

      {caso.orientacao && (
        <section aria-label="Orientação" className={`${CARTAO} px-4 py-4 space-y-1`}>
          <h2 className="text-base font-semibold text-slate-900">
            {encerrado ? "Orientação enviada" : "Resposta padrão a enviar"}
          </h2>
          <p className="text-sm text-slate-800">{caso.orientacao}</p>
        </section>
      )}

      {caso.prorrogacao && (
        <section aria-label="Prorrogação" className={`${CARTAO} px-4 py-4 space-y-2`}>
          <h2 className="text-base font-semibold text-slate-900">Prorrogação do prazo</h2>
          {caso.prorrogacao.justificativa ? (
            <p className="text-sm text-slate-800">{`Prorrogado por 30 dias. ${caso.prorrogacao.justificativa}`}</p>
          ) : passo === "prorrogar" ? (
            <form
              aria-label="Prorrogar o prazo"
              className="space-y-2"
              onSubmit={(e) => {
                e.preventDefault();
                void enviar("prorrogacao", { justificativa });
              }}
            >
              <label className="text-sm font-semibold text-slate-700 space-y-1 block">
                <span>Justificativa</span>
                <textarea className={CAMPO} rows={3} value={justificativa} onChange={(e) => setJustificativa(e.target.value)} />
              </label>
              <button type="submit" className={BOTAO} disabled={!justificativa.trim() || ocupado}>
                PRORROGAR POR 30 DIAS
              </button>
            </form>
          ) : (
            <>
              <p className="text-sm text-slate-700">O rito Completo prorroga uma única vez, por 30 dias, com justificativa.</p>
              <button
                type="button"
                className={BOTAO_CLARO}
                disabled={Boolean(caso.prorrogacao.bloqueio)}
                onClick={() => setPasso("prorrogar")}
              >
                PRORROGAR PRAZO
              </button>
              {caso.prorrogacao.bloqueio && <p className="text-sm text-slate-600">{caso.prorrogacao.bloqueio}</p>}
            </>
          )}
        </section>
      )}

      <section aria-label="Relato original" className={`${CARTAO} px-4 py-4 space-y-1`}>
        <h2 className="text-base font-semibold text-slate-900">Relato original</h2>
        <p className="text-sm text-slate-800 whitespace-pre-line break-words">{caso.relato}</p>
      </section>
    </div>
  );
}
