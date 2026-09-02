"use client";

import { useState, useEffect } from "react";
import { usePathname } from "next/navigation";
import { Sidebar } from "@/components/layout/Sidebar";
import { AdminSidebar } from "@/components/admin/AdminSidebar";
import { Header } from "@/components/layout/Header";
import { MobileDrawer } from "@/components/layout/MobileDrawer";
import { BottomNav } from "@/components/layout/BottomNav";
import { Footer } from "@/components/layout/Footer";
import { useNovidadesOuvidoria } from "@/hooks/useNovidadesOuvidoria";

interface AppShellProps {
  userName: string;
  userEmail?: string;
  variant?: "default" | "admin" | "secretaria";
  children: React.ReactNode;
}

export function AppShell({
  userName,
  userEmail,
  variant = "default",
  children,
}: AppShellProps) {
  const [drawerOpen, setDrawerOpen] = useState(false);
  const pathname = usePathname();
  // O contador de novidades da Ouvidoria (issue #487, RN-69). Buscado UMA vez
  // aqui e distribuído: o menu lateral, a gaveta e a barra do celular mostram
  // o mesmo número, e cada um perguntando por conta seriam três idas ao
  // servidor por navegação pela mesma resposta.
  const novidadesOuvidoria = useNovidadesOuvidoria();

  useEffect(() => {
    setDrawerOpen(false);
  }, [pathname]);

  const closeDrawer = () => setDrawerOpen(false);
  const openDrawer = () => setDrawerOpen(true);

  const sidebarDesktop =
    variant === "admin" ? (
      <AdminSidebar variant="desktop" />
    ) : (
      <Sidebar variant="desktop" novidadesOuvidoria={novidadesOuvidoria} />
    );

  const sidebarDrawer =
    variant === "admin" ? (
      <AdminSidebar variant="drawer" onNavigate={closeDrawer} />
    ) : (
      <Sidebar
        variant="drawer"
        onNavigate={closeDrawer}
        novidadesOuvidoria={novidadesOuvidoria}
      />
    );

  return (
    <div className="flex min-h-screen bg-bg">
      {sidebarDesktop}
      <MobileDrawer open={drawerOpen} onClose={closeDrawer}>
        {sidebarDrawer}
      </MobileDrawer>

      <div className="flex-1 flex flex-col min-w-0">
        <Header
          nome={userName}
          email={userEmail}
          onMenuClick={openDrawer}
        />
        <main className="flex-1 p-4 md:p-8 overflow-auto pb-[88px] md:pb-8">
          {children}
          <Footer />
        </main>
        <BottomNav novidadesOuvidoria={novidadesOuvidoria} />
      </div>
    </div>
  );
}
