"use client";

import { useCallback, useEffect, useState } from "react";
import {
  AlertCircle,
  CalendarClock,
  Loader2,
  Lock,
  Mail,
  Paperclip,
  PauseCircle,
  PhoneCall,
  PlayCircle,
  RotateCcw,
  RotateCw,
  ShieldAlert,
  UserRound,
} from "lucide-react";
import { AdminModal } from "@/components/admin/AdminModal";
import { LABEL_STATUS } from "@/lib/ouvidoria/fila";
import type { StatusManifestacao } from "@/lib/ouvidoria/prazo";
import type { PedidoDeProrrogacao } from "@/lib/ouvidoria/setor";
import {
  LABEL_GATILHO,
  LABEL_GRAVIDADE,
  LABEL_STATUS_NOTIFICACAO,
  TENTATIVAS_MINIMAS_DE_CONTATO,
  podePausar,
  podeReabrir,
  podeRetomar,
  type Gravidade,
  type Notificacao,
} from "@/lib/ouvidoria/validacao";

interface Anexo {
  id: string;
  filename: string;
  content_type: string;
  tamanho_bytes: number;
  enviado_por_nome: string;
}

export interface Dossie {
  id: string;
  protocolo: string;
  data_abertura: string;
  prazo_resposta: string;
  status: StatusManifestacao;
  categoria: string;
  setor: string;
  resumo: string;
  relato_integral: string | null;
  manifestante_nome: string | null;
  manifestante_contato: string | null;
  manifestante_vinculo: string | null;
  anonimo: boolean;
  sigilo_reforcado: boolean;
  dados_incompletos: boolean;
  desfecho: string | null;
  desfecho_descricao: string | null;
  gravidade: string | null;
  prazo_area_em: string | null;
  validada_em: string | null;
  respondida_em: string | null;
  resposta_da_area: string | null;
  respondida_por_nome: string | null;
  encerrada_em: string | null;
  // Pausa aguardando o manifestante e reincidência (issue #335).
  pausada_em: string | null;
  minutos_pausados: number;
  reincidencia: boolean;
  reaberta_em: string | null;
}

interface TentativaDeContato {
  id: string;
  tentada_em: string;
  canal: string;
  observacao: string | null;
  autor_nome: string;
}

