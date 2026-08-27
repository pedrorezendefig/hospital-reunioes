"use client";

import { useCallback, useEffect, useState } from "react";
import { AlertTriangle, RefreshCw, Search, Wallet } from "lucide-react";
import { useAuth } from "@/hooks/useAuth";
import { DataTable, type Column } from "@/components/admin/DataTable";

/**
 * Espelho da Global Health (ADR 0038), elos 1 a 3: as especialidades
 * publicadas na agenda online e, ao clicar numa delas, os convênios aceitos,
 * os profissionais disponíveis e os planos do convênio escolhido.
 *
 * Caminho paralelo às tabelas curadas: aqui não se cria, não se edita e nada
 * é gravado. O navegador fala com o backend do app, e só o backend fala com a
 * Global Health (o token da integração nunca chega até aqui).
 *
 * A busca é da própria Global Health (parâmetro `pesquisa`), aplicada ao
 * enviar o campo ou ao clicar em Atualizar, e não um filtro sobre uma cópia
 * velha.
 *
 * Três estados explícitos, porque a honestidade é o valor da tela:
 * carregando, erro (com a mensagem da falha) e vazio com o motivo. Falha da
 * Global Health nunca aparece como lista vazia.
 */

type Especialidade = {
  id: number;
  nome: string;
  bloqueado: boolean;
};

type Convenio = {
  id: number;
  nome: string;
  particular: boolean;
};

type Profissional = {
  id: number;
  nome: string;
};

type Plano = {
  id: number;
  nome: string;
};

type EspelhoResponse<T> = {
  data: T[];
  total: number;
  motivo_vazio: string | null;
};

const ENDPOINT = "/api/admin/espelho-global-health/especialidades";

