"use client";

import { useCallback, useEffect, useState } from "react";
import { AlertCircle, Loader2, Plus } from "lucide-react";

import {
  CADEIRAS,
  COR_SITUACAO,
  COR_TERMO,
  LABEL_ACAO_DO_REGISTRO,
  LABEL_SITUACAO,
  LABEL_TERMO,
  ROTA_DOS_MEMBROS,
  chamarConduta,
  formatarDia,
  type Cadeira,
  type LinhaDoRegistro,
  type ListaDeMembros,
  type MembroComAviso,
  type MembroDoComite,
} from "@/lib/conduta/membros";

const CARTAO = "bg-white rounded-2xl border border-border shadow-premium";
const CAMPO =
  "w-full px-3 py-2 rounded-lg border border-slate-200 text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary/40";
const ROTULO = "block text-xs font-semibold text-slate-500 uppercase tracking-wide mb-1";
const BOTAO =
  "inline-flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-semibold uppercase tracking-wide bg-primary text-white hover:bg-primary/90 disabled:opacity-50 transition-colors";
const BOTAO_LEVE =
  "inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold uppercase tracking-wide bg-slate-100 text-slate-700 hover:bg-slate-200 disabled:opacity-50 transition-colors";

const COLUNAS = ["Membro", "Cadeira", "Diretor", "Vigência", "Situação", "Termo"];

function diaDoCarimbo(carimbo: string): string {
  return new Date(carimbo).toLocaleDateString("pt-BR", { timeZone: "America/Sao_Paulo" });
}

/**
 * A tela Membros do Comitê de Conduta (issue #1822): quem compõe o Comitê e
 * até quando, a composição de qualquer data passada e o registro das
 * mudanças. Incluir e encerrar aparecem só para quem tem o perfil de cadastro
 * (`pode_cadastrar`, do servidor), que recusa de novo quem chamar a API
 * direto. Encerrar não apaga: a linha fica, como encerrada.
 *
 * Cada linha diz a situação do Termo de Confidencialidade e Posse (issue
 * #1823); quem cadastra reconsulta o status na ClickSign e reenvia o Termo.
 */
