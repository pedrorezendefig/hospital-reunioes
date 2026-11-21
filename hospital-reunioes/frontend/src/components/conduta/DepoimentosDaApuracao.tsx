"use client";

import { useEffect, useRef, useState } from "react";
import { Check, Lock, Minus } from "lucide-react";

import { chamarComite } from "@/lib/conduta/comite";
import {
  BOTOES,
  LIMITE_DO_AUDIO,
  PAPEIS,
  abrirArquivo,
  dataEHora,
  enviarArquivos,
  rotuloDoPapel,
  type Depoimento,
  type ItemDaLista,
  type Papel,
  type TipoDeArquivo,
  type VersaoDoArquivo,
} from "@/lib/conduta/depoimentos";

const CARTAO = "bg-white rounded-2xl border border-border shadow-premium";
const CAMPO = "w-full rounded-xl border border-border bg-white px-3 py-2 text-sm text-slate-900";
const BOTAO =
  "inline-flex items-center justify-center rounded-xl bg-[#282760] px-4 py-2.5 text-sm font-semibold text-white hover:bg-[#1f1e4d] disabled:bg-slate-300 disabled:text-slate-600 w-full sm:w-auto";
const BOTAO_CLARO =
  "inline-flex items-center justify-center rounded-xl border border-[#282760] bg-white px-4 py-2.5 text-sm font-semibold text-[#282760] disabled:opacity-50 w-full sm:w-auto";
const BOTAO_PEQUENO = "text-sm font-semibold text-[#282760] underline disabled:opacity-50";

const NOMES_DOS_ARQUIVOS: Record<TipoDeArquivo, string> = {
  transcricao: "Arquivo da transcrição do depoimento",
  audio: "Arquivo do áudio do depoimento",
  termo_assinado: "Arquivo do termo assinado",
};

/** O formulário de "ADICIONAR PESSOA A OUVIR": nome, cargo e papel. */
function NovaPessoa({ casoId, aoFechar, aoMudar }: { casoId: string; aoFechar: () => void; aoMudar: () => void }) {
  const [nome, setNome] = useState("");
  const [cargo, setCargo] = useState("");
  const [papel, setPapel] = useState<Papel | "">("");
  const [ocupado, setOcupado] = useState(false);
  const [aviso, setAviso] = useState<string | null>(null);

  const enviar = async () => {
    setOcupado(true);
    setAviso(null);
    try {
      await chamarComite(`/casos/${casoId}/depoimentos`, { method: "POST", body: { nome, cargo, papel } });
      aoFechar();
      aoMudar();
    } catch (e) {
      setAviso((e as Error).message);
    } finally {
      setOcupado(false);
    }
  };

  return (
    <form
      aria-label="Adicionar pessoa a ouvir"
      className={`${CARTAO} px-4 py-4 space-y-3`}
      onSubmit={(e) => {
        e.preventDefault();
        void enviar();
      }}
    >
      <label className="text-sm font-semibold text-slate-700 space-y-1 block">
        <span>Nome</span>
        <input className={CAMPO} value={nome} maxLength={200} onChange={(e) => setNome(e.target.value)} />
      </label>
      <label className="text-sm font-semibold text-slate-700 space-y-1 block">
        <span>Cargo</span>
        <input className={CAMPO} value={cargo} maxLength={200} onChange={(e) => setCargo(e.target.value)} />
      </label>
      <fieldset className="space-y-1">
        <legend className="text-sm font-semibold text-slate-700">Papel</legend>
        <div className="flex flex-wrap gap-3">
          {PAPEIS.map((p) => (
            <label key={p.valor} className="flex items-center gap-2 text-sm text-slate-800">
              <input type="radio" name="papel" value={p.valor} checked={papel === p.valor} onChange={() => setPapel(p.valor)} />
              {p.rotulo}
            </label>
          ))}
        </div>
      </fieldset>
      {aviso && (
        <p role="alert" className="text-sm text-red-700">
          {aviso}
        </p>
      )}
      <div className="flex flex-col sm:flex-row gap-2">
        <button type="submit" className={BOTAO} disabled={!nome.trim() || !cargo.trim() || !papel || ocupado}>
          ADICIONAR
        </button>
        <button type="button" className={BOTAO_CLARO} onClick={aoFechar}>
          CANCELAR
        </button>
      </div>
    </form>
  );
}

