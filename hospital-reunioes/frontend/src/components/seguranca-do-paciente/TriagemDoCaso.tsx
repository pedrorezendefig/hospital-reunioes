"use client";

import { useEffect, useMemo, useState, type ReactNode } from "react";
import Link from "next/link";
import { AlertCircle, AlertTriangle, CheckCircle2, Loader2, Sparkles } from "lucide-react";

import { useCurrentParticipante } from "@/hooks/useCurrentParticipante";
import { chamarNsp } from "@/lib/seguranca-do-paciente/membros";
import { CHEGOU_AO_PACIENTE, PERCEBIDO, TURNOS } from "@/lib/seguranca-do-paciente/notificacao";
import {
  CAMPOS,
  CANAIS,
  CLASSIFICACAO_EM_BRANCO,
  CONFIANCAS,
  FREQUENCIAS,
  GRAUS_DE_DANO,
  MOTIVOS_DA_CONFERENCIA,
  NATUREZAS,
  ORIENTACAO_DO_CASO_GRAVE,
  PRIORIDADES,
  PROTOCOLOS_BASICOS,
  SITUACOES_DA_LISTA,
  classificacaoDaSugestao,
  classificacaoPreenchida,
  faixaEsperada,
  podeConfirmar,
  rotulo,
  rotuloDaFaixa,
  textoDaRecorrencia,
  type Classificacao,
  type Contexto,
  type LinhaDeTriagem,
} from "@/lib/seguranca-do-paciente/triagem";
import { SeloDaFaixa } from "./FilaDeTriagem";
import { AnexosDoCaso, ESTADOS, formatarData, QuemNotificou, type Caso } from "./NotificacoesDoNucleo";

const CARTAO = "bg-white rounded-2xl border border-border shadow-premium";
const CAMPO_DE_FORMULARIO =
  "w-full rounded-xl border border-border bg-white px-3 py-2 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-primary/30";

interface Tela {
  caso: Caso;
  sugestao: LinhaDeTriagem | null;
  decisao: LinhaDeTriagem | null;
  pendente: boolean;
  classificar_manualmente: boolean;
  motivo_classificar_manualmente: string | null;
  conferencia: { campo_a_campo: boolean; motivos: string[]; campos: string[] };
  contexto: Contexto;
  opcoes: { categorias: { codigo: string; nome: string }[]; eventos: { item: number; evento: string }[] };
}

function Secao({ titulo, children }: { titulo: string; children: ReactNode }) {
  const id = `secao-${titulo.toLowerCase().replace(/\W+/g, "-")}`;
  return (
    <section aria-labelledby={id} className={`${CARTAO} px-4 py-4 md:px-5 space-y-3`}>
      <h2 id={id} className="text-xs font-semibold uppercase tracking-wide text-slate-500">
        {titulo}
      </h2>
      {children}
    </section>
  );
}

/** A caixa de conferência de um campo, na revisão campo a campo. */
function Conferi({
  campo,
  rotulo: nome,
  marcados,
  alternar,
}: {
  campo: string;
  rotulo: string;
  marcados: ReadonlySet<string>;
  alternar: (campo: string) => void;
}) {
  return (
    <label className="flex min-h-[44px] items-center gap-1.5 text-xs font-semibold text-slate-600 shrink-0">
      <input
        type="checkbox"
        aria-label={`Conferi o campo ${nome}`}
        checked={marcados.has(campo)}
        onChange={() => alternar(campo)}
        className="h-4 w-4 accent-primary"
      />
      Conferi
    </label>
  );
}

function valorDoCampo(campo: string, s: LinhaDeTriagem, categorias: Tela["opcoes"]["categorias"]): string {
  switch (campo) {
    case "natureza":
      return rotulo(NATUREZAS, s.natureza);
    case "grau_de_dano":
      return rotulo(GRAUS_DE_DANO, s.grau_de_dano);
    case "categoria":
      return categorias.find((c) => c.codigo === s.categoria)?.nome ?? s.categoria;
    case "evento":
      return s.evento.situacao === "nao" || !s.evento.situacao
        ? "Não"
        : `${rotulo(SITUACOES_DA_LISTA, s.evento.situacao)}, item ${s.evento.item}`;
    case "iras":
      return s.iras ? "Sim" : "Não";
    case "risco_de_imagem":
      return s.risco_de_imagem ? "Sim" : "Não";
    case "protocolo_basico":
      return rotulo(PROTOCOLOS_BASICOS, s.protocolo_basico);
    case "canais":
      return s.canais.map((c) => rotulo(CANAIS, c)).join(", ");
    case "faixa":
      return rotuloDaFaixa(s.faixa);
    case "assunto":
      return s.assunto;
    case "incidente":
      return s.incidente ?? "Não informado";
    default:
      return "";
  }
}

