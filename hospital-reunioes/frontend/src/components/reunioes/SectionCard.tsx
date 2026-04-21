"use client";

import type { LucideIcon } from "lucide-react";

interface SectionProps {
  title: string;
  icon?: LucideIcon;
  children: React.ReactNode;
  action?: React.ReactNode;
}

export default function SectionCard({ title, icon: Icon, children, action }: SectionProps) {
  return (
    <div className="bg-white rounded-2xl border border-border shadow-premium">
      <div className="px-6 py-4 border-b border-slate-100 flex items-center justify-between gap-2.5">
        <div className="flex items-center gap-2.5">
          {Icon && <Icon className="w-4.5 h-4.5 text-primary" strokeWidth={1.5} />}
          <h2 className="font-semibold text-slate-900">{title}</h2>
        </div>
        {action}
      </div>
      <div className="px-6 py-5">{children}</div>
    </div>
  );
}