/** Uma versão de um arquivo: quem enviou, quando, e o botão de abrir cada página. */
function Versao({
  casoId,
  depoimentoId,
  tipo,
  versao,
}: {
  casoId: string;
  depoimentoId: string;
  tipo: TipoDeArquivo;
  versao: VersaoDoArquivo;
}) {
  const [endereco, setEndereco] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);

  useEffect(() => () => void (endereco && URL.revokeObjectURL(endereco)), [endereco]);

  const abrir = async (arquivoId: string, tocar: boolean) => {
    setAviso(null);
    try {
      const local = await abrirArquivo(casoId, depoimentoId, arquivoId);
      if (tocar) setEndereco(local);
      else window.open(local, "_blank", "noopener");
    } catch (e) {
      setAviso((e as Error).message);
    }
  };

  return (
    <li className="space-y-1 text-sm text-slate-700">
      <p>{`Versão ${versao.versao}, por ${versao.enviado_por} em ${dataEHora(versao.enviado_em)}`}</p>
      <div className="flex flex-wrap gap-3">
        {tipo === "audio" ? (
          <button type="button" className={BOTAO_PEQUENO} onClick={() => void abrir(versao.paginas[0].id, true)}>
            {`OUVIR VERSÃO ${versao.versao}`}
          </button>
        ) : (
          versao.paginas.map((pagina, i) => (
            <button key={pagina.id} type="button" className={BOTAO_PEQUENO} onClick={() => void abrir(pagina.id, false)}>
              {versao.paginas.length > 1 ? `ABRIR PÁGINA ${i + 1}` : "ABRIR"}
            </button>
          ))
        )}
      </div>
      {endereco && (
        <audio controls src={endereco} aria-label={`Áudio do depoimento, versão ${versao.versao}`} className="w-full" />
      )}
      {aviso && (
        <p role="alert" className="text-red-700">
          {aviso}
        </p>
      )}
    </li>
  );
}

