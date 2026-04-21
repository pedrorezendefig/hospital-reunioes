"use client";

import { CalendarRange } from "lucide-react";
import { TaxonomyPage } from "@/components/admin/TaxonomyPage";

export default function TiposReuniaoPage() {
  return (
    <TaxonomyPage
      title="Tipos de Reunião"
      subtitle="Taxonomia de tipos de reunião"
      endpoint="/api/admin/tipos-reuniao"
      itemNoun="tipo de reunião"
      itemNounArticle="o"
      icon={CalendarRange}
    />
  );
}
