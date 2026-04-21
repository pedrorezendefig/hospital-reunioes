"use client";

import { BadgeCheck } from "lucide-react";
import { TaxonomyPage } from "@/components/admin/TaxonomyPage";

export default function CargosPage() {
  return (
    <TaxonomyPage
      title="Cargos"
      subtitle="Taxonomia de cargos da organização"
      endpoint="/api/admin/cargos"
      itemNoun="cargo"
      itemNounArticle="o"
      icon={BadgeCheck}
    />
  );
}
