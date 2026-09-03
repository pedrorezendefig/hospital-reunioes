"use client";

import { useEffect, useState } from "react";
import { createClient } from "@/lib/supabase/client";
import { AlertCircle, CheckCircle2, Loader2, Lock, Megaphone, Plus } from "lucide-react";
import { useCurrentParticipante } from "@/hooks/useCurrentParticipante";
import { AtalhosDaOuvidoria } from "@/components/ouvidoria/AtalhosDaOuvidoria";
import { NovaManifestacaoModal } from "@/components/ouvidoria/NovaManifestacaoModal";
import { ValidarModal } from "@/components/ouvidoria/ValidarModal";
import { ListaDaFila } from "@/components/ouvidoria/ListaDaFila";
import {
  aguardandoSeuEncerramento,
  agruparPorStatus,
  classeDoStatus,
  rotuloDoStatus,
  TITULO_AGUARDANDO_ENCERRAMENTO,
  type ManifestacaoIndice,
} from "@/lib/ouvidoria/fila";
import { avisosDeDegradacao, hojeNoHospital } from "@/lib/ouvidoria/painel";
import { decidirCobranca, type ResultadoDaCobranca } from "@/lib/ouvidoria/cobranca";
import { classificarPrazoDaManifestacao, EM_ANDAMENTO } from "@/lib/ouvidoria/prazo";
import { ALTURA_DE_TOQUE } from "@/lib/toque";
import { EncerrarModal } from "@/components/ouvidoria/EncerrarModal";
import { responsavelDoSetor, type Responsavel } from "@/lib/ouvidoria/validacao";

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
  // Quem responde por cada setor, para a linha escrever um nome ao lado da
  // área (issue #495, RN-72). Cadastro pequeno e estável, lido uma vez por
  // carga da tela em vez de por caso.
  // `null` é "ainda não li", e não "não tem ninguém": quem está fora da
  // Ouvidoria nunca lê este cadastro, e afirmar ausência a partir do silêncio
  // faria toda linha da fila mentir sobre o setor (issue #449, mesma régua).
  const [responsaveis, setResponsaveis] = useState<Responsavel[] | null>(null);
  // O que cada cobrança em voo está fazendo, por manifestação. Fica na tela, e
  // não na linha, porque o clique dispara duas chamadas e a resposta precisa
  // sobreviver a um rerender da lista.
  const [cobrancas, setCobrancas] = useState<Record<string, ResultadoDaCobranca>>({});

  const { participante } = useCurrentParticipante();
  const podeAbrirDossie = Boolean(participante?.perfil_ouvidoria);

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
        // O dia é relido a cada carga, como no painel: fila aberta na virada da
        // meia-noite continuaria chamando de "vence hoje" o que venceu ontem, e
        // deixando em âmbar o que passou a vencer hoje (issue #488).
        setHoje(hojeNoHospital());
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
    // O dia civil do HOSPITAL, e não o do navegador, só após montar: evita
    // divergência de hidratação no destaque de prazo. O fuso importa desde que
    // o semáforo passou a comparar dias (issue #488): num navegador em outro
    // fuso, "vence hoje" viraria "vence amanhã" na virada da noite, e a fila
    // diria o contrário do painel sobre o mesmo caso. Quem manda no semáforo é a
    // releitura do `recarregar`: sem linha na tela não há cor para pintar, e
    // esta chamada existe para espelhar o painel, não para cobrir um caso.
    setHoje(hojeNoHospital());

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

  // O cadastro de responsáveis só é lido por quem tem o Perfil da Ouvidoria: a
  // rota o exige, e pedir sem ele renderia um 403 por carga sem nada na tela
  // para mostrar. Quem está fora da Ouvidoria também chega nesta tela (o índice
  // é da equipe de Reuniões inteira), e para ele o cadastro segue `null`: a
  // linha então não escreve nome nenhum, em vez de afirmar "Sem responsável"
  // sobre um cadastro que ela nunca leu.
  //
  // Falha de leitura não derruba a fila e também não vira afirmação: entra no
  // mesmo `degradado` do calendário e da trilha (issue #449), que já tem a
  // frase pronta para a leitura `responsaveis`.
  useEffect(() => {
    if (!token || !podeAbrirDossie) return;
    let vivo = true;
    (async () => {
      const degradar = () =>
        setDegradado((antes) => (antes.includes("responsaveis") ? antes : [...antes, "responsaveis"]));
      try {
        const res = await fetch("/api/ouvidoria/responsaveis", {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (!res.ok) {
          if (vivo) degradar();
          return;
        }
        const corpo = await res.json();
        if (vivo) setResponsaveis(corpo.responsaveis ?? []);
      } catch (e) {
        console.error("Erro ao carregar responsáveis:", e);
        if (vivo) degradar();
      }
    })();
    return () => {
      vivo = false;
    };
  }, [token, podeAbrirDossie]);

  /**
   * Cobrar o setor (issue #495, RN-74): o reenvio do acionamento, que antes
   * exigia abrir o Dossiê e achar o registro certo na lista de notificações.
   *
   * A regra é a vigente (ADR 0034, decisão 7): o reenvio nasce como registro
   * próprio, e a data do primeiro envio continua sendo a que prova quando a
   * cobrança começou. Quem decide se ela pode sair é `decidirCobranca`, porque
   * o reenvio despacha o relato integral e um token novo do portal para o
   * destinatário do acionamento ORIGINAL, e a linha mostra o responsável de
   * hoje: quando os dois não são a mesma pessoa, o clique de um botão viraria
   * acesso novo ao caso para quem saiu do setor.
   *
   * A fila não recarrega: cobrar não muda o estado do caso, e uma recarga aqui
   * embaralharia a lista debaixo do cursor do ouvidor.
   */
  async function cobrar(m: ManifestacaoIndice) {
    if (!token) return;
    const cabecalho = { Authorization: `Bearer ${token}` };
    const anotar = (resultado: ResultadoDaCobranca) =>
      setCobrancas((antes) => ({ ...antes, [m.id]: resultado }));
    anotar({ fase: "enviando" });
    try {
      const res = await fetch(`/api/ouvidoria/manifestacoes/${m.id}/notificacoes`, {
        headers: cabecalho,
      });
      if (!res.ok) {
        anotar({ fase: "falha" });
        return;
      }
      const corpo = await res.json();
      const vigente = responsaveis && hoje ? responsavelDoSetor(responsaveis, m.setor, hoje) : null;
      const veredito = decidirCobranca(corpo.notificacoes ?? [], vigente, responsaveis !== null);
      if (!veredito.pode) {
        anotar({ fase: "recusada", motivo: veredito.motivo, destinatario: veredito.destinatario });
        return;
      }
      const envio = await fetch(
        `/api/ouvidoria/manifestacoes/${m.id}/notificacoes/${veredito.notificacaoId}/reenviar`,
        { method: "POST", headers: cabecalho }
      );
      if (!envio.ok) {
        anotar({ fase: "falha" });
        return;
      }
      // `entregue` é o que a rota afirma sobre o provedor. Sem ele, um email
      // recusado na hora sairia da tela como cobrança feita.
      const resposta = await envio.json();
      anotar({
        fase: "reenviada",
        destinatario: veredito.destinatario,
        entregue: Boolean(resposta?.entregue),
      });
    } catch (e) {
      console.error("Erro ao cobrar o setor:", e);
      anotar({ fase: "falha" });
    }
  }

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
          <div className="flex flex-wrap items-center gap-2">
            {/* As portas das outras telas da Ouvidoria, com o gate de perfil de
                cada uma (issue #496, RN-77). O gate de verdade é sempre o
                backend, que recusa a tela a quem não pode; aqui só não se
                oferece o caminho que terminaria em 403. */}
            <AtalhosDaOuvidoria perfil={participante?.perfil_ouvidoria} />
            {/* O volume do dia. Ficava na mesma caixa dos atalhos e o olho o
                lia como mais uma porta, num topo que já quebrava em três
                linhas (issue #496, D-16). Informação e navegação são coisas
                diferentes, e agora moram em caixas diferentes. */}
            <div className="flex items-center gap-2">
              <span className="inline-flex items-center px-3 py-1.5 rounded-full text-sm font-medium whitespace-nowrap bg-sky-100 text-sky-700">
                {emAndamento} em andamento
              </span>
              {estourados > 0 && (
                <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-sm font-medium whitespace-nowrap bg-red-100 text-red-700">
                  <AlertCircle className="w-4 h-4 shrink-0" />
                  {estourados} com prazo estourado
                </span>
              )}
            </div>
            {/* Registrar é ato da Ouvidoria: o gate de verdade é o backend
                (403), a tela só não oferece o caminho a quem não pode. */}
            {podeAbrirDossie && (
              <button
                onClick={() => setRegistrando(true)}
                className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-semibold uppercase tracking-wide whitespace-nowrap bg-primary text-white hover:bg-primary/90 transition-colors ${ALTURA_DE_TOQUE}`}
              >
                <Plus className="w-4 h-4 shrink-0" />
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
          <ListaDaFila
            itens={aguardandoEncerramento}
            hoje={hoje}
            responsaveis={responsaveis}
            podeAbrirDossie={podeAbrirDossie}
            cobrancas={cobrancas}
            onValidar={setValidando}
            onEncerrar={setEncerrando}
            onCobrar={cobrar}
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
              <section key={grupo.status} aria-label={rotuloDoStatus(grupo.status)}>
                {/* A faixa do grupo (issue #495, RN-70): largura total, fundo
                    na cor do estado e o contador na outra ponta. A cor de
                    estado vive só aqui (RN-71), e por isso a pílula que ficava
                    dentro do cabeçalho saiu: com ela e a faixa juntas, a mesma
                    informação era dita duas vezes e a linha ficava disputando
                    escala com a gravidade. Caixa alta é do CSS, e não do texto:
                    o leitor de tela continua ouvindo o nome do estado como ele
                    se escreve. */}
                <header
                  className={`flex items-center justify-between gap-2 px-5 py-2 ${classeDoStatus(grupo.status)}`}
                >
                  <span className="text-xs font-bold uppercase tracking-wide">
                    {rotuloDoStatus(grupo.status)}
                  </span>
                  <span className="text-xs font-semibold">
                    {grupo.itens.length}{" "}
                    {grupo.itens.length === 1 ? "manifestação" : "manifestações"}
                  </span>
                </header>
                <ListaDaFila
                  itens={grupo.itens}
                  hoje={hoje}
                  responsaveis={responsaveis}
                  podeAbrirDossie={podeAbrirDossie}
                  cobrancas={cobrancas}
                  onValidar={setValidando}
                  onEncerrar={setEncerrando}
                  onCobrar={cobrar}
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
