"""Pseudonimização do texto da Ouvidoria antes da IA externa (issues #342, #412, #398 e #441).

Função pura: entra texto livre da Manifestação, sai o mesmo texto com os dados
pessoais trocados por marcadores. Não lê banco, não fala com rede, não olha o
relógio. O relato original nunca sai deste banco (ADR 0034; PRD #319, história
17): o que viaja até o OpenRouter é a saída daqui.

A ordem das regras é parte do contrato, porque os desenhos se sobrepõem: o
email sai antes de tudo (tem ponto e dígito dentro), o CPF antes do telefone
(onze dígitos crus servem aos dois) e o Protocolo antes do telefone
("2026-0007" cabe no desenho de um fixo com DDD). O nome vem por último, sobre
um texto onde os números já viraram marcador.

Os seis identificadores da issue #398 entraram nessa mesma fila, cada um com
marcador próprio, e o lugar de cada um na ordem tem motivo:

- o handle de rede social (`[REDE_SOCIAL]`) sai LOGO DEPOIS do email, porque a
  arroba é a mesma: antes dele, comeria o local part e deixaria o domínio;
- placa (`[PLACA]`), RG (`[RG]`), CEP (`[CEP]`) e CNS (`[CNS]`) saem ANTES do
  telefone, porque a regra dos oito dígitos ou mais morde a cabeça de todos
  eles. Era assim que o CNS saía pela metade ("[TELEFONE] 6586 452"), e meio
  identificador no texto é pior que o identificador inteiro: tem cara de
  anonimizado e não é;
- o CNS também sai antes do PROTOCOLO, e isso é da issue #441: um cartão cujo
  miolo tem cara de ano ("445-3494-2018-2675") saía pela metade,
  "445-3494-[PROTOCOLO]". Quem conta quinze dígitos vai na frente de quem
  desenha quatro;
- o RG sai depois do CPF, que já levou o desenho `3.3.3-2` e tem rótulo
  próprio;
- a rede do CPF em pontuação torta (`_mascarar_cpf_pontuado`, issue #441) é a
  ÚLTIMA da fila numérica, logo antes do telefone: ela é a mais larga de
  todas, e rodando cedo partia um CNS ao meio. Rede larga vai depois de
  desenho específico, sempre;
- a data de nascimento (`[DATA_NASCIMENTO]`) sai cedo, mas só ATRÁS DE PISTA:
  leia o parágrafo dela nos limites conhecidos.

O separador dentro de um número não é um caractere só (issue #441). Quem digita
no balcão põe espaço antes do hífen, e texto colado de PDF chega com espaço
duplo: CPF e telefone aceitam até três caracteres de separador, sem atravessar
parágrafo. Era por aí que o número inteiro passava.

Nome tem três regras, porque a grafia carrega evidências diferentes:

1. **Desenho** (`_SEQUENCIA_DE_NOME`), para o texto em caixa mista: duas ou
   mais palavras capitalizadas seguidas, com conectivos, iniciais do meio
   ("Maria S. Souza") e apóstrofo ("Maria D'Ávila"). Caixa alta só conta como
   desenho quando o texto NÃO é predominantemente maiúsculo: num relato escrito
   todo em caixa alta, toda palavra teria cara de nome e o texto viraria
   marcador.
2. **Pista** (`_PISTA_DE_NOME`), sem olhar caixa: depois de "meu nome é", "me
   chamo", "Sr.", "Dra." e afins, o que vem é a pessoa de quem o relato fala.
   É o que pega o nome digitado todo em minúsculas pelo celular do QR, onde o
   desenho não diz nada.
3. **Base de nomes** (`_NOMES_PROPRIOS`, issue #412), por ÚLTIMO, sem olhar
   caixa nem pista: duas palavras seguidas que estejam na base de nomes
   próprios brasileiros do repositório viram um marcador só, com os conectivos
   do meio dentro. É a regra que fecha o canal do QR, onde a pessoa digita tudo
   em minúsculas e não se apresenta. Aqui o padrão é NÃO ser nome: quem não
   está na base não vira marcador por parecer nome, e uma palavra sozinha nunca
   basta.

   A ordem importa e ela é por último de propósito. Rodando primeiro, o
   marcador que ela deixa cortaria a frase no meio: nem o desenho nem a pista
   atravessam o `[`, e o sobrenome que elas apagavam sozinhas ficaria órfão no
   texto ("Maria Silva Kowalski" virava "[NOME] Kowalski"). Por último, ela só
   acrescenta: um `[NOME]` já posto conta como nome na varredura dela, então o
   que sobrou ao lado é absorvido pelo marcador.

O vocabulário da casa (áreas, palavras do caso, canais, tempo e as palavras
comuns do português) é **neutro** nas duas regras: nunca vira nome sozinho, mas
também não parte um nome ao meio. Um nome que contenha uma dessas palavras
("Maria Marco Silva") some inteiro; o que sobrevive é a palavra do vocabulário
quando ela está na BORDA do nome, e é isso que devolve a área ao texto ("[NOME]
do Centro Cirúrgico" em vez de "[NOME]").

Limites conhecidos. Esta seção é honesta de propósito, e ela mudou na issue
#412: a base de nomes fechou os quatro vazamentos que a #342 tinha deixado
abertos. O que virou GARANTIA e o que continua ESFORÇO está separado abaixo.
Quem chamar esta função e mandar o resultado para uma IA externa precisa ler as
duas listas.

O que virou garantia (cada item tem teste em `TestNomePelaListaDeNomes`):
- nome completo cujas palavras estão na base some em QUALQUER caixa e sem
  precisar de pista, inclusive o relato todo em minúsculas do canal do QR
  (ADR 0036), que era o vazamento 1;
- conectivo no meio ("maria da conceicao ferreira") não parte mais o nome nem
  gasta teto de pista: a base anda pelo grupo inteiro (vazamento 2);
- a guarda de caixa alta lê o texto ORIGINAL, então os marcadores maiúsculos
  que as outras regras deixam não a desligam mais, e a base pega o nome mesmo
  quando ela desliga de verdade (vazamento 3);
- sobrenome com terminação de verbo ("Clemente") não escapa mais: quem está na
  base é nome, e a heurística de terminação não desfaz isso (vazamento 4).

O que continua esforço, NÃO garantia:
- nome que não está na base (estrangeiro, raro, apelido, grafia inventada) só
  some pelo desenho, ou seja, se estiver em caixa mista, ou atrás de pista, ou
  ainda por estar colado num nome que a base reconheceu. A
  base tem os prenomes do Censo 2010 do IBGE com frequência total de 5 mil ou
  mais e uma lista curada de sobrenomes: nome fora desse corte, escrito todo em
  minúsculas e sem pista, ATRAVESSA;
- primeiro nome sozinho ("Carlos") continua só saindo atrás de pista. A base
  exige duas palavras de nome seguidas, senão "levou uma rosa para o leito"
  perderia a flor junto com a pessoa;
- palavra que é nome E é do vocabulário da casa ("Socorro", "Matheus",
  "Domingo") vale como nome na base e como palavra da casa no desenho. Quem
  protege "Pronto Socorro" e "Hospital São Matheus" é a parede comum: "Pronto"
  e "São" não estão na base, e uma palavra fora da base já parte o grupo;
- duas palavras ambíguas coladas, cada uma nome de gente E palavra de todo dia
  ("santa vitoria", "porto de santos"), viram marcador. A dúvida resolve para
  o mesmo lado que o resto do módulo: perder contexto, nunca vazar pessoa;
- área que não está no vocabulário e vem colada no nome ("Joao Silva da
  Nefrologia") some junto com ele: entre vazar sobrenome e perder o nome da
  área, o critério manda perder a área;
- número ambíguo sai sob o marcador do vizinho, e sequência de oito dígitos ou
  mais vira `[TELEFONE]` mesmo quando não é telefone. O rótulo erra e um número
  inocente às vezes some junto; o que não acontece é dado pessoal atravessar;
- data de nascimento SEM pista atravessa (issue #398). "Nasci em 12/08/1975",
  "Data de nascimento - 12/08/1975", "Nasc. 12/08/1975" e "O paciente nasceu em
  12/08/1975" viram marcador; "12/08/1975" solto no meio da frase, não.
  Nascimento e atendimento têm o mesmo desenho, e apagar toda data completa
  levaria junto o dia do fato, que é de onde a sugestão de ação corretiva tira
  o que corrigir. Aqui a dúvida resolveu para o lado do CONTEXTO, ao contrário
  do resto do módulo, e é decisão de domínio registrada na issue;
- RG sem pontuação e sem dígito verificador ("12345678" cru) sai como
  `[TELEFONE]`, pela rede dos oito dígitos. O rótulo erra, o dado não vaza;
- valor em reais escrito no desenho do RG ("R$ 12.345.678") sai como `[RG]`.
  A pontuação `2.3.3` é o que prova o documento quando o verificador não vem
  junto, e ela não distingue documento de dinheiro;
- RG com letra colada no verificador ("12.345.678-9X") deixa o `-9X` no texto.
  O corpo do documento some; o verificador sozinho não identifica ninguém;
- CEP exige o hífen. "20040020" corrido sai como `[TELEFONE]`, de novo com o
  rótulo errado e sem vazar;
- sigla de três letras colada em quatro dígitos ("UTI2024") vira `[PLACA]`. Com
  espaço no meio ("UTI 2024") ela fica, que é o caso comum no relato;
- bloco numérico de quinze dígitos que NÃO é CNS sai como `[CNS]`: "telefone
  21 98765-4321 1234 vezes" soma quinze e vira o marcador errado. O rótulo
  erra, o dado não vaza;
- bloco MAIOR que quinze só some quando algum trecho dele soma quinze exatos,
  que é o desenho de um cartão com um vizinho colado. Uma enumeração escapa
  dessa varredura ("Leitos 12, 14, 15, 18, 20, 22, 24, 26" pula de catorze
  para dezesseis e fica), e dois telefones colados saem os dois. Data nenhuma
  é atingida, em nenhuma grafia e em nenhuma quantidade, porque as datas saem
  do texto antes e voltam depois;
- lista de números cujos grupos POR ACASO somam quinze em algum trecho vira um
  `[TELEFONE]` só. É o preço que sobrou, e ele é estreito;
- CEP escrito com espaço ("20040 020") atravessa. O espaço ficou fora do
  separador de propósito: "R$ 12.345 678" tem o mesmo desenho de cinco mais
  três, e dinheiro virava endereço. Com hífen ou ponto o CEP some;
- placa em minúsculas atravessa, com hífen ou sem ("abc-1234"). A placa exige
  CAIXA ALTA, senão ela come abreviação de mês ("nov-2024", "jan-2026") e
  sigla interna ("SAC-2024"), que é o mês e o assunto do fato indo embora.
  Sigla da casa em caixa alta com quatro dígitos ("UTI-2024", "UTI2024")
  continua virando `[PLACA]`, e esse é o preço que ficou;
- hora e valor colados numa arroba ("14h@recepcao") saem como `[EMAIL]`. O
  desenho exige letra antes da arroba e domínio pontuado ou todo de letras, o
  que já barra "Cheguei@8h" e "100,00@farmacia", mas não separa um domínio
  interno de uma palavra qualquer;
- número com cara de ano e barra vira `[PROTOCOLO]` mesmo sem ser ("sala
  2026/103"), e Protocolo com sufixo ("2026-0007-01") deixa o "-01" para
  trás. Aceitar a barra e o terceiro dígito foi pedido pela issue, e este é o
  preço;
- perfil de rede social que comece com dígito ("@123maria") atravessa. A
  arroba seguida de número é hora ("@8h") ou preço unitário ("@2,50") muito
  mais vezes do que é perfil;
- RG de SETE dígitos escrito cru, sem pontuação e sem verificador ("1234567"),
  atravessa: a rede do telefone começa em oito dígitos e nenhuma outra regra o
  alcança. Com oito dígitos ele vira `[TELEFONE]`, com o verificador ou com os
  pontos vira `[RG]`;
- valor colado numa arroba com domínio de letras ("100,00@farmacia") sai como
  `[EMAIL]`. É a conta de fechar o login de matrícula em domínio interno
  ("12345@intranet"), que é dado pessoal e atravessava inteiro: os dois têm o
  mesmo desenho, e a dúvida resolve para o lado de não vazar;
- endereço interno sem ponto no domínio ("maria@intranet") sai como `[EMAIL]`
  desde a revisão do PR da #398. Antes atravessava inteiro, porque a regra de
  email exigia o ponto e a do handle recusa arroba colada em palavra;
- a data de nascimento depende inteiramente da PISTA, então pista que falta é
  a única forma de ela vazar. Estão cobertas "data de nascimento",
  "nascimento", "nascto", "nasc", "nasci", "nascido", "nascida", "nasceu",
  "dn" e "d.n.", com dois pontos, hífen, parêntese ou um conector ("em", "no
  dia", "na data de", "dia", "ao", "aos", "no", "nos") entre a pista e a data,
  e com pontuação dos DOIS lados do conector desde a issue #441 ("nasci em:
  24-7-1979"). Grafia fora dessa lista atravessa;
- Protocolo cujo sequencial é um ano de zero a dez à frente do ano dele
  ("2025/2028") continua lido como INTERVALO e atravessa (issue #441). A
  dúvida resolveu para o lado do contexto porque "exercício 2025/2026" e
  "gestão 2025/2028" são escritos o tempo todo, e um sequencial de protocolo
  nessa faixa exige mais de mil e novecentas manifestações no ano. Andando
  para trás ("2026/1916") ou para além de dez anos, é Protocolo e some;
- bloco de onze dígitos que fecha o dígito verificador POR ACASO vira `[CPF]`,
  mesmo sendo dois números vizinhos que só somam onze juntos. É uma chance em
  cem, o rótulo erra e nada vaza;
- CPF partido em mais de QUATRO pedaços ("5, 2, 9, 9, 8, 2, 2, 4, 7, 2, 5")
  atravessa. Quatro é o teto do desenho ("123 456 789 09"), e a alternativa
  era pior: sem ele, uma enumeração de leitos cujos dígitos por acaso fechem o
  verificador sumiria inteira do relato;
- CPF digitado ERRADO em pontuação torta ("529982.247-26", com o verificador
  que não fecha) atravessa. Nessa grafia quem prova o documento é a conta, não
  o desenho, e uma rede que aceitasse onze dígitos em pontuação qualquer sem
  conferir nada comeria número de nota, de guia e de valor;
- o separador repetível pode juntar dois números vizinhos num telefone só
  ("12  3456  7890"). É o preço de aceitar o espaço duplo do texto colado, e
  ele é do mesmo lado da dúvida que o resto do módulo: apaga demais, não de
  menos. Parágrafo continua sendo parede.

O custo da base foi medido antes de ela entrar (issue #412): em 40 relatos de
ouvidoria sem nenhum nome de pessoa (433 palavras) e em 28 mil palavras de
português técnico deste repositório, ela não apagou NENHUMA palavra a mais do
que a versão anterior. Nos relatos com nome, as palavras de nome que
sobreviviam caíram de 13 para nenhuma.

O custo desta rodada foi medido do mesmo jeito (issue #441): em 20 mil relatos
gerados SEM dado pessoal nenhum, a saída é caractere por caractere igual à da
versão anterior, e no fluxo do relatório mensal (#346) segue um único rótulo
alterado, o mesmo de antes ("Laboratorio de Analises Clinicas", que tem desenho
de nome de gente).

CPF, telefone, email e Protocolo eram descritos aqui como "a parte sólida, que
passou por dois ataques independentes sem saída". Isso deixou de ser verdade na
issue #441: o fuzz diferencial gerou 40 mil relatos com identificador em grafia
variada e achou 1.899 entradas em que a versão anterior deixava passar dado
pessoal, em quatro dos identificadores (CPF, telefone, CNS e Protocolo).
Nenhuma delas veio de leitura de código; todas vieram de gerar grafia. A conta
depois das correções é zero, em quatro sementes diferentes, e a lição que fica
não é que agora está sólido: é que review não substitui geração de entrada.
"""

