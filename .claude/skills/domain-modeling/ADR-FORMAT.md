# Formato de ADR (Hospital Reuniões)

A fonte de verdade do formato de ADR deste repo é **`docs/agents/domain.md`**: frontmatter com `status` de conjunto fechado (`accepted`/`superseded`/`deprecated`/`proposed`/`rejected`) e supersessão bidirecional (`supersedes`/`superseded_by`, `amends`/`amended_by`), tudo travado pelo CI `lint-adr` (`tools/lint_adr.py`).

Siga aquele documento. Não use o formato upstream do Matt Pocock aqui: ele trata `status` como seção opcional, o que o lint deste repo reprova.
