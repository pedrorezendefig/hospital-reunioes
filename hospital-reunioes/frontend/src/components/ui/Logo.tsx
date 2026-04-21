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
    sm: isHorizontal ? "w-52" : "w-36",
    md: isHorizontal ? "w-64" : "w-52",
    lg: isHorizontal ? "w-80" : "w-72",
  }[size];

  // Official Hospital São Matheus colors
  const archLeftColor = isWhite ? "#FFFFFF" : "#2B2E7E";
  const archRightColor = isWhite ? "rgba(255,255,255,0.75)" : "#2558A0";
  const textColor = isWhite ? "#FFFFFF" : "#2B2E7E";

  return (
    <div className={`flex items-center justify-center ${containerSize} ${className}`}>
      <div className="relative w-full h-auto transition-all duration-300 hover:scale-105 pointer-events-none select-none">
        {isHorizontal ? (
          // Horizontal layout: arches on the left, text on the right
          <svg
            viewBox="0 0 520 110"
            fill="none"
            xmlns="http://www.w3.org/2000/svg"
            className="w-full h-auto"
          >
            {/* Left arch (darker blue) — flat ends, more spread */}
            <path
              d="M 15 90 A 47 47 0 0 1 109 90"
              stroke={archLeftColor}
              strokeWidth="12"
              strokeLinecap="butt"
              fill="none"
            />
            {/* Right arch (lighter blue) — less overlap */}
            <path
              d="M 85 90 A 47 47 0 0 1 179 90"
              stroke={archRightColor}
              strokeWidth="12"
              strokeLinecap="butt"
              fill="none"
            />

            {/* Text: HOSPITAL — cor do arco direito */}
            <text
              x="200"
              y="52"
              fontFamily="'Barlow', 'Myriad Pro', 'Source Sans Pro', 'Inter', Arial, sans-serif"
              fontSize="26"
              fontWeight="700"
              fill={archRightColor}
              letterSpacing="4"
            >
              HOSPITAL
            </text>

            {/* Text: SÃO MATHEUS — cor do arco esquerdo */}
            <text
              x="200"
              y="87"
              fontFamily="'Barlow', 'Myriad Pro', 'Source Sans Pro', 'Inter', Arial, sans-serif"
              fontSize="30"
              fontWeight="700"
              fill={archLeftColor}
              letterSpacing="2"
            >
              SÃO MATHEUS
            </text>
          </svg>
        ) : (
          // Vertical layout: arcos em cima, texto alinhado a partir do centro dos arcos
          <svg
            viewBox="0 0 290 158"
            fill="none"
            xmlns="http://www.w3.org/2000/svg"
            className="w-full h-auto"
          >
            {/* Left arch (darker blue) — flat ends */}
            <path
              d="M 42 76 A 44 44 0 0 1 130 76"
              stroke={archLeftColor}
              strokeWidth="10"
              strokeLinecap="butt"
              fill="none"
            />
            {/* Right arch (lighter blue) — overlapping */}
            <path
              d="M 106 76 A 44 44 0 0 1 194 76"
              stroke={archRightColor}
              strokeWidth="10"
              strokeLinecap="butt"
              fill="none"
            />

            {/* Text: HOSPITAL — H começa no centro dos arcos (x=118) */}
            <text
              x="118"
              y="103"
              fontFamily="'Barlow', 'Myriad Pro', 'Source Sans Pro', 'Inter', Arial, sans-serif"
              fontSize="19"
              fontWeight="700"
              fill={archRightColor}
              textAnchor="start"
              letterSpacing="0.5"
            >
              HOSPITAL
            </text>

            {/* Text: SÃO MATHEUS — alinhado ao mesmo ponto inicial */}
            <text
              x="118"
              y="126"
              fontFamily="'Barlow', 'Myriad Pro', 'Source Sans Pro', 'Inter', Arial, sans-serif"
              fontSize="22"
              fontWeight="700"
              fill={archLeftColor}
              textAnchor="start"
              letterSpacing="0.5"
            >
              SÃO MATHEUS
            </text>
          </svg>
        )}
      </div>
    </div>
  );
}
