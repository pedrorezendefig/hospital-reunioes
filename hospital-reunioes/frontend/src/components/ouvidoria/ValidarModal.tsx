"use client";

import { useEffect, useState } from "react";
import { AlertCircle, CheckCircle2, Loader2, Send, ShieldAlert } from "lucide-react";
import { AdminModal } from "@/components/admin/AdminModal";
import {
  ehSigilosoPorNatureza,
  LABEL_TIPO,
  TIPOS_MANIFESTACAO,
  type TipoManifestacao,
} from "@/lib/ouvidoria/taxonomia";
import {
  AJUDA_GRAVIDADE,
  CLASSE_GRAVIDADE,
  GRAVIDADES,
  LABEL_GRAVIDADE,
  setorPreSelecionado,
  setorTemTitularVigente,
  type Gravidade,
  type Responsavel,
} from "@/lib/ouvidoria/validacao";

interface ValidarModalProps {
  manifestacao: {
    id: string;
    protocolo: string;
    tipo_manifestacao: TipoManifestacao | null;
    categoria: string;
    setor: string;
    // Obrigatório de propósito: com o campo opcional, um índice que não o
    // devolvesse deixaria a marca desligada num caso protegido, e a validação
    // mandaria `sigilo_reforcado: false`, retirando o sigilo sem ninguém
    // desmarcar nada (issue #372).
    sigilo_reforcado: boolean;
    // O que sobrou do acionamento anterior no caso (issue #601). Opcionais
    // porque a linha da fila abre esta mesma tela e não carrega o extrato: o
    // campo simplesmente nasce em branco, como sempre nasceu.
    gravidade?: string | null;
    extrato_para_o_setor?: string | null;
  } | null;
  token: string | null;
  /**
   * A área que devolveu o caso à Ouvidoria, quando foi isso que aconteceu
   * (issue #601). Nulo no acionamento comum.
   *
   * Vem de fora, e não do `setor` do caso, porque as duas coisas são
   * diferentes: `setor` é a área gravada agora (e continua sendo a errada até o
   * ouvidor trocar), enquanto esta é a área que DEVOLVEU, lida da trilha. Num
   * pingue-pongue elas divergem.
   */
  devolvidaPelaArea?: string | null;
  onClose: () => void;
  onAcionada: () => void;
}

const CAMPO =
  "w-full px-3 py-2 rounded-lg border border-slate-200 text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary/40";
const ROTULO = "block text-xs font-semibold text-slate-500 uppercase tracking-wide mb-1";

/**
 * A gravidade gravada no caso, quando ela é uma das quatro que a tela oferece.
 *
 * A poda existe pelo mesmo motivo da poda do setor: valor que a lista não tem
 * deixaria o campo aparentemente vazio com um valor por dentro, e o ouvidor
 * levaria um erro num campo que a tela mostra em branco.
 */
function gravidadeConhecida(gravidade: string | null | undefined): Gravidade | "" {
  return GRAVIDADES.includes(gravidade as Gravidade) ? (gravidade as Gravidade) : "";
}

function hojeLocal(): string {
  const agora = new Date();
  const mes = String(agora.getMonth() + 1).padStart(2, "0");
  const dia = String(agora.getDate()).padStart(2, "0");
  return `${agora.getFullYear()}-${mes}-${dia}`;
}

/**
 * Validar e acionar (issue #325, ADR 0034 decisão 3).
 *
 * O único caminho do despacho: o ouvidor confere tipo, área e gravidade,
 * escreve o extrato que o setor vai ler, e a área é acionada por email no mesmo
 * ato. A tela avisa antes quando o setor escolhido está sem titular vigente,
 * porque aí a demanda sobe ao gestor e a Diretoria recebe alerta: melhor o
 * ouvidor saber disso antes de clicar.
 */
