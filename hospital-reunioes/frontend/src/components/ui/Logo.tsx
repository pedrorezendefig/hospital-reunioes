import React from "react";

interface LogoProps {
  className?: string;
  variant?: "default" | "white";
  layout?: "horizontal" | "vertical";
  size?: "sm" | "md" | "lg";
}

export function Logo({
  className = "",
  variant = "default",
  layout = "vertical",
  size = "md",
}: LogoProps) {
  const isWhite = variant === "white";
  const isHorizontal = layout === "horizontal";

  const containerSize = {
    sm: isHorizontal ? "w-44" : "w-32",
    md: isHorizontal ? "w-56" : "w-44",
    lg: isHorizontal ? "w-72" : "w-64",
  }[size];

  return (
    <div
      className={`flex items-center justify-center ${containerSize} ${className}`}
    >
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src="/logo-hsm.png"
        alt="Hospital São Matheus"
        className="w-full h-auto transition-all duration-300 hover:scale-105 pointer-events-none select-none"
        style={isWhite ? { filter: "brightness(0) invert(1)" } : undefined}
        draggable={false}
      />
    </div>
  );
}
