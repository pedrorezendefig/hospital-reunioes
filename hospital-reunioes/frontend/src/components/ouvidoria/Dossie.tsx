"use client";

import { useCallback, useEffect, useState } from "react";
import {
  AlertCircle,
  CalendarClock,
  CheckCircle2,
  History,
  Loader2,
  Lock,
  Mail,
  MapPin,
  MessageSquareQuote,
  Paperclip,
  PauseCircle,
  PhoneCall,
  PlayCircle,
  RotateCcw,
  RotateCw,
  Send,
  ShieldAlert,
  UserRound,
} from "lucide-react";
import { EncerrarModal } from "@/components/ouvidoria/EncerrarModal";
import { ValidarModal } from "@/components/ouvidoria/ValidarModal";
import {
  ehSigilosoPorNatureza,
  LABEL_TIPO,
  rotuloDoTipo,
  sigiloResultante,
  TIPOS_MANIFESTACAO,
  type TipoManifestacao,
} from "@/lib/ouvidoria/taxonomia";
import { rotuloDoStatus } from "@/lib/ouvidoria/fila";
import {
  descreverPrazo,
  descreverTrecho,
  prazosVisiveis,
  MARCO_PENDENTE,
  SITUACAO_DO_ACUSE,
  SITUACAO_DO_AVISO_DE_ENCERRAMENTO,
  type AcuseDoCaso,
  type AvisoDeEncerramento,
  type MarcoDoCaso,
  type PrazoDoCaso,
} from "@/lib/ouvidoria/marcos";
import { descreverOrigem } from "@/lib/ouvidoria/origem";
import { descreverTempoDesdeOMarco, type EventoDaTrilha } from "@/lib/ouvidoria/trilha";
import { avisosDeDegradacao, calendarioUtilFoiLido } from "@/lib/ouvidoria/painel";
import { descreverNaturezaInformada } from "@/lib/ouvidoria/natureza-informada";
import { formatarEsperaUtil, type StatusManifestacao } from "@/lib/ouvidoria/prazo";
import type { PedidoDeProrrogacao } from "@/lib/ouvidoria/setor";
import {
  LABEL_GATILHO,
  LABEL_GRAVIDADE,
  LABEL_STATUS_NOTIFICACAO,
  TENTATIVAS_MINIMAS_DE_CONTATO,
  podeEncerrar,
  podePausar,
  podeReabrir,
  podeRetomar,
  podeValidar,
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
  // Lista fechada (issue #372). `null` é o caso ainda não classificado.
  tipo_manifestacao: TipoManifestacao | null;
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
  // De onde o caso chegou. `canal_setor` e `canal_ponto` só valem para o canal
  // aberto e eram gravados sem ninguém ler (issue #375, item 11).
  canal: string | null;
  canal_setor: string | null;
  canal_ponto: string | null;
  // O que o MANIFESTANTE disse que traz (issue #473). É sugestão dele, não a
  // classificação do caso: essa é o `tipo_manifestacao`, acima. `null` é o
  // normal, porque escolher é opcional no formulário público.
  natureza_informada: string | null;
  // Os quatro marcos, os dois prazos e a marca do calendário (issue #480).
  // Opcionais porque são calculados no servidor e chegam prontos: um frontend
  // servido enquanto o backend ainda é o da versão anterior apenas não mostra
  // o bloco, em vez de quebrar a página do caso.
  marcos?: MarcoDoCaso[];
  prazos?: PrazoDoCaso[];
  // O aviso de recebimento ao manifestante (issue #493, RN-56). Opcional pelo
  // mesmo motivo dos marcos, e ao lado deles: é a promessa feita a quem
  // manifestou, e o ouvidor precisa saber se ela foi cumprida sem abrir o
  // registro de notificações.
  acuse?: AcuseDoCaso;
  // O aviso de encerramento ao manifestante (issue #494, RN-80). O par do
  // acuse: um diz que a manifestação chegou, o outro diz no que deu. Opcional
  // pelo mesmo motivo.
  aviso_encerramento?: AvisoDeEncerramento;
  degradado?: string[];
}