/** O relato, as respostas de quem notificou e os anexos. */
function LadoDoRelato({ caso }: { caso: Caso & { percebido_ou_reclamacao?: string | null } }) {
  const chegou = CHEGOU_AO_PACIENTE.find((c) => c.valor === caso.chegou_ao_paciente)?.rotulo;
  const turno = TURNOS.find((t) => t.valor === caso.turno)?.rotulo;
  const percebido = PERCEBIDO.find((p) => p.valor === caso.percebido_ou_reclamacao)?.rotulo;
  return (
    <div className="space-y-4">
      <Secao titulo="Relato">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-base font-bold text-slate-900 tabular-nums">{caso.protocolo}</span>
          <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs font-semibold text-slate-700">
            {ESTADOS[caso.estado] ?? caso.estado}
          </span>
        </div>
        <p className="text-sm text-slate-800 whitespace-pre-wrap break-words leading-relaxed">{caso.relato}</p>
        <QuemNotificou caso={caso} />
      </Secao>
      <Secao titulo="Respostas">
        <dl className="grid grid-cols-1 sm:grid-cols-2 gap-x-4 gap-y-2 text-sm">
          <div>
            <dt className="text-slate-500">Onde</dt>
            <dd className="text-slate-900">{caso.setor ?? "Setor não informado"}</dd>
          </div>
          <div>
            <dt className="text-slate-500">Quando</dt>
            <dd className="text-slate-900">
              {formatarData(caso.data_ocorrencia)}
              {turno ? `, ${turno.toLowerCase()}` : ""}
            </dd>
          </div>
          {caso.leito_ou_atendimento && (
            <div>
              <dt className="text-slate-500">Leito ou atendimento</dt>
              <dd className="text-slate-900">{caso.leito_ou_atendimento}</dd>
            </div>
          )}
          <div>
            <dt className="text-slate-500">O paciente foi atingido</dt>
            <dd className="text-slate-900">{chegou ?? "Não informado"}</dd>
          </div>
          {caso.grave_ou_morte !== null && (
            <div>
              <dt className="text-slate-500">Grave ou houve morte</dt>
              <dd className={caso.grave_ou_morte ? "font-semibold text-red-700" : "text-slate-900"}>
                {caso.grave_ou_morte ? "Sim" : "Não"}
              </dd>
            </div>
          )}
          {percebido && (
            <div>
              <dt className="text-slate-500">A família ou o paciente percebeu</dt>
              <dd className="text-slate-900">{percebido}</dd>
            </div>
          )}
        </dl>
      </Secao>
      {(caso.anexos?.length ?? 0) > 0 && (
        <Secao titulo="Anexos">
          <AnexosDoCaso caso={caso} />
        </Secao>
      )}
    </div>
  );
}

