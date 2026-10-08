"use client";

/**
 * Os prints da Demanda no card aberto (issue #1061, PRD #1056, ADR 0069).
 *
 * A miniatura e o "abrir em tamanho real" usam a URL que o servidor ASSINOU, de
 * vida curta: o bucket é privado, e um endereço montado aqui não abriria nada.
 * A lista é pedida de novo cada vez que o card abre, então a URL que a pessoa
 * clica é sempre recente.
 *
 * O anexo apagado (Demanda Concluída ou Cancelada) continua na lista, com nome,
 * quem e quando, e a marca "apagado": o binário saiu do bucket, o registro de
 * que ele existiu, não.
 */

import { useEffect, useState } from "react";
import { ImageOff } from "lucide-react";

import { corpoValidado } from "./assistente";
import { AnexoDaDemanda, listaDeAnexosValida, urlDosAnexos } from "./anexos";
import { FALHA_DE_CONEXAO, momentoLegivel } from "./demandas";

type Props = {
  demandaId: string;
  token: string | null;
};

const NAO_CARREGOU = "Não foi possível carregar as imagens desta Demanda. Feche e abra o card de novo.";

function quemEQuando(anexo: AnexoDaDemanda): string {
  const quem = anexo.anexado_por_nome ?? "Alguém";
  const quando = momentoLegivel(anexo.criado_em);
  return quando ? `${quem}, ${quando}` : quem;
}

export function AnexosDaDemanda({ demandaId, token }: Props) {
  const [anexos, setAnexos] = useState<AnexoDaDemanda[]>([]);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    if (!token) return;
    let vivo = true;
    setErro(null);
    fetch(urlDosAnexos(demandaId), { headers: { Authorization: `Bearer ${token}` } })
      .then(async (resposta) => {
        if (!resposta.ok) throw new Error(String(resposta.status));
        const lista = await corpoValidado(resposta, listaDeAnexosValida);
        if (lista === null) throw new Error("lista de anexos fora do contrato");
        if (vivo) setAnexos(lista);
      })
      .catch((e) => {
        console.error("[admin/tecnologia] falha ao carregar os anexos", e);
        if (vivo) setErro(e instanceof TypeError ? FALHA_DE_CONEXAO : NAO_CARREGOU);
      });
    return () => {
      vivo = false;
    };
  }, [demandaId, token]);

  // Texto simples, e não `role="alert"`: o alerta do card é o das ações (salvar,
  // mover, responder), e uma lista de imagens que não carregou não pode tomar o
  // lugar dele nem ser lida como se a ação tivesse falhado.
  if (erro) return <p className="text-xs text-red-700">{erro}</p>;
  if (anexos.length === 0) return null;

  return (
    <section aria-label="Imagens da Demanda" className="space-y-2">
      <span className="text-xs font-medium text-text-secondary">Imagens</span>
      <ul className="flex flex-wrap gap-3">
        {anexos.map((anexo) => (
          <li key={anexo.id} className="w-32 space-y-1">
            {anexo.url && !anexo.apagado_em ? (
              <a
                href={anexo.url}
                target="_blank"
                rel="noopener noreferrer"
                aria-label={`Abrir ${anexo.nome} em tamanho real`}
                className="block"
              >
                {/* `<img>` puro: a URL é assinada e de vida curta, e o
                    otimizador do Next guardaria em cache um endereço que
                    morre em minutos. */}
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={anexo.url}
                  alt={anexo.nome}
                  className="h-20 w-32 object-cover rounded-lg border border-border hover:border-primary transition-colors"
                />
              </a>
            ) : (
              <div className="h-20 w-32 flex items-center justify-center rounded-lg border border-dashed border-border bg-slate-50 text-text-secondary">
                <ImageOff className="w-5 h-5" />
              </div>
            )}
            <p className="text-xs text-text truncate" title={anexo.nome}>
              {anexo.nome}
            </p>
            <p className="text-[11px] text-text-secondary">{quemEQuando(anexo)}</p>
            {anexo.apagado_em && <p className="text-[11px] font-semibold text-text-secondary">apagado</p>}
          </li>
        ))}
      </ul>
    </section>
  );
}
