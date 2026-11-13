// Os prints da página de Contas médicas do manual (issue #1724). Quem roda é o
// roteiro.sh, pelo `playwright-cli run-code`, depois de trocar __BASE__,
// __SAIDA__ (uma pasta de rascunho) e __SEED__ (o seed.json). Cada `foto` grava
// um print citado em public/manual/contas-medicas/pagina.md, e o teste do
// roteiro confere que as duas listas batem. O texto de cada print volta para o
// roteiro, que passa pela guarda antes de levar o PNG para a página.
//
// Nada é confirmado: nem Feito, nem Concluir, nem Perguntar ao auditor, que
// chamaria a IA. Só abrir o Guia muda a conta, e o semear.py a devolve à Fila.
async (page) => {
  const base = "__BASE__";
  const saida = "__SAIDA__";
  const seed = __SEED__;
  const primeira = seed.contas.na_fila.numero_atendimento;
  const doSeed = Object.values(seed.contas).map((conta) => conta.numero_atendimento);
  const semProntuario = seed.contas.falta_o_prontuario.numero_atendimento;
  const textos = [];

  // Uma moldura em volta do que o passo manda clicar. É a única marcação
  // sobre a tela, e quem desenha é este roteiro.
  const marcar = async (alvo) => {
    await alvo.first().waitFor({ state: "visible", timeout: 15000 });
    await alvo.first().evaluate((el) => {
      el.setAttribute("data-marca-do-manual", "");
      el.style.outline = "3px solid #F59E0B";
      el.style.outlineOffset = "2px";
    });
  };
  const limpar = () =>
    page.evaluate(() =>
      document.querySelectorAll("[data-marca-do-manual]").forEach((el) => {
        el.style.outline = "";
        el.removeAttribute("data-marca-do-manual");
      })
    );
  // Sem foco, sem mouse em cima de nada e sem o selo do `next dev` no canto.
  const semFoco = async () => {
    await page.evaluate(() => {
      if (document.activeElement) document.activeElement.blur();
      document.querySelectorAll("nextjs-portal").forEach((selo) => selo.remove());
    });
    await page.mouse.move(1439, 899);
    await page.waitForTimeout(400);
  };
  // O print de um pedaço da tela, ou da tela inteira sem `alvo`. O texto do
  // que foi fotografado vai junto para a guarda.
  const foto = async (arquivo, alvo) => {
    await semFoco();
    const fotografado = alvo ?? page.locator("body");
    textos.push({ arquivo, texto: await fotografado.innerText() });
    if (alvo) await alvo.screenshot({ path: `${saida}/${arquivo}` });
    else await page.screenshot({ path: `${saida}/${arquivo}` });
    await limpar();
  };
  const aba = (nome) => page.getByRole("tab", { name: new RegExp(`^${nome}`) });

  // Entrar com a faturista de exemplo.
  await page.goto(`${base}/login`);
  await page.locator("#email").fill(seed.faturista.email);
  await page.locator("#password").fill(seed.faturista.senha);
  await page.locator("#password").press("Enter");
  await page.waitForURL((url) => !url.pathname.startsWith("/login"), { timeout: 30000 });

  // Enviar uma conta: o quadro de envio e o cartão em Meus envios.
  await page.goto(`${base}/contas-medicas`);
  const envio = page.getByRole("region", { name: "Envio de contas" });
  await envio.waitFor();
  await marcar(envio.getByRole("button", { name: "Selecionar arquivos" }));
  await foto("enviar.png", envio);

  await aba("Meus envios").click();
  const cartao = page.locator("article").filter({ hasText: `Atendimento ${semProntuario}` }).first();
  await marcar(cartao.getByRole("button", { name: "Enviar o prontuário" }));
  await foto("meus-envios.png", cartao);

  // Pegar uma conta da Fila. O banco local tem contas de outros trabalhos: a
  // lista do print fica só com as do seed.
  await aba("Fila").click();
  const fila = page.getByRole("region", { name: "Fila de contas" });
  const linha = fila.getByRole("listitem").filter({ hasText: `Atendimento ${primeira}` });
  await linha.waitFor();
  await fila.evaluate((secao, numeros) => {
    secao.querySelectorAll("li").forEach((li) => {
      if (!numeros.some((n) => li.textContent.includes(`Atendimento ${n}`))) li.style.display = "none";
    });
  }, doSeed);
  await marcar(linha.getByRole("link", { name: "Abrir" }));
  await foto("fila.png", fila);

  await linha.getByRole("link", { name: "Abrir" }).click();
  await page.getByRole("heading", { name: `Atendimento ${primeira}` }).waitFor({ timeout: 30000 });
  await page.waitForTimeout(800);
  await marcar(page.getByRole("button", { name: "Devolver à fila" }));
  await foto("guia.png");

  // Analisar a conta no Guia: uma linha aberta, com a evidência, e o fim do Guia.
  const dipirona = page.getByRole("article", { name: "Dipirona 1 g injetável" });
  await dipirona.getByRole("button", { name: "Ver evidência" }).click();
  await marcar(dipirona.getByRole("button", { name: "Feito" }));
  await foto("linha-do-guia.png", dipirona);

  const rodape = page.locator("footer").filter({ hasText: "Concluir e abrir a próxima" });
  await marcar(rodape.getByRole("button", { name: "Concluir e abrir a próxima" }));
  await foto("concluir.png", rodape);

  // Pedir o que faltou: o Faltou isto do dia, com o quadro preenchido e sem enviar.
  const dia = page.getByRole("region", { name: /^03\/11/ });
  await dia.getByRole("button", { name: "Faltou isto" }).click();
  const conversa = page.getByRole("region", { name: "Falar com o auditor" });
  await conversa.getByLabel("Item que faltou", { exact: true }).fill(seed.faltou_isto.item);
  await conversa.getByLabel("Página do prontuário", { exact: true }).fill(seed.faltou_isto.pagina);
  await conversa.getByLabel("Mensagem para o auditor", { exact: true }).fill(seed.faltou_isto.texto);
  await marcar(conversa.getByRole("button", { name: "Perguntar ao auditor" }));
  await foto("faltou-isto.png", conversa);

  return JSON.stringify(textos);
}
