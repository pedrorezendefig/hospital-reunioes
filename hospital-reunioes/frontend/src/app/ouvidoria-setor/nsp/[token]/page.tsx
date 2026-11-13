"use client";

/**
 * O caso enviado ao Núcleo de Segurança do Paciente (issue #1621, ADR 0088).
 *
 * A presidência do Núcleo chega pelo link do email, sem senha (decisão 7), e
 * lê o caso inteiro: o relato como o paciente contou, o que a Ouvidoria
 * apurou, o paciente com a data de nascimento, os profissionais e o quarto,
 * mesmo no caso sigiloso (decisão 5). Quem manifestou só aparece quando o
 * caso não é sigiloso nem anônimo, e quem decide isso é o servidor.
 *
 * Abrir a tela não confirma nada, pelo mesmo motivo do elogio: leitor de email
 * que abre link sozinho gastaria o uso único. É o botão Recebido pelo NSP que
 * chama o servidor, e é o servidor que decide o uso único.
 */

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { AlertCircle, CheckCircle2, Loader2, ShieldAlert } from "lucide-react";
import { Logo } from "@/components/ui/Logo";
import { oQueOPassoAPassoContou } from "@/lib/ouvidoria/publico";
import { mensagemDoPortal } from "@/lib/ouvidoria/setor";
import { rotuloDoTipo } from "@/lib/ouvidoria/taxonomia";
import { LABEL_GRAVIDADE, type Gravidade } from "@/lib/ouvidoria/validacao";

const INSTAVEL = "Não foi possível confirmar agora. Tente novamente.";

interface TelaDoNucleo {
  protocolo: string;
  tipo_manifestacao: string | null;
  gravidade: string | null;
  sigiloso: boolean;
  anonimo: boolean;
  relato_integral: string | null;
  justificativa_tecnica: string | null;
  paciente: { nome: string | null; nascimento: string | null } | null;
  profissionais: string | null;
  quarto: string | null;
  data_ocorrencia: string | null;
  periodo: string | null;
  hora_aprox: string | null;
  local_informado: string | null;
  quem_manifestou: string | null;
  destinatario_nome: string | null;
  prazo: string | null;
  recebido: boolean;
  recebido_em: string | null;
}

/** "2026-11-10" em "10/11/2026", sem passar pelo fuso do navegador. */
function dataDoBrasil(iso: string): string {
  const [ano, mes, dia] = iso.split("-");
  return dia && mes && ano ? `${dia}/${mes}/${ano}` : iso;
}

function Bloco({ titulo, children }: { titulo: string; children: React.ReactNode }) {
  return (
    <section className="space-y-1">
      <h2 className="text-xs font-semibold uppercase tracking-wide text-slate-500">{titulo}</h2>
      <div className="text-sm text-slate-800 leading-relaxed">{children}</div>
    </section>
  );
}

