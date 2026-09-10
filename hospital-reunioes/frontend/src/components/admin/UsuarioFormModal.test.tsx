/**
 * @vitest-environment jsdom
 */

/**
 * O campo Login no GitHub na tela de Usuários (issue #674, ADR 0054).
 *
 * Ele não é um enfeite de cadastro: é a chave que abre os controles do Vínculo
 * com o desenvolvimento na aba Tecnologia. Duas coisas que só este teste
 * cobra:
 *
 * * o valor de quem já tem login APARECE no formulário (sem isso, reabrir o
 *   modal e salvar qualquer outro campo apagaria o login em silêncio);
 * * o campo apagado sai como `null`, e não como texto vazio: "esta pessoa não
 *   trabalha no GitHub" é a ausência do login, e é isso que o banco guarda.
 *
 * Quem recusa formato e login repetido é o backend, com frase de gente
 * (`test_admin_usuarios.py`): a tela não repete essa regra.
 */

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { UsuarioFormModal } from "./UsuarioFormModal";
import { AdminUsuario, AdminUsuarioPayload } from "./types";

const PEDRO: AdminUsuario = {
  id: "P010",
  nome_completo: "Pedro Vitta",
  email: "pedro@x.com",
  cargo: "Analista",
  area: null,
  setor: null,
  role: "coordenador",
  ativo: true,
  is_externo: false,
  is_super_admin: true,
  access_profile: "super_admin",
  github_login: "pedrorezendefig",
};

const CAMPO = "Login no GitHub (opcional)";

function montar(initial: AdminUsuario | undefined, mode: "create" | "edit") {
  const enviados: AdminUsuarioPayload[] = [];
  render(
    <UsuarioFormModal
      mode={mode}
      initial={initial}
      roleOptions={["coordenador", "gerente"]}
      onClose={() => {}}
      onSubmit={async (payload) => {
        enviados.push(payload);
        return true;
      }}
    />,
  );
  return enviados;
}

function salvar() {
  fireEvent.click(screen.getByRole("button", { name: /Criar|Salvar/ }));
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("O campo Login no GitHub", () => {
  it("mostra o login de quem já tem", () => {
    montar(PEDRO, "edit");

    expect((screen.getByLabelText(CAMPO) as HTMLInputElement).value).toBe("pedrorezendefig");
  });

  it("nasce vazio para quem não tem", () => {
    montar({ ...PEDRO, github_login: null }, "edit");

    expect((screen.getByLabelText(CAMPO) as HTMLInputElement).value).toBe("");
  });

  it("o login digitado entra no que se salva", async () => {
    const enviados = montar({ ...PEDRO, github_login: null }, "edit");

    fireEvent.change(screen.getByLabelText(CAMPO), { target: { value: "pedrorezendefig" } });
    salvar();

    await vi.waitFor(() => expect(enviados[0]?.github_login).toBe("pedrorezendefig"));
  });

  it("apagar o campo manda `null`, e não texto vazio", async () => {
    const enviados = montar(PEDRO, "edit");

    fireEvent.change(screen.getByLabelText(CAMPO), { target: { value: "" } });
    salvar();

    await vi.waitFor(() => expect(enviados[0]).toHaveProperty("github_login", null));
  });

  it("quem não mexeu no campo não manda o campo", async () => {
    // O PATCH da casa é parcial: mandar o login sem necessidade faria toda
    // edição de nome disputar a guarda de unicidade do backend à toa.
    const enviados = montar(PEDRO, "edit");

    fireEvent.change(screen.getByLabelText(/Nome completo/), { target: { value: "Pedro R. Vitta" } });
    salvar();

    await vi.waitFor(() => expect(enviados).toHaveLength(1));
    expect("github_login" in enviados[0]).toBe(false);
    expect(enviados[0].nome_completo).toBe("Pedro R. Vitta");
  });

  it("o usuário novo já pode nascer com login", async () => {
    const enviados = montar(undefined, "create");

    fireEvent.change(screen.getByLabelText(/Nome completo/), { target: { value: "Nova Pessoa" } });
    fireEvent.change(screen.getByLabelText(/^Email/), { target: { value: "nova@x.com" } });
    fireEvent.change(screen.getByLabelText(/^Cargo/), { target: { value: "Analista" } });
    fireEvent.change(screen.getByLabelText(CAMPO), { target: { value: "novapessoa" } });
    salvar();

    await vi.waitFor(() => expect(enviados[0]?.github_login).toBe("novapessoa"));
  });

  it("o usuário novo sem login nasce sem login", async () => {
    const enviados = montar(undefined, "create");

    fireEvent.change(screen.getByLabelText(/Nome completo/), { target: { value: "Nova Pessoa" } });
    fireEvent.change(screen.getByLabelText(/^Email/), { target: { value: "nova@x.com" } });
    fireEvent.change(screen.getByLabelText(/^Cargo/), { target: { value: "Analista" } });
    salvar();

    await vi.waitFor(() => expect(enviados).toHaveLength(1));
    expect(enviados[0].github_login).toBeNull();
  });
});
