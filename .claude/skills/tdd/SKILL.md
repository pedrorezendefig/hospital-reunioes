---
name: tdd
description: Test-driven development with red-green-refactor loop. Use when user wants to build features or fix bugs using TDD, mentions "red-green-refactor", wants integration tests, or asks for test-first development.
---

> **Hospital Reuniões:** os critérios de aceite da issue (`gh issue view <N>`) são a lista de testes a escrever (cada critério → um teste RED). Nomes de teste descrevem o comportamento de domínio em **pt-BR** (ex.: `test_facilitador_ve_status_de_assinatura`). Backend = `pytest` (TestClient/endpoints reais); frontend segue o padrão já existente no repo. Use a terminologia de `CONTEXT.md`.

> **Cadência de verificação (Hospital Reuniões):** durante o ciclo, rode só o arquivo de teste em que está mexendo. Rode os linters com regularidade, não só no fim (backend `ruff check` + `ruff format --check`; frontend `tsc`/lint): `pytest` local não pega lint e o gate de CI pega. A suíte completa roda uma vez, antes de invocar `/ship`.

# Test-Driven Development

## Philosophy

**Core principle**: Tests should verify behavior through public interfaces, not implementation details. Code can change entirely; tests shouldn't.

**Good tests** are integration-style: they exercise real code paths through public APIs. They describe _what_ the system does, not _how_ it does it. A good test reads like a specification - "user can checkout with valid cart" tells you exactly what capability exists. These tests survive refactors because they don't care about internal structure.

**Bad tests** are coupled to implementation. They mock internal collaborators, test private methods, or verify through external means (like querying a database directly instead of using the interface). The warning sign: your test breaks when you refactor, but behavior hasn't changed. If you rename an internal function and tests fail, those tests were testing implementation, not behavior.

See [tests.md](tests.md) for examples and [mocking.md](mocking.md) for mocking guidelines.

## Anti-Pattern: Horizontal Slices

**DO NOT write all tests first, then all implementation.** This is "horizontal slicing" - treating RED as "write all tests" and GREEN as "write all code."

This produces **crap tests**:

- Tests written in bulk test _imagined_ behavior, not _actual_ behavior
- You end up testing the _shape_ of things (data structures, function signatures) rather than user-facing behavior
- Tests become insensitive to real changes - they pass when behavior breaks, fail when behavior is fine
- You outrun your headlights, committing to test structure before understanding the implementation

**Correct approach**: Vertical slices via tracer bullets. One test → one implementation → repeat. Each test responds to what you learned from the previous cycle. Because you just wrote the code, you know exactly what behavior matters and how to verify it.

```
WRONG (horizontal):
  RED:   test1, test2, test3, test4, test5
  GREEN: impl1, impl2, impl3, impl4, impl5

RIGHT (vertical):
  RED→GREEN: test1→impl1
  RED→GREEN: test2→impl2
  RED→GREEN: test3→impl3
  ...
```

## Anti-Pattern: Tautological Tests

**DO NOT recompute the expected value the way the code computes it.** A tautological test mirrors the implementation in its assertion (`expect(add(a, b)).toBe(a + b)`, a snapshot derived by hand the same way, a constant asserted equal to itself), so it passes by construction and can never disagree with the code.

Expected values must come from an independent source of truth: a known-good literal, a worked example, the spec. Here, the acceptance criteria of the issue are that source.

See [tests.md](tests.md) for a BAD/GOOD example pair.

## Workflow

### 1. Planning

When exploring the codebase, use the project's domain glossary so that test names and interface vocabulary match the project's language, and respect ADRs in the area you're touching.

Before writing any code:

- [ ] List the behaviors to test (not implementation steps). In the issue pipeline, each acceptance criterion is one behavior; the issue IS the approved plan.
- [ ] Identify opportunities for deep modules (small interface, deep implementation): see the `codebase-design` skill
- [ ] Design interfaces for testability: see "Designing for testability" in the `codebase-design` skill
- [ ] Show the plan briefly and CONTINUE. Do NOT ask "posso começar?" or wait for approval: when the user grabbed the issue (`/pegar-issue`), that was the approval.

**Stop and ask ONLY when** a decision changes the deliverable and the issue does not answer it (e.g. two different deliverables are possible). Max 2 options, with a highlighted recommendation. Everything else: pick, say what you picked, keep going.

**You can't test everything.** The acceptance criteria define which behaviors matter. Focus testing effort on critical paths and complex logic, not every possible edge case.

### 2. Tracer Bullet

Write ONE test that confirms ONE thing about the system:

```
RED:   Write test for first behavior → test fails
GREEN: Write minimal code to pass → test passes
```

This is your tracer bullet - proves the path works end-to-end.

### 3. Incremental Loop

For each remaining behavior:

```
RED:   Write next test → fails
GREEN: Minimal code to pass → passes
```

Rules:

- One test at a time
- Only enough code to pass current test
- Don't anticipate future tests
- Keep tests focused on observable behavior

### 4. Refactor

After all tests pass, look for [refactor candidates](refactoring.md):

- [ ] Extract duplication
- [ ] Deepen modules (move complexity behind simple interfaces)
- [ ] Apply SOLID principles where natural
- [ ] Consider what new code reveals about existing code
- [ ] Run tests after each refactor step

**Never refactor while RED.** Get to GREEN first.

## Checklist Per Cycle

```
[ ] Test describes behavior, not implementation
[ ] Test uses public interface only
[ ] Test would survive internal refactor
[ ] Code is minimal for this test
[ ] No speculative features added
```