from __future__ import annotations

import pathlib
import re
import unicodedata

MARCADOR_EMAIL = "[EMAIL]"
MARCADOR_CPF = "[CPF]"
MARCADOR_TELEFONE = "[TELEFONE]"
MARCADOR_PROTOCOLO = "[PROTOCOLO]"
MARCADOR_CNS = "[CNS]"
MARCADOR_RG = "[RG]"
MARCADOR_CEP = "[CEP]"
MARCADOR_PLACA = "[PLACA]"
MARCADOR_REDE_SOCIAL = "[REDE_SOCIAL]"
MARCADOR_DATA_NASCIMENTO = "[DATA_NASCIMENTO]"
MARCADOR_NOME = "[NOME]"

# O `{1,64}` do local part não é capricho: com `+` livre, um texto longo sem
# arroba faz a busca varrer o mesmo trecho de novo a cada posição (medido: 7s
# em 50 mil caracteres). 64 é o teto do local part no RFC 5321.
_EMAIL = re.compile(r"[\w.+-]{1,64}@(?:[\w-]{1,63}(?:\.[\w-]{1,63}){1,8}|[A-Za-z][\w-]{1,62}(?![\w-]))")


# Handle de rede social (issue #398). Sai LOGO DEPOIS do email, nunca antes: a
# arroba do email é a mesma, e rodando primeiro esta regra comeria o local part
# e deixaria o domínio no texto. Depois do email, toda arroba que sobrou é
# perfil de alguém.
#
# Sem teto de tamanho, e isso é correção da revisão do PR: com `{1,29}`, o
# handle mais comprido que trinta caracteres não casava e vazava INTEIRO, em
# vez de sair cortado. Teto que falha para o lado do vazamento é pior que
# teto nenhum.
#
# O fim `(?:[\w.]*[\w])?` obriga o casamento a terminar em letra ou dígito. O
# ponto é parte do handle no meio ('maria.silva88') e não é no fim: comendo o
# ponto final, o marcador colava duas frases numa só.
_HANDLE = re.compile(r"(?<![\w@.])@[A-Za-z_](?:[\w.-]*[\w])?")

