import { Target } from "lucide-react";

import { EmConstrucao } from "@/components/central-de-comando/EmConstrucao";

/** Os Objetivos da Central de Comando: chegam numa fatia própria do PRD #809. */
export default function ObjetivosPage() {
  return (
    <EmConstrucao
      titulo="Objetivos"
      icone={Target}
      descricao="Escolha onde a diretoria quer chegar e veja só os números que importam para esse Objetivo."
    />
  );
}
