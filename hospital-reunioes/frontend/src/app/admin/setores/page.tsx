"use client";

import { Building2 } from "lucide-react";
import { TaxonomyPage } from "@/components/admin/TaxonomyPage";

export default function SetoresPage() {
  return (
    <TaxonomyPage
      title="Setores"
      subtitle="Taxonomia de setores organizacionais"
      endpoint="/api/admin/setores"
      itemNoun="setor"
      itemNounArticle="o"
      icon={Building2}
    />
  );
}
