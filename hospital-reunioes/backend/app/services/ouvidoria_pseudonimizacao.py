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

Limites conhecidos, escritos aqui para ninguém confundir alcance com garantia:
- primeiro nome sozinho ("Carlos") só some quando vem atrás de um tratamento
  ("Dr. Carlos"); o critério de aceite fala de nome completo, e apagar toda
  palavra capitalizada apagaria o assunto do caso junto;
- número ambíguo pode sair sob o marcador do vizinho (um CPF cru que não fecha
  o dígito verificador vira `[TELEFONE]`). O rótulo erra, o dado some, e é o
  dado que importa;
- a lista de vocabulário da casa é o que separa "Pronto Socorro" de um nome:
  área nova com nome capitalizado entra nela, ou vira `[NOME]` no texto da IA.
"""

from __future__ import annotations

import re

MARCADOR_EMAIL = "[EMAIL]"
MARCADOR_CPF = "[CPF]"
MARCADOR_TELEFONE = "[TELEFONE]"
MARCADOR_PROTOCOLO = "[PROTOCOLO]"
MARCADOR_NOME = "[NOME]"

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")

# CPF pontuado é forma inconfundível: nenhum outro número do relato tem esse
# desenho, então não precisa de conferência de dígito para ser reconhecido.
_CPF_PONTUADO = re.compile(r"(?<!\d)\d{3}\.\d{3}\.\d{3}-\d{2}(?!\d)")

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


# Protocolo de ouvidoria, `ANO-NNNN` com NNNN de quatro dígitos ou mais
# (CONTEXT.md). É o "número de atendimento" da issue #342. Some antes do
# telefone: "2026-0007" também cabe no desenho de um fixo com DDD.
_PROTOCOLO = re.compile(r"(?<![\d-])(?:19|20)\d{2}-\d{4,}(?![\d-])")

# Telefone como quem digita à mão escreve: com ou sem +55, com DDD entre
# parênteses, solto ou colado, fixo de oito dígitos ou celular de nove.
_TELEFONE = re.compile(
    r"(?<!\d)"
    r"(?:\+?\s?55[\s.-]?)?"  # país, opcional
    r"(?:"
    r"\(\d{2}\)\s?\d{4,5}[\s.-]?\d{4}"  # (21) 98765-4321
    r"|\d{2}[\s.-]\d{4,5}[\s.-]?\d{4}"  # 21 98765-4321
    r"|\d{10,11}"  # 21987654321
    r"|\d{4,5}[\s.-]\d{4}"  # 98765-4321, sem DDD
    r")(?!\d)"
)


def _mascarar_cpf_cru(match: re.Match[str]) -> str:
    numero = match.group(0)
    return MARCADOR_CPF if _fecha_digito_verificador(numero) else numero


# Nome completo não tem forma fixa como CPF: o que existe é o desenho de duas
# ou mais palavras capitalizadas seguidas, com os conectivos do meio ("Maria da
# Silva Souza"). Só que esse mesmo desenho é o de "Pronto Socorro" e "Hospital
# São Matheus", e apagar a área do caso estragaria justamente a sugestão de
# ação corretiva que o PRD #319 quer. Daí o vocabulário da casa abaixo: palavra
# que está nele nunca é tomada por nome. Fora dessa lista, o critério é o
# desenho, e a dúvida sempre resolve a favor de apagar.
_INICIAL = "A-ZÀ-ÖØ-Þ"
_INTERNA = "a-zà-öø-ÿ"
_PALAVRA_ISOLADA = re.compile(rf"[{_INICIAL}][{_INTERNA}]+")
_CONECTIVOS = frozenset({"de", "da", "do", "das", "dos", "e"})
_SEQUENCIA_CAPITALIZADA = re.compile(
    rf"[{_INICIAL}][{_INTERNA}]+(?: (?:(?:{'|'.join(sorted(_CONECTIVOS))}) )*[{_INICIAL}][{_INTERNA}]+)+"
)

_VOCABULARIO_DA_CASA = frozenset(
    (
        # A casa e suas áreas: é disso que a sugestão de ação corretiva precisa.
        "hospital são matheus ouvidoria diretoria executiva recepção recepcao "
        "enfermagem enfermaria pronto socorro centro cirúrgico cirurgico unidade "
        "terapia intensiva laboratório laboratorio farmácia farmacia nutrição "
        "nutricao manutenção manutencao higiene faturamento internação internacao "
        "ambulatório ambulatorio maternidade pediatria obstetrícia obstetricia "
        "radiologia tomografia ressonância ressonancia ultrassom imagem triagem "
        "recursos humanos financeiro portaria setor sala leito quarto andar bloco "
        "ala posto clínica clinica consultório consultorio plantão plantao "
        # Palavras do caso, que descrevem sem identificar ninguém.
        "paciente acompanhante colaborador manifestante atendimento agendamento "
        "convênio convenio plano saúde saude protocolo manifestação manifestacao "
        "exame exames cirurgia consulta medicamento prontuário prontuario "
        # Canais e serviços externos citados no relato.
        "reclame aqui google whatsapp instagram facebook sus "
        # Tempo, que abre frase capitalizado e não é nome de ninguém.
        "ontem hoje amanhã amanha segunda terça terca quarta quinta sexta sábado "
        "sabado domingo janeiro fevereiro março marco abril maio junho julho "
        "agosto setembro outubro novembro dezembro"
    ).split()
)


# Um primeiro nome solto ("Carlos") é palavra qualquer e não vale apagar. Atrás
# de um tratamento ele é a pessoa de quem o relato fala, e aí some. Roda depois
# da regra de nome e sobrenome, senão "Dr. Carlos Mendes" perderia só a metade.
_TRATAMENTO = re.compile(rf"\b(Sr|Sra|Srta|Dr|Dra|Doutor|Doutora)(\.?\s+)[{_INICIAL}][{_INTERNA}]+")


def _e_palavra_de_nome(palavra: str) -> bool:
    return bool(_PALAVRA_ISOLADA.fullmatch(palavra)) and palavra.lower() not in _VOCABULARIO_DA_CASA


def _fechar_grupo(grupo: list[str]) -> list[str]:
    """Troca o grupo pelo marcador quando ele tem nome e sobrenome."""
    if not grupo:
        return []
    fim = len(grupo)
    while fim and grupo[fim - 1].lower() in _CONECTIVOS:
        fim -= 1  # conectivo pendurado no fim é da frase, não do nome
    nucleo = [palavra for palavra in grupo[:fim] if palavra.lower() not in _CONECTIVOS]
    if len(nucleo) >= 2:
        return [MARCADOR_NOME, *grupo[fim:]]
    return list(grupo)


def _mascarar_nomes(match: re.Match[str]) -> str:
    saida: list[str] = []
    grupo: list[str] = []
    for palavra in match.group(0).split(" "):
        if _e_palavra_de_nome(palavra) or (grupo and palavra.lower() in _CONECTIVOS):
            grupo.append(palavra)
            continue
        saida.extend(_fechar_grupo(grupo))
        grupo = []
        saida.append(palavra)
    saida.extend(_fechar_grupo(grupo))
    return " ".join(saida)


def pseudonimizar(texto: str | None) -> str:
    """Devolve `texto` sem nome completo, CPF, telefone, email nem protocolo.

    Texto ausente vira texto vazio: campo do Dossiê que nunca foi preenchido
    (`relato_integral`, `manifestante_nome`) chega aqui como `None`, e quem
    chama monta o prompt sem precisar checar antes.
    """
    if not texto:
        return ""
    texto = _EMAIL.sub(MARCADOR_EMAIL, texto)
    texto = _CPF_PONTUADO.sub(MARCADOR_CPF, texto)
    texto = _DIGITOS_11.sub(_mascarar_cpf_cru, texto)
    texto = _PROTOCOLO.sub(MARCADOR_PROTOCOLO, texto)
    texto = _TELEFONE.sub(MARCADOR_TELEFONE, texto)
    texto = _SEQUENCIA_CAPITALIZADA.sub(_mascarar_nomes, texto)
    texto = _TRATAMENTO.sub(rf"\1\2{MARCADOR_NOME}", texto)
    return texto
