"""Pseudonimização do texto da Ouvidoria antes da IA externa (issue #342).

Função pura: entra texto livre da Manifestação, sai o mesmo texto com os dados
pessoais trocados por marcadores. Não lê banco, não fala com rede, não olha o
relógio. O relato original nunca sai deste banco (ADR 0034; PRD #319, história
17): o que viaja até o OpenRouter é a saída daqui.

A ordem das regras é parte do contrato, porque os desenhos se sobrepõem: o
email sai antes de tudo (tem ponto e dígito dentro), o CPF antes do telefone
(onze dígitos crus servem aos dois) e o Protocolo antes do telefone
("2026-0007" cabe no desenho de um fixo com DDD). O nome vem por último, sobre
um texto onde os números já viraram marcador.

Nome tem duas regras, porque a grafia carrega evidências diferentes:

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

O vocabulário da casa (áreas, palavras do caso, canais, tempo e as palavras
comuns do português) é **neutro** nas duas regras: nunca vira nome sozinho, mas
também não parte um nome ao meio. Um nome que contenha uma dessas palavras
("Maria Marco Silva") some inteiro; o que sobrevive é a palavra do vocabulário
quando ela está na BORDA do nome, e é isso que devolve a área ao texto ("[NOME]
do Centro Cirúrgico" em vez de "[NOME]").

Limites conhecidos, escritos aqui para ninguém confundir alcance com garantia:
- nome em caixa alta dentro de um relato TODO em caixa alta só some se vier
  atrás de uma pista; sem pista, não há como distinguir nome de qualquer outra
  palavra ali;
- primeiro nome sozinho ("Carlos") só some atrás de pista; o critério de aceite
  fala de nome completo, e apagar toda palavra capitalizada apagaria o assunto
  do caso junto;
- área que não está no vocabulário e vem colada no nome ("Joao Silva da
  Nefrologia") some junto com ele: entre vazar sobrenome e perder o nome da
  área, o critério manda perder a área;
- número ambíguo sai sob o marcador do vizinho, e sequência de oito dígitos ou
  mais vira `[TELEFONE]` mesmo quando não é telefone. O rótulo erra e um número
  inocente às vezes some junto; o que não acontece é dado pessoal atravessar;
- identificador fora do alcance desta rotina (RG, CEP, data de nascimento,
  placa, CNS, handle de rede social) continua no texto: está registrado na
  issue #398, follow-up do PRD #319.
"""

from __future__ import annotations

import re
import unicodedata

MARCADOR_EMAIL = "[EMAIL]"
MARCADOR_CPF = "[CPF]"
MARCADOR_TELEFONE = "[TELEFONE]"
MARCADOR_PROTOCOLO = "[PROTOCOLO]"
MARCADOR_NOME = "[NOME]"

# O `{1,64}` do local part não é capricho: com `+` livre, um texto longo sem
# arroba faz a busca varrer o mesmo trecho de novo a cada posição (medido: 7s
# em 50 mil caracteres). 64 é o teto do local part no RFC 5321.
_EMAIL = re.compile(r"[\w.+-]{1,64}@[\w-]{1,255}(?:\.[\w-]{1,63}){1,8}")

# CPF separado é forma inconfundível: nenhum outro número do relato tem esse
# desenho, então não precisa de conferência de dígito para ser reconhecido. Os
# separadores são os que aparecem no balcão: ponto, espaço, hífen e barra.
_CPF_SEPARADO = re.compile(r"(?<!\d)\d{3}[.\s/-]\d{3}[.\s/-]\d{3}[.\s/-]\d{2}(?!\d)")

# Onze dígitos seguidos são ambíguos: tanto um CPF cru quanto um celular com
# DDD têm esse tamanho. Quem desempata é o dígito verificador, que o celular
# não tem por que fechar. Nada escapa por causa do empate: o que não fecha aqui
# cai na regra de telefone logo abaixo e some do mesmo jeito.
_DIGITOS_11 = re.compile(r"(?<!\d)\d{11}(?!\d)")


def _fecha_digito_verificador(cpf: str) -> bool:
    """O CPF confere pelo módulo 11 (regra da Receita Federal)?"""
    if len(set(cpf)) == 1:
        return False
    for tamanho in (9, 10):
        soma = sum(int(cpf[i]) * (tamanho + 1 - i) for i in range(tamanho))
        resto = (soma * 10) % 11
        esperado = 0 if resto == 10 else resto
        if esperado != int(cpf[tamanho]):
            return False
    return True


def _mascarar_cpf_cru(match: re.Match[str]) -> str:
    numero = match.group(0)
    return MARCADOR_CPF if _fecha_digito_verificador(numero) else numero


