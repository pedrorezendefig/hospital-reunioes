"use client";

/**
 * O módulo da aba Tecnologia (issue #636, PRD #634, ADR 0050).
 *
 * As duas abas (Quadro e Painel). O gate de verdade é o `require_super_admin`
 * do backend; a sidebar apenas esconde o item. O cadastro de Produtos saiu do
 * rodapé do Quadro na issue #1060 e mora em tela própria
 * (`ProdutosDaTecnologia`, atrás da engrenagem ao lado de "Nova Demanda").
 *
 * As abas Minha vez e Histórico entraram na issue #641 e viraram blocos do
 * Painel na issue #1059. Os filtros por tipo, Produto e responsável saíram do
 * módulo na issue #1058 (PRD #1056).
 */

import { useCallback, useEffect, useState } from "react";
import { AlertCircle, Cpu } from "lucide-react";

import { useAuth } from "@/hooks/useAuth";

import { PainelDemandas } from "./PainelDemandas";
import { QuadroDemandas } from "./QuadroDemandas";
import {
  AbaDaTecnologia,
  abaInicial,
  BASE_TECNOLOGIA,
  CONSULTA_DO_CELULAR,
  EU_DESCONHECIDO,
  EuNaAba,
  FALHA_DE_CONEXAO,
} from "./demandas";

type Pessoa = { id: string; nome_completo: string; email: string };

type Produto = {
  id: string;
  nome: string;
  ativo: boolean;
  ordem: number;
  dono_id: string | null;
  dono_nome: string | null;
};

const ABAS: { id: AbaDaTecnologia; label: string }[] = [
  { id: "quadro", label: "Quadro" },
  { id: "painel", label: "Painel" },
];

/** Se a tela é de celular. Sem `matchMedia` (ambiente sem tela), não é. */
function ehCelular(): boolean {
  return typeof window.matchMedia === "function" && window.matchMedia(CONSULTA_DO_CELULAR).matches;
}

/**
 * A frase de quando `useAuth` não devolve token.
 *
 * Ela NÃO manda entrar de novo, de propósito. O hook devolve `token: null`
 * tanto quando a sessão acabou quanto quando o `getUser()` dele falhou por
 * rede, e o componente não distingue as duas: mandar sair e entrar de novo
 * seria cobrar justo a ação que a pessoa não consegue fazer quando a causa é a
 * rede. A frase nomeia as duas causas possíveis e sugere recarregar, que é
 * possível nos dois casos e resolve os dois quando a causa passa.
 */
const SEM_SESSAO =
  "Não foi possível carregar os Produtos: a sessão não está ativa ou o servidor não respondeu. Tente recarregar a página.";

