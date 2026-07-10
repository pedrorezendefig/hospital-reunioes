"""Gramática restrita do Fluxograma de POP (ADR 0024, issue #221).

O `conteudo` da seção de tipo `fluxograma` é um objeto JSON de gramática
restrita ao domínio, validado por schema nos dois lados (pydantic aqui,
types no frontend). Semântica:

- a lista `nos` é a coluna principal do fluxo (Início implícito antes do
  primeiro nó, Fim implícito depois do último);
- nó `passo` segue para o próximo da lista; nó `decisao` tem exatamente
  2 ramos rotulados (default Sim e Não);
- ramo sem `desvio` segue para o próximo nó da lista; ramo com `desvio`
  cria um card lateral que retorna a um nó (`retorna_para`) ou, sem
  `retorna_para`, segue o fluxo.

Fora desta fatia (ficam para a #222): decisões com 3 ou mais ramos e
saltos (`vai_para`), o `extra="forbid"` e a trava de 2 ramos recusam
essas formas por ora.
"""

from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator


class FluxogramaInvalidoError(ValueError):
    """O objeto não obedece à gramática restrita do fluxograma."""


class FluxogramaDesvio(BaseModel):
    """Card lateral de um ramo de decisão: ação corretiva que retorna a um nó
    anterior (`retorna_para`) ou segue o fluxo (sem `retorna_para`)."""

    model_config = ConfigDict(extra="forbid")

    texto: str
    retorna_para: str | None = None

    @field_validator("texto")
    @classmethod
    def _texto_nao_vazio(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("desvio sem texto")
        return v


class FluxogramaRamo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rotulo: str
    desvio: FluxogramaDesvio | None = None

    @field_validator("rotulo")
    @classmethod
    def _rotulo_nao_vazio(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("ramo sem rótulo")
        return v


class FluxogramaNo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., min_length=1)
    tipo: Literal["passo", "decisao"]
    texto: str
    ramos: list[FluxogramaRamo] | None = None

    @field_validator("texto")
    @classmethod
    def _texto_nao_vazio(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("nó sem texto")
        return v

    @model_validator(mode="after")
    def _ramos_conforme_o_tipo(self) -> FluxogramaNo:
        if self.tipo == "passo":
            if self.ramos:
                raise ValueError(f"nó de passo '{self.id}' não pode ter ramos")
            return self
        # decisao: exatamente 2 ramos nesta fatia (3+ ramos são a fatia #222).
        if not self.ramos or len(self.ramos) != 2:
            raise ValueError(f"decisão '{self.id}' deve ter exatamente 2 ramos")
        # Layout fechado (coluna principal + desvio lateral): no máximo um dos
        # ramos desvia; o outro segue o fluxo.
        com_desvio = sum(1 for r in self.ramos if r.desvio is not None)
        if com_desvio > 1:
            raise ValueError(f"decisão '{self.id}' só pode ter 1 ramo com desvio")
        return self


class FluxogramaEstrutura(BaseModel):
    """O objeto completo da seção `fluxograma` (raiz da gramática)."""

    model_config = ConfigDict(extra="forbid")

    nos: list[FluxogramaNo] = Field(..., min_length=1)

    @model_validator(mode="after")
    def _referencias_integras(self) -> FluxogramaEstrutura:
        ids = [no.id for no in self.nos]
        vistos: set[str] = set()
        for nid in ids:
            if nid in vistos:
                raise ValueError(f"id de nó duplicado: '{nid}'")
            vistos.add(nid)
        for no in self.nos:
            for ramo in no.ramos or []:
                alvo = ramo.desvio.retorna_para if ramo.desvio else None
                if alvo is not None and alvo not in vistos:
                    raise ValueError(f"desvio da decisão '{no.id}' retorna para nó inexistente: '{alvo}'")
        return self


def validar_fluxograma(obj) -> FluxogramaEstrutura:
    """Valida o objeto da seção `fluxograma` contra a gramática restrita.

    Levanta `FluxogramaInvalidoError` com mensagem legível, os endpoints
    respondem 4xx e a normalização decide o destino do conteúdo inválido.
    """
    if not isinstance(obj, dict):
        raise FluxogramaInvalidoError("o conteúdo do fluxograma deve ser um objeto JSON")
    try:
        return FluxogramaEstrutura.model_validate(obj)
    except ValidationError as e:
        primeiro = e.errors()[0]
        caminho = ".".join(str(p) for p in primeiro.get("loc", ()))
        msg = primeiro.get("msg", "estrutura inválida")
        raise FluxogramaInvalidoError(f"{caminho}: {msg}" if caminho else msg) from e


def fluxograma_valido(obj) -> bool:
    try:
        validar_fluxograma(obj)
    except FluxogramaInvalidoError:
        return False
    return True


def _retorno_legivel(alvo_id, nos: list, numero_do_passo: dict) -> str:
    """Sufixo em texto claro do retorno de um desvio (issue #223): passo
    numerado vira "; retorna ao passo N"; outro nó usa o próprio texto; id
    desconhecido omite o retorno (best-effort, nunca inventa)."""
    if alvo_id in numero_do_passo:
        return f"; retorna ao passo {numero_do_passo[alvo_id]}"
    for no in nos:
        if isinstance(no, dict) and no.get("id") == alvo_id:
            texto_alvo = str(no.get("texto") or "").strip()
            return f'; retorna a "{texto_alvo}"' if texto_alvo else ""
    return ""


def fluxograma_texto_fallback(obj) -> str:
    """Lista numerada derivada do objeto, para o PDF sem SVG capturado
    (PRD #210, decisão 9; issue #223). Best-effort e tolerante: lê o que
    houver no shape sem validar, nunca quebra a geração do documento."""
    if not isinstance(obj, dict):
        return str(obj)
    nos = obj.get("nos")
    if not isinstance(nos, list):
        return json.dumps(obj, ensure_ascii=False)
    # Numeração 1..N dos passos, na ordem do fluxo principal, para o retorno
    # dos desvios apontar "o passo N" em vez do id interno.
    numero_do_passo: dict = {}
    numero = 0
    for no in nos:
        if isinstance(no, dict) and no.get("tipo") != "decisao":
            numero += 1
            if no.get("id") is not None:
                numero_do_passo[no.get("id")] = numero
    linhas: list[str] = []
    numero = 0
    for no in nos:
        if not isinstance(no, dict):
            continue
        texto = str(no.get("texto") or "").strip()
        if no.get("tipo") == "decisao":
            linhas.append(f"{texto}" if texto else "Decisão")
            for ramo in no.get("ramos") or []:
                if not isinstance(ramo, dict):
                    continue
                rotulo = str(ramo.get("rotulo") or "").strip()
                desvio = ramo.get("desvio") if isinstance(ramo.get("desvio"), dict) else None
                if desvio:
                    acao = str(desvio.get("texto") or "").strip()
                    retorno = ""
                    if desvio.get("retorna_para") is not None:
                        retorno = _retorno_legivel(desvio.get("retorna_para"), nos, numero_do_passo)
                    linhas.append(f"- {rotulo}: {acao}{retorno}")
                else:
                    linhas.append(f"- {rotulo}: seguir o fluxo")
        else:
            numero += 1
            linhas.append(f"{numero}. {texto}")
    return "\n".join(linhas)
