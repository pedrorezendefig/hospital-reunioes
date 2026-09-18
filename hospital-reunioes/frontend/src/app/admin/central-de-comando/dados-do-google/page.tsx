import { ChartLine } from "lucide-react";

import { EmConstrucao } from "@/components/central-de-comando/EmConstrucao";

/** Os Dados do Google da Central de Comando: chegam numa fatia própria do PRD #809. */
export default function DadosDoGooglePage() {
  return (
    <EmConstrucao
      titulo="Dados do Google"
      icone={ChartLine}
      descricao="O movimento do Site, direto do Google Analytics, em linguagem simples."
    />
  );
}
