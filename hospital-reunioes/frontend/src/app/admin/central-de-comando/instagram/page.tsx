import { Camera } from "lucide-react";

import { EmConstrucao } from "@/components/central-de-comando/EmConstrucao";

/** O Instagram da Central de Comando: chega na fatia do provedor do Instagram (#819). */
export default function InstagramPage() {
  return (
    <EmConstrucao
      titulo="Instagram"
      icone={Camera}
      descricao="Seguidores, Alcance, Visualizações e Interações do Instagram do hospital."
    />
  );
}