/** A linha de um arquivo do cartão: o seu botão e as suas versões. */
function Arquivo({
  casoId,
  depoimento,
  tipo,
  podeAgir,
  aoMudar,
}: {
  casoId: string;
  depoimento: Depoimento;
  tipo: TipoDeArquivo;
  podeAgir: boolean;
  aoMudar: () => void;
}) {
  const seletor = useRef<HTMLInputElement>(null);
  const camera = useRef<HTMLInputElement>(null);
  const [fotos, setFotos] = useState<File[]>([]);
  const [ocupado, setOcupado] = useState(false);
  const [aviso, setAviso] = useState<string | null>(null);
  const config = BOTOES[tipo];
  const versoes = depoimento.arquivos[tipo];
  const naoSeAplica = tipo !== "termo_assinado" && depoimento.sem_gravacao;

  const enviar = async (arquivos: File[]) => {
    setAviso(null);
    if (arquivos.length === 0) return;
    if (tipo === "audio" && arquivos[0].size > LIMITE_DO_AUDIO) {
      setAviso("O áudio passa de 300 MB.");
      return;
    }
    setOcupado(true);
    try {
      await enviarArquivos(casoId, depoimento.id, tipo, arquivos);
      setFotos([]);
      aoMudar();
    } catch (e) {
      setAviso((e as Error).message);
    } finally {
      setOcupado(false);
    }
  };

  return (
    <section aria-label={config.titulo} className="space-y-2 border-t border-border pt-3">
      <h4 className="text-sm font-semibold text-slate-900">{config.titulo}</h4>
      {naoSeAplica ? (
        <p className="text-sm text-slate-600">{`Não se aplica: ${depoimento.sem_gravacao?.motivo}`}</p>
      ) : (
        <>
          {versoes.length > 0 && (
            <ul aria-label={`Versões ${tipo === "termo_assinado" ? "do termo assinado" : tipo === "audio" ? "do áudio" : "da transcrição"}`} className="space-y-2">
              {versoes.map((v) => (
                <Versao key={v.versao} casoId={casoId} depoimentoId={depoimento.id} tipo={tipo} versao={v} />
              ))}
            </ul>
          )}
          {podeAgir && (
            <div className="flex flex-col sm:flex-row gap-2">
              <input
                ref={seletor}
                type="file"
                className="hidden"
                aria-label={NOMES_DOS_ARQUIVOS[tipo]}
                accept={config.aceita}
                multiple={tipo === "termo_assinado"}
                onChange={(e) => {
                  void enviar(Array.from(e.target.files ?? []));
                  e.target.value = "";
                }}
              />
              <button type="button" className={BOTAO_CLARO} disabled={ocupado} onClick={() => seletor.current?.click()}>
                {config.botao}
              </button>
              {tipo === "termo_assinado" && (
                <>
                  <input
                    ref={camera}
                    type="file"
                    className="hidden"
                    aria-label="Foto do termo assinado"
                    accept="image/*"
                    capture="environment"
                    onChange={(e) => {
                      const nova = e.target.files?.[0];
                      if (nova) setFotos((atuais) => [...atuais, nova]);
                      e.target.value = "";
                    }}
                  />
                  <button type="button" className={BOTAO_CLARO} disabled={ocupado} onClick={() => camera.current?.click()}>
                    {fotos.length ? "FOTOGRAFAR OUTRA PÁGINA" : "FOTOGRAFAR TERMO ASSINADO"}
                  </button>
                </>
              )}
            </div>
          )}
          {fotos.length > 0 && (
            <button type="button" className={BOTAO} disabled={ocupado} onClick={() => void enviar(fotos)}>
              {`ENVIAR TERMO ASSINADO (${fotos.length} ${fotos.length === 1 ? "PÁGINA" : "PÁGINAS"})`}
            </button>
          )}
          {ocupado && <p className="text-sm text-slate-600">Enviando. Arquivo grande pode levar alguns minutos.</p>}
        </>
      )}
      {aviso && (
        <p role="alert" className="text-sm text-red-700">
          {aviso}
        </p>
      )}
    </section>
  );
}

function SemGravacao({ casoId, depoimentoId, aoMudar }: { casoId: string; depoimentoId: string; aoMudar: () => void }) {
  const [aberto, setAberto] = useState(false);
  const [motivo, setMotivo] = useState("");
  const [pontos, setPontos] = useState("");
  const [ocupado, setOcupado] = useState(false);
  const [aviso, setAviso] = useState<string | null>(null);

  if (!aberto) {
    return (
      <button type="button" className={BOTAO_PEQUENO} onClick={() => setAberto(true)}>
        A PESSOA NÃO ACEITOU GRAVAÇÃO
      </button>
    );
  }
  const enviar = async () => {
    setOcupado(true);
    setAviso(null);
    try {
      await chamarComite(`/casos/${casoId}/depoimentos/${depoimentoId}/sem-gravacao`, {
        method: "POST",
        body: { motivo, pontos },
      });
      aoMudar();
    } catch (e) {
      setAviso((e as Error).message);
    } finally {
      setOcupado(false);
    }
  };
  return (
    <form
      aria-label="Depoimento sem gravação"
      className="space-y-2 border-t border-border pt-3"
      onSubmit={(e) => {
        e.preventDefault();
        void enviar();
      }}
    >
      <p className="text-sm text-slate-700">Digite os pontos da conversa. Eles fazem as vezes da transcrição.</p>
      <label className="text-sm font-semibold text-slate-700 space-y-1 block">
        <span>Motivo</span>
        <input className={CAMPO} value={motivo} maxLength={500} onChange={(e) => setMotivo(e.target.value)} />
      </label>
      <label className="text-sm font-semibold text-slate-700 space-y-1 block">
        <span>Pontos da conversa</span>
        <textarea className={CAMPO} rows={5} value={pontos} onChange={(e) => setPontos(e.target.value)} />
      </label>
      {aviso && (
        <p role="alert" className="text-sm text-red-700">
          {aviso}
        </p>
      )}
      <button type="submit" className={BOTAO} disabled={!motivo.trim() || !pontos.trim() || ocupado}>
        REGISTRAR SEM GRAVAÇÃO
      </button>
    </form>
  );
}

