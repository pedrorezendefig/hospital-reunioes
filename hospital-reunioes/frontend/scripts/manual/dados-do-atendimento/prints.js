// Os prints da página de Dados do Atendimento do manual (issue #1726). Quem
// roda é o roteiro.sh, pelo `playwright-cli run-code`, depois de trocar
// __BASE__, __SAIDA__, __EMAIL__ e __SENHA__. Cada chamada de `foto` grava um
// print citado em public/manual/dados-do-atendimento/pagina.md, e o teste da
// página confere que as duas listas batem.
async (page) => {
  const base = "__BASE__";
  const saida = "__SAIDA__";

  // As linhas de exemplo que o roteiro.sh semeia. As tabelas do banco local
  // também trazem os preços de verdade das migrations 061 e 062, e eles não
  // podem sair num print: toda linha fora desta lista some da tela antes da
  // foto. O teste da página confere que a lista é a mesma do seed.
  const EXEMPLOS = [
    "Endocrinologia",
    "Reumatologia",
    "Otorrinolaringologia",
    "Glicemia de Jejum",
    "Teste Ergométrico",
    "Densitometria Óssea",
    "Correção de Hérnia Umbilical",
    "Retirada de Amígdalas",
    "Cirurgia de Varizes"
  ];

  const soExemplos = async () => {
    await page.locator("tbody tr").first().waitFor({ state: "visible", timeout: 15000 });
    await page.evaluate((exemplos) => {
      document.querySelectorAll("tbody tr").forEach((tr) => {
        const primeira = tr.querySelector("td")?.textContent?.trim() ?? "";
        tr.style.display = exemplos.includes(primeira) ? "" : "none";
      });
    }, EXEMPLOS);
  };

  // Uma moldura em volta do que o passo manda clicar ou preencher. É a única
  // marcação sobre a tela, e quem desenha é este roteiro.
  const marcar = async (alvo) => {
    await alvo.first().waitFor({ state: "visible", timeout: 15000 });
    await alvo.first().evaluate((el) => {
      el.scrollIntoView({ block: "center" });
      el.setAttribute("data-marca-do-manual", "");
      el.style.outline = "3px solid #F59E0B";
      el.style.outlineOffset = "3px";
      el.style.borderRadius = el.style.borderRadius || "8px";
    });
  };
  const limpar = () =>
    page.evaluate(() =>
      document.querySelectorAll("[data-marca-do-manual]").forEach((el) => {
        el.style.outline = "";
        el.removeAttribute("data-marca-do-manual");
      })
    );
  // Sem foco, sem mouse em cima de nada e sem o selo do `next dev` no canto:
  // nada disso é da tela que a pessoa vê.
  const semFoco = async () => {
    await page.evaluate(() => {
      if (document.activeElement) document.activeElement.blur();
      document.querySelectorAll("nextjs-portal").forEach((selo) => selo.remove());
    });
    await page.mouse.move(700, 899);
    await page.waitForTimeout(300);
  };
  const foto = async (arquivo) => {
    await semFoco();
    await page.screenshot({ path: `${saida}/${arquivo}` });
    await limpar();
  };

  const linha = (nome) => page.locator("tbody tr").filter({ hasText: nome }).first();
  const campo = (rotulo) =>
    page.locator(
      `xpath=//*[@role='dialog']//label[starts-with(normalize-space(.), '${rotulo}')]/parent::*`
    );
  const aba = async (titulo) => {
    await page.getByRole("button", { name: titulo, exact: true }).click();
    await page.waitForTimeout(800);
    await soExemplos();
  };
  const lapis = async (nome) => {
    await linha(nome).waitFor();
    await page.waitForTimeout(500);
    await marcar(linha(nome).getByTitle("Editar"));
  };
  const editar = async (nome) => {
    await linha(nome).getByTitle("Editar").click();
    await page.getByRole("dialog").waitFor();
    await page.waitForTimeout(800);
  };
  const fechar = async () => {
    await page.getByRole("dialog").getByRole("button", { name: "Cancelar" }).click();
    await page.getByRole("dialog").waitFor({ state: "hidden" });
  };

  // Entrar com a pessoa de exemplo (Renata Duarte, secretária).
  await page.goto(`${base}/login`);
  await page.getByPlaceholder("seu@email.com").fill("__EMAIL__");
  await page.getByPlaceholder("••••••••").fill("__SENHA__");
  await page.getByRole("button", { name: "Entrar" }).click();
  await page.waitForURL((url) => !url.toString().includes("/login"), { timeout: 30000 });

  await page.goto(`${base}/admin/dados-atendimento`);
  await page.getByRole("heading", { name: "Dados do Atendimento" }).waitFor();
  await soExemplos();

  // Mudar o preço de uma consulta particular: nada é salvo, a janela fecha
  // pelo Cancelar.
  await lapis("Endocrinologia");
  await foto("consultas-particulares.png");
  await editar("Endocrinologia");
  await marcar(campo("Valor (R$)"));
  await foto("editar-consulta.png");
  await fechar();

  // Mudar o preparo de um exame.
  await aba("Exames");
  await lapis("Glicemia de Jejum");
  await foto("exames.png");
  await editar("Glicemia de Jejum");
  await marcar(campo("Instruções de preparo"));
  await foto("editar-preparo.png");
  await fechar();

  // Mudar a estimativa de uma cirurgia: o total e, mais abaixo na mesma
  // janela, o aviso, cada um na sua foto.
  await aba("Estimativas de cirurgias");
  await lapis("Correção de Hérnia Umbilical");
  await foto("cirurgias.png");
  await editar("Correção de Hérnia Umbilical");
  await marcar(campo("Estimativa total (R$)"));
  await foto("editar-cirurgia.png");
  await marcar(campo("Aviso obrigatório da Ana"));
  await foto("aviso-da-ana.png");
  await fechar();

  return "prints da página de Dados do Atendimento refeitos";
}
