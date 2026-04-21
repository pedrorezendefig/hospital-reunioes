import { createClient } from "@/lib/supabase/server";
import { Search } from "lucide-react";
import { NotificacoesDropdown } from "./NotificacoesDropdown";
import { UserProfileDropdown } from "./UserProfileDropdown";

export async function Header() {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  const nome =
    (user?.user_metadata?.nome as string) || user?.email?.split("@")[0] || "Usuário";

  return (
    <header className="relative z-[100] h-16 bg-slate-50 border-b border-slate-200 flex items-center justify-between px-6">
      {/* Search bar (decorative) */}
      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-text-secondary/40" />
        <input
          type="text"
          placeholder="Buscar..."
          className="pl-9 pr-4 py-2 rounded-xl bg-bg border border-border text-sm text-text placeholder:text-text-secondary/40 focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all w-64"
        />
      </div>

      <div className="flex items-center gap-6 mr-6">
        {/* Notifications */}
        <NotificacoesDropdown />

        <div className="w-px h-8 bg-border" />

        {/* Profile with Dropdown */}
        <UserProfileDropdown nome={nome} email={user?.email} />
      </div>
    </header>
  );
}