export function ValidarModal({
  manifestacao,
  token,
  devolvidaPelaArea = null,
  onClose,
  onAcionada,
}: ValidarModalProps) {
  const [tipo, setTipo] = useState<TipoManifestacao | "">("");
  const [categoria, setCategoria] = useState("");
  const [sigilo, setSigilo] = useState(false);
  const [setor, setSetor] = useState("");
  const [gravidade, setGravidade] = useState<Gravidade | "">("");
  const [extrato, setExtrato] = useState("");
  const [observacao, setObservacao] = useState("");
  const [setores, setSetores] = useState<string[]>([]);
  const [responsaveis, setResponsaveis] = useState<Responsavel[]>([]);
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    if (!manifestacao) return;
    setTipo(manifestacao.tipo_manifestacao ?? "");
    setCategoria(manifestacao.categoria || "");
    setSigilo(Boolean(manifestacao.sigilo_reforcado));
    setSetor(manifestacao.setor || "");
    // Gravidade e extrato vêm do que JÁ está gravado no caso (issue #601). No
    // primeiro despacho as duas colunas são nulas e os campos nascem em branco,
    // como sempre nasceram: o extrato não é preenchido com o resumo, porque
    // isso levaria o ouvidor a mandar ao setor a palavra crua de quem
    // manifestou. No reacionamento do caso devolvido à Ouvidoria elas trazem a
    // decisão anterior, e o ouvidor só troca a área e confirma.
    setGravidade(gravidadeConhecida(manifestacao.gravidade));
    setExtrato(manifestacao.extrato_para_o_setor || "");
    setObservacao("");
    setErro(null);
  }, [manifestacao]);

  // A taxonomia chega depois do reset acima, então a poda é aqui: caso do
  // canal aberto vem com o marcador "A definir", e acionar assim é 422
  // (issue #419). Quem escolhe a área é o ouvidor.
  useEffect(() => {
    setSetor((atual) => setorPreSelecionado(atual, setores));
  }, [setores]);

  useEffect(() => {
    if (!manifestacao || !token) return;
    let cancelado = false;
    const headers = { Authorization: `Bearer ${token}` };
    Promise.all([
      fetch("/api/participantes/setores", { headers }).then((r) => (r.ok ? r.json() : [])),
      fetch("/api/ouvidoria/responsaveis", { headers }).then((r) =>
        r.ok ? r.json() : { responsaveis: [] }
      ),
    ])
      .then(([lista, cadastro]) => {
        if (cancelado) return;
        setSetores(Array.isArray(lista) ? lista : []);
        setResponsaveis(cadastro.responsaveis ?? []);
      })
      .catch(() => {
        if (!cancelado) setSetores([]);
      });
    return () => {
      cancelado = true;
    };
  }, [manifestacao, token]);

  const doSetor = responsaveis.filter((r) => r.setor === setor);
  const semTitular = Boolean(setor) && !setorTemTitularVigente(doSetor, hojeLocal());
  const semNinguem = Boolean(setor) && doSetor.length === 0;
  // O tipo sigiloso por natureza trava a marca ligada: a regra automática é
  // piso, e a tela não pode oferecer um caminho que o backend recusa com 409.
  const sigiloTravado = tipo !== "" && ehSigilosoPorNatureza(tipo);
  const sigiloFinal = sigiloTravado || sigilo;
  const pronto = Boolean(tipo && setor.trim() && gravidade && extrato.trim()) && !salvando;
  // A tela se apresenta pelo ato que o ouvidor clicou (issue #601): quem veio
  // do botão "Encaminhar para outra área" precisa reconhecer onde chegou.
  const titulo = manifestacao
    ? devolvidaPelaArea
      ? `Encaminhar ${manifestacao.protocolo} para outra área`
      : `Validar e acionar ${manifestacao.protocolo}`
    : devolvidaPelaArea
      ? "Encaminhar para outra área"
      : "Validar e acionar";

  async function acionar() {
    if (!manifestacao || !token || !gravidade || !tipo) return;
    setSalvando(true);
    setErro(null);
    try {
      const res = await fetch(`/api/ouvidoria/manifestacoes/${manifestacao.id}/validar`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
        body: JSON.stringify({
          tipo_manifestacao: tipo,
          categoria: categoria.trim() || null,
          sigilo_reforcado: sigiloFinal,
          setor: setor.trim(),
          gravidade,
          extrato_para_o_setor: extrato.trim(),
          observacao: observacao.trim() || null,
        }),
      });
      if (res.ok) {
        onAcionada();
        onClose();
        return;
      }
      const corpo = await res.json().catch(() => ({}));
      setErro(corpo.detail || "Não foi possível acionar a área. Tente novamente.");
    } catch {
      setErro("Não foi possível acionar a área. Tente novamente.");
    } finally {
      setSalvando(false);
    }
  }

  return (
    <AdminModal
      open={Boolean(manifestacao)}
      onClose={onClose}
      title={titulo}
      description="O setor recebe o email de acionamento com o prazo assim que você confirmar."
      icon={<Send className="w-5 h-5" />}
      size="lg"
      scrollable
    >
      <div className="space-y-5">
        <div>
          <label className={ROTULO} htmlFor="validar-tipo">
            Tipo da manifestação
          </label>
          <select
            id="validar-tipo"
            className={CAMPO}
            value={tipo}
            onChange={(e) => setTipo(e.target.value as TipoManifestacao)}
          >
            <option value="">Escolha o tipo</option>
            {TIPOS_MANIFESTACAO.map((valor) => (
              <option key={valor} value={valor}>
                {LABEL_TIPO[valor]}
              </option>
            ))}
          </select>
          <p className="mt-1.5 text-xs text-slate-500 leading-relaxed">
            Denúncia e relato de conduta são sigilosos por natureza: o caso sai do painel de quem
            está fora da Ouvidoria e o email do setor vai sem a identificação de quem manifestou.
          </p>
        </div>

        <div>
          <label className={ROTULO} htmlFor="validar-categoria">
            Rótulo do caso <span className="normal-case">(opcional)</span>
          </label>
          <input
            id="validar-categoria"
            className={CAMPO}
            value={categoria}
            onChange={(e) => setCategoria(e.target.value)}
            placeholder="Ex.: demora no atendimento, conduta da equipe noturna"
          />
        </div>

        <div className="px-4 py-3 rounded-xl bg-slate-50 border border-slate-200">
          <label className="flex items-start gap-2 text-sm text-slate-700">
            <input
              type="checkbox"
              className="mt-0.5"
              checked={sigiloFinal}
              disabled={sigiloTravado}
              onChange={(e) => setSigilo(e.target.checked)}
            />
            <span>
              <span className="font-semibold">Sigilo reforçado</span>
              <span className="block text-xs text-slate-500 mt-0.5">
                {sigiloTravado
                  ? "Este tipo é sigiloso por natureza e o sigilo não pode ser retirado."
                  : "Marque para restringir o caso ao Ouvidor e à Diretoria Executiva. Desmarque para devolver o caso ao painel de todos."}
              </span>
            </span>
          </label>
        </div>

        <div>
          <label className={ROTULO} htmlFor="validar-setor">
            Área responsável
          </label>
          <select
            id="validar-setor"
            className={CAMPO}
            value={setor}
            onChange={(e) => setSetor(e.target.value)}
          >
            <option value="">Escolha o setor</option>
            {setores.map((nome) => (
              <option key={nome} value={nome}>
                {nome}
              </option>
            ))}
            {/* Enquanto a lista não chega (fetch em voo, ou que falhou), o
                estado guarda a área gravada e o seletor precisa ter a opção
                dela: sem isto o campo apareceria em branco com valor por
                dentro, e o ouvidor levaria um erro num campo que a tela mostra
                vazio. Quando a lista chega, `setorPreSelecionado` já podou o
                que não existe, e esta opção some. */}
            {setores.length === 0 && setor && <option value={setor}>{setor}</option>}
          </select>
          {devolvidaPelaArea && (
            <p className="mt-1.5 text-xs text-slate-500 leading-relaxed">
              {devolvidaPelaArea} devolveu este caso à Ouvidoria. Escolha a área certa. Confirmar sem
              trocar também vale, se você tem certeza de que a área estava certa.
            </p>
          )}
        </div>

        {semNinguem ? (
          <div className="flex items-start gap-2 px-4 py-3 rounded-xl bg-red-50 border border-red-200 text-red-700 text-sm">
            <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
            <span>
              Este setor não tem titular nem gestor cadastrado. Peça à Diretoria Executiva para
              cadastrar o responsável antes de acionar.
            </span>
          </div>
        ) : semTitular ? (
          <div className="flex items-start gap-2 px-4 py-3 rounded-xl bg-amber-50 border border-amber-200 text-amber-800 text-sm">
            <ShieldAlert className="w-4 h-4 shrink-0 mt-0.5" />
            <span>
              Setor sem titular vigente. A demanda vai subir ao gestor da área e a Diretoria
              Executiva recebe o alerta.
            </span>
          </div>
        ) : null}

        <div>
          <span className={ROTULO}>Gravidade</span>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            {GRAVIDADES.map((nivel) => (
              <button
                key={nivel}
                type="button"
                // O botão é um seletor, e o estado precisa chegar a quem lê a
                // tela por leitor de tela: sem isto, a escolha vive só na cor.
                aria-pressed={gravidade === nivel}
                onClick={() => setGravidade(nivel)}
                className={`text-left px-3 py-2.5 rounded-xl border transition-colors ${
                  gravidade === nivel
                    ? CLASSE_GRAVIDADE[nivel]
                    : "bg-white border-slate-200 hover:bg-slate-50"
                }`}
              >
                <span className="block text-sm font-semibold">{LABEL_GRAVIDADE[nivel]}</span>
                <span className="block text-xs mt-0.5 opacity-80">{AJUDA_GRAVIDADE[nivel]}</span>
              </button>
            ))}
          </div>
        </div>

        <div>
          <label className={ROTULO} htmlFor="validar-extrato">
            Extrato para o setor <span className="normal-case">(obrigatório)</span>
          </label>
          <textarea
            id="validar-extrato"
            className={`${CAMPO} min-h-[90px]`}
            value={extrato}
            onChange={(e) => setExtrato(e.target.value)}
            placeholder="Ex.: Conduta da equipe de enfermagem no plantão noturno. Apurar e responder à Ouvidoria."
          />
          <p className="mt-1.5 text-xs text-slate-500 leading-relaxed">
            É este texto que vai no email do responsável, e só ele. Escreva com as suas palavras o
            que a área precisa resolver: o responsável do setor é de fora da Ouvidoria, e o relato
            de quem manifestou não sai daqui. Sem este texto o acionamento não sai.
          </p>
        </div>

        <div>
          <label className={ROTULO} htmlFor="validar-observacao">
            Observação da validação <span className="normal-case">(opcional)</span>
          </label>
          <textarea
            id="validar-observacao"
            className={`${CAMPO} min-h-[70px]`}
            value={observacao}
            onChange={(e) => setObservacao(e.target.value)}
            placeholder="Fica na trilha do caso, junto do movimento de acionamento."
          />
        </div>

        {erro && (
          <div className="flex items-start gap-2 px-4 py-3 rounded-xl bg-red-50 border border-red-200 text-red-700 text-sm">
            <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
            {erro}
          </div>
        )}

        <div className="flex items-center justify-end gap-2 pt-1">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 rounded-lg text-sm font-medium uppercase tracking-wide text-slate-600 hover:bg-slate-100 transition-colors"
          >
            Cancelar
          </button>
          <button
            type="button"
            onClick={acionar}
            disabled={!pronto}
            className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-semibold uppercase tracking-wide bg-primary text-white hover:bg-primary/90 disabled:opacity-50 transition-colors"
          >
            {salvando ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <CheckCircle2 className="w-4 h-4" />
            )}
            Validar e acionar a área
          </button>
        </div>
      </div>
    </AdminModal>
  );
}

export default ValidarModal;
