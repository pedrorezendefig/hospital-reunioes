/// <reference lib="webworker" />

import type { PrecacheEntry, SerwistGlobalConfig } from "serwist";
import { Serwist } from "serwist";

// A lista mora fora daqui porque este arquivo não roda em teste nenhum: ele é
// compilado direto para `public/sw.js` e só existe dentro de um
// ServiceWorkerGlobalScope. O import é relativo porque quem compila o service
// worker é o webpack do Serwist, não o do Next, e o alias `@/` não vale ali.
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