interface DossieModalProps {
  manifestacaoId: string | null;
  token: string | null;
  onClose: () => void;
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

/**
 * O crédito da resposta da área. Nome e data entram cada um por conta própria:
 * resposta gravada por um responsável já removido do cadastro ainda mostra
 * quando chegou.
 */
function creditoDaResposta(nome: string | null, quando: string | null): string {
  const partes = [nome, quando ? formatarDataHora(quando) : null].filter(Boolean);
  return partes.length ? ` (${partes.join(", ")})` : "";
}

/**
 * O tempo parado em linguagem de gente. O número vem em minutos de EXPEDIENTE,
 * e um dia útil do hospital tem nove horas: dizer "2 dias" para 18 horas úteis
 * é o que o ouvidor entende, e "1080 minutos" não é (issue #335).
 */
function formatarEsperaUtil(minutos: number): string {
  const MINUTOS_POR_DIA_UTIL = 9 * 60;
  const dias = Math.floor(minutos / MINUTOS_POR_DIA_UTIL);
  const horas = Math.round((minutos % MINUTOS_POR_DIA_UTIL) / 60);
  const partes: string[] = [];
  if (dias > 0) partes.push(dias === 1 ? "1 dia útil" : `${dias} dias úteis`);
  if (horas > 0) partes.push(horas === 1 ? "1 hora útil" : `${horas} horas úteis`);
  return partes.length > 0 ? partes.join(" e ") : "menos de uma hora útil";
}

function formatarTamanho(bytes: number): string {
  const mb = bytes / (1024 * 1024);
  return mb >= 1 ? `${mb.toFixed(1)} MB` : `${Math.max(1, Math.round(bytes / 1024))} KB`;
}

function Linha({ rotulo, valor }: { rotulo: string; valor: string }) {
  return (
    <div>
      <dt className="text-xs font-semibold text-slate-400 uppercase tracking-wide">{rotulo}</dt>
      <dd className="text-sm text-slate-700 mt-0.5">{valor}</dd>
    </div>
  );
}

/**
 * Dossiê completo da manifestação (ADR 0034, decisão 1).
 *
 * Só abre para ouvidor e diretoria executiva: o gate de verdade é o backend,
 * que devolve 403 e registra o acesso no log. A tela apenas não oferece o
 * caminho a quem não pode.
 */
export function DossieModal({ manifestacaoId, token, onClose }: DossieModalProps) {
  const [dossie, setDossie] = useState<Dossie | null>(null);
  const [carregando, setCarregando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [anexos, setAnexos] = useState<Anexo[]>([]);
  const [abrindoAnexo, setAbrindoAnexo] = useState<string | null>(null);
  // Erro de anexo é separado do erro de carga: um link que não abriu não pode
  // apagar da tela o relato e a identificação que o ouvidor está lendo.
  const [erroAnexo, setErroAnexo] = useState<string | null>(null);
  // A trilha de cobrança do caso: o que já foi enviado, para quem e quando.
  const [notificacoes, setNotificacoes] = useState<Notificacao[]>([]);
  const [reenviando, setReenviando] = useState<string | null>(null);
  const [avisoReenvio, setAvisoReenvio] = useState<string | null>(null);
  // Prorrogação de prazo (issue #333): o pedido da área espera a decisão da
  // Ouvidoria, e é aqui, ao lado da resposta e do prazo, que ela acontece.
  const [prorrogacoes, setProrrogacoes] = useState<PedidoDeProrrogacao[]>([]);
  const [justificativaDaDecisao, setJustificativaDaDecisao] = useState("");
  const [decidindo, setDecidindo] = useState(false);
  const [avisoDecisao, setAvisoDecisao] = useState<string | null>(null);
  // Devolução por insuficiência (issue #334): resposta fraca volta ao setor
  // com meio prazo. O motivo é obrigatório, então o botão só abre depois de o
  // ouvidor escrever por que a resposta não resolve.
  const [motivoDaDevolucao, setMotivoDaDevolucao] = useState("");
  const [devolvendo, setDevolvendo] = useState(false);
  const [avisoDevolucao, setAvisoDevolucao] = useState<string | null>(null);
  // Pausa aguardando o manifestante, tentativas de contato e reabertura por
  // reincidência (issue #335). Tudo o que a Ouvidoria faz com o manifestante,
  // e não com a área, mora num bloco só.
  const [tentativas, setTentativas] = useState<TentativaDeContato[]>([]);
  const [motivoDoManifestante, setMotivoDoManifestante] = useState("");
  const [canalDaTentativa, setCanalDaTentativa] = useState("telefone");
  const [observacaoDaTentativa, setObservacaoDaTentativa] = useState("");
  const [emAcaoDoManifestante, setEmAcaoDoManifestante] = useState(false);
  const [avisoDoManifestante, setAvisoDoManifestante] = useState<string | null>(null);

  useEffect(() => {
    if (!manifestacaoId || !token) {
      setAnexos([]);
      setErroAnexo(null);
      return;
    }
    let cancelado = false;
    fetch(`/api/ouvidoria/manifestacoes/${manifestacaoId}/anexos`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then(async (res) => {
        if (!cancelado && res.ok) setAnexos((await res.json()).anexos);
      })
      .catch(() => {
        if (!cancelado) setAnexos([]);
      });
    return () => {
      cancelado = true;
    };
  }, [manifestacaoId, token]);

  const carregarNotificacoes = useCallback(async () => {
    if (!manifestacaoId || !token) return;
    try {
      const res = await fetch(`/api/ouvidoria/manifestacoes/${manifestacaoId}/notificacoes`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) setNotificacoes((await res.json()).notificacoes);
    } catch {
      setNotificacoes([]);
    }
  }, [manifestacaoId, token]);

  useEffect(() => {
    setNotificacoes([]);
    setAvisoReenvio(null);
    carregarNotificacoes();
  }, [carregarNotificacoes]);

  const carregarProrrogacoes = useCallback(async () => {
    if (!manifestacaoId || !token) return;
    try {
      const res = await fetch(`/api/ouvidoria/manifestacoes/${manifestacaoId}/prorrogacoes`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) setProrrogacoes((await res.json()).prorrogacoes);
    } catch {
      setProrrogacoes([]);
    }
  }, [manifestacaoId, token]);

  useEffect(() => {
    setProrrogacoes([]);
    setAvisoDecisao(null);
    setJustificativaDaDecisao("");
    carregarProrrogacoes();
  }, [carregarProrrogacoes]);

  // O modal fica montado o tempo todo, então o texto digitado sobrevive à
  // troca de caso. Sem esta limpeza, o motivo escrito para o caso A aparece
  // no campo do caso B e um clique manda o texto de A ao setor de B.
  useEffect(() => {
    setMotivoDaDevolucao("");
    setAvisoDevolucao(null);
    setMotivoDoManifestante("");
    setObservacaoDaTentativa("");
    setAvisoDoManifestante(null);
  }, [manifestacaoId]);

  const carregarTentativas = useCallback(async () => {
    if (!manifestacaoId || !token) return;
    try {
      const res = await fetch(`/api/ouvidoria/manifestacoes/${manifestacaoId}/tentativas-contato`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) setTentativas((await res.json()).tentativas);
    } catch {
      setTentativas([]);
    }
  }, [manifestacaoId, token]);

  useEffect(() => {
    setTentativas([]);
    carregarTentativas();
  }, [carregarTentativas]);

  /**
   * Parar e religar o relógio da área. A pausa exige o motivo escrito, que vai
   * para a trilha: sem ele quem lê o caso meses depois vê o caso parar sem
   * saber por quê. A retomada não exige nada além do clique, porque o motivo
   * dela já está no que o manifestante respondeu.
   */
  async function moverRelogio(estado: "aguardando_manifestante" | "aguardando_area") {
    if (!manifestacaoId || !token) return;
    const pausando = estado === "aguardando_manifestante";
    const motivo = motivoDoManifestante.trim();
    if (pausando && !motivo) return;
    setEmAcaoDoManifestante(true);
    setAvisoDoManifestante(null);
    try {
      const res = await fetch(`/api/ouvidoria/manifestacoes/${manifestacaoId}/transicoes`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
        body: JSON.stringify({ estado, observacao: pausando ? motivo : "O manifestante respondeu." }),
      });
      if (!res.ok) {
        const corpo = await res.json().catch(() => ({}));
        setAvisoDoManifestante(
          typeof corpo.detail === "string" ? corpo.detail : "Não foi possível mover o caso agora. Tente novamente."
        );
        return;
      }
      setDossie(await res.json());
      setMotivoDoManifestante("");
      setAvisoDoManifestante(
        pausando
          ? "Caso parado. O prazo da área não corre enquanto ele esperar o manifestante."
          : "Caso retomado. O tempo parado foi devolvido ao prazo da área."
      );
    } catch {
      setAvisoDoManifestante("Não foi possível mover o caso agora. Tente novamente.");
    } finally {
      setEmAcaoDoManifestante(false);
    }
  }

  /** Registra que a Ouvidoria tentou falar com o manifestante. */
  async function registrarTentativa() {
    if (!manifestacaoId || !token) return;
    const canal = canalDaTentativa.trim();
    if (!canal) return;
    setEmAcaoDoManifestante(true);
    setAvisoDoManifestante(null);
    try {
      const res = await fetch(`/api/ouvidoria/manifestacoes/${manifestacaoId}/tentativas-contato`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
        body: JSON.stringify({ canal, observacao: observacaoDaTentativa.trim() || null }),
      });
      if (!res.ok) {
        setAvisoDoManifestante("Não foi possível registrar a tentativa agora. Tente novamente.");
        return;
      }
      setObservacaoDaTentativa("");
      await carregarTentativas();
    } catch {
      setAvisoDoManifestante("Não foi possível registrar a tentativa agora. Tente novamente.");
    } finally {
      setEmAcaoDoManifestante(false);
    }
  }

  /**
   * Reabre o caso original por reincidência. Não nasce protocolo novo: é isso
   * que impede a reincidência de inflar o volume de casos novos.
   */
  async function reabrirPorReincidencia() {
    if (!manifestacaoId || !token) return;
    const motivo = motivoDoManifestante.trim();
    if (!motivo) return;
    setEmAcaoDoManifestante(true);
    setAvisoDoManifestante(null);
    try {
      const res = await fetch(`/api/ouvidoria/manifestacoes/${manifestacaoId}/reaberturas`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
        body: JSON.stringify({ motivo }),
      });
      if (!res.ok) {
        const corpo = await res.json().catch(() => ({}));
        setAvisoDoManifestante(
          typeof corpo.detail === "string" ? corpo.detail : "Não foi possível reabrir o caso agora. Tente novamente."
        );
        return;
      }
      setDossie(await res.json());
      setMotivoDoManifestante("");
      setAvisoDoManifestante("Caso reaberto como reincidência. O setor foi avisado e tem prazo novo.");
      await carregarNotificacoes();
    } catch {
      setAvisoDoManifestante("Não foi possível reabrir o caso agora. Tente novamente.");
    } finally {
      setEmAcaoDoManifestante(false);
    }
  }

