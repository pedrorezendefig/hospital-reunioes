"use client";

import { useState } from "react";

/**
 * Se o menu lateral do computador está recolhido para só os ícones
 * (issue #1550). Uma preferência só para as duas barras, a do app e a da
 * administração.
 */
export function useMenuRecolhido(): [boolean, () => void] {
  const [recolhido, setRecolhido] = useState(false);
  const alternar = () => setRecolhido((atual) => !atual);
  return [recolhido, alternar];
}