# Protocolo de ouvidoria, `ANO-NNNN` com NNNN de quatro dígitos ou mais
# (CONTEXT.md). É o "número de atendimento" da issue #342. Some antes do
# telefone: "2026-0007" também cabe no desenho de um fixo com DDD.
_PROTOCOLO = re.compile(r"(?<![\d-])(?:19|20)\d{2}-\d{4,}(?![\d-])")

# Telefone como quem digita à mão escreve: com ou sem +55, com DDD entre
# parênteses, solto ou colado, fixo de oito dígitos ou celular de nove.
#
# A alternativa dos dígitos corridos é aberta em cima (`\d{8,}`) de propósito:
# ela é a rede que pega o que os desenhos nomeados deixam passar, inclusive o
# CPF digitado com um dígito a mais, que não fecha o verificador e escaparia
# inteiro. Número de oito dígitos ou mais que não seja telefone sai daqui como
# `[TELEFONE]`; apagar o que não precisava custa contexto, deixar passar custa
# dado pessoal, e a dúvida resolve sempre para o mesmo lado.
_TELEFONE = re.compile(
    r"(?<!\d)"
    r"(?:\+?\s?55[\s.-]?)?"  # país, opcional
    r"(?:"
    r"\(\d{2}\)\s?\d{4,5}[\s.-]?\d{4}"  # (21) 98765-4321
    r"|\d{2}[\s.-]\d{4,5}[\s.-]?\d{4}"  # 21 98765-4321
    r"|\d{8,}"  # 21987654321, 34567890, e qualquer sequência longa
    r"|\d{4,5}[\s.-]\d{4}"  # 98765-4321, sem DDD
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

_TITULO = rf"[{_MAIUSCULA}](?:[{_MINUSCULA}]+|[{_APOSTROFO}][{_LETRA}][{_MINUSCULA}]*)"
# Três letras é o piso da caixa alta: com duas, sigla de exame ("TC", "RX")
# entrava como nome e levava a frase inteira junto.
_CAIXA_ALTA = rf"[{_MAIUSCULA}]{{3,}}"
_INICIAL_DO_MEIO = rf"[{_MAIUSCULA}]\."
_PALAVRA_DE_NOME = rf"(?:{_TITULO}|{_CAIXA_ALTA}|{_INICIAL_DO_MEIO})"

_CONECTIVOS = ("de", "da", "do", "das", "dos", "e")
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


# Palavra terminada assim é verbo ou advérbio, não nome de gente. Vale mais que
# uma lista de verbos: é o que impede a pista de comer o resto da frase ("Sra.
# Rita confirmou") sem precisar prever cada conjugação que aparecer no relato.
_TERMINACAO_QUE_NAO_E_NOME = re.compile(r"(?:ou|eu|iu|ava|iam|aram|eram|iram|ando|endo|indo|mente)$", re.IGNORECASE)


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


def _mascarar_sequencia(trecho: str, caixa_alta_conta: bool) -> str:
    pedacos = re.split(rf"({_ESPACO})", trecho)
    palavras, espacos = pedacos[0::2], pedacos[1::2]
    papeis = [_papel(palavra, caixa_alta_conta) for palavra in palavras]

    grupos: list[list[int]] = []
    for indice, papel in enumerate(papeis):
        if papel != "nome":
            continue
        if grupos and not _ha_muro(papeis, grupos[-1][-1], indice):
            grupos[-1].append(indice)
        else:
            grupos.append([indice])

    # Só grupo com nome E sobrenome vira marcador, e o marcador cobre do
    # primeiro ao último nome do grupo: o que estiver na borda fica de fora.
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


def _mascarar_por_desenho(texto: str) -> str:
    caixa_alta_conta = not _predominantemente_em_caixa_alta(texto)
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
            if adiante is None or _e_palavra_neutra(adiante.group(2)):
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
    """Devolve `texto` sem nome completo, CPF, telefone, email nem protocolo.

    Texto ausente vira texto vazio: campo do Dossiê que nunca foi preenchido
    (`relato_integral`, `manifestante_nome`) chega aqui como `None`, e quem
    chama monta o prompt sem precisar checar antes.
    """
    if not texto:
        return ""
    texto = _EMAIL.sub(MARCADOR_EMAIL, texto)
    texto = _CPF_SEPARADO.sub(MARCADOR_CPF, texto)
    texto = _DIGITOS_11.sub(_mascarar_cpf_cru, texto)
    texto = _PROTOCOLO.sub(MARCADOR_PROTOCOLO, texto)
    texto = _TELEFONE.sub(MARCADOR_TELEFONE, texto)
    texto = _mascarar_por_desenho(texto)
    texto = _mascarar_por_pista(texto)
    return texto
