import gsap from "https://esm.sh/gsap@3.12.5";
import { ScrollTrigger } from "https://esm.sh/gsap@3.12.5/ScrollTrigger";
import Lenis from "https://esm.sh/lenis@1.1.13";

gsap.registerPlugin(ScrollTrigger);

const prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
if (prefersReducedMotion) document.documentElement.classList.add("no-motion");

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

const SVG_NS = "http://www.w3.org/2000/svg";
function svgEl(name, attrs = {}) {
  const el = document.createElementNS(SVG_NS, name);
  for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, v);
  return el;
}

async function bootstrap() {
  const skills = await fetch("./data/skills.json").then((r) => r.json());

  renderCategorias(skills);
  bindCopySnippets();
  bindCopyInstall();

  if (!prefersReducedMotion) {
    initLenis();
    initHeroIntro();
    initRevealAnimations();
  } else {
    $$("[data-reveal]").forEach((el) => (el.style.opacity = "1"));
  }
}

bootstrap().catch((err) => {
  console.error("falha no bootstrap", err);
});

/* ================================
   render: categorias e cards
   ================================ */
function renderCategorias(skills) {
  const container = $("#sessoes");
  const tplCat = $("#categoriaTemplate");
  const tplCard = $("#cardTemplate");

  skills.categories.forEach((cat) => {
    const node = tplCat.content.firstElementChild.cloneNode(true);
    node.id = `cat-${cat.id}`;
    node.dataset.categoria = cat.id;
    if (cat.tone) node.dataset.tone = cat.tone;
    if (cat.accent) node.style.setProperty("--cat-accent", cat.accent);

    $(".categoria__num", node).textContent = cat.number;
    $(".categoria__title", node).textContent = cat.name;
    $(".categoria__tagline", node).textContent = cat.tagline;
    $(".categoria__desc", node).textContent = cat.description;

    const grid = $(".categoria__grid", node);
    const items = skills.items.filter((it) => it.category === cat.id);

    items.forEach((item) => {
      const card = tplCard.content.firstElementChild.cloneNode(true);
      card.dataset.slug = item.slug;
      card.dataset.tone = cat.tone || "";
      card.dataset.category = cat.id;
      card.dataset.kind = item.kind;

      $(".card__name", card).textContent = item.name;
      const kind = $(".card__kind", card);
      kind.textContent = item.kind === "plugin" ? "plugin" : item.scope === "project" ? "skill · projeto" : "skill";
      kind.dataset.kind = item.kind;

      $(".card__tagline", card).textContent = item.tagline;
      $("[data-why]", card).textContent = item.why || "";
      $("[data-trigger]", card).textContent = item.trigger || "";

      if (item.triggerNatural && item.triggerNatural.length) {
        const wrap = $("[data-natural-wrap]", card);
        const list = $("[data-natural]", card);
        item.triggerNatural.forEach((t) => {
          const span = document.createElement("span");
          span.textContent = `"${t}"`;
          list.appendChild(span);
        });
        wrap.hidden = false;
      }

      if (item.prompt && item.promptExplain) {
        const promptWrap = $("[data-prompt-wrap]", card);
        $("[data-prompt]", card).textContent = item.prompt;
        $("[data-prompt-explain]", card).textContent = item.promptExplain;
        $("[data-copy-prompt]", card).dataset.copyText = item.prompt;
        promptWrap.hidden = false;
      }

      const installBtn = $("[data-copy-install]", card);
      installBtn.dataset.install =
        item.kind === "plugin"
          ? item.trigger
          : item.scope === "project"
            ? `mkdir -p <projeto>/.claude/skills/${item.slug} && curl -fsSL https://raw.githubusercontent.com/pedrorezende/claude-skills/main/${item.slug}/SKILL.md -o <projeto>/.claude/skills/${item.slug}/SKILL.md`
            : `curl -fsSL https://raw.githubusercontent.com/pedrorezende/claude-skills/main/install.sh | bash -s -- ${item.slug}`;

      const link = $("[data-link]", card);
      if (item.kind === "plugin") {
        link.firstChild.textContent = "marketplace";
        link.href = `https://github.com/search?q=${encodeURIComponent(item.name + " " + item.marketplace)}&type=repositories`;
      } else {
        link.href = `https://github.com/pedrorezende/claude-skills/blob/main/${item.slug}/SKILL.md`;
      }

      grid.appendChild(card);
    });

    container.appendChild(node);
  });
}

/* ================================
   motion: lenis
   ================================ */
function initLenis() {
  const lenis = new Lenis({
    duration: 1.0,
    easing: (t) => Math.min(1, 1.001 - Math.pow(2, -10 * t)),
  });
  lenis.on("scroll", ScrollTrigger.update);
  gsap.ticker.add((time) => lenis.raf(time * 1000));
  gsap.ticker.lagSmoothing(0);

  $$('a[href^="#"]').forEach((a) => {
    a.addEventListener("click", (e) => {
      const id = a.getAttribute("href");
      if (id.length > 1) {
        const target = document.querySelector(id);
        if (target) {
          e.preventDefault();
          lenis.scrollTo(target, { offset: -40 });
        }
      }
    });
  });
}