# Data de nascimento (issue #398), e SÓ ela. Nascimento e atendimento têm o
# mesmo desenho ("12/08/1975" e "12/08/2026"), então quem separa os dois é a
# PISTA que vem antes. Apagar toda data completa fecharia o vazamento inteiro,
# só que levaria junto o dia do fato, que é de onde a sugestão de ação
# corretiva tira o "o que corrigir". Sem pista, a data fica: está escrito nos
# limites conhecidos, no topo.
# Dia/mês/ano e a forma ISO ano-mês-dia, que aparece quando alguém copia de
# tela de sistema.
#
# Os três campos são VALIDADOS, e não é preciosismo: este desenho peneira o
# texto inteiro em `_guardar_datas`, e o que ele arranca escapa de todas as
# regras numéricas. Frouxo, ele lia a cabeça de um telefone pontuado como data
# ("55.21.9876" dentro de "+55.21.98765432"), tirava-a do caminho e devolvia o
# telefone inteiro ao texto no fim. Peneira larga demais não filtra, vaza.
#
# As guardas das pontas fecham o outro lado do mesmo buraco: sem elas, a data
# casaria no MEIO de um número mais comprido. Elas recusam dígito colado e
# dígito atrás de separador, e deixam passar o ponto final da frase.
#
# A guarda da frente abre exceção para OUTRA DATA, e essa exceção é o
# intervalo: em "12/08/2026-13/09/2026" o hífen leva a um dígito, mas o que
# vem depois dele é uma data inteira, não a cauda de um número.
_DIA = r"(?:0?[1-9]|[12]\d|3[01])"
_MES = r"(?:0?[1-9]|1[0-2])"
_ANO = r"(?:(?:19|20)\d{2}|\d{2})"
_DATA = rf"{_DIA}[/.-]{_MES}[/.-]{_ANO}|(?:19|20)\d{{2}}[/.-]{_MES}[/.-]{_DIA}"
_BORDA_DA_DATA_ATRAS = r"(?<!\d)(?<![\d][.\-/])"
_BORDA_DA_DATA_ADIANTE = rf"(?!\d)(?![.\-/](?!{_DATA})\d)"
# A pista, e depois dela o que pode aparecer ANTES da data: dois pontos, hífen,
# parêntese, um "em" solto. A folga toda vem da revisão do PR, que achou seis
# grafias vazando por um separador que a primeira versão não previa
# ("Data de nascimento - ", "Nascimento em ", "Nasc. ").
_PISTA_DE_NASCIMENTO = r"data de nascimento|nascimento|nascto|nasc\.?|nasci(?:d[oa])?|nasceu|d\.?n\.?"
# O que cabe entre a pista e a data. "no dia" é pelo menos tão comum quanto
# "em" num relato escrito, e conector que falta é a única forma de esta regra
# vazar, porque ela é toda governada por pista.
_PONTE_ATE_A_DATA = r"(?:em|no dia|na data de|dia|aos?|nos?)"
# O separador vale dos DOIS lados do conector, e isso é achado do fuzz
# diferencial da issue #441: com ele só antes, "nasci em: 24-7-1979" e
# "nascimento no dia - 21/07/1992" atravessavam inteiros, porque o conector
# exigia espaço colado na data. Foram 71 das 4 mil entradas geradas, todas com
# a mesma raiz. Ele não atravessa letra, então a pista continua sem alcançar a
# data da frase seguinte ("Nasci em Belo Horizonte. Consulta em 12/08/2026").
_SEPARADOR_DA_PISTA = r"[\s:.\-()]*"
_DATA_DE_NASCIMENTO = re.compile(
    rf"(?P<pista>\b(?:{_PISTA_DE_NASCIMENTO}){_SEPARADOR_DA_PISTA}"
    rf"(?:{_PONTE_ATE_A_DATA}{_SEPARADOR_DA_PISTA})?)(?P<data>{_DATA})(?!\d)",
    re.IGNORECASE,
)

# O separador que aparece DENTRO de um número escrito à mão, e que não é um
# caractere só: quem digita no balcão põe espaço antes do hífen ("529.982.247
# - 25") e o texto colado de PDF chega com espaço duplo. É a mesma cura que o
# CNS já tinha no separador dele, e o fuzz da issue #441 mostrou que o CPF e o
# telefone continuavam com a doença. O teto de três caracteres existe para
# limitar o trabalho da busca; a quebra de linha entra sozinha, porque duas
# seguidas são parágrafo novo e número não atravessa parágrafo.
#
# A BARRA fica de fora dele, e vale só no CPF, que sempre a aceitou: ela é o
# que separa ano de ano ("exercício 2025/2026"), e dentro do telefone ela fazia
# o intervalo virar número de telefone.
_SEPARADOR_CURTO = r"(?:[ \t.-]|\n(?!\n)){1,3}"
_SEPARADOR_CURTO_OPCIONAL = r"(?:[ \t.-]|\n(?!\n)){0,3}"
_SEPARADOR_DO_CPF = r"(?:[ \t./-]|\n(?!\n)){1,3}"

# CPF separado é forma inconfundível: nenhum outro número do relato tem esse
# desenho, então não precisa de conferência de dígito para ser reconhecido. Os
# separadores são os que aparecem no balcão: ponto, espaço, hífen e barra.
_CPF_SEPARADO = re.compile(
    rf"(?<!\d)\d{{3}}{_SEPARADOR_DO_CPF}\d{{3}}{_SEPARADOR_DO_CPF}\d{{3}}{_SEPARADOR_DO_CPF}\d{{2}}(?!\d)"
)

