"use client";

import { useState } from "react";

import { MOTIVOS_DE_IMPEDIMENTO, chamarComite, type CasoAberto } from "@/lib/conduta/comite";

const CARTAO = "bg-white rounded-2xl border border-border shadow-premium";
const CAMPO = "w-full rounded-xl border border-border bg-white px-3 py-2 text-sm text-slate-900";
const BOTAO =
  "inline-flex items-center justify-center rounded-xl bg-[#282760] px-4 py-2.5 text-sm font-semibold text-white hover:bg-[#1f1e4d] disabled:bg-slate-300 w-full sm:w-auto";
const BOTAO_CLARO =
  "inline-flex items-center justify-center rounded-xl border border-[#282760] bg-white px-4 py-2.5 text-sm font-semibold text-[#282760] disabled:opacity-50 w-full sm:w-auto";

type Parte = Pick<
  CasoAberto,
  "membros_do_caso" | "pode_contestar_participacao" | "contestacoes_de_participacao" | "citados"
>;

interface Pessoa {
  id: string;
  nome: string | null;
}

function situacaoDaContestacao(c: Parte["contestacoes_de_participacao"][number]): string {
  if (c.resultado === "confirmada") return `Os demais decidiram: ${c.contestado} ficou impedido neste caso.`;
  if (c.resultado === "rejeitada") return `Os demais decidiram: ${c.contestado} segue no caso.`;
  return `${c.votos} ${c.votos === 1 ? "voto" : "votos"} até agora. O contestado não decide.`;
}

/**
 * As ações laterais da tela do caso (issue #1828; especificação, 3.3 e 5.3):
 * declarar impedimento, contestar a participação de outro membro e marcar um
 * Citado. Depois de declarar impedimento a pessoa perde o acesso ao caso, e a
 * tela é avisada por `aoImpedir`.
 */
