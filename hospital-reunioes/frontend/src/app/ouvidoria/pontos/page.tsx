"use client";

/**
 * Pontos de escuta: os cartazes de QR da Ouvidoria (issue #378, ADR 0036).
 *
 * Cada linha é um cartaz impresso. O ouvidor cadastra o lugar, vê o QR na tela
 * e baixa o cartaz A4 pronto para a gráfica (o A5 continua disponível). Desde
 * a issue #1617 (ADR 0086, decisão 10) o cartaz tem nome público, descrição do
 * local, título, código de controle e a marca de ala de internação. O código curto que vai no papel é
 * sorteado pelo servidor e nunca muda: renomear o ponto ou aposentar o cartaz
 * não invalida o que já está na parede.
 *
 * Os dois perfis da Ouvidoria abrem esta tela, e não só a Diretoria: cartaz é
 * operação do canal. O backend recusa de novo, para quem chamar a API direto.
 */

import { useEffect, useState } from "react";
import Link from "next/link";
import { createClient } from "@/lib/supabase/client";
import {
  AlertCircle,
  ArrowLeft,
  Download,
  FileText,
  Loader2,
  MapPin,
  Pencil,
  Plus,
  Power,
} from "lucide-react";
import { useCurrentParticipante } from "@/hooks/useCurrentParticipante";
import {
  CARTAZ_VAZIO,
  TITULOS_DO_CARTAZ,
  agruparPorSetor,
  camposDoCartaz,
  cartazEstaCompleto,
  formDoPonto,
  nomeDoArquivo,
  podeGerirPontos,
  pontoEstaCompleto,
  type FormDoCartaz,
  type PontoDeEscuta,
  type TituloDoCartaz,
} from "@/lib/ouvidoria/pontos";

const CAMPO =
  "w-full px-3 py-2 rounded-lg border border-slate-200 text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary/40";
const ROTULO = "block text-xs font-semibold text-slate-500 uppercase tracking-wide mb-1";

const VAZIO = { setor: "", ...CARTAZ_VAZIO };

/**
 * Os campos do cartaz, iguais no cadastro e na edição. `prefixo` separa os ids
 * dos dois formulários, que podem estar abertos juntos.
 */
function CamposDoCartaz({
  prefixo,
  form,
  mudar,
}: {
  prefixo: string;
  form: FormDoCartaz;
  mudar: (mudanca: Partial<FormDoCartaz>) => void;
}) {
  return (
    <>
      <div>
        <label className={ROTULO} htmlFor={`${prefixo}-rotulo`}>
          Rótulo do ponto
        </label>
        <input
          id={`${prefixo}-rotulo`}
          className={CAMPO}
          placeholder="Poltrona 12"
          maxLength={80}
          value={form.ponto}
          onChange={(e) => mudar({ ponto: e.target.value })}
        />
      </div>
      <div>
        <label className={ROTULO} htmlFor={`${prefixo}-nome-publico`}>
          Nome público
        </label>
        <input
          id={`${prefixo}-nome-publico`}
          className={CAMPO}
          placeholder="Emergência adulta"
          maxLength={80}
          value={form.nome_publico}
          onChange={(e) => mudar({ nome_publico: e.target.value })}
        />
        <p className="text-xs text-slate-400 mt-1">O que o paciente lê. Em branco, vale o rótulo do ponto.</p>
      </div>
      <div className="md:col-span-2">
        <label className={ROTULO} htmlFor={`${prefixo}-descricao-local`}>
          Descrição do local
        </label>
        <input
          id={`${prefixo}-descricao-local`}
          className={CAMPO}
          placeholder="Parede ao lado do balcão de triagem"
          maxLength={300}
          value={form.descricao_local}
          onChange={(e) => mudar({ descricao_local: e.target.value })}
        />
      </div>
      <div>
        <label className={ROTULO} htmlFor={`${prefixo}-titulo`}>
          Título do cartaz
        </label>
        <select
          id={`${prefixo}-titulo`}
          className={CAMPO}
          value={form.titulo_cartaz}
          onChange={(e) => mudar({ titulo_cartaz: e.target.value as TituloDoCartaz })}
        >
          {TITULOS_DO_CARTAZ.map(({ valor, rotulo }) => (
            <option key={valor} value={valor}>
              {rotulo}
            </option>
          ))}
        </select>
      </div>
      <div>
        <label className={ROTULO} htmlFor={`${prefixo}-codigo-controle`}>
          Código de controle
        </label>
        <input
          id={`${prefixo}-codigo-controle`}
          className={CAMPO}
          placeholder="PSA-01"
          maxLength={20}
          value={form.codigo_controle}
          onChange={(e) => mudar({ codigo_controle: e.target.value })}
        />
      </div>
      <label className="md:col-span-2 flex items-start gap-2.5 cursor-pointer select-none normal-case">
        <input
          type="checkbox"
          checked={form.ala_internacao}
          onChange={(e) => mudar({ ala_internacao: e.target.checked })}
          className="mt-0.5 w-4 h-4 rounded border-border text-primary focus:ring-primary/30"
        />
        <span className="text-sm text-slate-600">
          Fica numa ala de internação
          <span className="block text-xs text-slate-400">
            O cartaz manda falar com a enfermagem do posto da ala, e não com a equipe do setor.
          </span>
        </span>
      </label>
    </>
  );
}