/* ================================
   motion: hero intro (contida)
   ================================ */
function initHeroIntro() {
  gsap.from(".nav", { y: -16, opacity: 0, duration: 0.6, ease: "power2.out" });
  gsap.from(".hero__inner", {
    y: 14,
    opacity: 0,
    duration: 0.75,
    delay: 0.05,
    ease: "power2.out",
  });
}

/* ================================
   motion: scroll reveal (sutil)
   ================================ */
function initRevealAnimations() {
  $$("[data-reveal]").forEach((el) => {
    if (el.closest(".hero") || el.closest(".nav")) return;
    gsap.fromTo(
      el,
      { opacity: 0, y: 14 },
      {
        opacity: 1,
        y: 0,
        duration: 0.6,
        ease: "power2.out",
        scrollTrigger: { trigger: el, start: "top 88%", once: true },
      }
    );
  });

  $$(".categoria__header").forEach((header) => {
    gsap.fromTo(
      header.children,
      { opacity: 0, y: 12 },
      {
        opacity: 1,
        y: 0,
        duration: 0.55,
        stagger: 0.04,
        ease: "power2.out",
        scrollTrigger: { trigger: header, start: "top 85%", once: true },
      }
    );
  });

  $$(".categoria__grid").forEach((grid) => {
    gsap.fromTo(
      grid.children,
      { opacity: 0, y: 12 },
      {
        opacity: 1,
        y: 0,
        duration: 0.5,
        stagger: 0.04,
        ease: "power2.out",
        scrollTrigger: { trigger: grid, start: "top 85%", once: true },
      }
    );
  });

  $$(".setup__card").forEach((card, i) => {
    gsap.fromTo(
      card,
      { opacity: 0, y: 12 },
      {
        opacity: 1,
        y: 0,
        duration: 0.55,
        delay: i * 0.05,
        ease: "power2.out",
        scrollTrigger: { trigger: card, start: "top 88%", once: true },
      }
    );
  });
}

/* ================================
   copy: snippets do setup
   ================================ */
function bindCopySnippets() {
  $$("[data-copy]").forEach((el) => {
    el.addEventListener("click", () => {
      const text = el.textContent.trim();
      navigator.clipboard.writeText(text).then(() => {
        el.classList.add("is-copied");
        showToast("comando copiado");
        setTimeout(() => el.classList.remove("is-copied"), 1400);
      });
    });
  });
}

/* ================================
   copy: install dos cards
   ================================ */
function bindCopyInstall() {
  document.addEventListener("click", (e) => {
    const btn = e.target.closest("[data-copy-install]");
    if (!btn) return;
    const text = btn.dataset.install;
    if (!text) return;
    navigator.clipboard.writeText(text).then(() => {
      btn.classList.add("is-copied");
      replaceBtnLabel(btn, true);
      showToast("install copiado");
      setTimeout(() => {
        btn.classList.remove("is-copied");
        replaceBtnLabel(btn, false);
      }, 1800);
    });
  });

  document.addEventListener("click", (e) => {
    const btn = e.target.closest("[data-copy-prompt]");
    if (!btn) return;
    const text = btn.dataset.copyText;
    if (!text) return;
    navigator.clipboard.writeText(text).then(() => {
      btn.classList.add("is-copied");
      showToast("prompt copiado");
      setTimeout(() => btn.classList.remove("is-copied"), 1400);
    });
  });
}

function replaceBtnLabel(btn, copied) {
  while (btn.firstChild) btn.removeChild(btn.firstChild);
  const svg = svgEl("svg", { width: "12", height: "12", viewBox: "0 0 12 12", fill: "none", "aria-hidden": "true" });
  if (copied) {
    svg.appendChild(
      svgEl("path", {
        d: "M2 6.5L5 9l5-6",
        stroke: "currentColor",
        "stroke-width": "1.4",
        "stroke-linecap": "round",
        "stroke-linejoin": "round",
      })
    );
  } else {
    svg.appendChild(
      svgEl("rect", {
        x: "2",
        y: "2",
        width: "6",
        height: "6",
        stroke: "currentColor",
        "stroke-width": "1.1",
        rx: "0.8",
      })
    );
    svg.appendChild(
      svgEl("rect", {
        x: "4",
        y: "4",
        width: "6",
        height: "6",
        stroke: "currentColor",
        "stroke-width": "1.1",
        rx: "0.8",
      })
    );
  }
  btn.appendChild(svg);
  btn.appendChild(document.createTextNode(copied ? "copiado" : "copiar install"));
}

/* ================================
   toast
   ================================ */
let toastTimer;
function showToast(msg) {
  const t = $("#toast");
  t.textContent = msg;
  t.classList.add("is-show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.remove("is-show"), 1600);
}