# Onze dígitos seguidos são ambíguos: tanto um CPF cru quanto um celular com
# DDD têm esse tamanho. Quem desempata é o dígito verificador, que o celular
# não tem por que fechar. Nada escapa por causa do empate: o que não fecha aqui
# cai na regra de telefone logo abaixo e some do mesmo jeito.
_DIGITOS_11 = re.compile(r"(?<!\d)\d{11}(?!\d)")


# Os pesos do módulo 11, pré-computados. A conta é a mesma da Receita; o que
# muda é não recalcular `tamanho + 1 - i` a cada dígito. Vale a pena porque a
# rede do CPF (`_mascarar_cpf_pontuado`) chama esta função uma vez por trecho
# de onze dígitos do texto, e um relato cheio de número pode ter dezenas de
# milhares deles.
_PESOS_DO_VERIFICADOR = ((10, 9, 8, 7, 6, 5, 4, 3, 2), (11, 10, 9, 8, 7, 6, 5, 4, 3, 2))


def _fecha_digito_verificador(cpf: str) -> bool:
    """O CPF confere pelo módulo 11 (regra da Receita Federal)?

    A recusa dos onze dígitos iguais fica no FIM, e não na entrada: eles fecham
    o módulo 11 (é por isso que a regra existe), então perguntar por último dá
    o mesmo veredito e deixa de montar um conjunto para cada trecho que a rede
    do CPF descarta na primeira conta."""
    digitos = [ord(caractere) - 48 for caractere in cpf]
    for pesos in _PESOS_DO_VERIFICADOR:
        soma = sum(peso * digito for peso, digito in zip(pesos, digitos))
        resto = (soma * 10) % 11
        esperado = 0 if resto == 10 else resto
        if esperado != digitos[len(pesos)]:
            return False
    return len(set(digitos)) != 1


def _mascarar_cpf_cru(match: re.Match[str]) -> str:
    numero = match.group(0)
    return MARCADOR_CPF if _fecha_digito_verificador(numero) else numero


_DIGITOS_DO_CPF = 11
# Quantos pedaços um CPF tem, no máximo: "123 456 789 09" são quatro, e
# "529982.247-25" são três. Onze pedaços de um dígito são uma enumeração de
# leitos, não um documento, e sem este teto os onze dígitos de um CPF válido
# escritos como lista virariam `[CPF]`. Ele também é o que segura o custo: a
# conta do verificador deixa de rodar uma vez por posição num relato só de
# números soltos (medido: 0,15s em 250 mil caracteres, contra 0,02s com o
# teto).
_MAXIMO_DE_GRUPOS_DO_CPF = 4


def _mascarar_cpf_pontuado(match: re.Match[str]) -> str:
    """Onze dígitos num bloco, em QUALQUER pontuação, se o verificador fechar.

    A rede que o fuzz da issue #441 pediu. Ponto no lugar errado
    ("529982.247-25") tirava o documento de todos os desenhos de uma vez: não
    é 3.3.3-2, não são onze dígitos corridos, e o telefone só pega oito
    dígitos SEGUIDOS. O documento atravessava inteiro.

    Aqui o desenho não prova nada, quem prova é o dígito verificador, e é por
    isso que esta rede pode ser larga sem moer o relato: um bloco qualquer de
    onze dígitos tem uma chance em cem de fechar o módulo 11 por acaso, e
    quando fecha o que se perde é o rótulo, não o número.

    Olha TRECHO de grupos, e não o bloco inteiro, pelo mesmo motivo que o CNS:
    um número vizinho colado ("111444.777-35 2 vezes") empurra a conta para
    doze dígitos e devolveria o documento inteiro ao texto. O trecho é achado
    com somas acumuladas, uma passada só, e o marcador cobre apenas ele: o
    vizinho continua no texto.

    Roda com `_BLOCO_NUMERICO`, o mesmo casamento que conta o CNS."""
    bloco = match.group(0)
    grupos = _GRUPOS_DE_DIGITOS.findall(bloco)
    # Os dígitos do bloco inteiro, uma vez só: o candidato a documento é uma
    # FATIA desta string, e não um pedaço do bloco filtrado de novo a cada
    # trecho. O laço anda sem tocar em posição de texto, que só é procurada no
    # acerto, e acerto aqui é raro. Num relato de 250 mil caracteres só de
    # números o custo caiu de 0,23s para 0,04s no runner do CI, que é o que
    # separa este teste de tempo de passar ou de ficar instável.
    digitos_do_bloco = "".join(grupos)
    primeiro_grupo_da_acumulada = {0: 0}
    acumulada = 0
    for indice, grupo in enumerate(grupos):
        acumulada += len(grupo)
        comeco = primeiro_grupo_da_acumulada.get(acumulada - _DIGITOS_DO_CPF)
        if (
            comeco is not None
            and indice - comeco < _MAXIMO_DE_GRUPOS_DO_CPF
            and _fecha_digito_verificador(digitos_do_bloco[acumulada - _DIGITOS_DO_CPF : acumulada])
        ):
            posicoes = list(_GRUPOS_DE_DIGITOS.finditer(bloco))
            inicio, fim = posicoes[comeco].start(), posicoes[indice].end()
            return bloco[:inicio] + MARCADOR_CPF + bloco[fim:]
        primeiro_grupo_da_acumulada.setdefault(acumulada, indice + 1)
    return bloco


# Placa de veículo, nos dois desenhos que circulam hoje (issue #398): o antigo
# `ABC-1234` e o Mercosul `ABC1D23`. O separador é hífen ou nada, nunca espaço:
# com espaço, "UTI 2024" viraria placa e a área sumiria da sugestão de ação
# corretiva. Sai antes do telefone, que morderia os quatro dígitos do fim.
_PLACA = re.compile(r"(?<![\w-])[A-Z]{3}-?(?:\d{4}|\d[A-Z]\d{2})(?![\w-])")

# CEP (issue #398). Cinco dígitos, separador, três dígitos. O separador é
# EXIGIDO: sem ele, "12345678" (oito dígitos corridos, que pode ser valor ou
# nota fiscal) viraria endereço. O desenho de cinco mais quatro do telefone
# continua distinto porque termina em quatro dígitos, não três.
#
# O ponto entre os dois primeiros grupos ("20.040-020") é tipografia normal
# de CEP no Brasil, e nessa grafia ele atravessava inteiro, nem como
# `[TELEFONE]`: nenhuma outra regra tem desenho de cinco mais três.
#
# O espaço NÃO é separador aqui, e essa porta ficou fechada de propósito:
# "R$ 12.345 678" tem o mesmo desenho de cinco mais três, e dinheiro virava
# endereço. CEP escrito com espaço atravessa, e está nos limites conhecidos.
_CEP = re.compile(r"(?<![\d.\-/])(?:\d{2}\.\d{3}|\d{5})[-.]\d{3}(?![\d-]|\.\d)")

# RG (issue #398). Sai depois do CPF, que já levou o desenho `3.3.3-2`, e
# antes do telefone, senão os oito dígitos do corpo virariam `[TELEFONE]` e o
# dígito verificador ficaria órfão no texto, o mesmo defeito que o CNS tinha.
# O verificador aceita `X`, que é o que o Detran usa quando ele dá dez.
#
# Duas formas, e cada uma paga o seu preço para ser reconhecida. Com os
# pontos, o verificador é OPCIONAL, porque `12.345.678` é como a maioria
# escreve o documento e a pontuação já é prova suficiente; o custo é que um
# valor em reais escrito assim ('R$ 12.345.678') vira `[RG]`. Sem os pontos,
# o verificador é OBRIGATÓRIO, senão qualquer número de sete ou oito dígitos
# viraria documento e o rótulo perderia o sentido.
_RG = re.compile(r"(?<![\d./])(?<!\d-)(?:\d{2}\.\d{3}\.\d{3}(?:-[\dxX])?|\d{7,8}-[\dxX])(?![\w]|\.\d)")