function EstadoDoItem({ item }: { item: ItemDaLista }) {
  if (item.estado === "nao_se_aplica") return <p className="text-xs text-slate-600">{`Não se aplica: ${item.motivo ?? ""}`}</p>;
  if (item.estado === "feito" && item.marcado_por && item.marcado_em) {
    return <p className="text-xs text-slate-600">{`Marcado por ${item.marcado_por} em ${dataEHora(item.marcado_em)}`}</p>;
  }
  if (item.estado === "feito" && item.automatico) return <p className="text-xs text-slate-600">Anexado</p>;
  return null;
}

/** A lista de conferência: três itens automáticos e quatro declarações. */
function ListaDeConferencia({
  depoimento,
  podeAgir,
  aoMarcar,
}: {
  depoimento: Depoimento;
  podeAgir: boolean;
  aoMarcar: (item: string) => void;
}) {
  return (
    <section aria-label="Lista de conferência" className="space-y-2 border-t border-border pt-3">
      <h4 className="text-sm font-semibold text-slate-900">Lista de conferência</h4>
      <ul className="space-y-2">
        {depoimento.lista.map((item) => (
          <li key={item.item} className="flex gap-2 items-start">
            {item.automatico ? (
              <span aria-hidden className="mt-0.5">
                {item.estado === "feito" ? (
                  <Check className="w-4 h-4 text-emerald-700" />
                ) : item.estado === "nao_se_aplica" ? (
                  <Minus className="w-4 h-4 text-slate-500" />
                ) : (
                  <Lock className="w-4 h-4 text-slate-400" />
                )}
              </span>
            ) : null}
            <div className="min-w-0">
              {item.automatico ? (
                <p className="text-sm text-slate-800">{item.rotulo}</p>
              ) : (
                <label className="flex gap-2 items-start text-sm text-slate-800">
                  <input
                    type="checkbox"
                    className="mt-0.5"
                    checked={item.estado === "feito"}
                    disabled={item.estado === "feito" || !podeAgir}
                    onChange={() => aoMarcar(item.item)}
                  />
                  {item.rotulo}
                </label>
              )}
              <EstadoDoItem item={item} />
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}

function Cartao({
  casoId,
  depoimento,
  emApuracao,
  aoMudar,
}: {
  casoId: string;
  depoimento: Depoimento;
  emApuracao: boolean;
  aoMudar: () => void;
}) {
  const [aviso, setAviso] = useState<string | null>(null);
  const [ocupado, setOcupado] = useState(false);
  const concluido = Boolean(depoimento.concluido_em);
  const podeAgir = emApuracao && !concluido;
  const temGravacao = depoimento.arquivos.transcricao.length > 0 || depoimento.arquivos.audio.length > 0;

  const agir = async (caminho: string, body?: unknown) => {
    setOcupado(true);
    setAviso(null);
    try {
      await chamarComite(`/casos/${casoId}/depoimentos/${depoimento.id}/${caminho}`, { method: "POST", body: body ?? {} });
      aoMudar();
    } catch (e) {
      setAviso((e as Error).message);
    } finally {
      setOcupado(false);
    }
  };

  return (
    <article aria-label={depoimento.nome} className={`${CARTAO} px-4 py-4 space-y-3 min-w-0`}>
      <header className="space-y-1">
        <h3 className="text-base font-semibold text-slate-900 break-words">{depoimento.nome}</h3>
        <p className="text-sm text-slate-600">{`${rotuloDoPapel(depoimento.papel)}, ${depoimento.cargo}`}</p>
        <p className={`text-xs font-semibold ${concluido ? "text-emerald-700" : "text-amber-700"}`}>{depoimento.situacao}</p>
        {concluido && depoimento.concluido_por && depoimento.concluido_em && (
          <p className="text-xs text-slate-600">{`Concluído por ${depoimento.concluido_por} em ${dataEHora(depoimento.concluido_em)}`}</p>
        )}
      </header>

      {depoimento.sem_gravacao && (
        <section aria-label="Pontos da conversa" className="space-y-1 border-t border-border pt-3">
          <h4 className="text-sm font-semibold text-slate-900">Pontos da conversa, sem gravação</h4>
          <p className="text-sm text-slate-800 whitespace-pre-line break-words">{depoimento.sem_gravacao.pontos}</p>
        </section>
      )}

      {(["transcricao", "audio", "termo_assinado"] as const).map((tipo) => (
        <Arquivo key={tipo} casoId={casoId} depoimento={depoimento} tipo={tipo} podeAgir={podeAgir} aoMudar={aoMudar} />
      ))}

      {podeAgir && !depoimento.sem_gravacao && !temGravacao && (
        <SemGravacao casoId={casoId} depoimentoId={depoimento.id} aoMudar={aoMudar} />
      )}

      <ListaDeConferencia depoimento={depoimento} podeAgir={podeAgir && !ocupado} aoMarcar={(item) => void agir("conferencia", { item })} />

      {aviso && (
        <p role="alert" className="text-sm text-red-700">
          {aviso}
        </p>
      )}

      {!concluido && (
        <div className="space-y-1">
          <button
            type="button"
            className={BOTAO}
            disabled={Boolean(depoimento.bloqueio_da_conclusao) || !podeAgir || ocupado}
            onClick={() => void agir("conclusao")}
          >
            CONCLUIR DEPOIMENTO
          </button>
          {depoimento.bloqueio_da_conclusao && (
            <p className="flex gap-2 items-start text-sm text-slate-700">
              <Lock className="w-4 h-4 shrink-0 mt-0.5 text-slate-500" aria-hidden />
              <span>{depoimento.bloqueio_da_conclusao}</span>
            </p>
          )}
        </div>
      )}
    </article>
  );
}

/**
 * Os depoimentos da Apuração (issue #1830; especificação, seções 7.1 e 7.2):
 * um cartão por pessoa ouvida, com a transcrição, o áudio e o termo assinado
 * cada um no seu botão, a lista de conferência e "CONCLUIR DEPOIMENTO".
 */
export function DepoimentosDaApuracao({
  casoId,
  depoimentos,
  emApuracao,
  bloqueioDoAvanco,
  adicionando,
  aoFecharAdicionar,
  aoMudar,
}: {
  casoId: string;
  depoimentos: Depoimento[];
  emApuracao: boolean;
  bloqueioDoAvanco: string | null;
  adicionando: boolean;
  aoFecharAdicionar: () => void;
  aoMudar: () => void;
}) {
  if (!adicionando && depoimentos.length === 0) return null;
  return (
    <section aria-label="Depoimentos" className="space-y-3">
      <h2 className="text-base font-semibold text-slate-900">Depoimentos</h2>
      {adicionando && emApuracao && <NovaPessoa casoId={casoId} aoFechar={aoFecharAdicionar} aoMudar={aoMudar} />}
      {depoimentos.map((d) => (
        <Cartao key={d.id} casoId={casoId} depoimento={d} emApuracao={emApuracao} aoMudar={aoMudar} />
      ))}
      {bloqueioDoAvanco && <p className="text-sm text-slate-700">{bloqueioDoAvanco}</p>}
    </section>
  );
}
