"""Gera a base de nomes próprios brasileiros da pseudonimização (issue #412).

Saída: `app/services/dados/nomes_proprios_br.txt`, um nome por linha, sem
acento e em minúsculas, que o `ouvidoria_pseudonimizacao` carrega no import.

Este script NÃO roda em produção nem em teste. Ele existe para que a base seja
reproduzível e para que a origem de cada linha esteja escrita em algum lugar:
o arquivo gerado é congelado no repositório e revisado como código.

Duas fontes:

1. **Prenomes**: Censo Demográfico 2010 do IBGE, tabela de nomes por década de
   nascimento, publicada em https://github.com/datasets-br/prenomes (CSV
   `data/nomes-censos-ibge.csv`, domínio público). Ficam os nomes com pelo
   menos `CORTE_DE_FREQUENCIA` registros somados em todas as décadas. Corte
   mais baixo entrega nome raro; corte mais alto deixa de fora nome de gente
   que reclama na Ouvidoria. Ver a medição de sobre-apagamento no PR da #412.
2. **Sobrenomes**: lista curada à mão neste arquivo. O Censo do IBGE publica
   prenome, não sobrenome, então não há fonte oficial equivalente. São os
   sobrenomes de uso corrente no Brasil, escritos aqui um a um.

Uso:

    uv run python scripts/gerar_nomes_proprios_br.py            # baixa o CSV
    uv run python scripts/gerar_nomes_proprios_br.py caminho.csv  # CSV local
"""

from __future__ import annotations

import csv
import io
import pathlib
import sys
import unicodedata
import urllib.request

CSV_DO_IBGE = "https://raw.githubusercontent.com/datasets-br/prenomes/master/data/nomes-censos-ibge.csv"
CORTE_DE_FREQUENCIA = 5_000

DESTINO = pathlib.Path(__file__).resolve().parent.parent / "app" / "services" / "dados" / "nomes_proprios_br.txt"

# Sobrenomes brasileiros de uso corrente, curados à mão. Ficaram DE FORA os
# que também são palavra comum do relato de ouvidoria e que, sozinhos, não
# valem o risco de apagar contexto: "mata", "pena", "conde", "cortes", "sá",
# "oliva", "sorte", "dores". Os que entraram apesar de terem outro sentido
# ("cruz", "luz", "porto", "campos", "serra") são frequentes demais como
# sobrenome para ficar de fora, e nenhum deles apaga nada sozinho: a camada
# exige duas palavras de nome seguidas.
SOBRENOMES = """
abreu aguiar albuquerque alencar almeida alves amaral amorim andrade antunes
aragao araujo arruda assis assuncao avila azevedo bahia balbino bandeira
barbalho barbosa barcelos barreto barros bastos batista bezerra bittencourt
boaventura bonfim borba borges braga brandao branco brito bueno caldas camargo
caminha campelo campos canuto cardoso carneiro carvalho castro cavalcante
cavalcanti chaves coelho colares cordeiro correa correia costa coutinho couto
cruz cunha damasceno dantas delgado dias diniz drummond duarte esteves falcao
faria farias felix fernandes ferraz ferreira figueiredo filgueiras fogaca
fonseca fontes fraga franca franco freire freitas furtado galvao garcia godoy
goes gomes goncalves gouveia guedes guerra guimaraes gusmao holanda jesus
junqueira lacerda lage lameira lara leal leite lemos lima lins lopes loureiro
lucena macedo machado maciel magalhaes maia malta marinho marques martins
mascarenhas matias matos mattos medeiros meireles melo mello mendes mendonca
menezes mesquita miranda monteiro moraes morais moreira mota motta moura muniz
murta nascimento nery neves nobre nogueira novaes nunes pacheco padilha paiva
parente passos pedrosa peixoto penha pereira pessoa pimentel pinheiro pinto
pires pontes portela porto prado quadros queiroz quintanilha rabelo ramos
rangel raposo rebelo rego reis rezende ribeiro rios rocha rodrigues roriz
rosario sabino saldanha sales salgado sampaio santana santos sarmento senna
sepulveda sequeira serpa serra siqueira silva silveira simoes soares sobral
sodre solano sousa souza tavares teixeira teles telles tenorio tolentino
toledo torres trajano trindade uchoa valadares valadao valente varela vargas
vasconcelos vaz veiga veloso ventura verissimo viana vidal vieira vilaca vilar
vilela vitorino wanderley xavier zanella zanetti zanini
""".split()


def sem_acento(palavra: str) -> str:
    decomposto = unicodedata.normalize("NFD", palavra)
    return "".join(letra for letra in decomposto if not unicodedata.combining(letra))


def prenomes_do_ibge(linhas: io.TextIOBase) -> set[str]:
    escolhidos = set()
    for linha in csv.DictReader(linhas):
        total = sum(int(linha[coluna] or 0) for coluna in linha if coluna != "Nome")
        if total < CORTE_DE_FREQUENCIA:
            continue
        nome = sem_acento(linha["Nome"].strip().lower())
        # Duas letras é sigla, não nome ("Tv", "Jr"), e o que não é só letra
        # vem de erro de digitação no recenseamento.
        if len(nome) >= 3 and nome.isalpha():
            escolhidos.add(nome)
    return escolhidos


def main() -> None:
    if len(sys.argv) > 1:
        with open(sys.argv[1], encoding="utf-8") as arquivo:
            prenomes = prenomes_do_ibge(arquivo)
    else:
        with urllib.request.urlopen(CSV_DO_IBGE) as resposta:  # noqa: S310
            prenomes = prenomes_do_ibge(io.StringIO(resposta.read().decode("utf-8")))

    nomes = sorted(prenomes | {sem_acento(sobrenome) for sobrenome in SOBRENOMES})
    cabecalho = (
        "# Nomes próprios brasileiros para a pseudonimização da Ouvidoria (issue #412).\n"
        "# GERADO por scripts/gerar_nomes_proprios_br.py. Não edite à mão.\n"
        f"# Prenomes: Censo 2010 do IBGE, frequência total >= {CORTE_DE_FREQUENCIA}.\n"
        "# Sobrenomes: lista curada no próprio script (o Censo não publica sobrenome).\n"
        "# Sem acento, minúsculas, um por linha, ordem alfabética.\n"
    )
    DESTINO.parent.mkdir(parents=True, exist_ok=True)
    DESTINO.write_text(cabecalho + "\n".join(nomes) + "\n", encoding="utf-8")
    print(f"{len(nomes)} nomes em {DESTINO}")


if __name__ == "__main__":
    main()
