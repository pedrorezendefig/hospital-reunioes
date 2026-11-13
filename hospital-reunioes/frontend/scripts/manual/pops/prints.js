// Os prints da página de POPs do manual (issue #1722). Quem roda é o
// roteiro.sh, pelo `playwright-cli run-code`, depois de trocar __BASE__,
// __SAIDA__, __EMAIL__ e __SENHA__. Cada chamada de `foto` grava um print
// citado em public/manual/pops/pagina.md, e o teste da página confere que as
// duas listas batem.
async (page) => {
  const base = "__BASE__";
  const saida = "__SAIDA__";

  // Uma moldura em volta do que o passo manda clicar. É a única marcação
  // sobre a tela, e quem desenha é este roteiro: quando a tela muda, ela vem junto.
  const marcar = async (alvo) => {
    await alvo.first().waitFor({ state: "visible", timeout: 15000 });
    await alvo.first().evaluate((el) => {
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
  const foto = async (arquivo, opcoes = {}) => {
    await semFoco();
    await page.screenshot({ path: `${saida}/${arquivo}`, ...opcoes });
    await limpar();
  };
  const linha = (codigo) => page.getByRole("row").filter({ hasText: codigo }).first();

  // Entrar com a pessoa de exemplo (Carla Mendes, perfil Gerente dos POPs).
  await page.goto(`${base}/login`);
  await page.getByPlaceholder("seu@email.com").fill("__EMAIL__");
  await page.getByPlaceholder("••••••••").fill("__SENHA__");
  await page.getByRole("button", { name: "Entrar" }).click();
  await page.waitForURL((url) => !url.toString().includes("/login"), { timeout: 30000 });

  const abrirGestao = async () => {
    await page.goto(`${base}/pops`);
    await linha("HSM_PA-003").waitFor();
    await page.waitForTimeout(800);
  };
  const idDoPop = async (codigo) => {
    await abrirGestao();
    const destino = await linha(codigo).getByRole("link").first().getAttribute("href");
    return destino.split("/pops/")[1].split("/")[0];
  };

  // Achar um POP publicado: a Biblioteca e a Ficha do POP.
  await page.goto(`${base}/pops/biblioteca`);
  await linha("HSM_LAB-001").waitFor();
  await page.waitForTimeout(800);
  await marcar(linha("HSM_LAB-001").getByTitle("Ficha do POP"));
  await foto("biblioteca.png");

  await linha("HSM_LAB-001").getByTitle("Ficha do POP").click();
  await page.getByText("Datas de cada etapa").waitFor();
  await page.waitForTimeout(1000);
  await marcar(page.getByRole("button", { name: "Baixar PDF assinado" }));
  await foto("ficha-do-pop.png");

  // Criar um POP: o botão na lista e o formulário preenchido (sem enviar).
  await abrirGestao();
  await marcar(page.getByRole("button", { name: "Criar novo POP" }));
  await foto("gestao-de-pops.png");

  await page.getByRole("button", { name: "Criar novo POP" }).click();
  await page.getByPlaceholder("Ex.: Higienização das Mãos").waitFor();
  await page.waitForTimeout(1200);
  const escolher = async (rotulo, opcao) => {
    await page
      .locator(`xpath=//label[normalize-space()='${rotulo}']/following::*[@role='combobox'][1]`)
      .first()
      .click();
    await page.getByRole("option", { name: opcao, exact: true }).first().click();
  };
  await escolher("Setor", "Pronto Atendimento (PA)");
  await escolher("Criticidade", "ALTA");
  await page.getByPlaceholder("Ex.: Higienização das Mãos").fill("POP Administração de Medicamentos");
  await escolher("Elaborador", "Lúcia Moraes");
  await escolher("Revisor", "Carla Mendes");
  await escolher("Validador", "Fábio Rangel");
  await escolher("Periodicidade de revisão", "1 ano");
  await marcar(page.getByRole("button", { name: "Criar POP", exact: true }));
  await foto("criar-novo-pop.png");
  await page.keyboard.press("Escape");

  // Escrever o POP: a tela de elaboração com o Consultor de POPs.
  const elaborar = await idDoPop("HSM_PA-003");
  await page.goto(`${base}/pops/${elaborar}/elaboracao`);
  await page.getByText("Consultor de POPs").waitFor();
  await page.waitForTimeout(1500);
  await marcar(page.getByRole("button", { name: "Aprovar versão final" }));
  await foto("elaboracao.png");

  // Revisar: a Versão aberta pela revisora, com Aprovar e Devolver.
  const revisar = await idDoPop("HSM_PA-001");
  await page.goto(`${base}/pops/${revisar}/versao`);
  await page.getByRole("button", { name: "Aprovar revisão" }).waitFor();
  await page.waitForTimeout(1000);
  await marcar(page.getByRole("button", { name: "Aprovar revisão" }));
  await marcar(page.getByRole("button", { name: "Devolver com comentários" }));
  await foto("revisao.png");

  // Devolver: a janela abre e nada é confirmado, para o POP não mudar de etapa.
  await page.getByRole("button", { name: "Devolver com comentários" }).click();
  await page.getByText("Devolver à elaboração?").waitFor();
  await page.waitForTimeout(1000);
  await foto("devolver.png");
  await page.keyboard.press("Escape");

  // Validar e mandar para a assinatura.
  const validar = await idDoPop("HSM_PA-002");
  await page.goto(`${base}/pops/${validar}/versao`);
  await page.getByRole("button", { name: "Aprovar validação" }).waitFor();
  await page.waitForTimeout(1000);
  await marcar(page.getByRole("button", { name: "Aprovar validação" }));
  await foto("validacao.png");

  // A versão em assinatura, na lista: publica sozinha com a última assinatura.
  await abrirGestao();
  await page.getByRole("button", { name: "Em Assinatura", exact: true }).click();
  await linha("HSM_LAB-002").waitFor();
  await page.waitForTimeout(600);
  await marcar(linha("HSM_LAB-002").getByText("Em Assinatura"));
  await foto("em-assinatura.png");

  return "prints da página de POPs refeitos";
}