# CNS, o cartão do SUS: quinze dígitos (issue #398). Sai ANTES do telefone,
# senão a regra dos quatro mais quatro dígitos morde o MEIO do cartão
# ("700 5083 [TELEFONE]") e devolve a cabeça ao texto.
#
# Uma tentativa de defender o outro lado da mordida com uma guarda de cauda
# NO TELEFONE foi escrita e removida no mesmo PR. Ela servia a uma ordem em
# que o telefone passava primeiro; revertida a ordem, ela deixou de ser
# coberta por qualquer teste e passou a ABRIR buraco, recusando telefone que
# tinha um número curto ao lado ("numero 12345678 1234" atravessava inteiro).
# Defesa que ninguém testa não é defesa; é código que só o mutante encontra.
#
# Quem impede a metade de sair, hoje, é o ramo do bloco MAIOR que quinze
# dígitos em `_mascarar_cns`, logo abaixo. Ele não é zelo: sem ele, um dígito
# solto ao lado do cartão empurra a conta para dezesseis e o cartão inteiro
# volta ao texto. Não apague esse ramo.
#
# A regra não é um desenho, é uma CONTAGEM: casa o bloco numérico inteiro e
# pergunta quantos dígitos ele tem. Exatamente quinze é CNS; qualquer outro
# número volta ao texto como estava. Contar em vez de desenhar é o que fecha a
# grafia torta, porque exigir o agrupamento certo (4-4-4-3, 3-4-4-4) deixava
# passar quem copia do cartão sem contar os grupos.
#
# O bloco maior que quinze some junto, e as datas não são atingidas por isso
# porque elas já saíram do texto antes (`_guardar_datas`, acima). Foram duas
# tentativas erradas até aqui: primeiro a varredura sem exceção nenhuma, que
# comia "12.08.2026 13.08.2026" inteiro; depois uma exceção de "fila de datas"
# dentro da contagem, que só valia no ramo do bloco grande e só reconhecia
# datas separadas por espaço. Guardar a data resolveu os dois de uma vez, e é
# por isso que a contagem aqui não precisa saber que datas existem.
#
# O separador não tem teto de tamanho, e isso só é seguro porque as datas já
# saíram do texto: um teto de dois caracteres deixava "7005 - 0831 - 6586 -
# 452" atravessar inteiro, e três espaços de um PDF colado faziam o cartão
# sair pela metade. Ele cobre o que aparece dentro de um número escrito à
# mão: espaço, tabulação, ponto, vírgula, hífen, barra e UMA quebra de linha.
# Duas quebras são parágrafo novo, e número não atravessa parágrafo.
_SEPARADOR_DE_NUMERO = r"(?:[ \t.,/-]|\n(?!\n))+"
# `\d+` de cada lado e separador OBRIGATÓRIO no meio. Com o separador opcional
# dentro da repetição (`\d(?:SEP*\d)*`), o mesmo trecho tem muitas maneiras de
# casar, e é a forma que costuma virar backtracking caro. Aqui a diferença
# medida foi NENHUMA, nos dois sentidos: o comportamento e o tempo são iguais
# (0,04s em 110 mil caracteres nas duas formas). Fica na forma sem ambiguidade
# porque ela é a correta, não porque ela resolveu um problema.
_BLOCO_NUMERICO = re.compile(rf"\d+(?:{_SEPARADOR_DE_NUMERO}\d+)*")
_DIGITOS_DO_CNS = 15
_GRUPOS_DE_DIGITOS = re.compile(r"\d+")


def _cabe_um_cns_dentro(bloco: str) -> bool:
    """Existe, dentro deste bloco, uma sequência de grupos que soma quinze?

    É a pergunta que separa o cartão com um vizinho colado de uma enumeração.
    "7005 0831 6586 452 3 vezes" tem dezesseis dígitos, e os quatro primeiros
    grupos somam quinze: é um CNS com um vizinho. "Leitos 12, 14, 15, 18, 20,
    22, 24, 26" também tem dezesseis, mas nenhum trecho dá quinze, porque
    grupos de dois dígitos pulam de catorze para dezesseis: é uma lista, e
    apagá-la levava embora justamente os números de que a sugestão de ação
    corretiva precisa.

    Olha TRECHO, e não prefixo, porque o cartão pode ter vizinho dos dois
    lados ("3 7005 0831 6586 452"): pelo prefixo, esse caso escapava, e o
    telefone voltava a morder o meio do cartão.

    A conta é feita com somas acumuladas, uma passada só: um trecho soma quinze
    exatamente quando a acumulada atual, menos quinze, já apareceu antes. O
    laço duplo ingênuo custava 0,74s num texto de 110 mil caracteres de datas;
    assim custa 0,04s."""
    vistas = {0}
    acumulada = 0
    for grupo in _GRUPOS_DE_DIGITOS.findall(bloco):
        acumulada += len(grupo)
        if acumulada - _DIGITOS_DO_CNS in vistas:
            return True
        vistas.add(acumulada)
    return False


# A data sai do caminho ANTES de qualquer regra numérica, e volta no fim.
#
# Este esconderijo substitui uma exceção que não deu conta. A tentativa
# anterior era "bloco que é uma fila de datas não vira marcador por tamanho", e
# ela vazava por dois lados: só valia no ramo do bloco GRANDE, então uma fila
# que somasse exatos quinze dígitos ("1/08/2026 13/09/2026") virava `[CNS]`; e
# ela só reconhecia datas separadas por espaço ou vírgula, então uma lista
# vertical, que é como se escreve um relato de verdade, virava `[TELEFONE]`.
# Cada remendo abria um buraco ao lado.
#
# Guardar é mais forte que excetuar, e é mais simples: com as datas fora do
# texto, as regras numéricas não têm como comê-las, e nenhuma delas precisa
# saber que datas existem. O lugar guardado é `\x00`, que não é dígito nem
# letra, então não vira número para uma regra nem palavra para a camada de
# nome. As datas voltam na ordem em que saíram.
_LUGAR_DA_DATA = "\x00"
_QUALQUER_DATA = re.compile(rf"{_BORDA_DA_DATA_ATRAS}(?:{_DATA}){_BORDA_DA_DATA_ADIANTE}")


def _guardar_datas(texto: str) -> tuple[str, list[str]]:
    # O NUL que vier de fora sai antes de qualquer coisa. Ele é o lugar
    # guardado, e um NUL no texto de entrada desalinhava toda a reposição:
    # cada data voltava uma posição adiante, e a última estourava a lista.
    texto = texto.replace(_LUGAR_DA_DATA, "")
    guardadas: list[str] = []

    def trocar(match: re.Match[str]) -> str:
        guardadas.append(match.group(0))
        return _LUGAR_DA_DATA

    return _QUALQUER_DATA.sub(trocar, texto), guardadas


def _repor_datas(texto: str, guardadas: list[str]) -> str:
    devolvendo = iter(guardadas)
    # `next` com padrão: a função é documentada como total, e nenhum texto de
    # entrada pode derrubá-la.
    return re.sub(re.escape(_LUGAR_DA_DATA), lambda _: next(devolvendo, ""), texto)


def _mascarar_cns(match: re.Match[str]) -> str:
    """Quinze dígitos é CNS. Mais que isso some como número comprido.

    O bloco MAIOR que quinze precisa sumir também, senão um dígito solto ao
    lado ("7005 0831 6586 452 3 vezes") empurra a conta para dezesseis e o
    cartão inteiro volta ao texto. Quem impede essa varredura de comer o dia do
    fato é `_guardar_datas`, que tira as datas do texto antes de esta função
    ver qualquer coisa."""
    bloco = match.group(0)
    digitos = sum(1 for caractere in bloco if caractere.isdigit())
    if digitos == _DIGITOS_DO_CNS:
        return MARCADOR_CNS
    if digitos > _DIGITOS_DO_CNS and _cabe_um_cns_dentro(bloco):
        return MARCADOR_TELEFONE
    return bloco


