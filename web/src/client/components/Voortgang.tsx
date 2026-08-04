/** Live voortgang van een lopende hergeneratie. */

import { useEffect, useRef } from "react";

import { TOTAAL_STAPPEN } from "../../shared/types.js";

export interface Regel {
  id: number;
  soort: "stap" | "info" | "warning" | "error";
  tekst: string;
}

interface VoortgangProps {
  stap: number;
  regels: Regel[];
}

const KLEUREN: Record<Regel["soort"], string> = {
  stap: "text-slate-900 font-medium",
  info: "text-slate-600",
  warning: "text-amber-700",
  error: "text-red-700 font-medium",
};

export function Voortgang({ stap, regels }: VoortgangProps) {
  const eindeRef = useRef<HTMLDivElement>(null);

  // Houd de laatste regel in beeld tijdens een lange run.
  useEffect(() => {
    eindeRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [regels.length]);

  const percentage = Math.round(
    (Math.min(stap, TOTAAL_STAPPEN) / TOTAAL_STAPPEN) * 100,
  );

  return (
    <div className="space-y-3">
      <div>
        <div className="mb-1 flex justify-between text-sm text-slate-600">
          <span>
            Stap {Math.min(stap, TOTAAL_STAPPEN)} van {TOTAAL_STAPPEN}
          </span>
          <span>{percentage}%</span>
        </div>
        <div
          role="progressbar"
          aria-valuenow={percentage}
          aria-valuemin={0}
          aria-valuemax={100}
          className="h-2 w-full overflow-hidden rounded-full bg-slate-200"
        >
          <div
            className="h-full rounded-full bg-miedema-goud transition-all duration-500"
            style={{ width: `${percentage}%` }}
          />
        </div>
      </div>

      <div
        className="max-h-64 overflow-y-auto rounded-lg border border-slate-200 bg-slate-50 p-3 font-mono text-xs leading-relaxed"
        aria-live="polite"
      >
        {regels.map((regel) => (
          <p key={regel.id} className={KLEUREN[regel.soort]}>
            {regel.soort === "stap" ? "▸ " : "  "}
            {regel.tekst}
          </p>
        ))}
        <div ref={eindeRef} />
      </div>
    </div>
  );
}
