"""Sanitizador de travessao da saida da IA (issue #136, ADR 0013).

Defesa em duas camadas contra travessao (em dash, U+2014) e meia-risca (en dash,
U+2013) na saida do LLM: o prompt instrui a nunca usa-los (reduz na origem) e
esta funcao garante no destino, trocando-os de forma deterministica antes do
texto virar Ata, Ata Guiada, POP ou email.

Regra (deliberadamente estreita, nao generica):
- travessao e meia-risca viram virgula no texto corrido;
- quando estao entre digitos (faixa numerica, ex. "10 a 15", "2024 a 2026"),
  viram hifen comum (U+002D);
- o hifen comum de palavra composta ou data nunca e tocado.
"""

from __future__ import annotations

import re
import unicodedata

# Travessao (em dash) e meia-risca (en dash). O hifen comum fica de fora de
# proposito: a string abaixo contem so os dois sinais longos que devem sumir.
_DASHES = "—–"

# Faixa numerica: digito, dash (com espacos opcionais ao redor), digito.
# Vira hifen, recolando os dois digitos das bordas.
_FAIXA_NUMERICA = re.compile(rf"(?<=\d)\s*[{_DASHES}]\s*(?=\d)")

# Dash de texto corrido (qualquer sinal longo restante), com os espacos ao redor:
# colapsa "palavra <dash> palavra" em "palavra, palavra".
_DASH_TEXTO = re.compile(rf"\s*[{_DASHES}]\s*")


def sanitizar_travessao(texto):
    """Troca travessao/meia-risca por virgula (texto) ou hifen (entre digitos).

    Aceita qualquer valor: nao-strings voltam intactas, para a funcao poder ser
    aplicada cegamente sobre as folhas de uma estrutura.
    """
    if not isinstance(texto, str):
        return texto
    # Faixa numerica primeiro (vira hifen), depois o resto vira virgula.
    texto = _FAIXA_NUMERICA.sub("-", texto)
    texto = _DASH_TEXTO.sub(", ", texto)
    return texto


def sem_invisiveis(texto: str) -> str:
    """Tira os caracteres de formatacao do Unicode (categoria Cf).

    Sao os de largura zero, e o `strip` nao os enxerga: `"​".isspace()` e
    False. Vinte espacos de largura zero passam por qualquer piso e chegam ao
    leitor como texto visualmente vazio.

    Mora aqui, e nao no modulo de quem valida, porque todo texto livre que a
    area escreve por link publico precisa da mesma peneira: a resposta da area
    (issue #482) e o motivo da devolucao a Ouvidoria (issue #600). Duas copias
    divergiriam no dia em que uma delas aprendesse um caractere novo.
    """
    return "".join(c for c in texto if unicodedata.category(c) != "Cf")


def sanitizar_estrutura(obj):
    """Aplica o sanitizador recursivamente nas folhas de texto de uma estrutura.

    A saida do LLM e JSON estruturado (dict/list): percorre preservando o shape
    e limpando so as strings. Tipos nao-texto (None, bool, int) passam intactos.
    """
    if isinstance(obj, str):
        return sanitizar_travessao(obj)
    if isinstance(obj, dict):
        return {chave: sanitizar_estrutura(valor) for chave, valor in obj.items()}
    if isinstance(obj, list):
        return [sanitizar_estrutura(item) for item in obj]
    return obj