export default function PontosDeEscutaPage() {
  const { participante, loading: carregandoPerfil } = useCurrentParticipante();
  const podeGerir = podeGerirPontos(participante?.perfil_ouvidoria);

  const [token, setToken] = useState<string | null>(null);
  const [pontos, setPontos] = useState<PontoDeEscuta[]>([]);
  const [setores, setSetores] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [erro, setErro] = useState<string | null>(null);
  const [novo, setNovo] = useState(VAZIO);
  const [salvando, setSalvando] = useState(false);
  const [mudando, setMudando] = useState<string | null>(null);
  const [editando, setEditando] = useState<string | null>(null);
  const [edicao, setEdicao] = useState<FormDoCartaz>(CARTAZ_VAZIO);

  useEffect(() => {
    async function init() {
      const supabase = createClient();
      const {
        data: { session },
      } = await supabase.auth.getSession();
      const sessionToken = session?.access_token ?? null;
      setToken(sessionToken);
      if (!sessionToken) {
        setLoading(false);
        return;
      }
      const headers = { Authorization: `Bearer ${sessionToken}` };
      try {
        const [resPontos, resSetores] = await Promise.all([
          fetch("/api/ouvidoria/pontos", { headers }),
          fetch("/api/participantes/setores", { headers }),
        ]);
        // A lista de setores é carregada fora do `else`: se a lista de pontos
        // falhar mas a taxonomia responder, o formulário de cartaz novo
        // continua utilizável em vez de ficar com o select vazio até um F5.
        setSetores(resSetores.ok ? await resSetores.json() : []);
        if (!resPontos.ok) {
          setErro("Não foi possível carregar os pontos de escuta.");
        } else {
          setPontos((await resPontos.json()).pontos);
        }
      } catch (e) {
        console.error("Erro ao carregar pontos de escuta:", e);
        setErro("Não foi possível carregar os pontos de escuta.");
      } finally {
        setLoading(false);
      }
    }
    init();
  }, []);

  async function recarregar(sessionToken: string) {
    const res = await fetch("/api/ouvidoria/pontos", {
      headers: { Authorization: `Bearer ${sessionToken}` },
    });
    if (res.ok) setPontos((await res.json()).pontos);
  }

  async function cadastrar() {
    if (!token) return;
    setSalvando(true);
    setErro(null);
    try {
      const res = await fetch("/api/ouvidoria/pontos", {
        method: "POST",
        headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
        body: JSON.stringify({ setor: novo.setor, ...camposDoCartaz(novo) }),
      });
      if (res.ok) {
        setNovo(VAZIO);
        await recarregar(token);
      } else {
        const corpo = await res.json().catch(() => ({}));
        setErro(
          typeof corpo.detail === "string"
            ? corpo.detail
            : "Não foi possível cadastrar o ponto de escuta. Confira os dados."
        );
      }
    } catch {
      setErro("Não foi possível cadastrar o ponto de escuta. Tente novamente.");
    } finally {
      setSalvando(false);
    }
  }

  async function editar(ponto: PontoDeEscuta, mudanca: Record<string, unknown>) {
    if (!token) return;
    setMudando(ponto.id);
    setErro(null);
    try {
      const res = await fetch(`/api/ouvidoria/pontos/${ponto.id}`, {
        method: "PATCH",
        headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
        body: JSON.stringify(mudanca),
      });
      if (res.ok) await recarregar(token);
      else setErro("Não foi possível salvar a mudança. Tente novamente.");
    } catch {
      setErro("Não foi possível salvar a mudança. Tente novamente.");
    } finally {
      setMudando(null);
      setEditando(null);
    }
  }

  async function baixar(ponto: PontoDeEscuta, tipo: "png" | "a4" | "a5") {
    if (!token) return;
    const caminho = tipo === "png" ? "qr.png" : `cartaz.pdf?formato=${tipo}`;
    try {
      // O download passa por fetch porque a rota é autenticada por header, e um
      // `<a href>` direto iria sem o token.
      const res = await fetch(`/api/ouvidoria/pontos/${ponto.id}/${caminho}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) {
        setErro("Não foi possível baixar o arquivo. Tente novamente.");
        return;
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = nomeDoArquivo(ponto, tipo === "png" ? "png" : "pdf");
      link.click();
      URL.revokeObjectURL(url);
    } catch {
      setErro("Não foi possível baixar o arquivo. Tente novamente.");
    }
  }

  const grupos = agruparPorSetor(pontos);
  const prontoParaCadastrar = pontoEstaCompleto(novo) && !salvando;

  if (!carregandoPerfil && !podeGerir) {
    return (
      <div className="p-4 md:p-8 max-w-3xl mx-auto">
        <div className="bg-white rounded-2xl border border-border shadow-premium p-10 text-center">
          <p className="text-slate-500 font-medium">
            Só o Perfil da Ouvidoria mantém os pontos de escuta.
          </p>
          <Link href="/ouvidoria" className="text-primary text-sm font-semibold mt-3 inline-block">
            Voltar para a Ouvidoria
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="p-4 md:p-8 max-w-5xl mx-auto">
      <Link
        href="/ouvidoria"
        className="inline-flex items-center gap-1.5 text-sm text-slate-500 hover:text-slate-700 mb-4"
      >
        <ArrowLeft className="w-4 h-4" />
        Ouvidoria
      </Link>

      <h1 className="text-2xl font-bold text-slate-900">Pontos de escuta</h1>
      <p className="text-slate-500 text-sm mt-0.5 mb-6">
        Cada ponto é um cartaz de QR code. Baixe o cartaz A4 e cole no lugar cadastrado: quem ler o
        código cai no formulário da Ouvidoria, e o caso já chega dizendo de onde veio.
      </p>

      {erro && (
        <div className="flex items-start gap-2 mb-4 px-4 py-3 rounded-xl bg-red-50 border border-red-200 text-red-700 text-sm">
          <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
          {erro}
        </div>
      )}

      <section className="bg-white rounded-2xl border border-border shadow-premium p-5 mb-6">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-700 mb-3">Novo ponto de escuta</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <div>
            <label className={ROTULO} htmlFor="ponto-setor">
              Setor
            </label>
            <select
              id="ponto-setor"
              className={CAMPO}
              value={novo.setor}
              onChange={(e) => setNovo({ ...novo, setor: e.target.value })}
            >
              <option value="">Escolha o setor</option>
              {setores.map((nome) => (
                <option key={nome} value={nome}>
                  {nome}
                </option>
              ))}
            </select>
          </div>
          <CamposDoCartaz prefixo="ponto" form={novo} mudar={(m) => setNovo({ ...novo, ...m })} />
        </div>
        <button
          type="button"
          disabled={!prontoParaCadastrar}
          onClick={cadastrar}
          className="mt-4 inline-flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-semibold uppercase tracking-wide bg-primary text-white disabled:opacity-40 disabled:cursor-not-allowed"
        >
          {salvando ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />}
          Criar cartaz
        </button>
      </section>

      {loading ? (
        <div className="flex justify-center py-12">
          <Loader2 className="w-6 h-6 text-primary animate-spin" />
        </div>
      ) : grupos.length === 0 ? (
        <div className="bg-white rounded-2xl border border-border shadow-premium p-10 text-center">
          <MapPin className="w-8 h-8 text-slate-300 mx-auto mb-3" />
          <p className="text-slate-500 text-sm">
            Nenhum cartaz cadastrado ainda. Crie o primeiro acima e cole na parede.
          </p>
        </div>
      ) : (
        grupos.map((grupo) => (
          <section key={grupo.setor} className="mb-6">
            <h2 className="text-sm font-bold text-slate-700 mb-2 normal-case">{grupo.setor}</h2>
            <div className="space-y-3">
              {grupo.pontos.map((ponto) => (
                <div
                  key={ponto.id}
                  className={`bg-white rounded-2xl border border-border shadow-premium p-4 flex flex-col sm:flex-row sm:items-center gap-4 ${
                    ponto.ativo ? "" : "opacity-60"
                  }`}
                >
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img
                    src={ponto.qr_data_uri}
                    alt={`QR code do cartaz ${ponto.codigo}`}
                    className="w-24 h-24 shrink-0 rounded-lg border border-slate-100"
                  />

                  <div className="flex-1 min-w-0">
                    <p className="normal-case font-semibold text-slate-800">{ponto.ponto}</p>
                    {ponto.nome_publico && (
                      <p className="text-sm text-slate-600 mt-0.5">
                        Para o paciente: <span className="font-semibold">{ponto.nome_publico}</span>
                      </p>
                    )}
                    {ponto.descricao_local && <p className="text-sm text-slate-500 mt-0.5">{ponto.descricao_local}</p>}
                    <p className="text-xs text-slate-500 mt-1">
                      Código <span className="font-mono font-semibold">{ponto.codigo}</span>
                      {ponto.codigo_controle && (
                        <span className="ml-2">
                          Controle <span className="font-mono font-semibold">{ponto.codigo_controle}</span>
                        </span>
                      )}
                      {!ponto.ativo && <span className="ml-2 text-amber-600">Aposentado</span>}
                    </p>
                    {editando === ponto.id && (
                      <fieldset aria-label="Editar ponto" className="mt-3 grid grid-cols-1 md:grid-cols-2 gap-3">
                        <CamposDoCartaz
                          prefixo={`edicao-${ponto.id}`}
                          form={edicao}
                          mudar={(m) => setEdicao({ ...edicao, ...m })}
                        />
                        <div className="md:col-span-2 flex gap-2">
                          <button
                            type="button"
                            disabled={!cartazEstaCompleto(edicao) || mudando === ponto.id}
                            onClick={() => editar(ponto, camposDoCartaz(edicao))}
                            className="px-3 py-2 rounded-lg text-sm font-semibold uppercase tracking-wide bg-primary text-white disabled:opacity-40"
                          >
                            Salvar
                          </button>
                          <button
                            type="button"
                            onClick={() => setEditando(null)}
                            className="px-3 py-2 rounded-lg text-sm font-semibold uppercase tracking-wide bg-slate-100 text-slate-700"
                          >
                            Cancelar
                          </button>
                        </div>
                      </fieldset>
                    )}
                  </div>

                  <div className="flex flex-wrap items-center gap-2">
                    <button
                      type="button"
                      onClick={() => {
                        setEditando(ponto.id);
                        setEdicao(formDoPonto(ponto));
                      }}
                      className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm font-semibold uppercase tracking-wide bg-slate-100 text-slate-700"
                    >
                      <Pencil className="w-4 h-4" />
                      Editar
                    </button>
                    <button
                      type="button"
                      onClick={() => baixar(ponto, "a4")}
                      className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm font-semibold uppercase tracking-wide bg-primary/10 text-primary"
                    >
                      <FileText className="w-4 h-4" />
                      Cartaz A4
                    </button>
                    <button
                      type="button"
                      onClick={() => baixar(ponto, "a5")}
                      className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm font-semibold uppercase tracking-wide bg-slate-100 text-slate-700"
                    >
                      <FileText className="w-4 h-4" />
                      Cartaz A5
                    </button>
                    <button
                      type="button"
                      onClick={() => baixar(ponto, "png")}
                      className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm font-semibold uppercase tracking-wide bg-slate-100 text-slate-700"
                    >
                      <Download className="w-4 h-4" />
                      PNG
                    </button>
                    <button
                      type="button"
                      disabled={mudando === ponto.id}
                      onClick={() => editar(ponto, { ativo: !ponto.ativo })}
                      className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm font-semibold uppercase tracking-wide bg-slate-100 text-slate-600 disabled:opacity-40"
                    >
                      {mudando === ponto.id ? (
                        <Loader2 className="w-4 h-4 animate-spin" />
                      ) : (
                        <Power className="w-4 h-4" />
                      )}
                      {ponto.ativo ? "Aposentar" : "Reativar"}
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </section>
        ))
      )}

      <p className="text-xs text-slate-400 mt-6 leading-relaxed">
        Aposentar mantém o cartaz e o código. Quem ler um QR aposentado continua caindo no
        formulário da Ouvidoria, só que sem dizer de onde veio.
      </p>
    </div>
  );
}
