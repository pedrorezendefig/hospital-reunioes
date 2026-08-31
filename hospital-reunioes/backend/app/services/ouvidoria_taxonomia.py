"""O tipo da manifestação e a regra de sigilo que sai dele (issue #372).

Até aqui o sigilo era decidido por texto livre: `nasce_sigilosa()` procurava as
palavras "denuncia" e "relato de conduta" no que o ouvidor tinha digitado. Um
caso classificado como "Assédio moral" não casava com nenhuma das duas, e o
email de acionamento chegava ao setor acusado com o nome de quem manifestou.

A partir daqui quem decide é o tipo, que é lista fechada (ADR 0034, decisão 1).
O texto livre continua existindo como rótulo humano na coluna `categoria`, mas
não decide nada.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from typing import Literal, NamedTuple

# A lista fechada. Vive aqui e no CHECK da migration 077: a aplicação recusa
# antes, o banco recusa depois, e nenhuma das duas confia na outra.
TipoManifestacao = Literal["denuncia", "reclamacao", "sugestao", "elogio", "relato_de_conduta"]
TIPOS_MANIFESTACAO: tuple[str, ...] = ("denuncia", "reclamacao", "sugestao", "elogio", "relato_de_conduta")

# O marcador de "ainda não classificado" que o canal aberto grava. `categoria`,
# `setor` e `resumo` são NOT NULL com CHECK anti-vazio desde a migration 063, e
# o formulário público não pergunta nem o tema nem a área: em vez de um palpite
# que passaria por classificação de verdade, o caso entra marcado.
#
# Vive aqui, e não na rota que o escreve, porque quem CONTA precisa reconhecê-lo
# tanto quanto quem grava: "A classificar" liderando os cinco temas mais
# frequentes é a fila de triagem aparecendo como se fosse tema (PRD #319).
CATEGORIA_PENDENTE = "A classificar"
SETOR_PENDENTE = "A definir"

# Um conjunto por DOMÍNIO, e não um único com os dois marcadores dentro. Eles são
# de campos diferentes, e o conjunto único era usado contra os dois: o marcador
# da categoria descartava também a área com aquele nome, e o da área descartava a
# categoria. O valor legítimo sumia do ranking sem deixar rastro, e ainda ia
# engrossar `nao_classificados`, que é o tamanho da fila de triagem (issue #433).
#
# `NAO_CLASSIFICADO_POR_CAMPO` é o despacho: quem filtra diz de qual campo está
# falando, e campo sem marcador (`tipo_manifestacao` é lista fechada, e sem
# classificação vem NULL) não descarta nada.
CATEGORIA_NAO_CLASSIFICADA = frozenset({CATEGORIA_PENDENTE})
SETOR_NAO_CLASSIFICADO = frozenset({SETOR_PENDENTE})
NAO_CLASSIFICADO_POR_CAMPO: dict[str, frozenset[str]] = {
    "categoria": CATEGORIA_NAO_CLASSIFICADA,
    "setor": SETOR_NAO_CLASSIFICADO,
}

# Sigilosos por natureza (ADR 0034, decisão 1): o sigilo vem junto do tipo, sem
# ato humano, nos três canais de entrada.
TIPOS_SIGILOSOS = frozenset({"denuncia", "relato_de_conduta"})


def nasce_sigilosa(tipo: str | None) -> bool:
    """O caso nasce sigiloso?

    Fail-closed: sem tipo, o caso ainda não foi classificado, e o índice de
    quem está fora da Ouvidoria mostra o `resumo`, que é o começo do relato.
    Uma denúncia escrita no formulário público viraria texto visível na fila de
    todo mundo até alguém classificar. A saída é a classificação, não afrouxar
    a entrada (issue #372, decisão 4)."""
    return tipo is None or tipo in TIPOS_SIGILOSOS


# O rótulo que aparece na trilha do caso e na tela. O valor gravado é o da
# lista fechada; o humano lê a palavra dele.
ROTULO_TIPO: dict[str, str] = {
    "denuncia": "Denúncia",
    "reclamacao": "Reclamação",
    "sugestao": "Sugestão",
    "elogio": "Elogio",
    "relato_de_conduta": "Relato de conduta",
}


class SigiloTravadoError(ValueError):
    """Pedido de abaixar o sigilo de um tipo que é sigiloso por natureza."""


def resolver_sigilo(tipo: str | None, *, sigilo_atual: bool, sigilo_pedido: bool | None) -> bool:
    """O sigilo do caso depois da classificação.

    A regra automática é PISO, nunca teto: o tipo sigiloso por natureza sobe o
    sigilo sozinho e não aceita descer (issue #372, decisão 5), e para os
    demais o ouvidor decide, inclusive elevando um caso que a lista não previu.
    Sem pedido explícito, o sigilo de hoje é mantido: descer é ato consciente,
    não efeito colateral de classificar."""
    if nasce_sigilosa(tipo):
        if sigilo_pedido is False:
            raise SigiloTravadoError(
                "Denúncia e relato de conduta são sigilosos por natureza: o sigilo não pode ser retirado."
            )
        return True
    return sigilo_atual if sigilo_pedido is None else sigilo_pedido


# O teto do nome de uma área, em caracteres. Vale na escrita (o schema das
# portas que gravam setor) e na leitura pelo portão da IA, que trunca o rótulo
# antes de montar o prompt. É um número só, e vive aqui, porque subir um sem o
# outro faria a IA receber o nome cortado no meio da palavra sem ninguém ver.
LIMITE_SETOR = 200


def chave_do_setor(valor: str | None) -> str:
    """A forma de comparar dois nomes de setor: sem caixa, sem acento e com o
    espaço em branco colapsado.

    É o que faz "Recepção", "recepcao" e "RECEPÇÃO " serem a mesma área. Sem
    isto, a mesma Recepção vira duas linhas no relatório que a Diretoria lê, e
    o erro não tem sinal nenhum na tela (issue #419)."""
    texto = unicodedata.normalize("NFKD", str(valor or ""))
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", texto).strip().casefold()


def casar_setor(valor: str | None, nomes: Iterable[str]) -> str | None:
    """O nome como a taxonomia o escreve, ou None se aquela área não existe.

    A comparação é em Python de propósito, e não com `ilike` no PostgREST: ali
    `%` e `_` são curinga, e um `%` digitado casaria com o primeiro setor da
    lista. São poucas dezenas de linhas (mesma escolha de `_setor_da_taxonomia`
    no canal aberto).

    Quem bate EXATO ganha, e só depois vale a chave. A tabela `setores` é
    única por `lower(nome)` (migration 027), o que é sensível a acento: nada
    impede "Recepção" e "Recepcao" ativas ao mesmo tempo. Sem a preferência
    pelo exato, a área escolhida na tela viraria a outra conforme a ordem que o
    banco devolvesse, o acionamento não acharia o titular (`carregar_
    responsaveis` casa string exata) e a linha do relatório se partiria de
    novo, que é o oposto do que esta guarda existe para fazer."""
    procurado = chave_do_setor(valor)
    if not procurado:
        return None
    candidatos = [str(nome).strip() for nome in nomes]
    exato = str(valor).strip()
    if exato in candidatos:
        return exato
    for nome in candidatos:
        if chave_do_setor(nome) == procurado:
            return nome
    return None


class PlanoBackfill(NamedTuple):
    """O que o backfill do histórico faz e o que ele devolve ao humano.

    `correcoes` são as linhas que casam com a taxonomia e só estão escritas
    diferente. `pendencias` são as áreas que não existem na lista: elas NÃO são
    tocadas. Adivinhar aqui trocaria um número errado por outro, sem ninguém
    saber (decisão da issue #419, caminho 2)."""

    correcoes: list[dict]
    pendencias: list[dict]


def planejar_backfill(
    linhas: Iterable[dict], setores: Iterable[str], identificador: str = "protocolo"
) -> PlanoBackfill:
    """Compara o `setor` já gravado com a taxonomia.

    Serve às duas tabelas que guardam setor e precisam concordar entre si: a
    manifestação (identificada pelo protocolo) e o cadastro de responsáveis
    (pelo nome de quem responde). `carregar_responsaveis` casa string EXATA, e
    corrigir só um lado quebraria o acionamento do outro.

    Idempotente por construção: o que já está na grafia canônica não entra no
    plano, então a segunda rodada não muda nada.

    O marcador de área pendente fica de fora dos dois lados. Ele não é erro de
    digitação: é o que o canal aberto grava enquanto ninguém classificou, e
    listá-lo encheria o relatório do ouvidor com a própria fila de triagem."""
    nomes = [str(n) for n in setores]
    correcoes: list[dict] = []
    pendencias: dict[str, list[str]] = {}
    for linha in linhas:
        gravado = str(linha.get("setor") or "")
        if not gravado.strip() or gravado.strip() in SETOR_NAO_CLASSIFICADO:
            continue
        canonico = casar_setor(gravado, nomes)
        identificacao = str(linha.get(identificador) or linha.get("id") or "")
        if canonico is None:
            pendencias.setdefault(gravado, []).append(identificacao)
        elif canonico != gravado:
            correcoes.append({"id": linha.get("id"), "protocolo": identificacao, "de": gravado, "para": canonico})
    return PlanoBackfill(
        correcoes,
        [{"setor": setor, "protocolos": identificacoes} for setor, identificacoes in sorted(pendencias.items())],
    )