# Protocolo de ouvidoria, `ANO-NNNN` com NNNN de quatro dígitos ou mais
# (CONTEXT.md). É o "número de atendimento" da issue #342. Some antes do
# telefone: "2026-0007" também cabe no desenho de um fixo com DDD.
#
# A barra e o terceiro dígito entraram na issue #398: o número real sempre
# tem hífen e quatro dígitos, mas quem copia à mão escreve "2026/0007" e
# "2026-007", e o número errado continua sendo o atendimento de alguém. A
# data completa não é atingida porque nela o ano vem por último
# ("12/08/2026"), e ali não sobra nada depois dele para casar.
#
# A guarda que salva "exercício 2025/2026" mudou na issue #441. Ela recusava
# QUALQUER sequencial de quatro dígitos começando em 19 ou 20, e o fuzz mostrou
# o preço: o Protocolo real "2026/1916" atravessava inteiro, com o número de
# atendimento de alguém dentro. Quem separa os dois é a DISTÂNCIA, não o
# desenho: intervalo anda para a frente e anda pouco ("1999/2000",
# "2025/2026"), e sequencial de protocolo cai onde quiser. O empate
# ("2026/2027") continua resolvendo para intervalo, que é como estava.
_PROTOCOLO = re.compile(r"(?<!\d)(?P<ano>(?:19|20)\d{2})[-/](?P<sequencial>\d{3,})(?!\d)")
_INTERVALO_MAXIMO_DE_ANOS = 10


def _e_intervalo_de_anos(ano: str, sequencial: str) -> bool:
    if len(sequencial) != 4 or not sequencial.startswith(("19", "20")):
        return False
    return 0 <= int(sequencial) - int(ano) <= _INTERVALO_MAXIMO_DE_ANOS


def _mascarar_protocolo(match: re.Match[str]) -> str:
    if _e_intervalo_de_anos(match.group("ano"), match.group("sequencial")):
        return match.group(0)
    return MARCADOR_PROTOCOLO


# Telefone como quem digita à mão escreve: com ou sem +55, com DDD entre
# parênteses, solto ou colado, fixo de oito dígitos ou celular de nove.
#
# A alternativa dos dígitos corridos é aberta em cima (`\d{8,}`) de propósito:
# ela é a rede que pega o que os desenhos nomeados deixam passar, inclusive o
# CPF digitado com um dígito a mais, que não fecha o verificador e escaparia
# inteiro. Número de oito dígitos ou mais que não seja telefone sai daqui como
# `[TELEFONE]`; apagar o que não precisava custa contexto, deixar passar custa
# dado pessoal, e a dúvida resolve sempre para o mesmo lado.
# O separador repetível e o nono dígito destacado entraram na issue #441, os
# dois pelo fuzz: "21  99843  3002" (espaço duplo de PDF colado) e
# "(21) 9 8765-4321" (grafia de formulário) atravessavam, o primeiro inteiro e
# o segundo deixando o corpo do número no texto.
_TELEFONE = re.compile(
    r"(?<!\d)"
    rf"(?:\+?\s?55{_SEPARADOR_CURTO_OPCIONAL})?"  # país, opcional
    r"(?:"
    rf"\(\d{{2}}\){_SEPARADOR_CURTO_OPCIONAL}9?{_SEPARADOR_CURTO_OPCIONAL}\d{{4,5}}"
    rf"{_SEPARADOR_CURTO_OPCIONAL}\d{{4}}"  # (21) 98765-4321 e (21) 9 8765-4321
    rf"|\d{{2}}{_SEPARADOR_CURTO}9{_SEPARADOR_CURTO}\d{{4}}{_SEPARADOR_CURTO_OPCIONAL}\d{{4}}"  # 21 9 8765-4321
    rf"|\d{{2}}{_SEPARADOR_CURTO}\d{{4,5}}{_SEPARADOR_CURTO_OPCIONAL}\d{{4}}"  # 21 98765-4321
    r"|\d{8,}"  # 21987654321, 34567890, e qualquer sequência longa
    rf"|\d{{4,5}}{_SEPARADOR_CURTO}\d{{4}}"  # 98765-4321, sem DDD
    r")(?!\d)"
)

_MAIUSCULA = "A-ZÀ-ÖØ-Þ"
_MINUSCULA = "a-zà-öø-ÿ"
_LETRA = f"{_MAIUSCULA}{_MINUSCULA}"
_APOSTROFO = "'’"

# Espaço que ainda está dentro do mesmo nome: espaço comum, espaço duplo, tab,
# NBSP de colar do Word e UMA quebra de linha (o relato chega multilinha). Duas
# quebras seguidas são parágrafo novo, e nome não atravessa parágrafo.
_ESPACO = r"(?:[^\S\n]|\n(?!\n))+"

# O teto de 40 letras por palavra não é sobre nome comprido: sem ele, uma
# sequência longa de letras faz a busca tentar todos os tamanhos em cada
# posição (medido: 3,7s em 20 mil maiúsculas seguidas).
_TITULO = rf"[{_MAIUSCULA}](?:[{_MINUSCULA}]{{1,40}}|[{_APOSTROFO}][{_LETRA}][{_MINUSCULA}]{{0,40}})"
# Três letras é o piso da caixa alta: com duas, sigla de exame ("TC", "RX")
# entrava como nome e levava a frase inteira junto.
_CAIXA_ALTA = rf"[{_MAIUSCULA}]{{3,40}}"
_INICIAL_DO_MEIO = rf"[{_MAIUSCULA}]\."
_PALAVRA_DE_NOME = rf"(?:{_TITULO}|{_CAIXA_ALTA}|{_INICIAL_DO_MEIO})"

# Duas ou mais palavras seguidas, em qualquer caixa: é o trecho que a camada
# da base de nomes examina. Pontuação e parágrafo cortam o trecho, porque nome
# não atravessa nenhum dos dois. Uma palavra sozinha não entra: a camada exige
# nome E sobrenome.
#
# O `[NOME]` que as camadas anteriores deixaram conta como palavra do trecho, e
# vale como nome. É o que absorve o sobrenome que sobrou ao lado de um marcador
# ("[NOME] Kowalski" vira "[NOME]"): sem isso, o `[` cortaria o trecho e a
# palavra órfã ficaria no texto (review do PR #423).
_PALAVRA_SOLTA = rf"[{_LETRA}][{_LETRA}{_APOSTROFO}]{{0,40}}"
_PALAVRA_OU_MARCADOR = rf"(?:{re.escape(MARCADOR_NOME)}|{_PALAVRA_SOLTA})"
_SEQUENCIA_DE_PALAVRAS = re.compile(rf"{_PALAVRA_OU_MARCADOR}(?:{_ESPACO}{_PALAVRA_OU_MARCADOR})+")

_CONECTIVOS = ("de", "da", "do", "das", "dos", "e")

# O "e" fica DE FORA na base. No desenho ele é seguro, porque a caixa já provou
# que os dois lados são nome; na base, ele fazia ponte entre duas palavras de
# todo dia que por acaso também são nome ("esperei dias e dias", "fui ao porto
# de santos") e a frase inteira virava marcador (review do PR #423).
_CONECTIVOS_DA_BASE = ("de", "da", "do", "das", "dos")
_SEQUENCIA_DE_NOME = re.compile(
    rf"{_PALAVRA_DE_NOME}(?:{_ESPACO}(?:(?:{'|'.join(_CONECTIVOS)}){_ESPACO})*{_PALAVRA_DE_NOME})+"
)

# Pista que anuncia pessoa. Vale sem olhar caixa, e é o que pega o nome
# digitado em minúsculas ou em caixa alta, onde o desenho não diz nada.
# A apresentação carrega até três palavras ("meu nome é Joana Maria Pereira");
# o tratamento carrega duas, porque a terceira já costuma ser o verbo.
_PISTA_LONGA = r"meu nome (?:é|e)|me chamo|chamo-me|nome completo"
_PISTA_CURTA = r"sr|sra|srta|dr|dra|doutor|doutora|senhor|senhora"
_PISTA_DE_NOME = re.compile(
    rf"\b(?:(?P<longa>{_PISTA_LONGA})|(?P<curta>{_PISTA_CURTA}))\.?(?={_ESPACO})",
    re.IGNORECASE,
)
_PALAVRA_APOS_PISTA = re.compile(rf"({_ESPACO})([{_LETRA}][{_LETRA}{_APOSTROFO}]*\.?)")


