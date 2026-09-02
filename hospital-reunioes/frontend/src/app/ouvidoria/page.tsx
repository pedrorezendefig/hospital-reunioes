"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { createClient } from "@/lib/supabase/client";
import {
  AlertCircle,
  CalendarDays,
  CheckCircle2,
  FileText,
  LayoutDashboard,
  Loader2,
  Lock,
  MapPin,
  Megaphone,
  Plus,
  Send,
  SlidersHorizontal,
  Star,
  UsersRound,
} from "lucide-react";
import { useCurrentParticipante } from "@/hooks/useCurrentParticipante";
import type { TipoManifestacao } from "@/lib/ouvidoria/taxonomia";
import { NovaManifestacaoModal } from "@/components/ouvidoria/NovaManifestacaoModal";
import { ValidarModal } from "@/components/ouvidoria/ValidarModal";
import {
  aguardandoSeuEncerramento,
  agruparPorStatus,
  classeDoStatus,
  rotuloDoStatus,
  TITULO_AGUARDANDO_ENCERRAMENTO,
} from "@/lib/ouvidoria/fila";
import { podeGerirPontos } from "@/lib/ouvidoria/pontos";
import { avisosDeDegradacao, podeVerPainel } from "@/lib/ouvidoria/painel";
import { podeRegistrarNotaExterna } from "@/lib/ouvidoria/nota-externa";
import {
  classificarPrazoDaManifestacao,
  podeEditarPrazos,
  EM_ANDAMENTO,
  type ClassePrazo,
  type StatusManifestacao,
} from "@/lib/ouvidoria/prazo";
import { EncerrarModal } from "@/components/ouvidoria/EncerrarModal";
import { podeEncerrar, podeGerirResponsaveis, podeValidar } from "@/lib/ouvidoria/validacao";

// Índice da manifestação: o que o painel lista para qualquer perfil com acesso.
// Relato, nome e contato só existem no Dossiê, atrás do perfil da Ouvidoria.
interface ManifestacaoIndice {
  id: string;
  numero: number;
  protocolo: string;
  data_abertura: string;
  prazo_resposta: string;
  status: StatusManifestacao;
  // Lista fechada (issue #372). `null` é o caso ainda não classificado, que
  // chega pelo canal aberto e pelo canal da Ana.
  tipo_manifestacao: TipoManifestacao | null;
  // A marca de sigilo do caso (issue #372). Para quem está fora da Ouvidoria é
  // sempre falso: a linha sigilosa nem chega até aqui.
  sigilo_reforcado: boolean;
  categoria: string;
  setor: string;
  resumo: string;
  conversa_id: string;
  // Motor de prazos (issue #322): o vencimento e o rótulo vêm calculados do
  // servidor, em calendário útil.
  gravidade: string | null;
  prazo_area_em: string | null;
  prazo_estourado: boolean;
  rotulo_prazo: string;
  minutos_uteis_restantes: number | null;
  // Movimentação mais nova que a última vez que a Ouvidoria abriu o caso
  // (issue #484, RN-66). Quem está fora da Ouvidoria recebe sempre falso: o
  // ponto diz "a Ouvidoria ainda não viu", e não significa nada para os
  // outros perfis do painel.
  tem_novidade: boolean;
}

function formatarData(iso: string): string {
  return new Date(`${iso}T12:00:00`).toLocaleDateString("pt-BR");
}