export function EspelhoGlobalHealth() {
  const { token, loading: authLoading } = useAuth();

  const [linhas, setLinhas] = useState<Especialidade[]>([]);
  const [motivoVazio, setMotivoVazio] = useState<string | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [busca, setBusca] = useState("");
  // O termo que foi de fato para a Global Health (o campo digitado só vale
  // depois de enviado).
  const [buscaAplicada, setBuscaAplicada] = useState("");
  // Incrementado a cada envio: mesmo com o termo igual, o clique em Atualizar
  // busca a resposta fresca.
  const [reloadKey, setReloadKey] = useState(0);

  // Elos 2 e 3: os ids vêm sempre do elo anterior clicado na tela, nunca de
  // um campo digitado. Trocar de especialidade zera o convênio escolhido,
  // porque um plano só faz sentido dentro da especialidade em que foi aberto.
  const [especialidade, setEspecialidade] = useState<Especialidade | null>(
    null,
  );
  const [convenio, setConvenio] = useState<Convenio | null>(null);

  function selecionarEspecialidade(linha: Especialidade) {
    const mesma = especialidade?.id === linha.id;
    setEspecialidade(mesma ? null : linha);
    setConvenio(null);
  }

  const idEspecialidade = especialidade?.id ?? null;
  const idConvenio = convenio?.id ?? null;

  // Dois blocos, duas chamadas disparadas no mesmo ciclo: a espera é a da
  // resposta mais lenta, não a soma das duas. Cada um com carregando, erro e
  // vazio próprios.
  const convenios = useBlocoDaGh<Convenio>(
    idEspecialidade === null ? null : `${ENDPOINT}/${idEspecialidade}/convenios`,
    token,
    reloadKey,
  );
  const profissionais = useBlocoDaGh<Profissional>(
    idEspecialidade === null
      ? null
      : `${ENDPOINT}/${idEspecialidade}/profissionais`,
    token,
    reloadKey,
  );
  const planos = useBlocoDaGh<Plano>(
    idEspecialidade === null || idConvenio === null
      ? null
      : `${ENDPOINT}/${idEspecialidade}/convenios/${idConvenio}/planos`,
    token,
    reloadKey,
  );

  useEffect(() => {
    if (authLoading || !token) return;
    let cancelled = false;
    setLoading(true);
    setErro(null);
    (async () => {
      try {
        const url = buscaAplicada
          ? `${ENDPOINT}?pesquisa=${encodeURIComponent(buscaAplicada)}`
          : ENDPOINT;
        const res = await fetch(url, {
          headers: { Authorization: `Bearer ${token}` },
        });
        const body = await res.json().catch(() => null);
        if (cancelled) return;
        if (!res.ok) {
          setLinhas([]);
          setMotivoVazio(null);
          setErro(mensagemDeErro(body, res.statusText));
          return;
        }
        const dados = body as EspelhoResponse<Especialidade>;
        setLinhas(dados.data ?? []);
        setMotivoVazio(dados.motivo_vazio ?? null);
      } catch {
        if (cancelled) return;
        setLinhas([]);
        setMotivoVazio(null);
        setErro(
          "Não foi possível falar com o servidor para consultar a Global Health.",
        );
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [authLoading, token, buscaAplicada, reloadKey]);

  function atualizar(evento?: React.FormEvent) {
    evento?.preventDefault();
    setBuscaAplicada(busca.trim());
    setReloadKey((k) => k + 1);
  }

  // Cada vazio diz por que está vazio: falha na consulta, busca sem resultado
  // ou agenda sem nada publicado (o motivo vem do backend).
  const estadoVazio = erro
    ? {
        title: "Nada a mostrar enquanto a consulta falhar",
        hint: "Clique em Atualizar para tentar de novo.",
      }
    : buscaAplicada
      ? {
          title: `Nenhuma especialidade publicada com "${buscaAplicada}" no nome`,
          hint: "Limpe a busca e atualize para ver tudo o que a agenda publica.",
        }
      : {
          title: motivoVazio ?? "Nenhuma especialidade encontrada",
          hint: "Publique a especialidade no Painel de Controle da Global Health para ela aparecer aqui.",
        };

  const columns: Column<Especialidade>[] = [
    {
      key: "id",
      header: "ID na Global Health",
      width: "160px",
      render: (linha) => (
        <span className="font-mono text-xs text-slate-500">{linha.id}</span>
      ),
    },
    {
      key: "nome",
      header: "Especialidade",
      render: (linha) => (
        <span
          className={
            linha.id === idEspecialidade
              ? "text-primary font-semibold"
              : "text-text"
          }
        >
          {linha.nome ?? "-"}
        </span>
      ),
    },
    {
      key: "bloqueado",
      header: "Situação",
      width: "150px",
      render: (linha) => (
        <span
          className={`inline-flex px-2 py-0.5 rounded text-xs font-medium ${
            linha.bloqueado
              ? "bg-amber-50 text-amber-700"
              : "bg-emerald-50 text-emerald-600"
          }`}
        >
          {linha.bloqueado ? "Bloqueada" : "Publicada"}
        </span>
      ),
    },
  ];

  return (
    <div className="space-y-4">
      <p className="text-sm text-text-secondary">
        O que a agenda online da Global Health publica agora. Esta seção é uma
        janela, não um caderno: nada fica gravado, e cada clique em Atualizar
        busca a resposta fresca. Clique numa especialidade para ver os
        convênios aceitos e os profissionais disponíveis nela.
      </p>

      {erro && (
        <AvisoDeFalha
          mensagem={erro}
          resumo="A consulta à Global Health falhou. A lista está vazia por causa da falha, não por falta de especialidade publicada."
        />
      )}

      <DataTable
        onRowClick={selecionarEspecialidade}
        data={erro ? [] : linhas}
        loading={loading || authLoading}
        columns={columns}
        getRowKey={(linha) => String(linha.id)}
        emptyState={estadoVazio}
        toolbar={
          <form
            onSubmit={atualizar}
            className="grid grid-cols-1 md:grid-cols-[1fr_auto] gap-3 items-center"
          >
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
              <input
                type="text"
                placeholder="Buscar especialidade na agenda..."
                value={busca}
                onChange={(e) => setBusca(e.target.value)}
                className="w-full pl-9 pr-3 py-2 text-sm border border-slate-200 rounded-lg outline-none focus:border-primary focus:ring-1 focus:ring-primary bg-white"
              />
            </div>
            <button
              type="submit"
              disabled={loading}
              className="flex items-center justify-center gap-2 px-4 py-2 rounded-lg text-sm font-medium border border-border bg-white text-text-secondary hover:bg-primary/5 hover:text-text transition-colors disabled:opacity-50 cursor-pointer"
            >
              <RefreshCw
                className={`w-4 h-4 ${loading ? "animate-spin" : ""}`}
              />
              Atualizar
            </button>
          </form>
        }
      />

      {especialidade && (
        <div className="space-y-4">
          <p className="text-sm text-text-secondary">
            Cadeia da agenda para{" "}
            <span className="font-semibold text-text">
              {especialidade.nome}
            </span>
            . Clique de novo na especialidade para fechar.
          </p>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <BlocoDoEspelho
              titulo="Convênios aceitos"
              subtitulo="A mesma lista que decide se o agendamento acontece. Clique num convênio para ver os planos dele."
              estado={convenios}
              resumoDaFalha="A consulta de convênios falhou. Nenhum convênio aparece por causa da falha, e não por falta de convênio aceito."
              dicaVazia="Libere o convênio para esta especialidade no Painel de Controle da Global Health."
              getRowKey={(linha) => String(linha.id)}
              onRowClick={(linha) =>
                setConvenio((atual) => (atual?.id === linha.id ? null : linha))
              }
              columns={colunasDeConvenio(idConvenio)}
            />

            <BlocoDoEspelho
              titulo="Profissionais disponíveis"
              subtitulo="Quem está com o botão ligado no Painel de Controle da Global Health."
              estado={profissionais}
              resumoDaFalha="A consulta de profissionais falhou. Ninguém aparece por causa da falha, e não por falta de médico disponível."
              dicaVazia="Ligue o profissional para esta especialidade no Painel de Controle da Global Health."
              getRowKey={(linha) => String(linha.id)}
              columns={COLUNAS_DE_PROFISSIONAL}
            />
          </div>

          {convenio && (
            <BlocoDoEspelho
              titulo={`Planos de ${convenio.nome}`}
              subtitulo={`Planos publicados para este convênio dentro de ${especialidade.nome}.`}
              estado={planos}
              resumoDaFalha="A consulta de planos falhou. Nenhum plano aparece por causa da falha, e não por falta de plano publicado."
              dicaVazia="Publique o plano deste convênio para esta especialidade no Painel de Controle da Global Health."
              getRowKey={(linha) => String(linha.id)}
              columns={COLUNAS_DE_PLANO}
            />
          )}
        </div>
      )}
    </div>
  );
}

/**
 * Um bloco da cadeia: cabeçalho, aviso de falha e tabela, com carregando,
 * erro e vazio próprios. Blocos irmãos falham e carregam de forma
 * independente, porque cada um é uma pergunta diferente à Global Health.
 */
function BlocoDoEspelho<T>(props: {
  titulo: string;
  subtitulo: string;
  estado: BlocoEstado<T>;
  resumoDaFalha: string;
  dicaVazia: string;
  columns: Column<T>[];
  getRowKey: (linha: T) => string;
  onRowClick?: (linha: T) => void;
}) {
  const { estado } = props;
  return (
    <div className="space-y-3">
      <div>
        <h4 className="text-sm font-semibold text-text">{props.titulo}</h4>
        <p className="text-xs text-text-secondary mt-0.5">{props.subtitulo}</p>
      </div>

      {estado.erro && (
        <AvisoDeFalha mensagem={estado.erro} resumo={props.resumoDaFalha} />
      )}

      <DataTable
        data={estado.erro ? [] : estado.linhas}
        loading={estado.loading}
        columns={props.columns}
        getRowKey={props.getRowKey}
        onRowClick={props.onRowClick}
        emptyState={
          estado.erro
            ? {
                title: "Nada a mostrar enquanto a consulta falhar",
                hint: "Clique em Atualizar para tentar de novo.",
              }
            : {
                title: estado.motivoVazio ?? "Nada publicado para esta escolha",
                hint: props.dicaVazia,
              }
        }
      />
    </div>
  );
}

function AvisoDeFalha({
  resumo,
  mensagem,
}: {
  resumo: string;
  mensagem: string;
}) {
  return (
    <div
      role="alert"
      className="flex items-start gap-3 p-4 rounded-xl border border-red-200 bg-red-50 text-sm text-red-700"
    >
      <AlertTriangle className="w-5 h-5 shrink-0 mt-0.5" />
      <div>
        <p className="font-semibold">{resumo}</p>
        <p className="mt-1">{mensagem}</p>
      </div>
    </div>
  );
}

const COLUNA_ID_NA_GH = {
  key: "id",
  header: "ID na Global Health",
  width: "160px",
  render: (linha: { id: number }) => (
    <span className="font-mono text-xs text-slate-500">{linha.id}</span>
  ),
};

/**
 * A linha do particular fica destacada: é o caminho de quem não tem convênio,
 * e a secretária precisa achar isso na hora, sem ler a lista inteira.
 */
function colunasDeConvenio(idSelecionado: number | null): Column<Convenio>[] {
  return [
    COLUNA_ID_NA_GH,
    {
      key: "nome",
      header: "Convênio",
      render: (linha) => (
        <span className="flex items-center gap-2">
          <span
            className={
              linha.particular
                ? "font-semibold text-primary"
                : linha.id === idSelecionado
                  ? "font-semibold text-text"
                  : "text-text"
            }
          >
            {linha.nome ?? "-"}
          </span>
          {linha.particular && (
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-primary/10 text-primary text-xs font-medium">
              <Wallet className="w-3 h-3" />
              Particular
            </span>
          )}
        </span>
      ),
    },
  ];
}

const COLUNAS_DE_PROFISSIONAL: Column<Profissional>[] = [
  COLUNA_ID_NA_GH,
  {
    key: "nome",
    header: "Profissional",
    render: (linha) => <span className="text-text">{linha.nome ?? "-"}</span>,
  },
];

const COLUNAS_DE_PLANO: Column<Plano>[] = [
  COLUNA_ID_NA_GH,
  {
    key: "nome",
    header: "Plano",
    render: (linha) => <span className="text-text">{linha.nome ?? "-"}</span>,
  },
];

type BlocoEstado<T> = {
  linhas: T[];
  motivoVazio: string | null;
  erro: string | null;
  loading: boolean;
};

const BLOCO_OCIOSO: BlocoEstado<never> = {
  linhas: [],
  motivoVazio: null,
  erro: null,
  loading: false,
};

/**
 * Um elo da cadeia da Global Health. Com `url` nula o bloco fica ocioso (o
 * elo anterior ainda não foi escolhido) e nenhuma chamada sai.
 *
 * `reloadKey` é o mesmo do botão Atualizar: um clique refaz a cadeia inteira,
 * porque uma parte fresca ao lado de outra velha seria pior que nenhuma.
 */
function useBlocoDaGh<T>(
  url: string | null,
  token: string | null,
  reloadKey: number,
): BlocoEstado<T> {
  const [estado, setEstado] = useState<BlocoEstado<T>>(BLOCO_OCIOSO);

  const buscar = useCallback(async (alvo: string, bearer: string) => {
    const res = await fetch(alvo, {
      headers: { Authorization: `Bearer ${bearer}` },
    });
    const body = await res.json().catch(() => null);
    if (!res.ok) {
      throw new Error(mensagemDeErro(body, res.statusText));
    }
    return body as EspelhoResponse<T>;
  }, []);

  useEffect(() => {
    if (!url || !token) {
      setEstado(BLOCO_OCIOSO);
      return;
    }
    let cancelled = false;
    setEstado({ linhas: [], motivoVazio: null, erro: null, loading: true });
    buscar(url, token)
      .then((dados) => {
        if (cancelled) return;
        setEstado({
          linhas: dados.data ?? [],
          motivoVazio: dados.motivo_vazio ?? null,
          erro: null,
          loading: false,
        });
      })
      .catch((falha: unknown) => {
        if (cancelled) return;
        setEstado({
          linhas: [],
          motivoVazio: null,
          erro:
            falha instanceof Error
              ? falha.message
              : "Não foi possível falar com o servidor para consultar a Global Health.",
          loading: false,
        });
      });
    return () => {
      cancelled = true;
    };
  }, [url, token, reloadKey, buscar]);

  return estado;
}

function mensagemDeErro(body: unknown, fallback: string): string {
  const detail = (body as { detail?: unknown } | null)?.detail;
  if (typeof detail === "string") return detail;
  if (detail) return JSON.stringify(detail);
  return fallback || "Falha desconhecida ao consultar a Global Health.";
}
