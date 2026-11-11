"use client";

import { useEffect, useState } from "react";

const CHAVE = "menu-recolhido";

/**
 * Se o menu lateral do computador está recolhido para só os ícones
 * (issue #1550). Uma preferência só para as duas barras, a do app e a da
 * administração, guardada no navegador.
 *
 * O armazenamento pode faltar (navegação privada, cota cheia, bloqueio do
 * navegador) e aí lança erro: a leitura cai na barra expandida e a gravação
 * só deixa de lembrar, sem quebrar a tela.
 */
export function useMenuRecolhido(): [boolean, () => void] {
  // Começa expandida e só lê depois de montar: o servidor não tem o
  // armazenamento, e ler no primeiro render desencontraria a hidratação.
  const [recolhido, setRecolhido] = useState(false);

  useEffect(() => {
    setRecolhido(lerPreferencia());
  }, []);

  const alternar = () => {
    const novo = !recolhido;
    setRecolhido(novo);
    gravarPreferencia(novo);
  };

  return [recolhido, alternar];
}

function lerPreferencia(): boolean {
  try {
    return window.localStorage.getItem(CHAVE) === "1";
  } catch {
    return false;
  }
}

function gravarPreferencia(recolhido: boolean): void {
  try {
    window.localStorage.setItem(CHAVE, recolhido ? "1" : "0");
  } catch {
    // Sem armazenamento a escolha vale só para a página aberta.
  }
}
