"""O contato do manifestante, e o que dá para fazer com ele (issue #493).

`manifestante_contato` é texto livre em todos os três canais de entrada: a
pessoa escreve o que quiser no formulário, a Ana transcreve o que ouviu e o
ouvidor digita o que a pessoa ditou no telefone. Sai de lá "joana@casa.com",
"(21) 99999-0000", "falar com a filha no 3º andar" e vazio.

Quem decide se existe para onde mandar um email é este módulo, e ele é ÚNICO no
app de propósito (critério de aceite da #493): o acuse de recebimento e o aviso
de encerramento (RN-80) fazem a mesma pergunta sobre o mesmo campo, e duas
regras diferentes fariam um caso receber o acuse e não receber o desfecho, ou
pior, entrar no denominador de um indicador e sair do outro.

A régua é deliberadamente conservadora: na dúvida, não há email. Um endereço
inventado a partir de texto solto queima uma tentativa de envio, suja o
registro de notificações com uma falha que não é do provedor e faz o caso
parecer avisado quando ninguém foi avisado. Não achar o email tem caminho
próprio e visível (a marcação da decisão 4 do ADR 0042); achar errado, não.
"""

from __future__ import annotations

import re

# Um endereço reconhecível dentro de texto livre. Sem espaço, com arroba e com
# um domínio de pelo menos dois níveis: é o que separa "joana@exemplo.com" de
# "joana@" e de "@exemplo.com", que não têm para onde ir.
#
# Não é o RFC 5322, e não tenta ser: o objetivo aqui é decidir se vale a pena
# chamar o provedor, e o veredito final sobre o endereço é dele.
_EMAIL = re.compile(
    r"[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+"
    r"(?:\.[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+)*"
    r"@"
    r"(?:[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?\.)+"
    r"[A-Za-z]{2,}"
)


def email_utilizavel(contato: str | None) -> str | None:
    """O email que dá para usar dentro do contato, em minúsculas, ou None.

    Devolve o PRIMEIRO endereço reconhecível: contato com dois emails é raro e
    o primeiro é o que a pessoa escreveu antes, não o que sobrou de um recado.

    A caixa desce porque a parte do domínio é insensível a ela e a parte local
    quase sempre também: guardar "JOANA@Exemplo.COM" faria a mesma pessoa
    aparecer como dois destinatários no registro de notificações."""
    if not contato:
        return None
    achado = _EMAIL.search(contato)
    return achado.group(0).lower() if achado else None