export function MembrosDoComite() {
  const [lista, setLista] = useState<ListaDeMembros | null>(null);
  const [registro, setRegistro] = useState<LinhaDoRegistro[]>([]);
  const [erro, setErro] = useState<string | null>(null);
  const [data, setData] = useState("");
  const [incluindo, setIncluindo] = useState(false);
  const [avisoDoTermo, setAvisoDoTermo] = useState<string | null>(null);

  const carregar = useCallback(async (dia?: string) => {
    try {
      const caminho = dia ? `${ROTA_DOS_MEMBROS}?data=${encodeURIComponent(dia)}` : ROTA_DOS_MEMBROS;
      setLista(await chamarConduta<ListaDeMembros>(caminho));
      const corpo = await chamarConduta<{ registro: LinhaDoRegistro[] }>(`${ROTA_DOS_MEMBROS}/registro`);
      setRegistro(corpo.registro);
      setErro(null);
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Não foi possível carregar os membros.");
    }
  }, []);

  useEffect(() => {
    carregar();
  }, [carregar]);

  const podeCadastrar = (lista?.pode_cadastrar ?? false) && !lista?.data;

  return (
    <div className="space-y-5">
      {erro && (
        <div className="flex items-start gap-2 px-4 py-3 rounded-xl bg-red-50 border border-red-200 text-red-700 text-sm">
          <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" aria-hidden />
          {erro}
        </div>
      )}

      <div className="flex flex-wrap items-end gap-3">
        <div>
          <label htmlFor="composicao-em" className={ROTULO}>
            Composição em
          </label>
          <input
            id="composicao-em"
            type="date"
            className={CAMPO}
            value={data}
            onChange={(e) => setData(e.target.value)}
          />
        </div>
        <button type="button" className={BOTAO_LEVE} disabled={!data} onClick={() => carregar(data)}>
          Ver a composição
        </button>
        {lista?.data && (
          <button
            type="button"
            className={BOTAO_LEVE}
            onClick={() => {
              setData("");
              carregar();
            }}
          >
            Voltar para todos
          </button>
        )}
        {lista?.pode_cadastrar && !lista.data && !incluindo && (
          <button type="button" className={`${BOTAO} ml-auto`} onClick={() => setIncluindo(true)}>
            <Plus className="w-4 h-4" aria-hidden />
            Incluir membro
          </button>
        )}
      </div>

      {incluindo && (
        <FormularioDeInclusao
          aoCancelar={() => setIncluindo(false)}
          aoSalvar={async (aviso) => {
            setIncluindo(false);
            setAvisoDoTermo(aviso);
            await carregar();
          }}
        />
      )}

      {avisoDoTermo && (
        <div role="status" className="px-4 py-3 rounded-xl bg-amber-50 border border-amber-200 text-amber-800 text-sm">
          <p className="font-semibold">O membro foi incluído, mas o Termo não saiu.</p>
          <p>{avisoDoTermo}</p>
        </div>
      )}

      {lista?.data && <p className="text-sm font-semibold text-slate-700">Composição em {formatarDia(lista.data)}</p>}

      <div className={`${CARTAO} overflow-x-auto`}>
        {lista === null && !erro ? (
          <div className="flex items-center justify-center h-32 gap-2 text-slate-400 text-sm">
            <Loader2 className="w-5 h-5 animate-spin text-primary/40" aria-hidden />
            Carregando os membros...
          </div>
        ) : (
          <table aria-label="Membros do Comitê de Conduta" className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs font-semibold uppercase tracking-wide text-slate-500 border-b border-slate-100">
                {COLUNAS.map((coluna) => (
                  <th key={coluna} scope="col" className="px-3 py-2.5 whitespace-nowrap">
                    {coluna}
                  </th>
                ))}
                {podeCadastrar && <th scope="col" className="px-3 py-2.5" aria-label="Ações" />}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {(lista?.membros ?? []).length === 0 && (
                <tr>
                  <td colSpan={COLUNAS.length + 1} className="px-3 py-8 text-center text-slate-500">
                    {lista?.data ? "Ninguém no Comitê nesta data." : "Ninguém cadastrado no Comitê ainda."}
                  </td>
                </tr>
              )}
              {(lista?.membros ?? []).map((m) => (
                <LinhaDoMembro key={m.id} membro={m} podeEncerrar={podeCadastrar} aoEncerrar={() => carregar()} />
              ))}
            </tbody>
          </table>
        )}
      </div>

      {registro.length > 0 && (
        <section className={`${CARTAO} px-4 py-4`}>
          <h2 className="text-sm font-semibold text-slate-900 mb-2">Registro do Comitê</h2>
          <ul aria-label="Registro do Comitê" className="space-y-1.5 text-sm text-slate-600">
            {registro.map((linha, i) => (
              <li key={`${linha.registrado_em}-${i}`}>
                <span className="font-semibold text-slate-800">{linha.pessoa ?? "Pessoa sem nome"}</span>:{" "}
                {LABEL_ACAO_DO_REGISTRO[linha.acao]}
                {linha.detalhe ? ` (${linha.detalhe})` : ""}, por {linha.autor ?? "pessoa sem nome"} em{" "}
                {diaDoCarimbo(linha.registrado_em)}
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}

function LinhaDoMembro({
  membro,
  podeEncerrar,
  aoEncerrar,
}: {
  membro: MembroDoComite;
  podeEncerrar: boolean;
  aoEncerrar: () => Promise<void>;
}) {
  const [confirmando, setConfirmando] = useState(false);
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);
  // Antes do início, encerrar desfaz a inclusão: a Participação nunca vale.
  const aComecar = membro.situacao === "a_comecar";

  async function encerrar() {
    setEnviando(true);
    try {
      await chamarConduta(`${ROTA_DOS_MEMBROS}/${encodeURIComponent(membro.id)}/encerrar`, {
        method: "POST",
        body: {},
      });
      await aoEncerrar();
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Não foi possível encerrar.");
    } finally {
      setEnviando(false);
      setConfirmando(false);
    }
  }

  async function cuidarDoTermo(acao: "reconsultar" | "reenviar") {
    setEnviando(true);
    setErro(null);
    try {
      const linha = await chamarConduta<MembroComAviso>(
        `${ROTA_DOS_MEMBROS}/${encodeURIComponent(membro.id)}/termo/${acao}`,
        { method: "POST", body: {} }
      );
      setAviso(linha.aviso_termo ?? null);
      await aoEncerrar();
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Não foi possível falar com a assinatura eletrônica.");
    } finally {
      setEnviando(false);
    }
  }

  const cuidaDoTermo = podeEncerrar && membro.situacao !== "encerrada" && membro.termo !== "assinado";

  return (
    <tr className="align-top">
      <td className="px-3 py-2.5 font-medium text-slate-900">{membro.nome ?? "Pessoa sem nome no cadastro"}</td>
      <td className="px-3 py-2.5 text-slate-700">{membro.cadeira}</td>
      <td className="px-3 py-2.5 text-slate-700">{membro.e_diretor ? "Diretor" : "Não"}</td>
      <td className="px-3 py-2.5 text-slate-700 whitespace-nowrap">
        {`${formatarDia(membro.vigencia_inicio)} a ${formatarDia(membro.vigencia_fim)}`}
      </td>
      <td className="px-3 py-2.5">
        <span className={`inline-block px-2 py-0.5 rounded-full text-xs font-semibold ${COR_SITUACAO[membro.situacao]}`}>
          {LABEL_SITUACAO[membro.situacao]}
        </span>
      </td>
      <td className="px-3 py-2.5">
        <span className={`inline-block px-2 py-0.5 rounded-full text-xs font-semibold ${COR_TERMO[membro.termo]}`}>
          {LABEL_TERMO[membro.termo]}
        </span>
      </td>
      {podeEncerrar && (
        <td className="px-3 py-2.5 text-right whitespace-nowrap">
          {cuidaDoTermo && (
            <span className="inline-flex gap-2 mr-2">
              {membro.termo === "aguardando_assinatura" && (
                <button type="button" className={BOTAO_LEVE} disabled={enviando} onClick={() => cuidarDoTermo("reconsultar")}>
                  Reconsultar status
                </button>
              )}
              <button type="button" className={BOTAO_LEVE} disabled={enviando} onClick={() => cuidarDoTermo("reenviar")}>
                Reenviar o Termo
              </button>
            </span>
          )}
          {membro.situacao !== "encerrada" &&
            (confirmando ? (
              <span className="inline-flex gap-2">
                <button type="button" className={BOTAO_LEVE} disabled={enviando} onClick={encerrar}>
                  {aComecar ? "Confirmar e desfazer" : "Confirmar o encerramento"}
                </button>
                <button type="button" className={BOTAO_LEVE} onClick={() => setConfirmando(false)}>
                  Cancelar
                </button>
              </span>
            ) : (
              <button type="button" className={BOTAO_LEVE} onClick={() => setConfirmando(true)}>
                {aComecar ? "Desfazer a inclusão" : "Encerrar"}
              </button>
            ))}
          {erro && <p className="text-xs text-red-600 mt-1">{erro}</p>}
          {aviso && <p className="text-xs text-amber-800 mt-1 whitespace-normal">{aviso}</p>}
        </td>
      )}
    </tr>
  );
}

function FormularioDeInclusao({
  aoCancelar,
  aoSalvar,
}: {
  aoCancelar: () => void;
  aoSalvar: (avisoDoTermo: string | null) => Promise<void>;
}) {
  const [pessoas, setPessoas] = useState<{ id: string; nome: string }[]>([]);
  const [pessoa, setPessoa] = useState("");
  const [cadeira, setCadeira] = useState<Cadeira>("membro");
  const [diretor, setDiretor] = useState(false);
  const [inicio, setInicio] = useState("");
  const [fim, setFim] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    chamarConduta<{ pessoas: { id: string; nome: string }[] }>(`${ROTA_DOS_MEMBROS}/pessoas`)
      .then((corpo) => setPessoas(corpo.pessoas))
      .catch(() => setErro("Não foi possível carregar as pessoas do cadastro."));
  }, []);

  async function salvar(e: React.FormEvent) {
    e.preventDefault();
    setEnviando(true);
    try {
      const nova = await chamarConduta<MembroComAviso>(ROTA_DOS_MEMBROS, {
        method: "POST",
        body: {
          participante_id: pessoa,
          papel: cadeira,
          e_diretor: diretor,
          vigencia_inicio: inicio,
          ...(fim ? { vigencia_fim: fim } : {}),
        },
      });
      await aoSalvar(nova.aviso_termo ?? null);
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Não foi possível incluir.");
    } finally {
      setEnviando(false);
    }
  }

  return (
    <form onSubmit={salvar} className={`${CARTAO} px-4 py-4 space-y-3`} aria-label="Incluir membro">
      <div className="grid gap-3 sm:grid-cols-2">
        <div>
          <label htmlFor="inclusao-pessoa" className={ROTULO}>
            Pessoa
          </label>
          <select id="inclusao-pessoa" className={CAMPO} value={pessoa} onChange={(e) => setPessoa(e.target.value)} required>
            <option value="">Escolha a pessoa</option>
            {pessoas.map((p) => (
              <option key={p.id} value={p.id}>
                {p.nome}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor="inclusao-cadeira" className={ROTULO}>
            Cadeira
          </label>
          <select
            id="inclusao-cadeira"
            className={CAMPO}
            value={cadeira}
            onChange={(e) => setCadeira(e.target.value as Cadeira)}
          >
            {CADEIRAS.map((c) => (
              <option key={c.valor} value={c.valor}>
                {c.rotulo}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor="inclusao-inicio" className={ROTULO}>
            Início do mandato
          </label>
          <input
            id="inclusao-inicio"
            type="date"
            className={CAMPO}
            value={inicio}
            onChange={(e) => setInicio(e.target.value)}
            required
          />
        </div>
        <div>
          <label htmlFor="inclusao-fim" className={ROTULO}>
            Fim do mandato
          </label>
          <input id="inclusao-fim" type="date" className={CAMPO} value={fim} onChange={(e) => setFim(e.target.value)} />
          <p className="text-xs text-slate-500 mt-1">Em branco, o mandato é de dois anos.</p>
        </div>
      </div>
      <label className="inline-flex items-center gap-2 text-sm text-slate-700">
        <input type="checkbox" checked={diretor} onChange={(e) => setDiretor(e.target.checked)} />
        É diretor
      </label>
      <p className="text-xs text-slate-500">
        Os membros do Comitê recebem um aviso desta inclusão, e a pessoa recebe o Termo de Confidencialidade e Posse
        no e-mail profissional, para assinar.
      </p>
      {erro && <p className="text-sm text-red-600">{erro}</p>}
      <div className="flex gap-2">
        <button type="submit" className={BOTAO} disabled={enviando || !pessoa || !inicio}>
          Salvar
        </button>
        <button type="button" className={BOTAO_LEVE} onClick={aoCancelar}>
          Cancelar
        </button>
      </div>
    </form>
  );
}