export function ImpedimentoECitados({
  casoId,
  caso,
  aoMudar,
  aoImpedir,
}: {
  casoId: string;
  caso: Parte;
  aoMudar: () => void;
  aoImpedir: () => void;
}) {
  const [passo, setPasso] = useState<"impedimento" | "contestar" | null>(null);
  const [motivo, setMotivo] = useState("");
  const [contestado, setContestado] = useState("");
  const [nome, setNome] = useState("");
  const [achados, setAchados] = useState<Pessoa[] | null>(null);
  const [ocupado, setOcupado] = useState(false);
  const [aviso, setAviso] = useState<string | null>(null);
  const membros = caso.membros_do_caso ?? [];
  const contestacoes = caso.contestacoes_de_participacao ?? [];
  const citados = caso.citados ?? [];

  const enviar = async (caminho: string, body: unknown, depois: () => void = aoMudar) => {
    setOcupado(true);
    setAviso(null);
    try {
      await chamarComite(`/casos/${casoId}/${caminho}`, { method: "POST", body });
      setPasso(null);
      setMotivo("");
      setContestado("");
      setNome("");
      setAchados(null);
      depois();
    } catch (e) {
      setAviso((e as Error).message);
    } finally {
      setOcupado(false);
    }
  };

  const buscar = async () => {
    setOcupado(true);
    setAviso(null);
    try {
      const corpo = await chamarComite<{ pessoas: Pessoa[] }>(
        `/casos/${casoId}/cadastro?busca=${encodeURIComponent(nome.trim())}`
      );
      setAchados(corpo.pessoas ?? []);
    } catch (e) {
      setAviso((e as Error).message);
    } finally {
      setOcupado(false);
    }
  };

  return (
    <section aria-label="Impedimento e Citados" className={`${CARTAO} px-4 py-4 space-y-4`}>
      <h2 className="text-base font-semibold text-slate-900">Impedimento e Citados</h2>

      {aviso && (
        <p role="alert" className="text-sm text-red-700">
          {aviso}
        </p>
      )}

      <div className="flex flex-col sm:flex-row gap-2">
        <button type="button" className={BOTAO_CLARO} onClick={() => setPasso("impedimento")}>
          DECLARAR IMPEDIMENTO
        </button>
        {caso.pode_contestar_participacao && (
          <button type="button" className={BOTAO_CLARO} onClick={() => setPasso("contestar")}>
            CONTESTAR PARTICIPAÇÃO
          </button>
        )}
      </div>

      {passo === "impedimento" && (
        <form
          aria-label="Declarar impedimento"
          className="space-y-2"
          onSubmit={(e) => {
            e.preventDefault();
            void enviar("impedimento", { motivo }, aoImpedir);
          }}
        >
          <p className="text-sm text-slate-700">
            Você perde o acesso a este caso na hora, e um suplente é convocado no seu lugar.
          </p>
          <fieldset className="space-y-1">
            <legend className="text-sm font-semibold text-slate-700">Motivo</legend>
            {MOTIVOS_DE_IMPEDIMENTO.map((m) => (
              <label key={m.valor} className="flex items-center gap-2 text-sm text-slate-800">
                <input
                  type="radio"
                  name="motivo-do-impedimento"
                  value={m.valor}
                  checked={motivo === m.valor}
                  onChange={() => setMotivo(m.valor)}
                />
                {m.rotulo}
              </label>
            ))}
          </fieldset>
          <button type="submit" className={BOTAO} disabled={!motivo || ocupado}>
            CONFIRMAR IMPEDIMENTO
          </button>
        </form>
      )}

      {passo === "contestar" && (
        <form
          aria-label="Contestar a participação"
          className="space-y-2"
          onSubmit={(e) => {
            e.preventDefault();
            void enviar("contestacoes-de-participacao", { contestado_id: contestado, motivo });
          }}
        >
          <p className="text-sm text-slate-700">Os demais membros decidem, sem o contestado.</p>
          <label className="text-sm font-semibold text-slate-700 space-y-1 block">
            <span>Membro</span>
            <select className={CAMPO} value={contestado} onChange={(e) => setContestado(e.target.value)}>
              <option value="">Escolha</option>
              {membros.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.nome ?? m.id}
                </option>
              ))}
            </select>
          </label>
          <label className="text-sm font-semibold text-slate-700 space-y-1 block">
            <span>Motivo</span>
            <select className={CAMPO} value={motivo} onChange={(e) => setMotivo(e.target.value)}>
              <option value="">Escolha</option>
              {MOTIVOS_DE_IMPEDIMENTO.map((m) => (
                <option key={m.valor} value={m.valor}>
                  {m.rotulo}
                </option>
              ))}
            </select>
          </label>
          <button type="submit" className={BOTAO} disabled={!contestado || !motivo || ocupado}>
            CONTESTAR PARTICIPAÇÃO
          </button>
        </form>
      )}

      {contestacoes.length > 0 && (
        <ul aria-label="Contestações de participação" className="space-y-2">
          {contestacoes.map((c) => (
            <li key={c.id} className="rounded-xl border border-border px-3 py-2 space-y-2">
              <p className="text-sm text-slate-800">{`Participação de ${c.contestado} contestada: ${c.motivo}.`}</p>
              <p className="text-xs text-slate-500">{situacaoDaContestacao(c)}</p>
              {c.pode_decidir && (
                <div className="flex flex-col sm:flex-row gap-2">
                  <button
                    type="button"
                    className={BOTAO}
                    disabled={ocupado}
                    onClick={() => void enviar(`contestacoes-de-participacao/${c.id}/decisao`, { escolha: "confirmar" })}
                  >
                    CONFIRMAR IMPEDIMENTO
                  </button>
                  <button
                    type="button"
                    className={BOTAO_CLARO}
                    disabled={ocupado}
                    onClick={() => void enviar(`contestacoes-de-participacao/${c.id}/decisao`, { escolha: "manter" })}
                  >
                    MANTER NO CASO
                  </button>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}

      <div className="space-y-2">
        <h3 className="text-sm font-semibold text-slate-900">Citados</h3>
        <p className="text-sm text-slate-700">
          Quem é citado como envolvido nunca vê o caso. Se for do Comitê, fica impedido na hora.
        </p>
        {citados.length > 0 && (
          <ul aria-label="Citados" className="space-y-1">
            {citados.map((c) => (
              <li key={c.id} className="flex flex-wrap items-center gap-2 text-sm text-slate-800">
                <span>{c.nome}</span>
                <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-600">
                  {c.ligado ? "No cadastro" : "Só o nome"}
                </span>
              </li>
            ))}
          </ul>
        )}
        <label className="text-sm font-semibold text-slate-700 space-y-1 block">
          <span>Nome do Citado</span>
          <input
            className={CAMPO}
            value={nome}
            maxLength={200}
            onChange={(e) => {
              setNome(e.target.value);
              setAchados(null);
            }}
          />
        </label>
        <div className="flex flex-col sm:flex-row gap-2">
          <button
            type="button"
            className={BOTAO_CLARO}
            disabled={nome.trim().length < 3 || ocupado}
            onClick={() => void buscar()}
          >
            BUSCAR NO CADASTRO
          </button>
          <button
            type="button"
            className={BOTAO_CLARO}
            disabled={!nome.trim() || ocupado}
            onClick={() => void enviar("citados", { nome: nome.trim() })}
          >
            MARCAR SÓ PELO NOME
          </button>
        </div>
        {achados !== null &&
          (achados.length === 0 ? (
            <p className="text-sm text-slate-600">Ninguém no cadastro com esse nome.</p>
          ) : (
            <ul aria-label="Achados no cadastro" className="space-y-1">
              {achados.map((p) => (
                <li key={p.id}>
                  <button
                    type="button"
                    aria-label={`Marcar ${p.nome ?? p.id}`}
                    className="text-left text-sm text-[#282760] underline"
                    disabled={ocupado}
                    onClick={() => void enviar("citados", { participante_id: p.id })}
                  >
                    {p.nome ?? p.id}
                  </button>
                </li>
              ))}
            </ul>
          ))}
      </div>
    </section>
  );
}