/** O que o sistema calcula: recorrência, casos parecidos, frequência e prioridade. */
function Calculado({ contexto, podeConfigurar }: { contexto: Contexto; podeConfigurar: boolean }) {
  const recorrencia = textoDaRecorrencia(contexto);
  return (
    <Secao titulo="Calculado pelo sistema">
      {recorrencia === null ? (
        <p className="text-sm text-slate-600">Escolha a categoria para o sistema contar a recorrência.</p>
      ) : (
        <div className="space-y-2 text-sm text-slate-800">
          <p className="font-semibold">{recorrencia}</p>
          <p>
            {`Frequência: ${FREQUENCIAS[contexto.frequencia ?? ""] ?? "sem cálculo"}`}
            {contexto.anteriores !== null
              ? ` (${contexto.anteriores} ${contexto.anteriores === 1 ? "anterior" : "anteriores"} em ${contexto.cortes.janela_meses} meses)`
              : ""}
          </p>
          <p>{`Prioridade: ${PRIORIDADES[contexto.prioridade ?? ""] ?? "não se aplica"}`}</p>
          {contexto.parecidos.length > 0 && (
            <div>
              <p className="text-slate-500">Casos parecidos</p>
              <ul className="mt-1 space-y-1">
                {contexto.parecidos.map((p) => (
                  <li key={p.id}>
                    <Link
                      href={`/seguranca-do-paciente/notificacoes/${p.id}`}
                      className="text-primary font-semibold hover:underline tabular-nums"
                    >
                      {p.protocolo}
                    </Link>
                    <span className="text-slate-600">
                      {`, ${formatarData(p.data_ocorrencia)}${p.assunto ? `: ${p.assunto}` : ""}`}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
      {podeConfigurar && (
        <Link href="/seguranca-do-paciente/configuracao" className="text-xs text-slate-500 hover:underline">
          Ver os cortes de frequência na Configuração
        </Link>
      )}
    </Secao>
  );
}

function Selecao({
  id,
  rotulo: nome,
  valor,
  opcoes,
  mudar,
}: {
  id: string;
  rotulo: string;
  valor: string;
  opcoes: { valor: string; rotulo: string }[];
  mudar: (valor: string) => void;
}) {
  return (
    <div className="space-y-1 min-w-0 flex-1">
      <label htmlFor={id} className="text-xs font-semibold text-slate-600">
        {nome}
      </label>
      <select id={id} value={valor} onChange={(e) => mudar(e.target.value)} className={CAMPO_DE_FORMULARIO}>
        <option value="">Escolha</option>
        {opcoes.map((o) => (
          <option key={o.valor} value={o.valor}>
            {o.rotulo}
          </option>
        ))}
      </select>
    </div>
  );
}

/** O formulário do ajuste e da classificação manual. */
function FormularioDaClassificacao({
  valor,
  mudar,
  opcoes,
  conferir,
}: {
  valor: Classificacao;
  mudar: (c: Classificacao) => void;
  opcoes: Tela["opcoes"];
  conferir: (campo: string, nome: string) => ReactNode;
}) {
  const faixa = valor.natureza && valor.grau_de_dano ? faixaEsperada(valor.natureza, valor.grau_de_dano, valor.evento_situacao) : null;
  const linha = (campo: string, nome: string, filho: ReactNode) => (
    <div className="flex items-end gap-3">
      {filho}
      {conferir(campo, nome)}
    </div>
  );
  return (
    <div className="space-y-3">
      {linha(
        "assunto",
        "Assunto",
        <div className="space-y-1 min-w-0 flex-1">
          <label htmlFor="triagem-assunto" className="text-xs font-semibold text-slate-600">
            Assunto
          </label>
          <input
            id="triagem-assunto"
            value={valor.assunto}
            maxLength={300}
            onChange={(e) => mudar({ ...valor, assunto: e.target.value })}
            className={CAMPO_DE_FORMULARIO}
          />
        </div>
      )}
      {linha(
        "natureza",
        "Natureza",
        <Selecao id="triagem-natureza" rotulo="Natureza" valor={valor.natureza} opcoes={NATUREZAS} mudar={(v) => mudar({ ...valor, natureza: v })} />
      )}
      {linha(
        "grau_de_dano",
        "Grau de dano",
        <Selecao id="triagem-dano" rotulo="Grau de dano" valor={valor.grau_de_dano} opcoes={GRAUS_DE_DANO} mudar={(v) => mudar({ ...valor, grau_de_dano: v })} />
      )}
      {linha(
        "categoria",
        "Categoria",
        <Selecao
          id="triagem-categoria"
          rotulo="Categoria"
          valor={valor.categoria}
          opcoes={opcoes.categorias.map((c) => ({ valor: c.codigo, rotulo: c.nome }))}
          mudar={(v) => mudar({ ...valor, categoria: v })}
        />
      )}
      {linha(
        "incidente",
        "Incidente",
        <div className="space-y-1 min-w-0 flex-1">
          <label htmlFor="triagem-incidente" className="text-xs font-semibold text-slate-600">
            Incidente
          </label>
          <input
            id="triagem-incidente"
            value={valor.incidente}
            maxLength={300}
            onChange={(e) => mudar({ ...valor, incidente: e.target.value })}
            className={CAMPO_DE_FORMULARIO}
          />
        </div>
      )}
      {linha(
        "evento",
        "Evento que nunca deveria ocorrer",
        <div className="flex flex-col sm:flex-row gap-3 min-w-0 flex-1">
          <Selecao
            id="triagem-evento"
            rotulo="Evento que nunca deveria ocorrer"
            valor={valor.evento_situacao}
            opcoes={SITUACOES_DA_LISTA}
            mudar={(v) => mudar({ ...valor, evento_situacao: v, evento_item: v === "nao" ? null : valor.evento_item })}
          />
          {valor.evento_situacao && valor.evento_situacao !== "nao" && (
            <Selecao
              id="triagem-evento-item"
              rotulo="Item da lista"
              valor={valor.evento_item === null ? "" : String(valor.evento_item)}
              opcoes={opcoes.eventos.map((e) => ({ valor: String(e.item), rotulo: `${e.item}. ${e.evento}` }))}
              mudar={(v) => mudar({ ...valor, evento_item: v ? Number(v) : null })}
            />
          )}
        </div>
      )}
      {linha(
        "iras",
        "IRAS",
        <label className="flex min-h-[44px] items-center gap-2 text-sm text-slate-800 flex-1">
          <input type="checkbox" checked={valor.iras} onChange={(e) => mudar({ ...valor, iras: e.target.checked })} className="h-4 w-4 accent-primary" />
          IRAS (infecção associada à assistência)
        </label>
      )}
      {linha(
        "risco_de_imagem",
        "Risco de imagem",
        <label className="flex min-h-[44px] items-center gap-2 text-sm text-slate-800 flex-1">
          <input
            type="checkbox"
            checked={valor.risco_de_imagem}
            onChange={(e) => mudar({ ...valor, risco_de_imagem: e.target.checked })}
            className="h-4 w-4 accent-primary"
          />
          Risco de imagem
        </label>
      )}
      {linha(
        "protocolo_basico",
        "Protocolo básico",
        <Selecao
          id="triagem-protocolo"
          rotulo="Protocolo básico"
          valor={valor.protocolo_basico}
          opcoes={PROTOCOLOS_BASICOS}
          mudar={(v) => mudar({ ...valor, protocolo_basico: v })}
        />
      )}
      {linha(
        "canais",
        "Canal",
        <fieldset className="min-w-0 flex-1">
          <legend className="text-xs font-semibold text-slate-600">Canal</legend>
          <div className="flex flex-wrap gap-x-4">
            {CANAIS.map((canal) => (
              <label key={canal.valor} className="flex min-h-[44px] items-center gap-1.5 text-sm text-slate-800">
                <input
                  type="checkbox"
                  checked={valor.canais.includes(canal.valor)}
                  onChange={(e) =>
                    mudar({
                      ...valor,
                      canais: e.target.checked
                        ? [...valor.canais, canal.valor]
                        : valor.canais.filter((c) => c !== canal.valor),
                    })
                  }
                  className="h-4 w-4 accent-primary"
                />
                {canal.rotulo}
              </label>
            ))}
          </div>
        </fieldset>
      )}
      {linha(
        "faixa",
        "Faixa",
        <p className="text-sm text-slate-800 flex-1 min-h-[44px] flex items-center gap-2">
          <span className="text-slate-500">Faixa calculada:</span>
          <SeloDaFaixa faixa={faixa} />
        </p>
      )}
    </div>
  );
}

/**
 * A tela única da triagem (issue #1992): à esquerda, o relato, as respostas e
 * os anexos; à direita, a sugestão do agente, marcada, e o que o sistema
 * calcula; embaixo, Confirmar e Ajustar. Na revisão campo a campo, cada campo
 * tem a sua caixa, e Confirmar só libera com todas marcadas. Sem sugestão, a
 * tela abre com os campos em branco.
 */
export function TriagemDoCaso({ id }: { id: string }) {
  const { participante } = useCurrentParticipante();
  const [tela, setTela] = useState<Tela | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [ajustando, setAjustando] = useState(false);
  const [classificacao, setClassificacao] = useState<Classificacao>(CLASSIFICACAO_EM_BRANCO);
  const [marcados, setMarcados] = useState<ReadonlySet<string>>(new Set());
  const [contexto, setContexto] = useState<Contexto | null>(null);
  const [enviando, setEnviando] = useState(false);
  const [erroDoEnvio, setErroDoEnvio] = useState<string | null>(null);
  const [feito, setFeito] = useState<string | null>(null);

  useEffect(() => {
    let vivo = true;
    chamarNsp<Tela>(`/api/nsp/triagem/${encodeURIComponent(id)}`)
      .then((corpo) => {
        if (!vivo) return;
        setTela(corpo);
        setContexto(corpo.contexto);
        if (corpo.sugestao) setClassificacao(classificacaoDaSugestao(corpo.sugestao));
      })
      .catch((e: Error) => vivo && setErro(e.message));
    return () => {
      vivo = false;
    };
  }, [id]);

  const semSugestao = tela !== null && tela.sugestao === null;
  const editando = ajustando || semSugestao;
  const faixaDoForm = useMemo(
    () =>
      classificacao.natureza && classificacao.grau_de_dano
        ? faixaEsperada(classificacao.natureza, classificacao.grau_de_dano, classificacao.evento_situacao)
        : null,
    [classificacao.natureza, classificacao.grau_de_dano, classificacao.evento_situacao]
  );

  // Ao ajustar, o cálculo acompanha a categoria e a faixa escolhidas.
  useEffect(() => {
    if (!tela || !editando || !classificacao.categoria) return;
    let vivo = true;
    const busca = new URLSearchParams({ categoria: classificacao.categoria, faixa: faixaDoForm ?? "" });
    chamarNsp<Contexto>(`/api/nsp/triagem/${encodeURIComponent(id)}/contexto?${busca}`)
      .then((corpo) => vivo && setContexto(corpo))
      .catch(() => undefined);
    return () => {
      vivo = false;
    };
  }, [tela, editando, id, classificacao.categoria, faixaDoForm]);

  if (erro) {
    return (
      <div role="alert" className={`${CARTAO} flex gap-2 items-start px-4 py-4`}>
        <AlertCircle className="w-5 h-5 shrink-0 text-red-500" aria-hidden />
        <p className="text-sm text-red-700">{erro}</p>
      </div>
    );
  }
  if (tela === null) {
    return <Loader2 className="w-5 h-5 animate-spin text-slate-400" aria-label="Carregando" />;
  }

  const campoACampo = tela.conferencia.campo_a_campo;
  const alternar = (campo: string) =>
    setMarcados((atual) => {
      const novo = new Set(atual);
      if (novo.has(campo)) novo.delete(campo);
      else novo.add(campo);
      return novo;
    });
  const conferencia = (campo: string, nome: string) =>
    campoACampo ? <Conferi campo={campo} rotulo={nome} marcados={marcados} alternar={alternar} /> : null;
  const liberado = podeConfirmar(campoACampo, marcados) && (!editando || classificacaoPreenchida(classificacao));

  async function enviar() {
    setEnviando(true);
    setErroDoEnvio(null);
    try {
      const corpo: { conferidos: string[]; classificacao?: unknown } = { conferidos: campoACampo ? [...marcados] : [] };
      if (editando) {
        corpo.classificacao = {
          ...classificacao,
          incidente: classificacao.incidente.trim() || null,
          evento_item: classificacao.evento_situacao === "nao" ? null : classificacao.evento_item,
        };
      }
      const resultado = await chamarNsp<{ estado: string }>(`/api/nsp/triagem/${encodeURIComponent(id)}`, {
        method: "POST",
        body: corpo,
      });
      setFeito(ESTADOS[resultado.estado] ?? resultado.estado);
    } catch (e) {
      setErroDoEnvio((e as Error).message);
    } finally {
      setEnviando(false);
    }
  }

  const podeConfigurar = participante?.recursos_nsp?.includes("configuracao") ?? false;
  const decidida = tela.decisao !== null || !tela.pendente;

  return (
    <div className="space-y-4">
      {campoACampo && !decidida && !feito && (
        <div role="alert" className="rounded-2xl border border-red-200 bg-red-50 px-4 py-3 space-y-1">
          <p className="flex gap-2 items-center text-sm font-semibold text-red-800">
            <AlertTriangle className="w-4 h-4 shrink-0" aria-hidden />
            {ORIENTACAO_DO_CASO_GRAVE}
          </p>
          <ul className="text-sm text-red-700 list-disc pl-6">
            {tela.conferencia.motivos.map((m) => (
              <li key={m}>{MOTIVOS_DA_CONFERENCIA[m] ?? m}</li>
            ))}
          </ul>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 items-start">
        <LadoDoRelato caso={tela.caso} />

        <div className="space-y-4">
          {feito ? (
            <div role="status" className={`${CARTAO} flex gap-3 items-start px-4 py-4`}>
              <CheckCircle2 className="w-5 h-5 shrink-0 text-emerald-600" aria-hidden />
              <div className="space-y-1">
                <p className="text-sm font-semibold text-slate-900">{`Triagem confirmada. O caso está em ${feito}.`}</p>
                <Link href="/seguranca-do-paciente/notificacoes/triagem" className="text-sm text-primary font-semibold hover:underline">
                  Voltar à fila de triagem
                </Link>
              </div>
            </div>
          ) : decidida ? (
            <div role="status" className={`${CARTAO} px-4 py-4`}>
              <p className="text-sm font-semibold text-slate-900">A triagem deste caso já foi confirmada.</p>
            </div>
          ) : editando ? (
            <Secao titulo={semSugestao ? "Classificar manualmente" : "Ajuste"}>
              {semSugestao && (
                <p className="text-sm text-violet-800">
                  Esta notificação chegou sem sugestão do agente. Preencha cada campo.
                </p>
              )}
              <FormularioDaClassificacao
                valor={classificacao}
                mudar={setClassificacao}
                opcoes={tela.opcoes}
                conferir={conferencia}
              />
            </Secao>
          ) : (
            tela.sugestao && (
              <Secao titulo="Sugestão">
                <p className="flex items-center gap-1.5 text-xs font-semibold text-violet-700">
                  <Sparkles className="w-3.5 h-3.5" aria-hidden />
                  Sugestão do agente de triagem. Quem decide é você.
                </p>
                <dl className="space-y-1">
                  {CAMPOS.map(({ campo, rotulo: nome }) => (
                    <div key={campo} className="flex items-center gap-3 border-b border-slate-100 last:border-0">
                      <div className="min-w-0 flex-1 py-1.5">
                        <dt className="text-xs text-slate-500">{nome}</dt>
                        <dd className="text-sm text-slate-900">{valorDoCampo(campo, tela.sugestao!, tela.opcoes.categorias)}</dd>
                      </div>
                      {conferencia(campo, nome)}
                    </div>
                  ))}
                </dl>
                {tela.sugestao.justificativa && (
                  <div>
                    <p className="text-xs text-slate-500">Justificativa</p>
                    <p className="text-sm text-slate-900">{tela.sugestao.justificativa}</p>
                  </div>
                )}
                {tela.sugestao.confianca && (
                  <p className="text-sm text-slate-900">
                    {`Confiança ${CONFIANCAS[tela.sugestao.confianca] ?? tela.sugestao.confianca}`}
                    {tela.sugestao.motivo_da_confianca ? `: ${tela.sugestao.motivo_da_confianca}` : ""}
                  </p>
                )}
                {tela.sugestao.alertas.length > 0 && (
                  <ul aria-label="Alertas" className="space-y-1">
                    {tela.sugestao.alertas.map((alerta) => (
                      <li key={alerta} className="flex gap-2 rounded-xl bg-amber-50 px-3 py-2 text-sm text-amber-900">
                        <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" aria-hidden />
                        <span>{alerta}</span>
                      </li>
                    ))}
                  </ul>
                )}
              </Secao>
            )
          )}

          {contexto && <Calculado contexto={contexto} podeConfigurar={podeConfigurar} />}

          {!feito && !decidida && (
            <div className="space-y-2">
              {erroDoEnvio && (
                <p role="alert" className="text-sm text-red-700">
                  {erroDoEnvio}
                </p>
              )}
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={enviar}
                  disabled={!liberado || enviando}
                  className="inline-flex min-h-[44px] items-center justify-center gap-2 rounded-xl bg-primary px-5 py-2 text-sm font-semibold text-white hover:bg-primary/90 disabled:opacity-50"
                >
                  {enviando && <Loader2 className="w-4 h-4 animate-spin" aria-hidden />}
                  {semSugestao ? "Confirmar a classificação" : ajustando ? "Confirmar o ajuste" : "Confirmar"}
                </button>
                {!semSugestao && (
                  <button
                    type="button"
                    onClick={() => {
                      if (ajustando && tela.sugestao) setClassificacao(classificacaoDaSugestao(tela.sugestao));
                      setAjustando(!ajustando);
                    }}
                    className="inline-flex min-h-[44px] items-center justify-center rounded-xl border border-border bg-white px-5 py-2 text-sm font-semibold text-slate-700 hover:border-primary/40"
                  >
                    {ajustando ? "Voltar à sugestão" : "Ajustar"}
                  </button>
                )}
              </div>
              {campoACampo && !podeConfirmar(campoACampo, marcados) && (
                <p className="text-xs text-slate-500">Marque cada campo como conferido para liberar a confirmação.</p>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
