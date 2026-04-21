"use client";

import { useState, useEffect } from "react";
import { Palette, Sun, Moon } from "lucide-react";

export default function AppearanceSection() {
  const [theme, setTheme] = useState<"light" | "dark">("light");
  const [mounted, setMounted] = useState(false);

  // Read theme from localStorage on mount
  useEffect(() => {
    const stored = localStorage.getItem("theme");
    if (stored === "dark") {
      setTheme("dark");
    }
    setMounted(true);
  }, []);

  function handleThemeChange(newTheme: "light" | "dark") {
    setTheme(newTheme);
    localStorage.setItem("theme", newTheme);

    if (newTheme === "dark") {
      document.documentElement.classList.add("dark");
    } else {
      document.documentElement.classList.remove("dark");
    }
  }

  if (!mounted) {
    return (
      <div className="bg-white rounded-2xl border border-border shadow-premium p-6 animate-fade-in-up">
        <div className="h-64" />
      </div>
    );
  }

  return (
    <div className="bg-white rounded-2xl border border-border shadow-premium p-6 animate-fade-in-up">
      {/* Header */}
      <div className="flex items-center gap-3 mb-1">
        <div className="p-2 rounded-xl bg-primary/10">
          <Palette className="w-5 h-5 text-primary" />
        </div>
        <h2 className="text-lg font-bold text-text">Aparência</h2>
      </div>
      <p className="text-text-secondary text-sm mb-6 ml-[44px]">
        Personalize a aparência do sistema
      </p>

      {/* Theme selector */}
      <div className="grid grid-cols-2 gap-4 max-w-md">
        {/* Light */}
        <button
          onClick={() => handleThemeChange("light")}
          className={`group relative flex flex-col items-center gap-3 p-5 rounded-xl border-2 transition-all duration-200 cursor-pointer ${
            theme === "light"
              ? "border-primary bg-primary/5 shadow-md"
              : "border-border hover:border-slate-300 hover:shadow-sm"
          }`}
        >
          {/* Preview card */}
          <div className="w-full aspect-[4/3] rounded-lg border border-slate-200 bg-white overflow-hidden p-2">
            <div className="h-2 w-12 bg-slate-200 rounded mb-1.5" />
            <div className="h-1.5 w-16 bg-slate-100 rounded mb-2" />
            <div className="flex gap-1.5">
              <div className="h-6 flex-1 bg-slate-50 rounded" />
              <div className="h-6 flex-1 bg-primary/10 rounded" />
            </div>
          </div>

          <div className="flex items-center gap-2">
            <Sun className="w-4 h-4 text-amber-500" />
            <span className="text-sm font-medium text-text">Claro</span>
          </div>

          {theme === "light" && (
            <div className="absolute top-2.5 right-2.5 w-5 h-5 rounded-full bg-primary flex items-center justify-center">
              <svg className="w-3 h-3 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
              </svg>
            </div>
          )}
        </button>

        {/* Dark */}
        <button
          onClick={() => handleThemeChange("dark")}
          className={`group relative flex flex-col items-center gap-3 p-5 rounded-xl border-2 transition-all duration-200 cursor-pointer ${
            theme === "dark"
              ? "border-primary bg-primary/5 shadow-md"
              : "border-border hover:border-slate-300 hover:shadow-sm"
          }`}
        >
          {/* Preview card */}
          <div className="w-full aspect-[4/3] rounded-lg border border-slate-600 bg-slate-800 overflow-hidden p-2">
            <div className="h-2 w-12 bg-slate-600 rounded mb-1.5" />
            <div className="h-1.5 w-16 bg-slate-700 rounded mb-2" />
            <div className="flex gap-1.5">
              <div className="h-6 flex-1 bg-slate-700 rounded" />
              <div className="h-6 flex-1 bg-primary/30 rounded" />
            </div>
          </div>

          <div className="flex items-center gap-2">
            <Moon className="w-4 h-4 text-indigo-400" />
            <span className="text-sm font-medium text-text">Escuro</span>
          </div>

          {theme === "dark" && (
            <div className="absolute top-2.5 right-2.5 w-5 h-5 rounded-full bg-primary flex items-center justify-center">
              <svg className="w-3 h-3 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
              </svg>
            </div>
          )}
        </button>
      </div>

      {/* Info */}
      <p className="text-xs text-text-secondary mt-4">
        O tema escuro será disponibilizado em breve. A preferência já está sendo salva.
      </p>
    </div>
  );
}