def _sem_acento(palavra: str) -> str:
    decomposto = unicodedata.normalize("NFD", palavra)
    return "".join(letra for letra in decomposto if not unicodedata.combining(letra))


# Vocabulário neutro: nunca é nome sozinho, nunca parte um nome ao meio.
# Guardado sem acento (a comparação também tira o acento), então cada palavra
# aparece uma vez só. Os meses ficaram DE FORA de propósito: "março" sem acento
# é "marco", que é primeiro nome brasileiro comum, e cada palavra daqui que
# também é nome de gente é uma palavra que sobrevive na borda de um nome.
_NEUTRAS = frozenset(
    _sem_acento(palavra)
    for palavra in (
        # A casa e suas áreas: é disso que a sugestão de ação corretiva precisa.
        "hospital são matheus ouvidoria diretoria executiva recepção enfermagem "
        "enfermaria pronto socorro centro cirúrgico unidade terapia intensiva uti cti "
        "laboratório farmácia nutrição manutenção higiene faturamento internação "
        "ambulatório maternidade pediatria obstetrícia radiologia tomografia "
        "ressonância ultrassom imagem triagem urgência emergência hemodinâmica "
        "endoscopia oncologia cardiologia ortopedia fisioterapia psicologia "
        "odontologia nefrologia central marcação recursos humanos financeiro "
        "portaria setor sala leito quarto andar bloco ala posto clínica consultório "
        "plantão "
        # Palavras do caso, que descrevem sem identificar ninguém.
        "paciente acompanhante colaborador manifestante atendimento agendamento "
        "convênio plano saúde protocolo manifestação exame exames cirurgia consulta "
        "consultas medicamento prontuário equipe atendente recepcionista coordenador "
        "coordenadora enfermeiro enfermeira médico médica técnico técnica "
        # Canais e serviços externos citados no relato.
        "reclame aqui google whatsapp instagram facebook sus "
        # Tempo (sem os meses) e as palavras comuns que abrem frase capitalizadas.
        "ontem hoje amanhã segunda terça quarta quinta sexta sábado domingo feira "
        "eu ele ela nós meu minha seu sua nosso nossa este esta isso aquilo que "
        "não sim também então porém mas quando como onde porque muito mais menos "
        "sempre nunca ainda já aí lá aqui ali por para com sem sobre até desde "
        "após antes durante entre foi era estava fui estive fomos disse falou "
        "reclamou informou pediu relatou atendeu ligou procurou chegou saiu entrou "
        "veio respondeu quero queria preciso gostaria vim"
    ).split()
)

# Base de nomes próprios brasileiros (issue #412). Arquivo de dados congelado
# no repositório, gerado por `scripts/gerar_nomes_proprios_br.py`: prenomes do
# Censo 2010 do IBGE com frequência total de 5 mil ou mais, e sobrenomes de uso
# corrente curados à mão (o Censo não publica sobrenome). Fica dentro de `app/`
# porque é assim que ele entra na imagem do Docker (`COPY app/ app/`).
#
# Três nomes da base também são palavra da casa: "Socorro", "Matheus" e
# "Domingo". Eles ficam na base assim mesmo, e valem como nome AQUI (no desenho
# eles continuam sendo palavra da casa). Quem protege "Pronto Socorro" e
# "Hospital São Matheus" não é uma exceção, é a parede comum: "Pronto" e "São"
# não estão na base, e uma palavra fora da base já parte o grupo. Tirá-los da
# base era o que fazia "maria socorro" e "matheus ferreira" vazarem inteiros
# (review do PR #423).
_ARQUIVO_DE_NOMES = pathlib.Path(__file__).parent / "dados" / "nomes_proprios_br.txt"
_NOMES_PROPRIOS = frozenset(
    linha.strip()
    for linha in _ARQUIVO_DE_NOMES.read_text(encoding="utf-8").splitlines()
    if linha.strip() and not linha.startswith("#")
)


# Palavra terminada assim é verbo ou advérbio, não nome de gente. Vale mais que
# uma lista de verbos: é o que impede a pista de comer o resto da frase ("Sra.
# Rita confirmou") sem precisar prever cada conjugação que aparecer no relato.
_TERMINACAO_QUE_NAO_E_NOME = re.compile(r"(?:ou|eu|iu|ava|iam|aram|eram|iram|ando|endo|indo|mente)$", re.IGNORECASE)


def _para_a_pista(palavra: str) -> bool:
    """A pista deve PARAR nesta palavra?

    Ela para no vocabulário da casa, para "Dr." não comer a área que vem
    depois ("Dr. Pronto Socorro"). Mas ela não pode parar numa palavra que a
    base conhece como nome de gente: "Matheus" e "Socorro" estão nas duas
    listas, e a pista travava neles logo na primeira palavra, deixando o
    prenome inteiro no texto mesmo com "meu nome é" na frente (review do
    PR #423)."""
    limpa = _sem_acento(palavra.lower()).strip(".'’")
    if limpa in _NOMES_PROPRIOS:
        return False
    return _e_palavra_neutra(palavra)


def _e_palavra_neutra(palavra: str) -> bool:
    limpa = _sem_acento(palavra.lower()).strip(".'’")
    if limpa in _NEUTRAS:
        return True
    return len(limpa) >= 4 and _TERMINACAO_QUE_NAO_E_NOME.search(limpa) is not None


def _predominantemente_em_caixa_alta(texto: str) -> bool:
    maiusculas = sum(1 for letra in texto if letra.isupper())
    minusculas = sum(1 for letra in texto if letra.islower())
    return maiusculas > minusculas


def _papel(palavra: str, caixa_alta_conta: bool) -> str:
    """Cada palavra da sequência é nome, neutra ou conectivo."""
    if _sem_acento(palavra.lower()) in _CONECTIVOS:
        return "conectivo"
    if _e_palavra_neutra(palavra):
        return "neutra"
    if not caixa_alta_conta and palavra.isupper():
        return "neutra"
    return "nome"


def _ha_muro(papeis: list[str], inicio: int, fim: int) -> bool:
    """Duas palavras neutras seguidas separam dois nomes; uma só não separa.

    É o que devolve a área ao texto: "[NOME] do Centro Cirúrgico" em vez de um
    marcador que engoliu tudo. Uma palavra neutra sozinha não parte nada,
    porque ela pode estar no meio de um nome ("Maria Marco Silva")."""
    seguidas = 0
    for papel in papeis[inicio + 1 : fim]:
        seguidas = seguidas + 1 if papel == "neutra" else 0
        if seguidas >= 2:
            return True
    return False


def _trocar_grupos_por_marcador(palavras: list[str], espacos: list[str], grupos: list[list[int]]) -> str:
    """Cada grupo de dois nomes ou mais vira um marcador só.

    O marcador cobre do primeiro ao último nome do grupo, então o conectivo do
    meio some junto e o que estiver na BORDA fica de fora: é isso que devolve a
    área ao texto ("[NOME] do Centro Cirúrgico" em vez de só o marcador)."""
    apagados = {
        indice: indice == grupo[0] for grupo in grupos if len(grupo) >= 2 for indice in range(grupo[0], grupo[-1] + 1)
    }

    saida: list[str] = []
    for indice, palavra in enumerate(palavras):
        if indice not in apagados:
            saida.append(palavra)
        elif apagados[indice]:
            saida.append(MARCADOR_NOME)
        engoliu_o_proximo = (indice + 1) in apagados and not apagados[indice + 1]
        if indice < len(espacos) and not engoliu_o_proximo:
            saida.append(espacos[indice])
    return "".join(saida)


def _partir_em_palavras(trecho: str) -> tuple[list[str], list[str]]:
    pedacos = re.split(rf"({_ESPACO})", trecho)
    return pedacos[0::2], pedacos[1::2]


