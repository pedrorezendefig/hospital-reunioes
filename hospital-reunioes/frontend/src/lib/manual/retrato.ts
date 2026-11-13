/**
 * A montagem do Retrato da Ana numa página só (issue #1720, ADR 0094, decisão 3).
 *
 * O backend serve o Retrato arquivo por arquivo, só para Super admin, e o
 * login vai no cabeçalho de cada pedido. O quadro em que o Retrato aparece é
 * isolado da página do app (sem o login e sem os dados dela), então ele não
 * consegue buscar nada sozinho. Por isso a tela busca tudo antes, com o login
 * do app, e entrega ao quadro uma página que já traz dentro o CSS, os scripts,
 * as imagens, as fontes e os dados.
 *
 * Os dados entram por `window.RETRATO_DADOS`, que o script do Retrato lê no
 * lugar de `dados/retrato.json` quando existe.
 */

/** Um arquivo do Retrato pelo caminho a partir de `retrato/`, pela rota do backend. */
export type BuscarArquivoDoRetrato = (caminho: string) => Promise<Response>;

const DADOS = "dados/retrato.json";

/** Caminho relativo à página, e não endereço de fora, âncora ou dado embutido. */
function relativo(endereco: string | null): endereco is string {
  return !!endereco && !/^([a-z][a-z0-9+.-]*:|\/|#)/i.test(endereco.trim());
}

/** O caminho a partir de `retrato/`, resolvido contra o arquivo que o cita. */
function resolver(arquivo: string, endereco: string): string {
  const url = new URL(endereco.trim(), `https://retrato.invalido/${arquivo}`);
  return decodeURIComponent(url.pathname.slice(1));
}

async function pedir(buscar: BuscarArquivoDoRetrato, caminho: string): Promise<Response> {
  const resposta = await buscar(caminho);
  if (!resposta.ok) throw new Error(`O Retrato não entregou ${caminho} (${resposta.status})`);
  return resposta;
}

async function comoDataUrl(buscar: BuscarArquivoDoRetrato, caminho: string): Promise<string> {
  const resposta = await pedir(buscar, caminho);
  const tipo = resposta.headers.get("Content-Type") || "application/octet-stream";
  const bytes = new Uint8Array(await resposta.arrayBuffer());
  let binario = "";
  for (let i = 0; i < bytes.length; i += 0x8000) {
    binario += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  }
  return `data:${tipo};base64,${btoa(binario)}`;
}

async function comoTexto(buscar: BuscarArquivoDoRetrato, caminho: string): Promise<string> {
  return (await pedir(buscar, caminho)).text();
}

/** O CSS com cada `url(...)` relativo trocado pelo arquivo embutido. */
async function cssEmbutido(buscar: BuscarArquivoDoRetrato, caminho: string): Promise<string> {
  const css = await comoTexto(buscar, caminho);
  const padrao = /url\(\s*(['"]?)([^'")]+)\1\s*\)/g;
  const trocas = new Map<string, string>();
  for (const [, , endereco] of css.matchAll(padrao)) {
    if (relativo(endereco) && !trocas.has(endereco)) {
      trocas.set(endereco, await comoDataUrl(buscar, resolver(caminho, endereco)));
    }
  }
  return css.replace(padrao, (inteiro, _aspas, endereco: string) =>
    trocas.has(endereco) ? `url("${trocas.get(endereco)}")` : inteiro,
  );
}

/** Um `</script>` ou `</style>` dentro do código fecharia a tag antes da hora. */
function semFechamento(codigo: string, tag: "script" | "style"): string {
  return codigo.replace(new RegExp(`</(${tag})`, "gi"), "<\\/$1");
}

/** A página do Retrato com tudo dentro, pronta para o quadro isolado. */
export async function montarRetrato(buscar: BuscarArquivoDoRetrato): Promise<string> {
  const doc = new DOMParser().parseFromString(await comoTexto(buscar, "index.html"), "text/html");

  for (const link of doc.querySelectorAll<HTMLLinkElement>("link[rel~=stylesheet][href]")) {
    const href = link.getAttribute("href");
    if (!relativo(href)) continue;
    const estilo = doc.createElement("style");
    estilo.textContent = semFechamento(await cssEmbutido(buscar, resolver("index.html", href)), "style");
    link.replaceWith(estilo);
  }

  for (const script of doc.querySelectorAll<HTMLScriptElement>("script[src]")) {
    const src = script.getAttribute("src");
    if (!relativo(src)) continue;
    script.removeAttribute("src");
    script.textContent = semFechamento(await comoTexto(buscar, resolver("index.html", src)), "script");
  }

  for (const img of doc.querySelectorAll<HTMLImageElement>("img[src]")) {
    const src = img.getAttribute("src");
    if (relativo(src)) img.setAttribute("src", await comoDataUrl(buscar, resolver("index.html", src)));
  }

  const dados = doc.createElement("script");
  dados.textContent = `window.RETRATO_DADOS = ${JSON.stringify(await comoDataUrl(buscar, DADOS))};`;
  doc.head.prepend(dados);

  return `<!doctype html>\n${doc.documentElement.outerHTML}`;
}
