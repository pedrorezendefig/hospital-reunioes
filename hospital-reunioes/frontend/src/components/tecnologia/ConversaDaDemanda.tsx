"use client";

/**
 * A Conversa dentro do card (issue #638, PRD #634, ADR 0050).
 *
 * O fio em ordem cronológica, respostas e movimentos misturados, mais as duas
 * portas de escrita: responder e corrigir a própria resposta por 10 minutos.
 * Não existe apagar, aqui nem na API (PRD #634, história 29).
 *
 * Criar a Demanda NÃO gera linha: a Conversa mostra o que aconteceu DEPOIS, e
 * quem abriu e quando já está no card.
 *
 * Quem diz se uma linha ainda aceita correção é o backend, no `editavel_ate`
 * de cada linha: a tela não sabe qual participante é o usuário logado (o
 * `useAuth` carrega o id do Supabase Auth, e não o `participantes.id`).
 */

import { useState } from "react";
import { Pencil, Send } from "lucide-react";

import {
  aplicarMencao,
  avisoPorEmail,
  BASE_TECNOLOGIA,
  FALHA_DE_CONEXAO,
  LinhaDaConversa,
  mencoesNoTexto,
  momentoLegivel,
  motivoDaRecusa,
  pedacosDoTexto,
  PessoaDaAba,
  pessoasDoAutocomplete,
  podeCorrigirAgora,
  termoDaMencao,
} from "./demandas";

type Props = {
  demandaId: string;
  linhas: LinhaDaConversa[];
  pessoas: PessoaDaAba[];
  token: string | null;
  /** Recarrega o fio depois de escrever nele. */
  onFioMudou: () => void | Promise<void>;
  /** O alerta é um só, e mora no modal. */
  onErro: (mensagem: string | null) => void;
};

const CLASSE_CAIXA =
  "w-full px-3 py-2 text-sm border border-slate-200 rounded-lg outline-none focus:border-primary focus:ring-1 focus:ring-primary bg-white";

/**
 * A caixa de texto com o autocomplete do @.
 *
 * A mesma nos dois usos, escrever e corrigir, porque a regra da menção é a
 * mesma: só aparece quem tem acesso à aba, e a escolha guarda o id junto do
 * nome escrito no texto.
 */