/**
 * Um ciclo de resposta da área (issue #374). Vem da trilha imutável, não da
 * coluna do caso: `resposta_da_area` guarda só a resposta corrente, e o portal
 * do setor a sobrescreve inteira a cada resposta nova.
 */
interface CicloDeResposta {
  respondida_em: string | null;
  respondida_por_nome: string | null;
  resposta: string;
}

interface TentativaDeContato {
  id: string;
  tentada_em: string;
  canal: string;
  observacao: string | null;
  autor_nome: string;
}

interface DossieProps {
  /** O endereço público do caso, que é o que vem na URL da página (RN-53). */
  protocolo: string;
  token: string | null;
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
 *
 * Desde a issue #476 o Dossiê é uma PÁGINA, e não um modal sobre a lista: ele
 * é procurado pelo protocolo, que é o endereço público do caso e o que chega
 * no link do email. O modal não tinha URL, e por isso o botão do email de
 * cobrança não tinha para onde apontar.
 */
export function Dossie({ protocolo, token }: DossieProps) {
  const [dossie, setDossie] = useState<Dossie | null>(null);
  // O id só existe depois que o caso chega: quem endereça é o protocolo, e é
  // dele que sai o id que as rotas irmãs (anexos, notificações, trilha) pedem.
  const manifestacaoId = dossie?.id ?? null;
  const [carregando, setCarregando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [anexos, setAnexos] = useState<Anexo[]>([]);
  const [abrindoAnexo, setAbrindoAnexo] = useState<string | null>(null);
  // Erro de anexo é separado do erro de carga: um link que não abriu não pode
  // apagar da tela o relato e a identificação que o ouvidor está lendo.
  const [erroAnexo, setErroAnexo] = useState<string | null>(null);
  // A trilha de cobrança do caso: o que já foi enviado, para quem e quando.
  const [notificacoes, setNotificacoes] = useState<Notificacao[]>([]);
  // A linha do tempo do caso, e a marca de calendário da própria rota dela:
  // ela afirma tempo em dias úteis por conta própria, e a marca do Dossiê não
  // responde por uma leitura que aconteceu em outra requisição.
  const [movimentos, setMovimentos] = useState<EventoDaTrilha[]>([]);
  const [degradadoDaTrilha, setDegradadoDaTrilha] = useState<string[] | null>(null);
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
  const [respostas, setRespostas] = useState<CicloDeResposta[]>([]);
  const [tentativas, setTentativas] = useState<TentativaDeContato[]>([]);
  const [motivoDoManifestante, setMotivoDoManifestante] = useState("");
  const [canalDaTentativa, setCanalDaTentativa] = useState("telefone");
  const [observacaoDaTentativa, setObservacaoDaTentativa] = useState("");
  const [emAcaoDoManifestante, setEmAcaoDoManifestante] = useState(false);
  const [avisoDoManifestante, setAvisoDoManifestante] = useState<string | null>(null);
  // Classificação e sigilo (issue #372). Os dois moram no mesmo bloco porque
  // são o mesmo ato: dizer o que o caso é decide quem pode vê-lo.
  const [tipoEscolhido, setTipoEscolhido] = useState<TipoManifestacao | "">("");
  const [rotuloDoCaso, setRotuloDoCaso] = useState("");
  const [sigiloMarcado, setSigiloMarcado] = useState(false);
  const [classificando, setClassificando] = useState(false);
  const [avisoClassificacao, setAvisoClassificacao] = useState<string | null>(null);
  // As duas ações que a lista oferecia e que passam a viver junto do caso
  // (issue #476). Elas mudam o caso inteiro, então o que vem depois delas é
  // uma leitura nova, e não um remendo no que está na tela.
  const [validando, setValidando] = useState(false);
  const [encerrando, setEncerrando] = useState(false);
  const [recarga, setRecarga] = useState(0);

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

  /**
   * A linha do tempo do caso (issue #485). A trilha é a única leitura da
   * página que pode chegar VAZIA por falha: o servidor responde 503 quando não
   * conseguiu lê-la, e é por isso que a falha zera a lista em vez de deixar na
   * tela os eventos do caso anterior.
   */
  const carregarMovimentos = useCallback(async () => {
    if (!manifestacaoId || !token) return;
    try {
      const res = await fetch(`/api/ouvidoria/manifestacoes/${manifestacaoId}/movimentos`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) {
        setMovimentos([]);
        setDegradadoDaTrilha(null);
        return;
      }
      const corpo = await res.json();
      setMovimentos(corpo.movimentos ?? []);
      setDegradadoDaTrilha(corpo.degradado ?? null);
    } catch {
      setMovimentos([]);
      setDegradadoDaTrilha(null);
    }
  }, [manifestacaoId, token]);

  useEffect(() => {
    setMovimentos([]);
    setDegradadoDaTrilha(null);
    carregarMovimentos();
  }, [carregarMovimentos]);

  /**
   * O que vem depois de validar ou encerrar: o caso é lido de novo pelo
   * protocolo, e a trilha de cobrança junto, porque o acionamento acabou de
   * criar email novo. Sem isso a página seguiria mostrando o estado anterior.
   * A linha do tempo entra na mesma recarga: o ato que acabou de acontecer é
   * justamente o evento que o ouvidor procura no topo dela.
   */
  const recarregarCaso = useCallback(() => {
    setRecarga((n) => n + 1);
    carregarNotificacoes();
    carregarMovimentos();
  }, [carregarNotificacoes, carregarMovimentos]);

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

  const carregarRespostas = useCallback(async () => {
    if (!manifestacaoId || !token) return;
    try {
      const res = await fetch(`/api/ouvidoria/manifestacoes/${manifestacaoId}/respostas`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) setRespostas((await res.json()).respostas);
    } catch {
      setRespostas([]);
    }
  }, [manifestacaoId, token]);

  useEffect(() => {
    setRespostas([]);
    carregarRespostas();
  }, [carregarRespostas]);

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
    if (!protocolo || !token) {
      setDossie(null);
      return;
    }
    let cancelado = false;
    // O caso anterior sai da tela ANTES de o novo ser pedido. Trocar de
    // endereço na mesma aba (dois links de email, o botão avançar) reusa este
    // componente e só troca o protocolo: sem esta limpeza, o cabeçalho, os
    // botões de ação e as listas irmãs continuariam sendo os do caso velho
    // durante a busca, e um clique em "Validar e acionar" dispararia o email
    // para o setor do CASO ERRADO, que é irreversível.
    setDossie(null);
    setCarregando(true);
    setErro(null);
    fetch(`/api/ouvidoria/manifestacoes/por-protocolo/${encodeURIComponent(protocolo)}`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then(async (res) => {
        if (cancelado) return;
        if (res.status === 403) {
          setErro("Seu perfil não permite abrir esta manifestação.");
        } else if (res.status === 404) {
          // Recusa e ausência são mensagens diferentes na tela porque quem
          // chega aqui já passou pelo login: dizer "não encontrada" a quem não
          // pode ver seria mentir para o ouvidor legítimo de um caso que só
          // ele enxerga. Quem separa as duas no servidor é o gate, que corre
          // antes da busca (issue #476).
          setErro("Manifestação não encontrada. Confira o protocolo do link.");
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
  }, [protocolo, token, recarga]);

  // O formulário do bloco de classificação sempre parte do que está gravado:
  // quem abre um caso já classificado vê a escolha atual, não um campo vazio.
  useEffect(() => {
    setTipoEscolhido(dossie?.tipo_manifestacao ?? "");
    setRotuloDoCaso(dossie?.categoria ?? "");
    setSigiloMarcado(Boolean(dossie?.sigilo_reforcado));
  }, [dossie?.id, dossie?.tipo_manifestacao, dossie?.categoria, dossie?.sigilo_reforcado]);

  // O aviso morre com o caso, não com o Dossiê: salvar a classificação troca o
  // Dossiê por um novo, e limpar o aviso ali apagaria a confirmação no mesmo
  // instante em que ela aparece.
  useEffect(() => {
    setAvisoClassificacao(null);
  }, [manifestacaoId]);

  /**
   * Classificar é a porta do sigilo (issue #372), nos dois sentidos: o caso do
   * canal aberto volta ao painel de todos quando o ouvidor diz que é elogio, e
   * o que se revela denúncia sai da vista de quem está fora da Ouvidoria. A
   * rota devolve o Dossiê atualizado, então a tela lê dali.
   */
  async function classificar() {
    if (!manifestacaoId || !token || !tipoEscolhido) return;
    setClassificando(true);
    setAvisoClassificacao(null);
    try {
      const res = await fetch(`/api/ouvidoria/manifestacoes/${manifestacaoId}/classificacao`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
        body: JSON.stringify({
          tipo_manifestacao: tipoEscolhido,
          categoria: rotuloDoCaso.trim() || null,
          sigilo_reforcado: sigiloResultante(tipoEscolhido, sigiloMarcado),
        }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        setAvisoClassificacao(
          typeof body.detail === "string" ? body.detail : "Não foi possível classificar agora. Tente novamente."
        );
        return;
      }
      setDossie(await res.json());
      setAvisoClassificacao("Classificação salva. A mudança está na trilha do caso, com o seu nome.");
    } catch {
      setAvisoClassificacao("Não foi possível classificar agora. Tente novamente.");
    } finally {
      setClassificando(false);
    }
  }

  const identificacao = dossie?.anonimo
    ? "Manifestação anônima"
    : dossie?.manifestante_nome || "Não informado";

  const origem = dossie ? descreverOrigem(dossie) : null;
  const naturezaInformada = dossie ? descreverNaturezaInformada(dossie) : null;
  // Sem o calendário confirmado, nenhum número em dias úteis deste caso vale, e
  // ele sai da tela em vez de sair errado (issue #449, a mesma régua do
  // painel). `null` é a resposta que nem declarou o `degradado`: não saber não
  // é saber que está bom.
  const calendarioConfiavel = calendarioUtilFoiLido(dossie?.degradado ?? null);
  // A trilha lê o calendário na PRÓPRIA requisição dela, e por isso responde
  // pela própria marca: uma leitura pode ter dado certo e a outra não.
  const calendarioDaTrilhaConfiavel = calendarioUtilFoiLido(degradadoDaTrilha);

  return (
    <section className="bg-white rounded-2xl border border-border shadow-premium p-5 md:p-6">
      <header className="flex flex-wrap items-start justify-between gap-3 pb-4 mb-5 border-b border-slate-100">
        <div className="flex items-start gap-3">
          <span className="w-10 h-10 rounded-xl bg-primary/10 text-primary flex items-center justify-center shrink-0">
            <UserRound className="w-5 h-5" />
          </span>
          <div>
            <h1 className="text-xl font-bold text-slate-900">
              Manifestação {dossie?.protocolo ?? protocolo}
            </h1>
            {dossie && (
              <p className="text-sm text-slate-500 mt-0.5">{rotuloDoStatus(dossie.status)}</p>
            )}
          </div>
        </div>

        {/* As ações do caso moram com o caso (issue #476). Elas ficavam só na
            linha da lista, e quem chegasse pelo link do email não as
            alcançava sem voltar para a fila. */}
        {dossie && (
          <div className="flex items-center gap-2">
            {podeValidar(dossie.status) && (
              <button
                onClick={() => setValidando(true)}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold uppercase tracking-wide bg-primary text-white hover:bg-primary/90 transition-colors"
              >
                <Send className="w-3.5 h-3.5" />
                Validar e acionar
              </button>
            )}
            {podeEncerrar(dossie.status) && (
              <button
                onClick={() => setEncerrando(true)}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold uppercase tracking-wide bg-emerald-50 text-emerald-700 border border-emerald-200 hover:bg-emerald-100 transition-colors"
              >
                <CheckCircle2 className="w-3.5 h-3.5" />
                Encerrar
              </button>
            )}
          </div>
        )}
      </header>

      <ValidarModal
        manifestacao={validando ? dossie : null}
        token={token}
        onClose={() => setValidando(false)}
        onAcionada={recarregarCaso}
      />

      <EncerrarModal
        manifestacao={encerrando ? dossie : null}
        token={token}
        onClose={() => setEncerrando(false)}
        onEncerrada={recarregarCaso}
      />

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

          {origem && (
            <div className="flex items-start gap-2 px-4 py-3 rounded-xl bg-slate-50 border border-border text-slate-700 text-sm">
              <MapPin className="w-4 h-4 shrink-0 mt-0.5 text-slate-500" />
              <div>
                <span className="font-medium text-slate-800">{origem.titulo}</span>
                {origem.detalhe && <span className="text-slate-600"> ({origem.detalhe})</span>}
                {origem.aviso && (
                  <span className="block text-xs text-slate-500 mt-0.5">{origem.aviso}</span>
                )}
              </div>
            </div>
          )}

          {/* A natureza que o manifestante marcou no formulário público
              (issue #474). Fica junto da origem, no mesmo padrão de bloco, e
              antes da classificação de propósito: é dica de entrada, e o
              rótulo diz de quem é a palavra para ninguém ler como decisão. */}
          {naturezaInformada && (
            <div className="flex items-start gap-2 px-4 py-3 rounded-xl bg-slate-50 border border-border text-slate-700 text-sm">
              <MessageSquareQuote className="w-4 h-4 shrink-0 mt-0.5 text-slate-500" />
              <div>
                <span className="font-medium text-slate-800">{naturezaInformada.titulo}</span>
                <span className="block text-xs text-slate-500 mt-0.5">{naturezaInformada.aviso}</span>
              </div>
            </div>
          )}

          <dl className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <Linha rotulo="Quem manifestou" valor={identificacao} />
            <Linha rotulo="Contato" valor={dossie.manifestante_contato || "Não informado"} />
            <Linha rotulo="Vínculo" valor={dossie.manifestante_vinculo || "Não informado"} />
            <Linha rotulo="Setor" valor={dossie.setor} />
            <Linha rotulo="Tipo" valor={rotuloDoTipo(dossie.tipo_manifestacao)} />
            <Linha rotulo="Rótulo do caso" valor={dossie.categoria} />
            <Linha
              rotulo="Gravidade"
              valor={
                dossie.gravidade
                  ? LABEL_GRAVIDADE[dossie.gravidade as Gravidade] ?? dossie.gravidade
                  : "Ainda não classificada"
              }
            />
          </dl>

          {/* Os quatro marcos com o tempo decorrido em cada trecho (issue
              #480, RN-55, diagnóstico D-05 e D-10). O prazo da área e a data
              de validação saíram da grade acima e vieram para cá: eram os
              mesmos números, e repeti-los em dois lugares só cria a chance de
              a tela dizer duas coisas.

              Nenhuma conta acontece aqui. O tempo chega em minutos de
              expediente, contado no servidor pelo calendário útil do hospital,
              e a contagem regressiva de cada prazo chega como a mesma frase
              que o painel e o email do setor mostram. */}
          {dossie.marcos && dossie.marcos.length > 0 && (
            <div className="px-4 py-3 rounded-xl bg-slate-50 border border-slate-200 space-y-3">
              <h3 className="flex items-center gap-1.5 text-xs font-semibold text-slate-400 uppercase tracking-wide">
                <CalendarClock className="w-3.5 h-3.5" />
                Marcos do caso
              </h3>

              {avisosDeDegradacao(dossie.degradado ?? []).map((aviso) => (
                <p key={aviso.leitura} className="text-xs text-amber-700">
                  {aviso.texto}
                </p>
              ))}

              <ol className="space-y-2">
                {dossie.marcos.map((marco) => {
                  const trecho = descreverTrecho(marco, calendarioConfiavel);
                  return (
                    <li
                      key={marco.chave}
                      className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-0.5 pb-2 border-b border-slate-200 last:border-0 last:pb-0"
                    >
                      <div className="min-w-0">
                        <span className="text-sm font-medium text-slate-800">{marco.rotulo}</span>
                        <span className="block text-xs text-slate-500">
                          {marco.em ? formatarDataHora(marco.em) : MARCO_PENDENTE}
                        </span>
                        {/* O encerramento que a reabertura por reincidência
                            preservou. Ele não passa por conclusão do ciclo
                            aberto, e também não some da tela: fica dito pelo
                            que é. */}
                        {marco.tramitacao_anterior_em && (
                          <span className="block text-xs text-slate-500">
                            A tramitação anterior foi concluída em{" "}
                            {formatarDataHora(marco.tramitacao_anterior_em)}.
                          </span>
                        )}
                      </div>
                      {trecho && <span className="text-xs text-slate-600">{trecho}</span>}
                    </li>
                  );
                })}
              </ol>

              {/* A promessa feita a quem manifestou (RN-56, ADR 0042). Fica
                  junto dos marcos e fora da lista deles: é um fato do caso ao
                  lado da linha do tempo, não um degrau dela. */}
              {dossie.acuse && (
                <div className="pt-3 border-t border-slate-200">
                  <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-0.5">
                    <span className="text-sm font-medium text-slate-800">{dossie.acuse.rotulo}</span>
                    <span
                      className={`text-xs ${
                        dossie.acuse.situacao === "falha_no_envio"
                          ? "text-red-600 font-semibold"
                          : "text-slate-600"
                      }`}
                    >
                      {SITUACAO_DO_ACUSE[dossie.acuse.situacao]}
                      {dossie.acuse.em ? `, ${formatarDataHora(dossie.acuse.em)}` : ""}
                    </span>
                  </div>
                  {dossie.acuse.nota && (
                    <p className="text-xs text-slate-500 mt-0.5">{dossie.acuse.nota}</p>
                  )}
                </div>
              )}

              {/* A outra ponta da promessa (RN-80, ADR 0042): encerrar no
                  sistema é encerrar para o paciente. Fica logo abaixo do acuse
                  porque as duas contam a mesma história, do "chegou" ao "no que
                  deu". A frase sai do STATUS da notificação, nunca do carimbo:
                  o carimbo diz que o aviso foi gerado. */}
              {dossie.aviso_encerramento && (
                <div className="pt-3 border-t border-slate-200">
                  <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-0.5">
                    <span className="text-sm font-medium text-slate-800">
                      {dossie.aviso_encerramento.rotulo}
                    </span>
                    <span
                      className={`text-xs ${
                        dossie.aviso_encerramento.situacao === "falha_no_envio"
                          ? "text-red-600 font-semibold"
                          : "text-slate-600"
                      }`}
                    >
                      {SITUACAO_DO_AVISO_DE_ENCERRAMENTO[dossie.aviso_encerramento.situacao]}
                      {dossie.aviso_encerramento.em
                        ? `, ${formatarDataHora(dossie.aviso_encerramento.em)}`
                        : ""}
                    </span>
                  </div>
                  {dossie.aviso_encerramento.nota && (
                    <p className="text-xs text-slate-500 mt-0.5">{dossie.aviso_encerramento.nota}</p>
                  )}
                </div>
              )}

              {prazosVisiveis(dossie.prazos ?? []).length > 0 && (
                <div className="pt-3 border-t border-slate-200 space-y-2">
                  {prazosVisiveis(dossie.prazos ?? []).map((prazo) => (
                    <div key={prazo.chave}>
                      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-0.5">
                        <span className="text-sm font-medium text-slate-800">{prazo.rotulo}</span>
                        <span
                          className={`text-xs ${prazo.estourado ? "text-red-600 font-semibold" : "text-slate-600"}`}
                        >
                          {prazo.em
                            ? `${formatarDataHora(prazo.em)}, ${descreverPrazo(prazo, calendarioConfiavel)}`
                            : descreverPrazo(prazo, calendarioConfiavel)}
                        </span>
                      </div>
                      {/* Por que o relógio do manifestante está onde está. A
                          nota vem do servidor porque é ele que sabe o que
                          moveu (ou não moveu) cada vencimento. */}
                      {prazo.nota && (
                        <p className="text-xs text-slate-500 mt-0.5">{prazo.nota}</p>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Classificação e sigilo (issue #372). É a única porta que sobe e
              desce o sigilo fora da validação: o caso que chegou pelo canal
              aberto ou pela Ana nasce sem tipo, logo sigiloso, e é aqui que ele
              volta ao painel de todos. */}
          <div className="px-4 py-3 rounded-xl bg-slate-50 border border-slate-200 space-y-2.5">
            <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wide">
              Classificação e sigilo
            </h3>
            <select
              value={tipoEscolhido}
              onChange={(e) => setTipoEscolhido(e.target.value as TipoManifestacao)}
              className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-800 focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary"
            >
              <option value="">Escolha o tipo</option>
              {TIPOS_MANIFESTACAO.map((valor) => (
                <option key={valor} value={valor}>
                  {LABEL_TIPO[valor]}
                </option>
              ))}
            </select>
            <input
              value={rotuloDoCaso}
              onChange={(e) => setRotuloDoCaso(e.target.value)}
              placeholder="Rótulo do caso (opcional). Ex.: conduta da equipe noturna"
              className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-800 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary"
            />
            <label className="flex items-start gap-2 text-sm text-slate-700">
              <input
                type="checkbox"
                className="mt-0.5"
                checked={tipoEscolhido ? sigiloResultante(tipoEscolhido, sigiloMarcado) : sigiloMarcado}
                disabled={tipoEscolhido !== "" && ehSigilosoPorNatureza(tipoEscolhido)}
                onChange={(e) => setSigiloMarcado(e.target.checked)}
              />
              <span>
                <span className="font-semibold">Sigilo reforçado</span>
                <span className="block text-xs text-slate-500 mt-0.5">
                  {tipoEscolhido !== "" && ehSigilosoPorNatureza(tipoEscolhido)
                    ? "Este tipo é sigiloso por natureza e o sigilo não pode ser retirado."
                    : "Marque para restringir o caso ao Ouvidor e à Diretoria Executiva. Desmarque para devolver o caso ao painel de todos."}
                </span>
              </span>
            </label>
            <button
              onClick={classificar}
              disabled={classificando || !tipoEscolhido}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold uppercase tracking-wide bg-primary text-white hover:bg-primary/90 disabled:opacity-50 transition-colors"
            >
              {classificando && <Loader2 className="w-3 h-3 animate-spin" />}
              Salvar classificação
            </button>
            {avisoClassificacao && <p className="text-xs text-slate-500">{avisoClassificacao}</p>}
          </div>

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
                    {pedido.aprovacao_possivel === false && pedido.motivo_da_aprovacao && (
                      <p className="flex items-start gap-1.5 rounded-lg bg-amber-50 border border-amber-200 px-3 py-2 text-xs text-amber-800">
                        <AlertCircle className="w-3.5 h-3.5 shrink-0 mt-0.5" />
                        <span>{pedido.motivo_da_aprovacao}</span>
                      </p>
                    )}
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
                        disabled={decidindo || pedido.aprovacao_possivel === false}
                        className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold uppercase tracking-wide bg-emerald-600 text-white hover:bg-emerald-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                      >
                        {decidindo && <Loader2 className="w-3 h-3 animate-spin" />}
                        Aprovar
                      </button>
                      <button
                        onClick={() => decidirProrrogacao(pedido, false)}
                        disabled={decidindo}
                        className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold uppercase tracking-wide bg-white border border-slate-200 text-slate-600 hover:bg-slate-100 disabled:opacity-50 transition-colors"
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
                      className="ml-auto inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs font-semibold uppercase tracking-wide bg-white border border-slate-200 text-slate-600 hover:bg-slate-100 disabled:opacity-50 transition-colors"
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
                  {/* Estes dois botões da pausa ficam em caixa mista, e os
                      vizinhos não (issue #489, RN-76): o rótulo deles é frase,
                      não rótulo curto, e frase em maiúscula é o que a regra
                      existe para impedir. Encurtá-los custaria a clareza de
                      quem decide parar o relógio de um caso. */}
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
                        className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold uppercase tracking-wide bg-white border border-slate-200 text-slate-600 hover:bg-slate-100 disabled:opacity-50 transition-colors"
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
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold uppercase tracking-wide bg-purple-600 text-white hover:bg-purple-700 disabled:opacity-50 transition-colors"
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
                {/* O crédito sai da caixa alta do título (issue #489, RN-76):
                    nome próprio e data em maiúscula gritam e ficam mais
                    difíceis de ler que o rótulo que eles acompanham. */}
                <span className="normal-case">
                  {creditoDaResposta(dossie.respondida_por_nome, dossie.respondida_em)}
                </span>
              </h3>
              <p className="text-sm text-slate-700 whitespace-pre-line">{dossie.resposta_da_area}</p>

              {/*
                Os ciclos anteriores, quando o ouvidor já devolveu uma resposta
                e o setor respondeu de novo (issue #374). A última entrada da
                lista é a resposta corrente, já mostrada acima: repeti-la aqui
                faria o Dossiê contar um ciclo a mais do que houve.
              */}
              {respostas.length > 1 && (
                <div className="mt-3 pt-2.5 border-t border-slate-200">
                  <h4 className="text-xs font-semibold text-slate-400 uppercase tracking-wide mb-1.5">
                    Respostas anteriores ({respostas.length - 1})
                  </h4>
                  <ul className="space-y-2">
                    {respostas.slice(0, -1).map((ciclo, indice) => (
                      <li key={`${ciclo.respondida_em ?? indice}`} className="text-xs">
                        <p className="text-slate-500">
                          {indice + 1}ª resposta
                          {creditoDaResposta(ciclo.respondida_por_nome, ciclo.respondida_em)}
                        </p>
                        <p className="text-slate-600 whitespace-pre-line">{ciclo.resposta}</p>
                      </li>
                    ))}
                  </ul>
                  <p className="mt-1.5 text-xs text-slate-400 leading-relaxed">
                    Ciclos anteriores do caso: resposta devolvida por insuficiência, ou resposta de uma
                    tramitação encerrada antes de uma reabertura. O texto vem da trilha, que não muda.
                  </p>
                </div>
              )}

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
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold uppercase tracking-wide bg-amber-600 text-white hover:bg-amber-700 disabled:opacity-50 transition-colors"
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
                <span className="normal-case">
                  {dossie.encerrada_em
                    ? ` (encerrada em ${formatarDataHora(dossie.encerrada_em)})`
                    : ""}
                </span>
              </h3>
              <p className="text-sm text-slate-700 whitespace-pre-line">
                {dossie.desfecho_descricao || dossie.desfecho}
              </p>
            </div>
          )}

          {/* A linha do tempo do caso (issue #485, RN-63 a RN-65). Vem por
              último de propósito: o topo da página responde "como está o caso
              agora", e esta seção responde "como ele chegou aqui". Ordem
              decrescente, para o ato mais novo estar na primeira linha. */}
          {movimentos.length > 0 && (
            <div>
              <h3 className="flex items-center gap-1.5 text-xs font-semibold text-slate-400 uppercase tracking-wide mb-2">
                <History className="w-3.5 h-3.5" />
                Linha do tempo
              </h3>

              {avisosDeDegradacao(degradadoDaTrilha ?? []).map((aviso) => (
                <p key={aviso.leitura} className="text-xs text-amber-700 mb-2">
                  {aviso.texto}
                </p>
              ))}

              {/* O nome da lista é o que dá à linha do tempo uma fronteira
                  própria: leitor de tela anuncia de que lista se trata, e o
                  teste consegue perguntar o que está DENTRO dela, em vez de
                  procurar a frase na página inteira e casar com o bloco da
                  resposta corrente, que diz o mesmo texto logo acima. */}
              <ol
                aria-label="Linha do tempo do caso"
                className="relative border-l border-slate-200 ml-1.5 space-y-4"
              >
                {movimentos.map((evento, indice) => {
                  const tempo = descreverTempoDesdeOMarco(evento, calendarioDaTrilhaConfiavel);
                  return (
                    <li key={`${evento.ocorrido_em}-${indice}`} className="relative pl-4">
                      {/* O marcador cheio é dos quatro marcos do caso, que são
                          as viradas que o ouvidor procura. O resto acontece
                          dentro de um trecho e não disputa o olho com eles. */}
                      <span
                        aria-hidden="true"
                        className={`absolute -left-[4.5px] top-1.5 w-2 h-2 rounded-full ${
                          evento.marco ? "bg-blue-600" : "bg-slate-300"
                        }`}
                      />
                      <p className="text-xs text-slate-500">
                        {formatarDataHora(evento.ocorrido_em)}, {evento.autor}
                      </p>
                      <p className="text-sm text-slate-800">{evento.descricao}</p>
                      {tempo && <p className="text-xs text-slate-500">{tempo}</p>}
                      {evento.texto && (
                        <p className="mt-1 text-sm text-slate-600 whitespace-pre-line">{evento.texto}</p>
                      )}
                    </li>
                  );
                })}
              </ol>
            </div>
          )}
        </div>
      ) : null}
    </section>
  );
}

export default Dossie;
