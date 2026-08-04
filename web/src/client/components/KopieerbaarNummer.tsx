/** Een nummer dat je met één klik naar het klembord kopieert. */

import { useEffect, useRef, useState } from "react";

import { kopieerNaarKlembord } from "../klembord.js";

interface KopieerbaarNummerProps {
  /** De waarde die gekopieerd wordt. */
  waarde: string | number;
  /** Wat er getoond wordt; standaard de waarde zelf. */
  children?: React.ReactNode;
  /** Omschrijving voor schermlezers, bijv. "Ordernummer". */
  omschrijving: string;
  /** Extra uitleg in de tooltip, bijv. hoe je ermee zoekt in MendriX. */
  toelichting?: string;
  className?: string;
}

export function KopieerbaarNummer({
  waarde,
  children,
  omschrijving,
  toelichting,
  className = "",
}: KopieerbaarNummerProps) {
  const [status, setStatus] = useState<"rust" | "gekopieerd" | "mislukt">(
    "rust",
  );
  const timer = useRef<ReturnType<typeof setTimeout>>(undefined);

  useEffect(() => () => clearTimeout(timer.current), []);

  const kopieer = async () => {
    const gelukt = await kopieerNaarKlembord(String(waarde));
    setStatus(gelukt ? "gekopieerd" : "mislukt");
    clearTimeout(timer.current);
    timer.current = setTimeout(() => setStatus("rust"), 1600);
  };

  const titel =
    status === "gekopieerd"
      ? "Gekopieerd"
      : status === "mislukt"
        ? "Kopiëren niet gelukt — selecteer handmatig"
        : [`${omschrijving} kopiëren naar klembord`, toelichting]
            .filter(Boolean)
            .join("\n");

  return (
    <button
      type="button"
      onClick={kopieer}
      title={titel}
      aria-label={`${omschrijving} ${waarde} kopiëren naar klembord`}
      // Vormgeving komt volledig van de aanroeper: dit is soms een kaal
      // ordernummer en soms een hele badge.
      className={`relative cursor-pointer transition focus:ring-2 focus:ring-miedema-goud focus:outline-none ${className}`}
    >
      {children ?? waarde}
      {status !== "rust" && (
        <span
          role="status"
          className={`absolute -top-7 left-1/2 z-20 -translate-x-1/2 rounded px-2 py-0.5 text-xs font-medium whitespace-nowrap text-white ${
            status === "gekopieerd" ? "bg-slate-800" : "bg-red-600"
          }`}
        >
          {status === "gekopieerd" ? "Gekopieerd" : "Niet gelukt"}
        </span>
      )}
    </button>
  );
}