function formatarDataHora(iso: string): string {
  return new Date(iso).toLocaleString("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function PrazoCell({ m, classe }: { m: ManifestacaoIndice; classe: ClassePrazo }) {
  // Caso já classificado mostra o vencimento em data e hora, com a contagem
  // regressiva do motor logo abaixo. Caso ainda sem gravidade mostra o prazo
  // de referência da fundação, que é o que existe antes da validação.
  const label = m.prazo_area_em ? formatarDataHora(m.prazo_area_em) : formatarData(m.prazo_resposta);
  // Caso já respondido ou encerrado saiu das mãos de quem precisava correr:
  // o relógio para, e "vencido há 5 dias úteis" ali só assusta à toa.
  const rotulo = m.prazo_area_em && classe !== "respondido" ? m.rotulo_prazo : null;

  if (classe === "estourado") {
    return (
      <span className="inline-flex flex-col gap-0.5">
        <span className="inline-flex items-center gap-1 text-red-600 text-sm font-semibold">
          <AlertCircle className="w-3.5 h-3.5" />
          {label}
          <span className="text-[10px] font-bold uppercase tracking-wide bg-red-100 text-red-700 px-1.5 py-0.5 rounded-full">
            Estourado
          </span>
        </span>
        {rotulo && <span className="text-[11px] text-red-500">{rotulo}</span>}
      </span>
    );
  }
  if (classe === "perto") {
    return (
      <span className="inline-flex flex-col gap-0.5">
        <span className="inline-flex items-center gap-1 text-amber-600 text-sm font-medium">
          <CalendarDays className="w-3.5 h-3.5" />
          {label}
        </span>
        {rotulo && <span className="text-[11px] text-amber-600">{rotulo}</span>}
      </span>
    );
  }
  return (
    <span className="inline-flex flex-col gap-0.5">
      <span className="text-slate-600 text-sm">{label}</span>
      {rotulo && <span className="text-[11px] text-slate-400">{rotulo}</span>}
    </span>
  );
}

/**
 * A tabela de linhas da fila. Vive fora do grupo de estado porque o bloco de
 * destaque (issue #486) mostra as MESMAS linhas: com o JSX copiado, o botão
 * novo de amanhã nasceria só num dos dois lugares.
 */
function TabelaDaFila({
  itens,
  hoje,
  podeAbrirDossie,
  onValidar,
  onEncerrar,
}: {
  itens: ManifestacaoIndice[];
  hoje: string | null;
  podeAbrirDossie: boolean;
  onValidar: (m: ManifestacaoIndice) => void;
  onEncerrar: (m: ManifestacaoIndice) => void;
}) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead className="sr-only">
          <tr>
            {["Protocolo", "Abertura", "Prazo", "Categoria", "Setor", "Resumo"].map((h) => (
              <th key={h}>{h}</th>
            ))}
            <th>Ações</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-50">
          {itens.map((m) => {
            const classe = hoje ? classificarPrazoDaManifestacao(m, hoje) : "normal";
            return (
              <tr key={m.id} className={classe === "estourado" ? "bg-red-50/50" : undefined}>
                <td className="px-5 py-3 font-mono font-semibold text-slate-800 whitespace-nowrap">
                  {/* O marcador de novidade (issue #484, RN-68).
                      Sinal permanente, e não intermitente: piscar
                      cansa, atrapalha a acessibilidade e some
                      justo quando o olho chega. O ponto é cor, e
                      cor sozinha não conta a história para quem
                      não a enxerga, então ele anda com o rótulo
                      em sr-only ao lado. */}
                  {m.tem_novidade && (
                    <>
                      <span
                        aria-hidden="true"
                        className="inline-block w-2 h-2 mr-2 rounded-full bg-primary align-middle"
                      />
                      <span className="sr-only">Movimentação nova</span>
                    </>
                  )}
                  {m.protocolo}
                </td>
                <td className="px-5 py-3 text-slate-600 whitespace-nowrap">
                  {formatarData(m.data_abertura)}
                </td>
                <td className="px-5 py-3 whitespace-nowrap">
                  <PrazoCell m={m} classe={classe} />
                </td>
                <td className="px-5 py-3 text-slate-600 whitespace-nowrap">{m.categoria}</td>
                <td className="px-5 py-3 text-slate-600 whitespace-nowrap">{m.setor}</td>
                {/* Peso médio no resumo do caso com novidade
                    (issue #484, RN-68): é o segundo sinal, para o
                    ponto não ficar sozinho carregando a cor. */}
                <td
                  className={`px-5 py-3 max-w-md ${
                    m.tem_novidade ? "font-medium text-slate-800" : "text-slate-600"
                  }`}
                >
                  {m.resumo}
                </td>
                <td className="px-5 py-3 text-right whitespace-nowrap">
                  {podeAbrirDossie && podeValidar(m.status) && (
                    <button
                      onClick={() => onValidar(m)}
                      className="inline-flex items-center gap-1.5 px-3 py-1.5 mr-2 rounded-lg text-xs font-semibold bg-primary text-white hover:bg-primary/90 transition-colors"
                    >
                      <Send className="w-3.5 h-3.5" />
                      Validar e acionar
                    </button>
                  )}
                  {podeAbrirDossie && podeEncerrar(m.status) && (
                    <button
                      onClick={() => onEncerrar(m)}
                      className="inline-flex items-center gap-1.5 px-3 py-1.5 mr-2 rounded-lg text-xs font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200 hover:bg-emerald-100 transition-colors"
                    >
                      <CheckCircle2 className="w-3.5 h-3.5" />
                      Encerrar
                    </button>
                  )}
                  {/* Link de verdade, e não botão que abre modal
                      (issue #476): o caso tem endereço próprio, e
                      é isso que faz o voltar do navegador, o
                      favorito e o link do email funcionarem. */}
                  {podeAbrirDossie && (
                    <Link
                      href={`/ouvidoria/m/${m.protocolo}`}
                      className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-slate-100 text-slate-700 hover:bg-slate-200 transition-colors"
                    >
                      <FileText className="w-3.5 h-3.5" />
                      Abrir manifestação
                    </Link>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export default function OuvidoriaPage() {
  const [manifestacoes, setManifestacoes] = useState<ManifestacaoIndice[]>([]);
  const [loading, setLoading] = useState(true);
  const [semAcesso, setSemAcesso] = useState(false);
  const [erroCarga, setErroCarga] = useState(false);
  const [token, setToken] = useState<string | null>(null);
  const [hoje, setHoje] = useState<string | null>(null);
  const [registrando, setRegistrando] = useState(false);
  const [validando, setValidando] = useState<ManifestacaoIndice | null>(null);
  const [encerrando, setEncerrando] = useState<ManifestacaoIndice | null>(null);
  // O que o servidor não conseguiu ler nesta carga (issue #449). Chega aqui
  // pelo marcador de novidade (issue #484): trilha fora do ar desenha uma fila
  // sem ponto nenhum, que é indistinguível de uma fila sem novidade.
  const [degradado, setDegradado] = useState<string[]>([]);

  const { participante } = useCurrentParticipante();
  const podeAbrirDossie = Boolean(participante?.perfil_ouvidoria);
  const podeAjustarPrazos = podeEditarPrazos(participante?.perfil_ouvidoria);
  const podeCadastrarResponsaveis = podeGerirResponsaveis(participante?.perfil_ouvidoria);

  // Recarrega a fila depois de registrar: o caso novo precisa aparecer sem o
  // ouvidor ter que atualizar a página na mão.
  async function recarregar(sessionToken: string) {
    try {
      const res = await fetch("/api/ouvidoria/protocolos", {
        headers: { Authorization: `Bearer ${sessionToken}` },
      });
      if (res.status === 403) {
        setSemAcesso(true);
      } else if (res.ok) {
        const corpo = await res.json();
        setManifestacoes(corpo.protocolos);
        setDegradado(corpo.degradado ?? []);
      } else {
        // Erro não pode virar "nenhuma manifestação": falso negativo num
        // painel de prazo.
        setErroCarga(true);
      }
    } catch (e) {
      console.error("Erro ao carregar manifestações:", e);
      setErroCarga(true);
    }
  }

  useEffect(() => {
    // Data local do navegador (data civil, sem UTC), só após montar: evita
    // divergência de hidratação no destaque de prazo.
    const agora = new Date();
    setHoje(
      `${agora.getFullYear()}-${String(agora.getMonth() + 1).padStart(2, "0")}-${String(
        agora.getDate()
      ).padStart(2, "0")}`
    );

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
      await recarregar(sessionToken);
      setLoading(false);
    }
    init();
  }, []);

  const grupos = agruparPorStatus(manifestacoes).filter((g) => g.itens.length > 0);
  // O trabalho do dia do ouvidor, em cima de tudo (issue #486, RN-67): o caso
  // que a área respondeu e que ele ainda não abriu. Sai da mesma lista que os
  // grupos, sem consumi-la: o caso destacado continua no grupo de estado dele.
  const aguardandoEncerramento = aguardandoSeuEncerramento(manifestacoes);
  const emAndamento = manifestacoes.filter((m) => EM_ANDAMENTO.has(m.status)).length;
  const estourados = hoje
    ? manifestacoes.filter((m) => classificarPrazoDaManifestacao(m, hoje) === "estourado").length
    : 0;

  return (
    <div className="p-4 md:p-8 max-w-6xl mx-auto">
      <div className="flex flex-wrap items-end justify-between gap-3 mb-6">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Ouvidoria</h1>
          <p className="text-slate-500 text-sm mt-0.5">
            Manifestações do hospital, na ordem do trabalho da ouvidoria
          </p>
        </div>
        {!loading && !semAcesso && !erroCarga && (
          <div className="flex items-center gap-2">
            {/* O retrato de agora, restrito aos dois perfis da Ouvidoria
                (issue #344). O gate de verdade é o backend, que recusa as
                métricas a quem não pode; a tela só não oferece a porta. */}
            {podeVerPainel(participante?.perfil_ouvidoria) && (
              <Link
                href="/ouvidoria/painel"
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-sm font-medium bg-slate-100 text-slate-700 hover:bg-slate-200 transition-colors"
              >
                <LayoutDashboard className="w-4 h-4" />
                Painel em tempo real
              </Link>
            )}
            {/* RN-21: quem define o prazo é a Diretoria Executiva. Os demais
                perfis não veem sequer a porta da tela. */}
            {/* A nota de fora entra pela mão do ouvidor, e é a Ouvidoria
                inteira que responde por ela (issue #347). */}
            {podeRegistrarNotaExterna(participante?.perfil_ouvidoria) && (
              <Link
                href="/ouvidoria/nota-externa"
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-sm font-medium bg-slate-100 text-slate-700 hover:bg-slate-200 transition-colors"
              >
                <Star className="w-4 h-4" />
                Nota externa
              </Link>
            )}
            {podeGerirPontos(participante?.perfil_ouvidoria) && (
              <Link
                href="/ouvidoria/pontos"
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-sm font-medium bg-slate-100 text-slate-700 hover:bg-slate-200 transition-colors"
              >
                <MapPin className="w-4 h-4" />
                Pontos de escuta
              </Link>
            )}
            {podeCadastrarResponsaveis && (
              <Link
                href="/ouvidoria/responsaveis"
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-sm font-medium bg-slate-100 text-slate-700 hover:bg-slate-200 transition-colors"
              >
                <UsersRound className="w-4 h-4" />
                Responsáveis por setor
              </Link>
            )}
            {podeAjustarPrazos && (
              <Link
                href="/ouvidoria/prazos"
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-sm font-medium bg-slate-100 text-slate-700 hover:bg-slate-200 transition-colors"
              >
                <SlidersHorizontal className="w-4 h-4" />
                Tabela de prazos
              </Link>
            )}
            <span className="inline-flex items-center px-3 py-1.5 rounded-full text-sm font-medium bg-sky-100 text-sky-700">
              {emAndamento} em andamento
            </span>
            {estourados > 0 && (
              <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-sm font-medium bg-red-100 text-red-700">
                <AlertCircle className="w-4 h-4" />
                {estourados} com prazo estourado
              </span>
            )}
            {/* Registrar é ato da Ouvidoria: o gate de verdade é o backend
                (403), a tela só não oferece o caminho a quem não pode. */}
            {podeAbrirDossie && (
              <button
                onClick={() => setRegistrando(true)}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-semibold bg-primary text-white hover:bg-primary/90 transition-colors"
              >
                <Plus className="w-4 h-4" />
                Nova manifestação
              </button>
            )}
          </div>
        )}
      </div>

      {/* O que esta carga não pôde afirmar (issue #449, e agora a trilha do
          marcador de novidade, issue #484). Sinal ausente e sinal desligado
          desenham a mesma lista, então a falha precisa estar escrita. */}
      {!loading &&
        !semAcesso &&
        !erroCarga &&
        avisosDeDegradacao(degradado).map((aviso) => (
          <div
            key={aviso.leitura}
            className="flex items-start gap-2 mb-4 px-4 py-3 rounded-xl bg-amber-50 border border-amber-200 text-amber-800 text-sm"
          >
            <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
            <span>{aviso.texto}</span>
          </div>
        ))}

      {!loading && !semAcesso && !erroCarga && !podeAbrirDossie && manifestacoes.length > 0 && (
        <div className="flex items-start gap-2 mb-4 px-4 py-3 rounded-xl bg-slate-50 border border-slate-200 text-slate-600 text-sm">
          <Lock className="w-4 h-4 shrink-0 mt-0.5" />
          <span>
            Você vê o índice das manifestações. O conteúdo completo é restrito ao Ouvidor e à
            Diretoria Executiva.
          </span>
        </div>
      )}

      {/* O bloco AGUARDANDO SEU ENCERRAMENTO (issue #486, RN-67). Fica acima
          de todos os grupos e some quando não há nenhum caso: bloco vazio
          ocupando o topo todo dia ensinaria o olho a pular a região justo
          quando ela tivesse algo. Destaque, e não filtro novo: as linhas daqui
          continuam nos seus grupos logo abaixo.

          A guarda de `erroCarga` é a mesma dos blocos irmãos daqui de cima: com
          a recarga falhada, a lista na memória é a de antes do que o ouvidor
          acabou de fazer, e o topo seguiria oferecendo o botão Encerrar sobre
          um estado que não vale mais, enquanto o card logo abaixo já diz que
          não conseguiu carregar. */}
      {!erroCarga && aguardandoEncerramento.length > 0 && (
        <section
          aria-label={TITULO_AGUARDANDO_ENCERRAMENTO}
          className="bg-white rounded-2xl border border-primary/30 shadow-premium overflow-hidden mb-4"
        >
          <header className="flex items-center gap-2 px-5 py-3 bg-primary/5 border-b border-primary/20">
            <span className="inline-flex items-center gap-1.5 text-xs font-bold uppercase tracking-wide text-primary">
              <CheckCircle2 className="w-4 h-4" />
              {TITULO_AGUARDANDO_ENCERRAMENTO}
            </span>
            <span className="text-xs text-slate-400">
              {aguardandoEncerramento.length}{" "}
              {aguardandoEncerramento.length === 1 ? "manifestação" : "manifestações"}
            </span>
          </header>
          <TabelaDaFila
            itens={aguardandoEncerramento}
            hoje={hoje}
            podeAbrirDossie={podeAbrirDossie}
            onValidar={setValidando}
            onEncerrar={setEncerrando}
          />
        </section>
      )}

      <div className="bg-white rounded-2xl border border-border shadow-premium overflow-hidden min-h-[300px]">
        {loading ? (
          <div className="flex items-center justify-center h-48 gap-2 text-slate-400 text-sm">
            <Loader2 className="w-5 h-5 animate-spin text-primary/40" />
            Carregando manifestações...
          </div>
        ) : semAcesso ? (
          <div className="text-center py-16">
            <p className="text-slate-500 font-medium">Acesso restrito à equipe de Reuniões</p>
          </div>
        ) : erroCarga ? (
          <div className="text-center py-16">
            <div className="w-14 h-14 rounded-2xl bg-red-50 flex items-center justify-center mx-auto mb-3">
              <AlertCircle className="w-7 h-7 text-red-400" strokeWidth={1.5} />
            </div>
            <p className="text-slate-500 font-medium">Não foi possível carregar as manifestações</p>
            <p className="text-slate-400 text-sm mt-1">Recarregue a página para tentar novamente.</p>
          </div>
        ) : manifestacoes.length === 0 ? (
          <div className="text-center py-16">
            <div className="w-14 h-14 rounded-2xl bg-slate-100 flex items-center justify-center mx-auto mb-3">
              <Megaphone className="w-7 h-7 text-slate-300" strokeWidth={1.5} />
            </div>
            <p className="text-slate-500 font-medium">Nenhuma manifestação registrada</p>
            <p className="text-slate-400 text-sm mt-1">
              As manifestações chegam pelo atendimento da Ana e pelo registro da ouvidoria.
            </p>
          </div>
        ) : (
          <div className="divide-y divide-slate-100">
            {grupos.map((grupo) => (
              <section key={grupo.status}>
                <header className="flex items-center gap-2 px-5 py-3 bg-slate-50 border-b border-slate-100">
                  <span
                    className={`inline-flex items-center px-2.5 py-1 rounded-full text-xs font-semibold ${classeDoStatus(grupo.status)}`}
                  >
                    {rotuloDoStatus(grupo.status)}
                  </span>
                  <span className="text-xs text-slate-400">
                    {grupo.itens.length}{" "}
                    {grupo.itens.length === 1 ? "manifestação" : "manifestações"}
                  </span>
                </header>
                <TabelaDaFila
                  itens={grupo.itens}
                  hoje={hoje}
                  podeAbrirDossie={podeAbrirDossie}
                  onValidar={setValidando}
                  onEncerrar={setEncerrando}
                />
              </section>
            ))}
          </div>
        )}
      </div>

      <ValidarModal
        manifestacao={validando}
        token={token}
        onClose={() => setValidando(null)}
        onAcionada={() => {
          if (token) recarregar(token);
        }}
      />

      <EncerrarModal
        manifestacao={encerrando}
        token={token}
        onClose={() => setEncerrando(null)}
        onEncerrada={() => {
          if (token) recarregar(token);
        }}
      />

      <NovaManifestacaoModal
        aberto={registrando}
        token={token}
        onClose={() => setRegistrando(false)}
        onRegistrada={() => {
          if (token) recarregar(token);
        }}
      />
    </div>
  );
}