def _mascarar_sequencia(trecho: str, caixa_alta_conta: bool) -> str:
    palavras, espacos = _partir_em_palavras(trecho)
    papeis = [_papel(palavra, caixa_alta_conta) for palavra in palavras]

    grupos: list[list[int]] = []
    for indice, papel in enumerate(papeis):
        if papel != "nome":
            continue
        if grupos and not _ha_muro(papeis, grupos[-1][-1], indice):
            grupos[-1].append(indice)
        else:
            grupos.append([indice])

    return _trocar_grupos_por_marcador(palavras, espacos, grupos)


def _papel_pela_base(palavra: str) -> str:
    """Cada palavra é nome (está na base), conectivo, ou nada disso ("fora").

    Ao contrário do desenho, aqui o padrão é NÃO ser nome: quem não está na
    base não vira marcador por parecer nome. É o que deixa a camada rodar em
    qualquer caixa sem moer o relato."""
    if palavra == MARCADOR_NOME:
        return "nome"
    limpa = _sem_acento(palavra.lower()).strip(".'’")
    if limpa in _CONECTIVOS_DA_BASE:
        return "conectivo"
    return "nome" if limpa in _NOMES_PROPRIOS else "fora"


def _mascarar_trecho_pela_base(trecho: str) -> str:
    palavras, espacos = _partir_em_palavras(trecho)
    papeis = [_papel_pela_base(palavra) for palavra in palavras]

    # Aqui o muro é de UMA palavra: qualquer coisa que não seja nome nem
    # conectivo parte o grupo. O desenho precisa tolerar uma palavra do
    # vocabulário no meio do nome ("Maria Marco Silva"), porque para ele
    # "Marco" é palavra da casa; para a base, "Marco" é nome e o grupo se
    # forma sozinho. Sem essa diferença, "Carlos Nunes / Acompanhante de Rita"
    # viraria um marcador só e comeria o "Acompanhante".
    grupos: list[list[int]] = []
    for indice, papel in enumerate(papeis):
        if papel != "nome":
            continue
        colado = grupos and all(anterior == "conectivo" for anterior in papeis[grupos[-1][-1] + 1 : indice])
        if colado:
            grupos[-1].append(indice)
        else:
            grupos.append([indice])

    return _trocar_grupos_por_marcador(palavras, espacos, grupos)


def _mascarar_pela_base(texto: str) -> str:
    return _SEQUENCIA_DE_PALAVRAS.sub(lambda m: _mascarar_trecho_pela_base(m.group(0)), texto)


def _mascarar_por_desenho(texto: str, caixa_alta_conta: bool) -> str:
    return _SEQUENCIA_DE_NOME.sub(lambda m: _mascarar_sequencia(m.group(0), caixa_alta_conta), texto)


def _mascarar_por_pista(texto: str) -> str:
    """Come as palavras que vêm logo depois de uma pista de pessoa.

    Varre à mão em vez de `re.sub` porque a pista seguinte pode estar dentro do
    trecho que a anterior olhou e não comeu ("sou paciente da dra ana"): com
    `sub`, o ponteiro pularia por cima dela."""
    saida: list[str] = []
    copiado = 0
    posicao = 0
    while (pista := _PISTA_DE_NOME.search(texto, posicao)) is not None:
        teto = 3 if pista.group("longa") else 2
        cursor = pista.end()
        primeiro_espaco = ""
        comidas = 0
        while comidas < teto:
            adiante = _PALAVRA_APOS_PISTA.match(texto, cursor)
            if adiante is None or _para_a_pista(adiante.group(2)):
                break
            if not comidas:
                primeiro_espaco = adiante.group(1)
            cursor = adiante.end()
            comidas += 1
        if comidas:
            saida.append(texto[copiado : pista.end()])
            saida.append(primeiro_espaco)
            saida.append(MARCADOR_NOME)
            copiado = cursor
        posicao = cursor if comidas else pista.end()
    saida.append(texto[copiado:])
    return "".join(saida)


def pseudonimizar(texto: str | None) -> str:
    """Troca por marcador os dados pessoais do `texto`.

    Cada identificador tem marcador próprio: `[EMAIL]`, `[REDE_SOCIAL]`,
    `[CPF]`, `[RG]`, `[CEP]`, `[PLACA]`, `[CNS]`, `[DATA_NASCIMENTO]`,
    `[PROTOCOLO]`, `[TELEFONE]` e `[NOME]`.

    Nome tem garantia PARCIAL: leia a seção "Limites conhecidos" no topo do
    módulo antes de mandar a saída para fora do hospital. Nome completo cujas
    palavras estão na base de nomes brasileiros some em qualquer caixa, com ou
    sem pista (issue #412); nome fora da base só some em caixa mista ou atrás
    de pista.

    Texto ausente vira texto vazio: campo do Dossiê que nunca foi preenchido
    (`relato_integral`, `manifestante_nome`) chega aqui como `None`, e quem
    chama monta o prompt sem precisar checar antes.
    """
    if not texto:
        return ""
    # A guarda de caixa alta lê o texto ORIGINAL, antes de qualquer marcador:
    # `[CPF]`, `[TELEFONE]`, `[EMAIL]` e `[PROTOCOLO]` são maiúsculos e
    # empurravam a contagem para cima até o desenho se desligar sozinho num
    # relato escrito em caixa mista (issue #412, vazamento 3).
    caixa_alta_conta = not _predominantemente_em_caixa_alta(texto)
    texto = _EMAIL.sub(MARCADOR_EMAIL, texto)
    texto = _HANDLE.sub(MARCADOR_REDE_SOCIAL, texto)
    texto = _DATA_DE_NASCIMENTO.sub(lambda m: m.group("pista") + MARCADOR_DATA_NASCIMENTO, texto)
    texto, datas = _guardar_datas(texto)
    texto = _CPF_SEPARADO.sub(MARCADOR_CPF, texto)
    texto = _DIGITOS_11.sub(_mascarar_cpf_cru, texto)
    texto = _PLACA.sub(MARCADOR_PLACA, texto)
    texto = _RG.sub(MARCADOR_RG, texto)
    texto = _CEP.sub(MARCADOR_CEP, texto)
    # O CNS conta os quinze dígitos ANTES de o Protocolo desenhar, e essa ordem
    # é achado do fuzz da issue #441: um cartão cujo miolo tem cara de ano
    # ("445-3494-2018-2675") saía pela metade, "445-3494-[PROTOCOLO]", com sete
    # dígitos do cartão de volta no texto. É o mesmo defeito que o telefone
    # tinha, e a cura é a mesma que já valia para ele.
    texto = _BLOCO_NUMERICO.sub(_mascarar_cns, texto)
    texto = _PROTOCOLO.sub(_mascarar_protocolo, texto)
    # A rede do CPF em pontuação torta vem no fim da fila numérica, depois de
    # todo desenho específico e antes só do telefone. Foi o próprio fuzz que
    # ensinou o lugar: rodando cedo, ela achava um trecho de onze dígitos que
    # fecha o verificador por acaso DENTRO de um cartão do SUS com vizinho
    # colado, partia o cartão ao meio e devolvia a cabeça dele ao texto. Rede
    # larga vai depois de desenho específico, sempre.
    texto = _BLOCO_NUMERICO.sub(_mascarar_cpf_pontuado, texto)
    texto = _TELEFONE.sub(MARCADOR_TELEFONE, texto)
    texto = _mascarar_por_desenho(texto, caixa_alta_conta)
    texto = _mascarar_por_pista(texto)
    # A base vem por ÚLTIMO de propósito. Rodando antes, o marcador que ela
    # deixa cortaria a frase no meio: nem o desenho nem a pista atravessam o
    # `[`, e o sobrenome que elas apagavam sozinhas ficaria órfão no texto
    # ("[NOME] Kowalski"). Por último, ela só acrescenta, e o que sobrou ao
    # lado de um marcador é absorvido por ele (review do PR #423).
    texto = _mascarar_pela_base(texto)
    return _repor_datas(texto, datas)
