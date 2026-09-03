"use client";

/**
 * A linha da fila da Ouvidoria, em dois níveis (issue #495, PRD #471, RN-72).
 *
 * Era uma tabela de sete colunas com rolagem horizontal: o resumo quebrava
 * linha num corredor estreito e a ação principal ficava fora da área visível
 * (D-06, D-15). Aqui cada caso ocupa uma linha de duas alturas, com a ação do
 * estado sempre à direita, e nada sai para o lado: o que não cabe é truncado e
 * mora no Dossiê (RN-73).
 *
 * É UM componente para os dois lugares que desenham a fila (os grupos de
 * estado e o bloco "Aguardando seu encerramento", issue #486). Com o JSX
 * copiado, o botão novo de amanhã nasceria só num deles.
 */

import { useRef, useState } from "react";
import Link from "next/link";
import {
  AlertCircle,
  CalendarDays,
  CheckCircle2,
  FileText,
  MoreHorizontal,
  Send,
} from "lucide-react";

import { useFecharFlutuante } from "@/hooks/useFecharFlutuante";
import { ALTURA_DE_TOQUE, ALVO_DE_TOQUE } from "@/lib/toque";
import {
  ROTULO_ACAO,
  acaoPrimariaDoStatus,
  acoesSecundariasDoStatus,
  type ChaveDeAcao,
} from "@/lib/ouvidoria/acoes";
import {
  textoDaCobranca,
  tomDaCobranca,
  type ResultadoDaCobranca,
} from "@/lib/ouvidoria/cobranca";
import type { ManifestacaoIndice } from "@/lib/ouvidoria/fila";
import { classificarPrazoDaManifestacao, type ClassePrazo } from "@/lib/ouvidoria/prazo";
import {
  classeDaGravidade,
  responsavelDoSetor,
  rotuloDaGravidade,
  type Responsavel,
} from "@/lib/ouvidoria/validacao";

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

/**
 * O prazo do nível 2, em linguagem natural e na cor da régua (issue #488,
 * RN-58). A régua vive em `lib/ouvidoria/prazo`; aqui só se pinta o que ela
 * decidiu.
 */