export function TecnologiaModulo() {
  const { token, loading: carregandoAuth } = useAuth();

  /**
   * A aba à vista, ou `null` antes de saber qual abre (issue #1059).
   *
   * A escolha depende da largura da tela e do link, que só existem no
   * navegador: decidida no primeiro render, ela divergiria da página que o
   * servidor pré-renderizou. E nenhuma aba monta antes da escolha, para o
   * celular não pedir o Quadro inteiro à rede só para desmontá-lo em seguida.
   */
  const [aba, setAba] = useState<AbaDaTecnologia | null>(null);

  useEffect(() => {
    setAba(abaInicial(ehCelular(), window.location.search));
  }, []);
  const [produtos, setProdutos] = useState<Produto[]>([]);
  const [pessoas, setPessoas] = useState<Pessoa[]>([]);
  /**
   * Quem está olhando, do ponto de vista do Vínculo (issue #674).
   *
   * Carregado UMA vez aqui e passado às duas abas: elas mostram o mesmo modal,
   * e uma chamada por aba multiplicaria a ida à rede e abriria espaço para as
   * abas discordarem entre si.
   *
   * O default é o mais restrito: sem resposta, nenhum controle da Vitta
   * aparece. Backend uma versão atrás (sem a rota) cai exatamente nesse
   * default, em vez de desenhar um campo que ele não sabe atender.
   */
  const [eu, setEu] = useState<EuNaAba>(EU_DESCONHECIDO);
  const [erro, setErro] = useState<string | null>(null);

  const autorizacao = useCallback(
    () => ({ Authorization: `Bearer ${token}`, "Content-Type": "application/json" }),
    [token],
  );

  /**
   * Carrega Produtos e pessoas.
   *
   * A falha de rede tem que virar AVISO, não lista vazia: sem o `catch`, o
   * backend fora do ar desenharia a tela calada e sem Produto nenhum, que é
   * indistinguível de "o seed da migration não rodou". Molde do
   * `app/admin/usuarios/page.tsx`, que já trata assim.
   */
  const carregar = useCallback(async () => {
    if (!token) return;
    try {
      const [respProdutos, respPessoas, respEu] = await Promise.all([
        fetch(`${BASE_TECNOLOGIA}/produtos`, { headers: autorizacao() }),
        fetch(`${BASE_TECNOLOGIA}/pessoas`, { headers: autorizacao() }),
        fetch(`${BASE_TECNOLOGIA}/eu`, { headers: autorizacao() }),
      ]);
      if (!respProdutos.ok || !respPessoas.ok) {
        setErro("Não foi possível carregar os Produtos.");
        return;
      }
      setProdutos(await respProdutos.json());
      setPessoas(await respPessoas.json());
      // O "eu" NÃO entra na condição acima de propósito: ele decide apenas se
      // os controles do Vínculo aparecem, e uma aba inteira em erro vermelho
      // porque essa rota falhou seria desproporcional. Sem resposta, o default
      // restrito vale e o resto da aba funciona.
      setEu(respEu.ok ? await respEu.json() : EU_DESCONHECIDO);
      setErro(null);
    } catch (e) {
      console.error("[admin/tecnologia] falha ao carregar", e);
      setErro(FALHA_DE_CONEXAO);
    }
  }, [token, autorizacao]);

  useEffect(() => {
    if (carregandoAuth) return;
    if (!token) {
      // Sem token `carregar` desiste na primeira linha e os Produtos nunca
      // chegam ao card aberto. Dizer o que aconteceu é melhor do que calar.
      setErro(SEM_SESSAO);
      return;
    }
    carregar();
  }, [carregandoAuth, token, carregar]);

  return (
    <div className="animate-fade-in-up space-y-6">
      <div className="flex items-center gap-3">
        <div className="p-2 rounded-xl bg-primary/10 text-primary">
          <Cpu className="w-6 h-6" />
        </div>
        <div>
          <h1 className="text-2xl font-bold text-text">Tecnologia</h1>
          <p className="text-sm text-text-secondary">
            As Demandas entre o hospital e a Vitta sobre os sistemas.
          </p>
        </div>
      </div>

      {/* O aviso de quando Produtos ou pessoas não carregaram: o Quadro e o
          Painel usam os dois no card aberto, e sem ele a escolha de Produto
          ficaria vazia e calada. */}
      {erro && (
        <p
          role="alert"
          className="flex items-start gap-2 px-4 py-3 rounded-xl bg-red-50 border border-red-200 text-red-700 text-sm"
        >
          <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
          <span>{erro}</span>
        </p>
      )}

      <div className="flex gap-2 border-b border-border" role="tablist">
        {ABAS.map((item) => (
          <button
            key={item.id}
            role="tab"
            aria-selected={aba === item.id}
            onClick={() => setAba(item.id)}
            className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
              aba === item.id
                ? "border-primary text-primary"
                : "border-transparent text-text-secondary hover:text-text"
            }`}
          >
            {item.label}
          </button>
        ))}
      </div>

      <div role="tabpanel">
        {aba === "quadro" && (
          <QuadroDemandas
            token={token}
            carregandoAuth={carregandoAuth}
            produtos={produtos}
            pessoas={pessoas}
            eu={eu}
          />
        )}
        {aba === "painel" && (
          <PainelDemandas
            token={token}
            carregandoAuth={carregandoAuth}
            produtos={produtos}
            pessoas={pessoas}
            eu={eu}
          />
        )}
      </div>

    </div>
  );
}