  /**
   * A decisão do ouvidor. Aprovar move o prazo do caso, e a própria resposta
   * da rota já traz o prazo projetado: o aviso lê dali em vez de refazer o
   * fetch do Dossiê, para a tela não dizer "o prazo novo já vale" ao lado da
   * data antiga.
   */
  async function decidirProrrogacao(pedido: PedidoDeProrrogacao, aprovada: boolean) {
    if (!manifestacaoId || !token) return;
    setDecidindo(true);
    setAvisoDecisao(null);
    try {
      const res = await fetch(
        `/api/ouvidoria/manifestacoes/${manifestacaoId}/prorrogacoes/${pedido.id}/decidir`,
        {
          method: "POST",
          headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
          body: JSON.stringify({
            aprovada,
            justificativa: justificativaDaDecisao.trim() || null,
          }),
        }
      );
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        setAvisoDecisao(body.detail || "Não foi possível registrar a decisão agora. Tente novamente.");
        return;
      }
      const corpo = await res.json().catch(() => ({}));
      const rotulo = typeof corpo.rotulo_prazo === "string" ? ` Prazo da área: ${corpo.rotulo_prazo}.` : "";
      setJustificativaDaDecisao("");
      setAvisoDecisao(
        (aprovada
          ? "Prorrogação aprovada. O prazo novo já vale e o setor foi avisado."
          : "Prorrogação negada. O prazo continua o mesmo e o setor foi avisado.") + rotulo
      );
      await Promise.all([carregarProrrogacoes(), carregarNotificacoes()]);
    } catch {
      setAvisoDecisao("Não foi possível registrar a decisão agora. Tente novamente.");
    } finally {
      setDecidindo(false);
    }
  }

  /**
   * A devolução do ouvidor. O caso volta para a área com metade do prazo
   * original da gravidade contada de agora, e o setor recebe o motivo por
   * email. A rota devolve o Dossiê já atualizado, então a tela lê dali em vez
   * de refazer o fetch: prazo novo e estado novo aparecem juntos.
   */
  async function devolverPorInsuficiencia() {
    if (!manifestacaoId || !token) return;
    const motivo = motivoDaDevolucao.trim();
    if (!motivo) return;
    setDevolvendo(true);
    setAvisoDevolucao(null);
    try {
      const res = await fetch(`/api/ouvidoria/manifestacoes/${manifestacaoId}/devolucoes`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
        body: JSON.stringify({ motivo }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        setAvisoDevolucao(
          typeof body.detail === "string"
            ? body.detail
            : "Não foi possível devolver a resposta agora. Tente novamente."
        );
        return;
      }
      setDossie(await res.json());
      setMotivoDaDevolucao("");
      setAvisoDevolucao("Resposta devolvida. O setor foi avisado e o prazo novo já vale.");
      await carregarNotificacoes();
    } catch {
      setAvisoDevolucao("Não foi possível devolver a resposta agora. Tente novamente.");
    } finally {
      setDevolvendo(false);
    }
  }

  /**
   * Reenvio manual: o ouvidor insiste quando o setor diz que não recebeu. O
   * envio original continua registrado, porque é ele que prova a data em que a
   * cobrança começou.
   */
  async function reenviar(notificacao: Notificacao) {
    if (!manifestacaoId || !token) return;
    setReenviando(notificacao.id);
    setAvisoReenvio(null);
    try {
      const res = await fetch(
        `/api/ouvidoria/manifestacoes/${manifestacaoId}/notificacoes/${notificacao.id}/reenviar`,
        { method: "POST", headers: { Authorization: `Bearer ${token}` } }
      );
      if (res.ok) {
        const { entregue } = await res.json();
        setAvisoReenvio(
          entregue
            ? `Reenviado para ${notificacao.destinatario_email}.`
            : "O reenvio ficou na fila: o provedor de email recusou agora e o sistema tenta de novo."
        );
        await carregarNotificacoes();
      } else {
        setAvisoReenvio("Não foi possível reenviar agora. Tente novamente.");
      }
    } catch {
      setAvisoReenvio("Não foi possível reenviar agora. Tente novamente.");
    } finally {
      setReenviando(null);
    }
  }

  /**
   * O binário vive em bucket privado: o link é assinado na hora, vale por
   * pouco tempo e por isso não pode ser um href fixo na tela.
   *
   * A aba abre ANTES do fetch, ainda dentro do clique: aberta depois do await
   * ela cai no bloqueador de pop-up do navegador e o anexo não abriria nem
   * daria erro.
   */
  async function abrirAnexo(anexo: Anexo) {
    if (!manifestacaoId || !token) return;
    setAbrindoAnexo(anexo.id);
    setErroAnexo(null);
    // Sem "noopener" na string de features: com ela o navegador devolve null e
    // a gente perderia a aba que acabou de abrir. O isolamento vem do
    // `aba.opener = null` logo abaixo, que faz o mesmo sem custo.
    const aba = window.open("", "_blank");
    if (aba) aba.opener = null;
    try {
      const res = await fetch(
        `/api/ouvidoria/manifestacoes/${manifestacaoId}/anexos/${anexo.id}/url`,
        { headers: { Authorization: `Bearer ${token}` } }
      );
      if (res.ok) {
        const { url } = await res.json();
        // Sem aba (bloqueador agressivo), o anexo simplesmente nao abre: tirar
        // o ouvidor da tela do Dossie para mostrar um PDF seria pior.
        if (aba) aba.location.href = url;
        else setErroAnexo("Libere os pop-ups deste site para abrir o anexo.");
      } else {
        aba?.close();
        setErroAnexo("Não foi possível abrir o anexo. Tente novamente.");
      }
    } catch {
      aba?.close();
      setErroAnexo("Não foi possível abrir o anexo. Tente novamente.");
    } finally {
      setAbrindoAnexo(null);
    }
  }

  useEffect(() => {
    if (!manifestacaoId || !token) {
      setDossie(null);
      return;
    }
    let cancelado = false;
    setCarregando(true);
    setErro(null);
    fetch(`/api/ouvidoria/manifestacoes/${manifestacaoId}`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then(async (res) => {
        if (cancelado) return;
        if (res.status === 403) {
          setErro("Seu perfil não permite abrir esta manifestação.");
        } else if (res.ok) {
          setDossie(await res.json());
        } else {
          setErro("Não foi possível abrir a manifestação. Tente novamente.");
        }
      })
      .catch(() => {
        if (!cancelado) setErro("Não foi possível abrir a manifestação. Tente novamente.");
      })
      .finally(() => {
        if (!cancelado) setCarregando(false);
      });
    return () => {
      cancelado = true;
    };
  }, [manifestacaoId, token]);

  const identificacao = dossie?.anonimo
    ? "Manifestação anônima"
    : dossie?.manifestante_nome || "Não informado";

  return (
    <AdminModal
      open={Boolean(manifestacaoId)}
      onClose={onClose}
      title={dossie ? `Manifestação ${dossie.protocolo}` : "Manifestação"}
      description={dossie ? LABEL_STATUS[dossie.status] : undefined}
      icon={<UserRound className="w-5 h-5" />}
      size="lg"
      scrollable
    >
      {carregando ? (
        <div className="flex items-center justify-center py-12 gap-2 text-slate-400 text-sm">
          <Loader2 className="w-5 h-5 animate-spin text-primary/40" />
          Abrindo a manifestação...
        </div>
      ) : erro ? (
        <div className="flex items-start gap-2 px-4 py-3 rounded-xl bg-red-50 border border-red-200 text-red-700 text-sm">
          <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
          {erro}
        </div>
      ) : dossie ? (
        <div className="space-y-5">
          {dossie.sigilo_reforcado && (
            <div className="flex items-start gap-2 px-4 py-3 rounded-xl bg-amber-50 border border-amber-200 text-amber-800 text-sm">
              <Lock className="w-4 h-4 shrink-0 mt-0.5" />
              <span>
                Sigilo reforçado. O conteúdo desta manifestação é restrito ao Ouvidor e à
                Diretoria Executiva.
              </span>
            </div>
          )}

          {dossie.dados_incompletos && (
            <div className="flex items-start gap-2 px-4 py-3 rounded-xl bg-sky-50 border border-sky-200 text-sky-800 text-sm">
              <ShieldAlert className="w-4 h-4 shrink-0 mt-0.5" />
              <span>
                Cadastro incompleto: o caso chegou resumido e precisa ser completado na
                validação.
              </span>
            </div>
          )}

          <dl className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <Linha rotulo="Quem manifestou" valor={identificacao} />
            <Linha rotulo="Contato" valor={dossie.manifestante_contato || "Não informado"} />
            <Linha rotulo="Vínculo" valor={dossie.manifestante_vinculo || "Não informado"} />
            <Linha rotulo="Setor" valor={dossie.setor} />
            <Linha rotulo="Categoria" valor={dossie.categoria} />
            <Linha
              rotulo="Gravidade"
              valor={
                dossie.gravidade
                  ? LABEL_GRAVIDADE[dossie.gravidade as Gravidade] ?? dossie.gravidade
                  : "Ainda não classificada"
              }
            />
            <Linha
              rotulo="Prazo da área"
              valor={
                dossie.prazo_area_em
                  ? formatarDataHora(dossie.prazo_area_em)
                  : "Definido no acionamento"
              }
            />
            <Linha
              rotulo="Validada em"
              valor={dossie.validada_em ? formatarDataHora(dossie.validada_em) : "Ainda não validada"}
            />
          </dl>

          <div>
            <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wide mb-1">
              Resumo
            </h3>
            <p className="text-sm text-slate-700 whitespace-pre-line">{dossie.resumo}</p>
          </div>

          <div>
            <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wide mb-1">
              Relato integral
            </h3>
            <p className="text-sm text-slate-700 whitespace-pre-line">
              {dossie.relato_integral || "O relato integral ainda não foi registrado."}
            </p>
          </div>

          {anexos.length > 0 && (
            <div>
              <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wide mb-1">
                Anexos
              </h3>
              {erroAnexo && (
                <p className="flex items-start gap-2 mb-1.5 px-3 py-2 rounded-lg bg-red-50 border border-red-200 text-red-700 text-xs">
                  <AlertCircle className="w-3.5 h-3.5 shrink-0 mt-0.5" />
                  {erroAnexo}
                </p>
              )}
              <ul className="space-y-1">
                {anexos.map((anexo) => (
                  <li key={anexo.id}>
                    <button
                      onClick={() => abrirAnexo(anexo)}
                      disabled={abrindoAnexo === anexo.id}
                      className="flex items-center gap-2 w-full text-left text-sm text-slate-700 px-3 py-2 rounded-lg bg-slate-50 hover:bg-slate-100 disabled:opacity-50 transition-colors"
                    >
                      {abrindoAnexo === anexo.id ? (
                        <Loader2 className="w-3.5 h-3.5 shrink-0 animate-spin text-slate-400" />
                      ) : (
                        <Paperclip className="w-3.5 h-3.5 shrink-0 text-slate-400" />
                      )}
                      <span className="truncate flex-1">{anexo.filename}</span>
                      <span className="text-xs text-slate-400 shrink-0">
                        {formatarTamanho(anexo.tamanho_bytes)}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {prorrogacoes.map((pedido) => (
            <div key={pedido.id}>
              <h3 className="flex items-center gap-1.5 text-xs font-semibold text-slate-400 uppercase tracking-wide mb-1">
                <CalendarClock className="w-3.5 h-3.5" />
                Prorrogação de prazo
              </h3>
              <div className="rounded-lg bg-slate-50 border border-slate-200 px-3 py-2.5 space-y-2">
                <p className="text-sm text-slate-700">
                  {pedido.solicitante_nome} pediu {pedido.dias_uteis_pedidos} dia(s) útil(eis) a mais
                  {pedido.prazo_novo ? `, até ${formatarDataHora(pedido.prazo_novo)}` : ""}.
                </p>
                <p className="text-sm text-slate-600 whitespace-pre-line">{pedido.justificativa}</p>

                {pedido.status === "pendente" ? (
                  <div className="space-y-2 pt-1">
                    <textarea
                      value={justificativaDaDecisao}
                      onChange={(e) => setJustificativaDaDecisao(e.target.value)}
                      rows={2}
                      placeholder="Motivo da decisão (opcional, vai no email ao setor)"
                      className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-800 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary resize-y"
                    />
                    <div className="flex gap-2">
                      <button
                        onClick={() => decidirProrrogacao(pedido, true)}
                        disabled={decidindo}
                        className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-emerald-600 text-white hover:bg-emerald-700 disabled:opacity-50 transition-colors"
                      >
                        {decidindo && <Loader2 className="w-3 h-3 animate-spin" />}
                        Aprovar
                      </button>
                      <button
                        onClick={() => decidirProrrogacao(pedido, false)}
                        disabled={decidindo}
                        className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-white border border-slate-200 text-slate-600 hover:bg-slate-100 disabled:opacity-50 transition-colors"
                      >
                        Negar
                      </button>
                    </div>
                  </div>
                ) : (
                  <p className="text-xs text-slate-500">
                    {pedido.status === "aprovada" ? "Aprovada" : "Negada"} por{" "}
                    {pedido.decidida_por_nome ?? "Ouvidoria"}
                    {pedido.decidida_em ? ` em ${formatarDataHora(pedido.decidida_em)}` : ""}.
                    {pedido.decisao_justificativa ? ` ${pedido.decisao_justificativa}` : ""}
                  </p>
                )}

                {avisoDecisao && (
                  <p className="text-xs text-slate-600 bg-white border border-slate-200 rounded-lg px-3 py-2">
                    {avisoDecisao}
                  </p>
                )}
              </div>
            </div>
          ))}

          {notificacoes.length > 0 && (
            <div>
              <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wide mb-1">
                Notificações enviadas
              </h3>
              {avisoReenvio && (
                <p className="mb-1.5 px-3 py-2 rounded-lg bg-slate-50 border border-slate-200 text-slate-600 text-xs">
                  {avisoReenvio}
                </p>
              )}
              <ul className="space-y-1">
                {notificacoes.map((n) => (
                  <li
                    key={n.id}
                    className="flex flex-wrap items-center gap-2 text-sm text-slate-700 px-3 py-2 rounded-lg bg-slate-50"
                  >
                    <Mail className="w-3.5 h-3.5 shrink-0 text-slate-400" />
                    <span className="font-medium">{LABEL_GATILHO[n.gatilho] ?? n.gatilho}</span>
                    <span className="text-slate-500 truncate">{n.destinatario_email}</span>
                    <span className="text-xs text-slate-400">
                      {n.enviada_em
                        ? formatarDataHora(n.enviada_em)
                        : LABEL_STATUS_NOTIFICACAO[n.status]}
                    </span>
                    <button
                      onClick={() => reenviar(n)}
                      disabled={reenviando === n.id}
                      className="ml-auto inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs font-semibold bg-white border border-slate-200 text-slate-600 hover:bg-slate-100 disabled:opacity-50 transition-colors"
                    >
                      {reenviando === n.id ? (
                        <Loader2 className="w-3 h-3 animate-spin" />
                      ) : (
                        <RotateCw className="w-3 h-3" />
                      )}
                      Reenviar
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Tudo o que a Ouvidoria faz com o MANIFESTANTE (issue #335): parar
              o relógio quando falta dado dele, registrar as tentativas de
              contato, e reabrir o caso quando ele volta. Fica separado do
              bloco da área de propósito: são duas conversas diferentes. */}
          {(podePausar(dossie.status) ||
            podeRetomar(dossie.status) ||
            podeReabrir(dossie.status, dossie.encerrada_em, new Date().toISOString()) ||
            dossie.minutos_pausados > 0) && (
            <div className="rounded-xl border border-slate-200 bg-slate-50/60 p-3.5">
              <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wide mb-2 flex items-center gap-1.5">
                <PhoneCall className="w-3.5 h-3.5" />
                Manifestante
                {dossie.reincidencia && (
                  <span className="ml-1 px-2 py-0.5 rounded-full text-[11px] font-semibold bg-purple-100 text-purple-700 border border-purple-200">
                    Reincidência
                  </span>
                )}
              </h3>

              {dossie.minutos_pausados > 0 && (
                <p className="text-sm text-slate-600 mb-2.5">
                  Este caso já esperou {formatarEsperaUtil(dossie.minutos_pausados)} pelo manifestante. Esse
                  tempo saiu do prazo da área e continua contado aqui.
                </p>
              )}

              {podePausar(dossie.status) && (
                <div className="space-y-2">
                  <textarea
                    value={motivoDoManifestante}
                    onChange={(e) => setMotivoDoManifestante(e.target.value)}
                    rows={2}
                    placeholder="O que falta do manifestante (obrigatório, fica na trilha do caso)"
                    className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-800 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary resize-y"
                  />
                  <button
                    onClick={() => moverRelogio("aguardando_manifestante")}
                    disabled={emAcaoDoManifestante || !motivoDoManifestante.trim()}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-slate-700 text-white hover:bg-slate-800 disabled:opacity-50 transition-colors"
                  >
                    {emAcaoDoManifestante ? (
                      <Loader2 className="w-3 h-3 animate-spin" />
                    ) : (
                      <PauseCircle className="w-3.5 h-3.5" />
                    )}
                    Parar: falta dado do manifestante
                  </button>
                  <p className="text-xs text-slate-500 leading-relaxed">
                    O prazo da área para de correr. Na volta, o tempo parado é devolvido ao prazo dela.
                  </p>
                </div>
              )}

              {podeRetomar(dossie.status) && (
                <div className="space-y-3">
                  <button
                    onClick={() => moverRelogio("aguardando_area")}
                    disabled={emAcaoDoManifestante}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-emerald-600 text-white hover:bg-emerald-700 disabled:opacity-50 transition-colors"
                  >
                    {emAcaoDoManifestante ? (
                      <Loader2 className="w-3 h-3 animate-spin" />
                    ) : (
                      <PlayCircle className="w-3.5 h-3.5" />
                    )}
                    O manifestante respondeu: voltar para a área
                  </button>

                  <div className="pt-1 border-t border-slate-200">
                    <p className="text-xs text-slate-500 leading-relaxed mb-2">
                      Encerrar por sem retorno exige {TENTATIVAS_MINIMAS_DE_CONTATO} tentativas de contato
                      registradas e cinco dias úteis de espera desde a primeira. Registradas até agora:{" "}
                      <strong className="text-slate-700">{tentativas.length}</strong>.
                    </p>
                    <div className="flex flex-wrap items-center gap-2">
                      <input
                        value={canalDaTentativa}
                        onChange={(e) => setCanalDaTentativa(e.target.value)}
                        placeholder="Canal (telefone, email...)"
                        className="w-40 rounded-lg border border-slate-200 px-2.5 py-1.5 text-xs text-slate-800 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary"
                      />
                      <input
                        value={observacaoDaTentativa}
                        onChange={(e) => setObservacaoDaTentativa(e.target.value)}
                        placeholder="O que aconteceu na tentativa"
                        className="flex-1 min-w-[180px] rounded-lg border border-slate-200 px-2.5 py-1.5 text-xs text-slate-800 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary"
                      />
                      <button
                        onClick={registrarTentativa}
                        disabled={emAcaoDoManifestante || !canalDaTentativa.trim()}
                        className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-white border border-slate-200 text-slate-600 hover:bg-slate-100 disabled:opacity-50 transition-colors"
                      >
                        <PhoneCall className="w-3 h-3" />
                        Registrar tentativa
                      </button>
                    </div>
                    {tentativas.length > 0 && (
                      <ul className="mt-2 space-y-1">
                        {tentativas.map((t) => (
                          <li key={t.id} className="text-xs text-slate-600">
                            {formatarDataHora(t.tentada_em)} por {t.autor_nome} ({t.canal})
                            {t.observacao ? `: ${t.observacao}` : ""}
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                </div>
              )}

              {podeReabrir(dossie.status, dossie.encerrada_em, new Date().toISOString()) && (
                <div className="space-y-2">
                  <textarea
                    value={motivoDoManifestante}
                    onChange={(e) => setMotivoDoManifestante(e.target.value)}
                    rows={2}
                    placeholder="O que o manifestante trouxe de volta (obrigatório, vai no email ao setor)"
                    className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-800 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary resize-y"
                  />
                  <button
                    onClick={reabrirPorReincidencia}
                    disabled={emAcaoDoManifestante || !motivoDoManifestante.trim()}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-purple-600 text-white hover:bg-purple-700 disabled:opacity-50 transition-colors"
                  >
                    {emAcaoDoManifestante ? (
                      <Loader2 className="w-3 h-3 animate-spin" />
                    ) : (
                      <RotateCcw className="w-3.5 h-3.5" />
                    )}
                    Reabrir por reincidência
                  </button>
                  <p className="text-xs text-slate-500 leading-relaxed">
                    O caso original volta para a área com o prazo inteiro da gravidade e fica marcado como
                    reincidência. Não nasce protocolo novo.
                  </p>
                </div>
              )}

              {avisoDoManifestante && <p className="mt-2 text-xs text-slate-500">{avisoDoManifestante}</p>}
            </div>
          )}

          {dossie.resposta_da_area && (
            <div>
              <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wide mb-1">
                Resposta da área
                {creditoDaResposta(dossie.respondida_por_nome, dossie.respondida_em)}
              </h3>
              <p className="text-sm text-slate-700 whitespace-pre-line">{dossie.resposta_da_area}</p>

              {dossie.status === "respondido" && (
                <div className="mt-2.5 space-y-2">
                  <textarea
                    value={motivoDaDevolucao}
                    onChange={(e) => setMotivoDaDevolucao(e.target.value)}
                    rows={2}
                    placeholder="Motivo da devolução (obrigatório, vai no email ao setor)"
                    className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-800 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary resize-y"
                  />
                  <button
                    onClick={devolverPorInsuficiencia}
                    disabled={devolvendo || !motivoDaDevolucao.trim()}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-amber-600 text-white hover:bg-amber-700 disabled:opacity-50 transition-colors"
                  >
                    {devolvendo && <Loader2 className="w-3 h-3 animate-spin" />}
                    Devolver por insuficiência
                  </button>
                  <p className="text-xs text-slate-500 leading-relaxed">
                    O caso volta para o setor com metade do prazo da gravidade, contada de agora. O tempo
                    já gasto continua valendo: o relógio não recomeça.
                  </p>
                </div>
              )}

              {avisoDevolucao && <p className="mt-2 text-xs text-slate-500">{avisoDevolucao}</p>}
            </div>
          )}

          {dossie.desfecho && (
            <div>
              <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wide mb-1">
                Desfecho
                {dossie.encerrada_em ? ` (encerrada em ${formatarDataHora(dossie.encerrada_em)})` : ""}
              </h3>
              <p className="text-sm text-slate-700 whitespace-pre-line">
                {dossie.desfecho_descricao || dossie.desfecho}
              </p>
            </div>
          )}
        </div>
      ) : null}
    </AdminModal>
  );
}

export default DossieModal;
