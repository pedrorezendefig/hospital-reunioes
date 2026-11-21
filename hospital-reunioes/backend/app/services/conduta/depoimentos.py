"""O depoimento do Canal de Conduta (issue #1830; especificação, seções 7.1 e
7.2; ADR 0097, decisão 2).

Na etapa Apuração, cada pessoa ouvida ganha um cartão (nome, cargo e papel),
que recebe a transcrição, o áudio e o termo assinado, cada um pelo seu botão.
Nome e cargo entram cifrados. Os arquivos entram cifrados no bucket privado do
Canal, sem nome original e sem URL: o arquivo só sai pela rota que confere o
acesso e decifra. Uma versão nova não apaga a anterior.

"CONCLUIR DEPOIMENTO" só vale com os sete itens da lista de conferência: três
automáticos (os arquivos) e quatro declarações de quem conduziu, com quem
marcou e quando. Sem gravação, os pontos digitados fazem as vezes da
transcrição e os itens de transcrição e áudio ficam "Não se aplica", com o
motivo.

Toda ação grava a sua linha na trilha antes de mudar qualquer coisa. A trilha
não leva nome de pessoa ouvida.
"""

from __future__ import annotations

from typing import Any

from app.services.conduta import cifra, trilha
from app.services.conduta.portao import CasoAberto
from app.services.conduta.ritos import agora_utc

TABELA = "conduta_depoimentos"

PAPEIS = {"acusado": "Acusado", "testemunha": "Testemunha", "denunciante": "Denunciante identificado"}

_TAMANHO_DO_NOME = 200


class DepoimentoRecusadoError(Exception):
    """A ação não pode acontecer agora. `status` vai para a resposta, e a
    mensagem diz o motivo numa linha."""

    def __init__(self, status: int, mensagem: str):
        super().__init__(mensagem)
        self.status = status
        self.mensagem = mensagem


def _exigir_apuracao(caso: dict) -> None:
    if caso.get("etapa") != "apuracao" or caso.get("encerrado_em"):
        raise DepoimentoRecusadoError(409, "Os depoimentos são da etapa Apuração.")


def adicionar_pessoa(supabase, aberto: CasoAberto, *, nome: str, cargo: str, papel: str) -> dict:
    _exigir_apuracao(aberto.caso)
    nome, cargo = (nome or "").strip(), (cargo or "").strip()
    if not nome or not cargo:
        raise DepoimentoRecusadoError(422, "Diga o nome e o cargo da pessoa a ouvir.")
    if len(nome) > _TAMANHO_DO_NOME or len(cargo) > _TAMANHO_DO_NOME:
        raise DepoimentoRecusadoError(422, "O nome e o cargo cabem em uma linha.")
    if papel not in PAPEIS:
        raise DepoimentoRecusadoError(422, "Escolha o papel: acusado, testemunha ou denunciante identificado.")
    nome_cifrado, cargo_cifrado = cifra.cifrar_texto(nome), cifra.cifrar_texto(cargo)
    trilha.registrar(
        supabase, aberto.caso["id"], aberto.autor_id, "adicionou_pessoa_a_ouvir", f"pessoa a ouvir: {PAPEIS[papel]}"
    )
    return (
        supabase.table(TABELA)
        .insert(
            {
                "caso_id": aberto.caso["id"],
                "nome_cifrado": nome_cifrado,
                "cargo_cifrado": cargo_cifrado,
                "papel": papel,
                "criado_por": aberto.autor_id,
                "criado_em": agora_utc().isoformat(),
            }
        )
        .execute()
        .data[0]
    )


def _do_caso(supabase, caso_id: str) -> list[dict]:
    linhas = supabase.table(TABELA).select("*").eq("caso_id", caso_id).execute().data or []
    return sorted(linhas, key=lambda d: str(d.get("criado_em") or ""))


def situacao(depoimento: dict) -> str:
    if depoimento.get("concluido_em"):
        return "Concluído"
    return "Aguardando assinatura"


def para_a_tela(supabase, caso: dict) -> dict[str, Any]:
    """Os cartões do caso, decifrados. Levanta `CifraIndisponivelError` se a
    chave não abre."""
    cartoes = [
        {
            "id": d["id"],
            "nome": cifra.decifrar_texto(d["nome_cifrado"]),
            "cargo": cifra.decifrar_texto(d["cargo_cifrado"]),
            "papel": d["papel"],
            "situacao": situacao(d),
        }
        for d in _do_caso(supabase, caso["id"])
    ]
    return {"depoimentos": cartoes}
