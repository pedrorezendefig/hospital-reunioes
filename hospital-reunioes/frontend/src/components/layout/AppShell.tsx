"use client";

import { useState, useEffect } from "react";
import { usePathname } from "next/navigation";
import { Sidebar } from "@/components/layout/Sidebar";
import { AdminSidebar } from "@/components/admin/AdminSidebar";
import { Header } from "@/components/layout/Header";
import { MobileDrawer } from "@/components/layout/MobileDrawer";
import { BottomNav } from "@/components/layout/BottomNav";
import { Footer } from "@/components/layout/Footer";

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

  useEffect(() => {
    setDrawerOpen(false);
  }, [pathname]);

  const closeDrawer = () => setDrawerOpen(false);
  const openDrawer = () => setDrawerOpen(true);

  const sidebarDesktop =
    variant === "admin" ? (
      <AdminSidebar variant="desktop" />
    ) : (
      <Sidebar variant="desktop" />
    );

  const sidebarDrawer =
    variant === "admin" ? (
      <AdminSidebar variant="drawer" onNavigate={closeDrawer} />
    ) : (
      <Sidebar variant="drawer" onNavigate={closeDrawer} />
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
        <BottomNav />
      </div>
    </div>
  );
}
