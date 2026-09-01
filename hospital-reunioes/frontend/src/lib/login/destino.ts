/**
 * O destino de retorno do login (issue #477, RN-54, PRD #468).
 *
 * Quem clica no link de um caso da Ouvidoria estando deslogado cai no login e,
 * depois de autenticar, precisa cair no caso, e não na tela inicial. O destino
 * viaja na query string do `/login`, e é justamente por viajar em URL que ele
 * não pode ser obedecido cru: quem monta o link escolhe o valor. Um destino
 * apontando para fora transformaria a nossa tela de login em trampolim de
 * phishing (a pessoa confere o domínio do hospital, autentica, e é jogada num
 * site parecido que pede a senha de novo). É o open redirect de manual.
 *
 * A régua, então, é uma só e vale nas duas pontas: só caminho do próprio site
 * é destino. O que não for cai no padrão, em silêncio, sem mensagem de erro
 * (não há nada que o usuário legítimo possa fazer a respeito, e explicar a
 * recusa só ajudaria quem está testando o que passa).
 */

/** Para onde o login manda quem não trouxe destino, ou trouxe destino que não vale. */
export const DESTINO_PADRAO = "/dashboard";

/** O nome do parâmetro que carrega o destino na query string do login. */
export const PARAM_DESTINO = "redirect";

// Origem de mentira, só para o parser de URL ter contra o que medir. Nada é
// buscado nela: se o valor recebido conseguir trocar esta origem, ele aponta
// para fora e está reprovado.
const ORIGEM_DE_MEDICAO = "http://interno.invalido";

/**
 * O caminho interno equivalente ao valor recebido, ou `null` se ele não for um.
 *
 * Devolve a forma normalizada pelo parser de URL, e não o texto cru: o que vai
 * para a navegação é o que foi medido.
 */
export function caminhoInternoOuNulo(valor: unknown): string | null {
  if (typeof valor !== "string") return null;

  // Caminho é caminho: começa na raiz do próprio site.
  if (!valor.startsWith("/")) return null;

  // Barra invertida não tem uso legítimo em rota nossa, e tem dois usos
  // ilegítimos. No começo, `/\evil.com` vira `//evil.com` na normalização do
  // navegador, que é URL de protocolo relativo apontando para fora. No meio,
  // `/ouvidoria\..\evil` é a travessia de diretório que o parser de URL desfaz
  // sem reclamar, entregando um caminho que ninguém escreveu.
  if (valor.includes("\\")) return null;

  // Espaço, tabulação, quebra de linha e caracteres de controle são o material
  // de que se fazem os contrabandos de cabeçalho e os esquemas disfarçados.
  const temCaractereProibido = Array.from(valor).some((c) => {
    const codigo = c.codePointAt(0) ?? 0;
    return codigo <= 0x20 || codigo === 0x7f;
  });
  if (temCaractereProibido) return null;

  let url: URL;
  try {
    url = new URL(valor, ORIGEM_DE_MEDICAO);
  } catch {
    return null;
  }
  // A prova final, e a que não depende de eu ter lembrado de toda variante: se
  // a origem mudou, o valor levava para fora. É ela que pega `//evil.com`, que
  // começa com barra e mesmo assim é URL de protocolo relativo, e os esquemas
  // de origem opaca como `javascript:`.
  if (url.origin !== ORIGEM_DE_MEDICAO) return null;

  return `${url.pathname}${url.search}${url.hash}`;
}

/** Para onde mandar a pessoa depois de autenticar. */
export function destinoAposLogin(valor: unknown): string {
  return caminhoInternoOuNulo(valor) ?? DESTINO_PADRAO;
}

/**
 * A URL do login carregando o destino original.
 *
 * Destino que não vale não vira query string nenhuma: a pessoa vai para o login
 * limpo e, depois de autenticar, para o padrão.
 */
export function urlDeLoginCom(destino: unknown): string {
  const seguro = caminhoInternoOuNulo(destino);
  if (!seguro) return "/login";
  return `/login?${PARAM_DESTINO}=${encodeURIComponent(seguro)}`;
}
