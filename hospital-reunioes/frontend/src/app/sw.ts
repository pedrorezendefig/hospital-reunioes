/// <reference lib="webworker" />

import type { PrecacheEntry, SerwistGlobalConfig } from "serwist";
import { Serwist } from "serwist";

// A lista mora fora daqui porque este arquivo não roda em teste nenhum: ele é
// compilado direto para `public/sw.js` e só existe dentro de um
// ServiceWorkerGlobalScope. O import é relativo porque quem compila o service
// worker é o webpack do Serwist, não o do Next, e o alias `@/` não vale ali.
import { registrarLimpezaNaAtivacao } from "../lib/pwa/cache-limpeza";
import { runtimeCaching } from "../lib/pwa/cache-runtime";

declare global {
  interface WorkerGlobalScope extends SerwistGlobalConfig {
    __SW_MANIFEST: (PrecacheEntry | string)[] | undefined;
  }
}

declare const self: ServiceWorkerGlobalScope;

const serwist = new Serwist({
  precacheEntries: self.__SW_MANIFEST,
  skipWaiting: true,
  clientsClaim: true,
  navigationPreload: true,
  runtimeCaching,
});

serwist.addEventListeners();

// Depois do Serwist, e não antes: os dois escutam `activate`, e a faxina das
// entradas velhas (issue #508) roda em cima dos caches que o Serwist já
// conhece. É o que apaga do aparelho o que o service worker antigo gravou das
// rotas de token antes desta versão existir.
registrarLimpezaNaAtivacao(self);
