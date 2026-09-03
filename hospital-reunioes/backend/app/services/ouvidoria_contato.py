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


def destinatario_do_caso(caso: dict) -> str | None:
    """Para quem o sistema pode escrever NESTE caso, ou None quando não há para
    quem (issue #494).

    A pergunta é a mesma nas duas pontas do ADR 0042, o acuse da abertura e o
    aviso de encerramento, e por isso ela é respondida em um lugar só: com duas
    cópias, o dia em que a régua mudar produziria um caso que recebe o "chegou"
    e não recebe o "no que deu", ou pior, que entra no denominador de um
    indicador e sai do outro.

    O pedido de anonimato vence qualquer dado que tenha sobrado no corpo do
    registro: a tela prometeu que não haveria identificação, e escrever para
    aquele endereço quebraria a promessa mesmo com o email ali à mão."""
    if caso.get("anonimo"):
        return None
    return email_utilizavel(caso.get("manifestante_contato"))


# O papel gravado em `ouvidoria_notificacoes.papel_destinatario` quando quem
# recebe é o manifestante, e não gente do hospital.
#
# Mora aqui porque esta é a casa da regra de para quem dá para escrever, e
# porque o valor virou decisão de SEGURANÇA quando a omissão do endereço no log
# passou a derivar dele (issue #547). Enquanto cada consumidor tinha a sua
# cópia, o dia em que um deles divergisse produziria um caso protegido e outro
# vazando, e nada na tela denunciaria a diferença.
PAPEL_MANIFESTANTE = "manifestante"


# Os papéis de quem é do HOSPITAL, e a lista é fechada de propósito. Cada um
# tem dono no código, e o teste `TestPapeisInternos` trava a divergência:
#
#   titular, substituto, gestor  -> `ouvidoria_responsaveis.PAPEIS`
#   ouvidor, diretoria_executiva -> `PERFIS_OUVIDORIA` (routers/ouvidoria.py)
#   setor                        -> o portal do setor (routers/ouvidoria.py)
#
# A lista existe do lado seguro, e é essa a diferença para a tupla de gatilhos
# que a issue #547 aposentou: o que NÃO está aqui tem o endereço omitido. Papel
# novo do hospital que ninguém cadastrar perde uma conveniência de diagnóstico;
# papel novo de FORA que ninguém cadastrar continua protegido.
PAPEIS_INTERNOS = frozenset(
    {
        "titular",
        "substituto",
        "gestor",
        "ouvidor",
        "diretoria_executiva",
        "setor",
    }
)


def destinatario_e_o_manifestante(papel_destinatario: str | None) -> bool:
    """A linha de notificação fala para FORA do hospital?

    É esta pergunta, e não uma lista de gatilhos escrita à mão, que decide se o
    endereço entra no log da aplicação (issue #547). O dado já está na própria
    linha: `registrar` declara `papel_destinatario` keyword-only e sem default,
    então nenhum chamador consegue esquecer de informá-lo, e um retorno NOVO ao
    manifestante (o transporte por WhatsApp do ADR 0042, decisão 3) nasce
    protegido sem ninguém lembrar de cadastrá-lo em lista nenhuma.

    **A pergunta é feita pelo avesso: só quem está na lista de papéis INTERNOS
    tem o endereço no log; todo o resto é TRATADO como o manifestante.**
    Perguntar `papel == PAPEL_MANIFESTANTE` traria de volta o mesmo modo de
    falha da tupla, só que mudado de lugar: o retorno por WhatsApp gravado como
    `"manifestante_whatsapp"`, ou um papel com caixa diferente, ou com espaço em
    volta, nasceria vazando. Nulo, vazio, espaço em branco e qualquer papel
    desconhecido caem todos no mesmo lado, o seguro.

    O custo de errar não é simétrico, e é isso que decide o default. Omitir o
    endereço de um email interno tira uma conveniência do diagnóstico, que o
    assunto no log e a linha da notificação ainda respondem; imprimir o do
    manifestante põe o email pessoal de quem reclamou no log do container, ao
    lado do protocolo, para quem não tem perfil nenhum no módulo.

    O ramo do nulo é defesa PREVENTIVA, e não conserto de linha existente:
    `papel_destinatario` nasceu junto com a tabela (migration 068) e os
    chamadores passam literal, o papel do responsável (não anulável) ou a cópia
    da linha anterior, então hoje não há linha sem papel. Ele existe porque a
    coluna é anulável no schema e porque `registrar` aceita `None`.

    O nulo é resolvido AQUI, em Python, e não por filtro no banco: `.eq`
    descarta NULL em silêncio no PostgREST, e a linha sem papel escaparia da
    regra justamente por ser aquela de que menos se sabe (issue #175)."""
    if not papel_destinatario:
        return True
    return papel_destinatario.strip().casefold() not in PAPEIS_INTERNOS