export default function NucleoPage() {
  const params = useParams();
  const token = params.token as string;

  const [caso, setCaso] = useState<TelaDoNucleo | null>(null);
  const [erroDaAbertura, setErroDaAbertura] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);
  const [recebido, setRecebido] = useState(false);
  // O 503 e a falha do fetch deixam o botão: o link continua valendo. O 404 e
  // o 410 dizem que não há mais o que confirmar, e o botão some.
  const [erro, setErro] = useState<{ mensagem: string; podeTentarDeNovo: boolean } | null>(null);

  useEffect(() => {
    let cancelado = false;
    fetch(`/api/ouvidoria-setor/nsp/${encodeURIComponent(token)}`)
      .then(async (res) => {
        const corpo = await res.json().catch(() => ({}));
        if (cancelado) return;
        if (!res.ok) {
          setErroDaAbertura(mensagemDoPortal(res.status, corpo.detail));
          return;
        }
        setCaso(corpo as TelaDoNucleo);
        setRecebido(Boolean(corpo.recebido));
      })
      .catch(() => {
        if (!cancelado) setErroDaAbertura("Não foi possível abrir o caso agora. Tente novamente.");
      });
    return () => {
      cancelado = true;
    };
  }, [token]);

  async function confirmar() {
    setEnviando(true);
    setErro(null);
    try {
      const res = await fetch(`/api/ouvidoria-setor/nsp/${encodeURIComponent(token)}/recebido`, {
        method: "POST",
      });
      const corpo = await res.json().catch(() => ({}));
      if (!res.ok) {
        setErro({
          mensagem: res.status >= 500 ? corpo.detail || INSTAVEL : mensagemDoPortal(res.status, corpo.detail),
          podeTentarDeNovo: res.status >= 500,
        });
        return;
      }
      setRecebido(true);
    } catch {
      setErro({ mensagem: INSTAVEL, podeTentarDeNovo: true });
    } finally {
      setEnviando(false);
    }
  }

  if (erroDaAbertura) {
    return (
      <main className="min-h-screen bg-slate-50 flex items-center justify-center p-4">
        <div className="w-full max-w-lg bg-white rounded-2xl border border-slate-200 shadow-premium p-8 text-center space-y-4">
          <div className="flex justify-center">
            <Logo />
          </div>
          <p role="alert" className="text-sm text-amber-700">
            {erroDaAbertura}
          </p>
        </div>
      </main>
    );
  }

  if (!caso) {
    return (
      <main className="min-h-screen bg-slate-50 flex items-center justify-center p-4">
        <Loader2 className="w-6 h-6 animate-spin text-primary/40" aria-label="Abrindo o caso" />
      </main>
    );
  }

  const quandoEOnde = oQueOPassoAPassoContou({
    data_ocorrencia: caso.data_ocorrencia,
    periodo: caso.periodo,
    hora_aprox: caso.hora_aprox,
    local_informado: caso.local_informado,
    quarto: caso.quarto,
  });
  const linkAcabou = erro !== null && !erro.podeTentarDeNovo;

  return (
    <main className="min-h-screen bg-slate-50 p-4 flex justify-center">
      <div className="w-full max-w-2xl bg-white rounded-2xl border border-slate-200 shadow-premium p-6 md:p-8 space-y-5">
        <div className="flex justify-center">
          <Logo />
        </div>
        <header className="space-y-1">
          <p className="text-sm font-semibold text-rose-700">Núcleo de Segurança do Paciente</p>
          <h1 className="text-xl font-bold text-slate-900">Manifestação {caso.protocolo}</h1>
          <p className="text-sm text-slate-500">
            {[
              caso.tipo_manifestacao ? rotuloDoTipo(caso.tipo_manifestacao as never) : null,
              caso.gravidade ? LABEL_GRAVIDADE[caso.gravidade as Gravidade] ?? caso.gravidade : null,
            ]
              .filter(Boolean)
              .join(" · ")}
          </p>
        </header>

        {caso.sigiloso && (
          <div className="flex items-start gap-2 px-4 py-3 rounded-xl bg-amber-50 border border-amber-200 text-amber-800 text-sm">
            <ShieldAlert className="w-4 h-4 shrink-0 mt-0.5" />
            <span>
              Caso sob sigilo reforçado. O Núcleo recebe o relato inteiro por exceção à regra do sigilo. Não
              encaminhe este link nem o conteúdo da tela.
            </span>
          </div>
        )}

        <Bloco titulo="Relato integral">
          <p className="whitespace-pre-wrap break-words">
            {caso.relato_integral || "O relato original não está registrado neste caso."}
          </p>
        </Bloco>

        {caso.justificativa_tecnica && (
          <Bloco titulo="O que a Ouvidoria apurou">
            <p className="whitespace-pre-wrap break-words">{caso.justificativa_tecnica}</p>
          </Bloco>
        )}

        <Bloco titulo="Paciente">
          {caso.paciente ? (
            <p>
              <span>{caso.paciente.nome || "Nome não informado"}</span>
              {caso.paciente.nascimento && (
                <>
                  {", nascimento em "}
                  <span>{dataDoBrasil(caso.paciente.nascimento)}</span>
                </>
              )}
            </p>
          ) : (
            <p className="text-slate-500">Paciente não informado.</p>
          )}
        </Bloco>

        {caso.profissionais && (
          <Bloco titulo="Profissionais citados">
            <p>{caso.profissionais}</p>
          </Bloco>
        )}

        {quandoEOnde.map((linha) => (
          <Bloco key={linha.rotulo} titulo={linha.rotulo}>
            <p>{linha.valor}</p>
          </Bloco>
        ))}

        <Bloco titulo="Quem manifestou">
          {caso.quem_manifestou ? (
            <p>{caso.quem_manifestou}</p>
          ) : (
            <p className="text-slate-500">
              Quem manifestou não é identificado neste caso, porque ele é sigiloso ou anônimo.
            </p>
          )}
        </Bloco>

        <div className="border-t border-slate-100 pt-5 space-y-3">
          {recebido ? (
            <p
              data-testid="nucleo-recebido"
              className="flex items-start gap-2 text-sm text-emerald-700 bg-emerald-50 border border-emerald-200 rounded-xl px-3 py-2.5"
            >
              <CheckCircle2 className="w-4 h-4 mt-0.5 shrink-0" />
              <span>
                Recebimento confirmado. A Ouvidoria segue com o caso, e a investigação do Núcleo corre por
                fora da plataforma.
              </span>
            </p>
          ) : (
            <>
              {caso.prazo && (
                <p className="text-sm text-slate-600">Confirme o recebimento até {caso.prazo}.</p>
              )}
              {erro && (
                <p
                  role="alert"
                  className="flex items-start gap-2 text-sm text-amber-700 bg-amber-50 border border-amber-200 rounded-xl px-3 py-2.5"
                >
                  <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
                  <span>{erro.mensagem}</span>
                </p>
              )}
              {!linkAcabou && (
                <button
                  type="button"
                  onClick={() => void confirmar()}
                  disabled={enviando}
                  className="w-full inline-flex items-center justify-center gap-2 rounded-xl bg-primary px-4 py-3 text-sm font-semibold text-white hover:bg-primary/90 disabled:opacity-60"
                >
                  {enviando && <Loader2 className="w-4 h-4 animate-spin" aria-hidden="true" />}
                  Recebido pelo NSP
                </button>
              )}
            </>
          )}
        </div>
      </div>
    </main>
  );
}