function CaixaComMencao({
  rotulo,
  valor,
  aoMudar,
  pessoas,
  aoMencionar,
}: {
  rotulo: string;
  valor: string;
  aoMudar: (texto: string) => void;
  pessoas: PessoaDaAba[];
  aoMencionar: (pessoa: PessoaDaAba) => void;
}) {
  const termo = termoDaMencao(valor);
  const sugestoes = termo === null ? [] : pessoasDoAutocomplete(termo, pessoas);

  return (
    <div className="relative">
      <textarea
        aria-label={rotulo}
        rows={3}
        value={valor}
        onChange={(e) => aoMudar(e.target.value)}
        className={CLASSE_CAIXA}
      />
      {sugestoes.length > 0 && (
        <ul aria-label="Pessoas para mencionar" className="mt-1 rounded-lg border border-border bg-surface">
          {sugestoes.map((pessoa) => (
            <li key={pessoa.id}>
              <button
                type="button"
                onClick={() => {
                  aoMudar(aplicarMencao(valor, pessoa.nome_completo));
                  aoMencionar(pessoa);
                }}
                className="w-full px-3 py-1.5 text-left text-sm text-text hover:bg-primary/5 transition-colors"
              >
                {pessoa.nome_completo}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/** O texto da linha com as menções em destaque: o par na tela da coluna `mencoes`. */
function TextoDaLinha({ linha, pessoas }: { linha: LinhaDaConversa; pessoas: PessoaDaAba[] }) {
  const nomes = linha.mencoes
    .map((id) => pessoas.find((p) => p.id === id)?.nome_completo)
    .filter((nome): nome is string => Boolean(nome));

  return (
    <>
      {pedacosDoTexto(linha.texto, nomes).map((pedaco, i) =>
        pedaco.mencao ? (
          <strong key={i} className="font-semibold text-primary">
            {pedaco.texto}
          </strong>
        ) : (
          <span key={i}>{pedaco.texto}</span>
        ),
      )}
    </>
  );
}

export function ConversaDaDemanda({ demandaId, linhas, pessoas, token, onFioMudou, onErro }: Props) {
  const [texto, setTexto] = useState("");
  const [escolhidas, setEscolhidas] = useState<PessoaDaAba[]>([]);
  const [editandoId, setEditandoId] = useState<string | null>(null);
  const [textoEditado, setTextoEditado] = useState("");
  const [escolhidasEditadas, setEscolhidasEditadas] = useState<PessoaDaAba[]>([]);
  const [enviando, setEnviando] = useState(false);

  function guardarEscolhida(atuais: PessoaDaAba[], pessoa: PessoaDaAba): PessoaDaAba[] {
    return atuais.some((p) => p.id === pessoa.id) ? atuais : [...atuais, pessoa];
  }

  /**
   * Devolve `true` quando o servidor aceitou.
   *
   * O `catch` não é enfeite: sem ele, a rede fora deixaria a resposta sumir em
   * silêncio e a pessoa acharia que falou.
   */
  async function escrever(url: string, metodo: string, corpo: unknown): Promise<boolean> {
    setEnviando(true);
    try {
      let resposta: Response;
      try {
        resposta = await fetch(url, {
          method: metodo,
          headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
          body: JSON.stringify(corpo),
        });
      } catch (e) {
        console.error("[admin/tecnologia] falha ao escrever na Conversa", e);
        onErro(FALHA_DE_CONEXAO);
        return false;
      }
      if (!resposta.ok) {
        onErro(await motivoDaRecusa(resposta));
        return false;
      }
      // A resposta entrou. Falta saber se os avisos por e-mail que ela dispara
      // (a @menção e o "chegou resposta" para quem responde pela Demanda)
      // saíram (issue #642). A correção passa por aqui pelo mesmo motivo: a
      // menção acrescentada nos 10 minutos também chama (issue #670). Quando não
      // saem, quem escreveu é quem ainda pode dar o recado por outro caminho, e
      // é a única pessoa que está com a tela aberta agora. `null` quando não
      // havia nada a avisar, ou tudo saiu.
      onErro(await avisoPorEmail(resposta));
      await onFioMudou();
      return true;
    } finally {
      setEnviando(false);
    }
  }

  async function responder() {
    const enviado = await escrever(`${BASE_TECNOLOGIA}/demandas/${demandaId}/conversa`, "POST", {
      texto,
      mencoes: mencoesNoTexto(texto, escolhidas),
    });
    if (enviado) {
      setTexto("");
      setEscolhidas([]);
    }
  }

  function abrirCorrecao(linha: LinhaDaConversa) {
    setEditandoId(linha.id);
    setTextoEditado(linha.texto);
    // As menções que já estavam na linha entram como escolhidas: sem isso, uma
    // correção de vírgula apagaria o "@Fulano" da lista sem a pessoa pedir.
    setEscolhidasEditadas(pessoas.filter((p) => linha.mencoes.includes(p.id)));
  }

  async function salvarCorrecao(linhaId: string) {
    const salvo = await escrever(`${BASE_TECNOLOGIA}/demandas/${demandaId}/conversa/${linhaId}`, "PATCH", {
      texto: textoEditado,
      mencoes: mencoesNoTexto(textoEditado, escolhidasEditadas),
    });
    if (salvo) setEditandoId(null);
  }

  return (
    <section aria-labelledby="titulo-conversa" className="pt-4 border-t border-border">
      <h3 id="titulo-conversa" className="text-sm font-semibold text-text">
        Conversa
      </h3>

      {linhas.length === 0 ? (
        <p className="mt-2 text-sm text-text-secondary">Nada aconteceu nesta Demanda ainda.</p>
      ) : (
        <ol className="mt-2 space-y-2">
          {linhas.map((linha) => (
            <li
              key={linha.id}
              className={`px-3 py-2 rounded-lg text-sm ${
                linha.linha === "movimento" ? "bg-slate-50 text-text-secondary" : "bg-white border border-border"
              }`}
            >
              {editandoId === linha.id ? (
                <div className="space-y-2">
                  <CaixaComMencao
                    rotulo="Corrigir a resposta"
                    valor={textoEditado}
                    aoMudar={setTextoEditado}
                    pessoas={pessoas}
                    aoMencionar={(pessoa) => setEscolhidasEditadas((atuais) => guardarEscolhida(atuais, pessoa))}
                  />
                  <div className="flex gap-2">
                    <button
                      type="button"
                      onClick={() => salvarCorrecao(linha.id)}
                      disabled={!textoEditado.trim() || enviando}
                      className="px-3 py-1.5 rounded-lg bg-primary text-white text-sm font-medium disabled:opacity-50"
                    >
                      Salvar correção
                    </button>
                    <button
                      type="button"
                      onClick={() => setEditandoId(null)}
                      className="px-3 py-1.5 rounded-lg border border-border text-sm text-text hover:border-primary hover:text-primary transition-colors"
                    >
                      Cancelar
                    </button>
                  </div>
                </div>
              ) : (
                <>
                  <span className="block">
                    {linha.autor_nome ? (
                      <strong className="font-medium text-text">{linha.autor_nome}: </strong>
                    ) : null}
                    <TextoDaLinha linha={linha} pessoas={pessoas} />
                  </span>
                  <span className="mt-0.5 flex items-center gap-2 text-xs text-slate-400">
                    <span>{momentoLegivel(linha.criado_em)}</span>
                    {/* O par na tela do carimbo `editado_em` do backend: sem
                        ele, a correção mudaria o fio sem ninguém saber. */}
                    {linha.editado_em && <span>(editado)</span>}
                    {podeCorrigirAgora(linha.editavel_ate) && (
                      <button
                        type="button"
                        onClick={() => abrirCorrecao(linha)}
                        className="inline-flex items-center gap-1 text-primary hover:underline"
                      >
                        <Pencil className="w-3 h-3" />
                        Corrigir
                      </button>
                    )}
                  </span>
                </>
              )}
            </li>
          ))}
        </ol>
      )}

      <div className="mt-3 space-y-2">
        <CaixaComMencao
          rotulo="Resposta"
          valor={texto}
          aoMudar={setTexto}
          pessoas={pessoas}
          aoMencionar={(pessoa) => setEscolhidas((atuais) => guardarEscolhida(atuais, pessoa))}
        />
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={responder}
            // Por cima da guarda do backend, não no lugar dela: a API recusa
            // texto vazio com frase de gente.
            disabled={!texto.trim() || enviando}
            className="flex items-center gap-2 px-4 py-2 rounded-xl bg-gradient-to-r from-primary to-primary-light text-white text-sm font-semibold shadow-md hover:shadow-lg transition-all disabled:opacity-50"
          >
            <Send className="w-4 h-4" />
            Responder
          </button>
          <span className="text-xs text-text-secondary">
            Digite @ para chamar alguém com acesso à aba. Você corrige a sua resposta por 10 minutos.
          </span>
        </div>
      </div>
    </section>
  );
}