function Prazo({ m, classe }: { m: ManifestacaoIndice; classe: ClassePrazo }) {
  // Caso já classificado mostra o vencimento em data e hora, com a contagem
  // regressiva do motor ao lado. Caso ainda sem gravidade mostra o prazo de
  // referência da fundação, que é o que existe antes da validação.
  const label = m.prazo_area_em ? formatarDataHora(m.prazo_area_em) : formatarData(m.prazo_resposta);
  // Caso já respondido ou encerrado saiu das mãos de quem precisava correr: o
  // relógio para, e "vencido há 5 dias úteis" ali só assusta à toa.
  const rotulo = m.prazo_area_em && classe !== "respondido" ? m.rotulo_prazo : null;

  // Vencido e vence hoje dividem o vermelho (issue #488, RN-58): os dois
  // precisam de resposta ainda hoje. Quem separa um do outro é o carimbo,
  // porque a cor sozinha diria que o caso já rompeu quando ele ainda tem o dia
  // inteiro pela frente.
  if (classe === "estourado" || classe === "vence_hoje") {
    return (
      <span className="inline-flex items-center gap-1 text-red-600 font-semibold">
        <AlertCircle className="w-3.5 h-3.5 shrink-0" />
        {label}
        <span className="text-[10px] font-bold uppercase tracking-wide bg-red-100 text-red-700 px-1.5 py-0.5 rounded-full">
          {classe === "estourado" ? "Estourado" : "Vence hoje"}
        </span>
        {rotulo && <span className="text-red-500 font-normal">{rotulo}</span>}
      </span>
    );
  }
  if (classe === "perto") {
    return (
      <span className="inline-flex items-center gap-1 text-amber-600 font-medium">
        <CalendarDays className="w-3.5 h-3.5 shrink-0" />
        {label}
        {rotulo && <span className="text-amber-600 font-normal">{rotulo}</span>}
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 text-slate-500">
      {label}
      {rotulo && <span className="text-slate-400">{rotulo}</span>}
    </span>
  );
}

const ICONE_DA_ACAO: Record<ChaveDeAcao, typeof Send> = {
  validar: Send,
  cobrar: Send,
  encerrar: CheckCircle2,
  abrir: FileText,
};

/** A cor da ação primária. Só ela é cheia: o menu é a saída de tudo o mais. */
const CLASSE_DA_ACAO: Record<ChaveDeAcao, string> = {
  validar: "bg-primary text-white hover:bg-primary/90",
  cobrar: "bg-amber-500 text-white hover:bg-amber-600",
  encerrar: "bg-emerald-600 text-white hover:bg-emerald-700",
  abrir: "bg-slate-100 text-slate-700 hover:bg-slate-200",
};

/**
 * A ação, botão ou link conforme o que ela faz. Abrir é `<a href>` de verdade,
 * e não botão que navega (issue #476): é isso que faz o voltar do navegador, o
 * favorito e o link do email de cobrança funcionarem.
 */
function Acao({
  chave,
  m,
  className,
  onValidar,
  onEncerrar,
  onCobrar,
  onEscolher,
  cobrando,
}: {
  chave: ChaveDeAcao;
  m: ManifestacaoIndice;
  className: string;
  onValidar: (m: ManifestacaoIndice) => void;
  onEncerrar: (m: ManifestacaoIndice) => void;
  onCobrar: (m: ManifestacaoIndice) => void;
  onEscolher?: () => void;
  cobrando?: boolean;
}) {
  const Icone = ICONE_DA_ACAO[chave];
  // Rótulo de ação é rótulo curto, e vai em caixa alta (issue #489, RN-76). A
  // maiúscula é do CSS: o DOM continua guardando "Encerrar", que é o que o
  // leitor de tela anuncia e o que a busca da página acha. Fica aqui, e não no
  // `className` de quem chama, porque a linha e o menu desenham a mesma ação:
  // separado, um dos dois nasceria em caixa mista amanhã.
  const caixa = `${className} uppercase tracking-wide`;
  if (chave === "abrir") {
    return (
      <Link href={`/ouvidoria/m/${m.protocolo}`} className={caixa} onClick={onEscolher}>
        <Icone className="w-3.5 h-3.5" />
        {ROTULO_ACAO.abrir}
      </Link>
    );
  }
  const acionar = { validar: onValidar, cobrar: onCobrar, encerrar: onEncerrar }[chave];
  return (
    <button
      type="button"
      disabled={chave === "cobrar" && cobrando}
      onClick={() => {
        onEscolher?.();
        acionar(m);
      }}
      className={`${caixa} disabled:opacity-60`}
    >
      <Icone className="w-3.5 h-3.5" />
      {ROTULO_ACAO[chave]}
    </button>
  );
}

/**
 * O menu do que sobra. Fecha ao clicar fora e no Escape, como o resto dos
 * flutuantes da casa (`components/ui/MultiSelect`).
 */
function MenuDeAcoes({
  m,
  acoes,
  onValidar,
  onEncerrar,
  onCobrar,
}: {
  m: ManifestacaoIndice;
  acoes: ChaveDeAcao[];
  onValidar: (m: ManifestacaoIndice) => void;
  onEncerrar: (m: ManifestacaoIndice) => void;
  onCobrar: (m: ManifestacaoIndice) => void;
}) {
  const [aberto, setAberto] = useState(false);
  const caixa = useRef<HTMLDivElement>(null);
  useFecharFlutuante(aberto, caixa, () => setAberto(false));

  return (
    <div className="relative" ref={caixa}>
      <button
        type="button"
        aria-haspopup="true"
        aria-expanded={aberto}
        aria-label={`Mais ações da manifestação ${m.protocolo}`}
        onClick={() => setAberto((antes) => !antes)}
        className={`inline-flex items-center justify-center shrink-0 rounded-lg text-slate-500 hover:bg-slate-100 transition-colors ${ALVO_DE_TOQUE} md:w-8 md:h-8`}
      >
        <MoreHorizontal className="w-4 h-4" />
      </button>
      {aberto && (
        // Sem `role="menu"` de propósito: um menu ARIA espera filhos
        // `menuitem`, e o papel explícito apagaria o que estas ações são de
        // verdade, um botão e um link (issue #476). Agrupar e nomear basta.
        <div
          aria-label={`Ações da manifestação ${m.protocolo}`}
          className="absolute right-0 top-9 z-20 min-w-[13rem] py-1 rounded-xl border border-border bg-white shadow-premium"
        >
          {acoes.map((chave) => (
            <Acao
              key={chave}
              chave={chave}
              m={m}
              onValidar={onValidar}
              onEncerrar={onEncerrar}
              onCobrar={onCobrar}
              onEscolher={() => setAberto(false)}
              className={`flex w-full items-center gap-2 px-3 py-2 text-left text-sm text-slate-700 hover:bg-slate-50 ${ALTURA_DE_TOQUE}`}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function LinhaDaFila({
  m,
  hoje,
  responsaveis,
  podeAbrirDossie,
  cobranca,
  onValidar,
  onEncerrar,
  onCobrar,
}: {
  m: ManifestacaoIndice;
  hoje: string | null;
  responsaveis: Responsavel[] | null;
  podeAbrirDossie: boolean;
  cobranca: ResultadoDaCobranca | undefined;
  onValidar: (m: ManifestacaoIndice) => void;
  onEncerrar: (m: ManifestacaoIndice) => void;
  onCobrar: (m: ManifestacaoIndice) => void;
}) {
  const classe = hoje ? classificarPrazoDaManifestacao(m, hoje) : "normal";
  const gravidade = rotuloDaGravidade(m.gravidade);
  // Cadastro não lido é `null`, e disso não sai afirmação nenhuma sobre o
  // setor. A linha só fala de responsável quando ela leu o cadastro.
  const cadastroLido = responsaveis !== null && hoje !== null;
  const responsavel = cadastroLido ? responsavelDoSetor(responsaveis!, m.setor, hoje!) : null;
  const primaria = acaoPrimariaDoStatus(m.status);
  const secundarias = acoesSecundariasDoStatus(m.status);

  return (
    <li
      data-protocolo={m.protocolo}
      // Coluna no celular, linha no computador (issue #496, RN-75): abaixo de
      // 768px não há corredor para dois níveis lado a lado com a ação à
      // direita, e insistir nisso espremeria o resumo a um punhado de pixels.
      className={`flex flex-col md:flex-row md:items-center gap-2 md:gap-3 px-4 md:px-5 py-2.5 min-h-16 ${
        classe === "estourado" || classe === "vence_hoje" ? "bg-red-50/50" : ""
      }`}
    >
      {/* `min-w-0` é o que autoriza o filho a encolher: sem ele o resumo
          empurraria a linha para fora da tela em vez de truncar, que é a
          rolagem horizontal que a RN-73 proíbe. */}
      <div className="min-w-0 flex-1">
        {/* Empilhado, o nível 1 vira duas alturas: protocolo e gravidade em
            cima, resumo embaixo com a largura toda da tela para ele. Junto com
            o nível 2, são as três alturas da RN-75. */}
        <div className="flex flex-col md:flex-row md:items-center gap-0.5 md:gap-2 min-w-0">
          <div className="flex items-center gap-2 shrink-0">
            {/* O marcador de novidade (issue #484, RN-68). Sinal permanente, e
                não intermitente: piscar cansa, atrapalha a acessibilidade e
                some justo quando o olho chega. O ponto é cor, e cor sozinha
                não conta a história para quem não a enxerga, então ele anda
                com o rótulo em sr-only ao lado. */}
            {m.tem_novidade && (
              <span className="inline-flex items-center shrink-0">
                <span
                  aria-hidden="true"
                  className="inline-block w-2 h-2 rounded-full bg-primary align-middle"
                />
                <span className="sr-only">Movimentação nova</span>
              </span>
            )}
            <span className="font-mono text-sm font-semibold text-slate-800 shrink-0">
              {m.protocolo}
            </span>
            {gravidade && (
              <span
                // Rótulo de escala, não texto: vai em caixa alta junto com o
                // carimbo do prazo e a faixa do estado (issue #489, RN-76).
                className={`shrink-0 px-2 py-0.5 rounded-full border text-[11px] font-semibold uppercase tracking-wide ${classeDaGravidade(m.gravidade)}`}
              >
                {gravidade}
              </span>
            )}
          </div>
          {/* Uma linha só, com reticências, e o resumo inteiro no tooltip do
              desktop (RN-72). Peso médio quando há novidade (issue #484,
              RN-68): é o segundo sinal, para o ponto não ficar sozinho
              carregando a cor. */}
          <span
            title={m.resumo}
            className={`truncate text-sm ${
              m.tem_novidade ? "font-medium text-slate-800" : "text-slate-600"
            }`}
          >
            {m.resumo}
          </span>
        </div>
        {/* `overflow-hidden` é a rede da RN-73 no nível 2: o prazo é a última
            coisa da linha e não encolhe, então numa janela estreita ele
            empurraria a linha para fora em vez de ser cortado. O que não cabe
            sai da linha e continua no Dossiê. Empilhada, esta é a terceira e
            última altura da linha (issue #496, RN-75). */}
        <div className="flex items-center gap-2 mt-1 text-xs text-slate-500 min-w-0 overflow-hidden">
          <span className="truncate">{m.setor}</span>
          <span aria-hidden="true" className="text-slate-300">
            ·
          </span>
          {/* Setor órfão é o que mais atrasa, e o branco ali não denuncia nada
              (issue #325). Mas "Sem responsável" só pode ser dito por quem leu
              o cadastro: para quem está fora da Ouvidoria, que nunca o lê, a
              frase apareceria em TODA linha e deixaria de denunciar coisa
              alguma. Sem leitura, o nível 2 fica com setor e prazo. */}
          {cadastroLido && (
            <>
              <span className="truncate">
                {responsavel ? responsavel.nome : "Sem responsável"}
              </span>
              <span aria-hidden="true" className="text-slate-300">
                ·
              </span>
            </>
          )}
          <Prazo m={m} classe={classe} />
        </div>
      </div>

      {podeAbrirDossie && (
        // No celular as ações descem para baixo do conteúdo e tomam a largura
        // toda (issue #496, RN-75). O aviso da cobrança também empilha ali: ao
        // lado do botão, num corredor estreito, ele roubaria a largura da
        // única ação da linha.
        <div className="w-full md:w-auto flex flex-col md:flex-row md:items-center gap-1.5 shrink-0">
          {cobranca && (
            <span
              role="status"
              className={`text-xs md:max-w-xs ${
                { ok: "text-emerald-600", alerta: "text-amber-700", neutro: "text-slate-500" }[
                  tomDaCobranca(cobranca)
                ]
              }`}
            >
              {textoDaCobranca(cobranca)}
            </span>
          )}
          <div className="w-full md:w-auto flex items-center gap-1.5">
            <Acao
              chave={primaria}
              m={m}
              onValidar={onValidar}
              onEncerrar={onEncerrar}
              onCobrar={onCobrar}
              cobrando={cobranca?.fase === "enviando" || cobranca?.fase === "reenviada"}
              className={`inline-flex flex-1 md:flex-none items-center justify-center md:justify-start gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors ${ALTURA_DE_TOQUE} ${CLASSE_DA_ACAO[primaria]}`}
            />
            {secundarias.length > 0 && (
              <MenuDeAcoes
                m={m}
                acoes={secundarias}
                onValidar={onValidar}
                onEncerrar={onEncerrar}
                onCobrar={onCobrar}
              />
            )}
          </div>
        </div>
      )}
    </li>
  );
}

/**
 * A lista de linhas da fila. Sem `overflow-x`: a promessa da RN-73 é que nada
 * importante saia da área visível em nenhuma largura, e um contêiner rolável
 * aqui seria justamente o esconderijo.
 */
export function ListaDaFila({
  itens,
  hoje,
  responsaveis,
  podeAbrirDossie,
  cobrancas,
  onValidar,
  onEncerrar,
  onCobrar,
}: {
  itens: ManifestacaoIndice[];
  hoje: string | null;
  responsaveis: Responsavel[] | null;
  podeAbrirDossie: boolean;
  cobrancas: Record<string, ResultadoDaCobranca>;
  onValidar: (m: ManifestacaoIndice) => void;
  onEncerrar: (m: ManifestacaoIndice) => void;
  onCobrar: (m: ManifestacaoIndice) => void;
}) {
  return (
    <ul className="divide-y divide-slate-50">
      {itens.map((m) => (
        <LinhaDaFila
          key={m.id}
          m={m}
          hoje={hoje}
          responsaveis={responsaveis}
          podeAbrirDossie={podeAbrirDossie}
          cobranca={cobrancas[m.id]}
          onValidar={onValidar}
          onEncerrar={onEncerrar}
          onCobrar={onCobrar}
        />
      ))}
    </ul>
  );
}
