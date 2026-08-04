/** Beheer van de e-mailadressen in de regenereer-modal.
 *
 * De adressen uit .env worden als aangevinkt getoond. De gebruiker kan ze
 * uitvinken (dan gaan ze niet mee in de mailing), extra adressen toevoegen en
 * het Aan-adres aanpassen.
 */

import { useCallback, useMemo, useState } from "react";

import type { EmailInstellingen, EmailSelectie } from "../shared/types.js";

export type Veld = "to" | "cc" | "bcc";

export interface Adres {
  id: string;
  adres: string;
  actief: boolean;
  /** Adressen uit .env zijn "standaard"; door de gebruiker toegevoegde "extra". */
  bron: "standaard" | "extra";
}

export type AdresSelectie = Record<Veld, Adres[]>;

/** Bewust dezelfde controle als Zod op de server, zodat de UI direct meldt. */
const EMAIL_PATROON = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

export function isGeldigAdres(adres: string): boolean {
  return EMAIL_PATROON.test(adres.trim());
}

/**
 * Valt dit adres binnen de toegestane domeinen (DASHBOARD_EMAIL_DOMEINEN)?
 *
 * Een lege lijst betekent geen begrenzing. Deze controle is een spiegel van
 * email_allowlist.py; de bindende versie staat daar, want de browser is geen
 * beveiliging. Hier staat hij zodat een verkeerd adres al in de modal opvalt
 * in plaats van pas nadat de run is gestart.
 */
export function domeinToegestaan(adres: string, domeinen: string[]): boolean {
  if (domeinen.length === 0) return true;
  const schoon = adres.trim().toLowerCase();
  const domein = schoon.slice(schoon.lastIndexOf("@") + 1);
  return domeinen.some((d) => d.trim().replace(/^@/, "").toLowerCase() === domein);
}

let teller = 0;
const volgendeId = () => `adres-${++teller}`;

function naarAdressen(adressen: string[], uitgevinkt: Set<string>): Adres[] {
  return adressen.map((adres) => ({
    id: volgendeId(),
    adres,
    // Adressen uit DASHBOARD_EMAIL_UITGEVINKT staan er wel, maar staan uit.
    actief: !uitgevinkt.has(adres.trim().toLowerCase()),
    bron: "standaard" as const,
  }));
}

export function beginSelectie(instellingen: EmailInstellingen): AdresSelectie {
  const uitgevinkt = new Set(
    (instellingen.uitgevinkt ?? []).map((adres) => adres.trim().toLowerCase()),
  );
  return {
    to: naarAdressen(instellingen.to, uitgevinkt),
    cc: naarAdressen(instellingen.cc, uitgevinkt),
    bcc: naarAdressen(instellingen.bcc, uitgevinkt),
  };
}

export interface EmailSelectieApi {
  selectie: AdresSelectie;
  /** Adressen zoals ze daadwerkelijk verstuurd worden. */
  actieveSelectie: EmailSelectie;
  /**
   * Structureel probleem met de selectie — nu alleen: er is geen enkel
   * Aan-adres aangevinkt. Bewust NIET voor ongeldige adressen: die meldt het
   * veld zelf bij focus verlies. Anders krijg je twee meldingen over hetzelfde
   * met verschillende timing.
   */
  probleem: string | null;
  /** Actieve adressen die niet aan de e-mailvorm voldoen. */
  ongeldigeAdressen: string[];
  /** Actieve adressen buiten de toegestane domeinen. */
  geweigerdeAdressen: string[];
  /**
   * Wat er mis is met één adres, of null als het mag. Gebruikt door de velden
   * om per regel te melden; zo staat de domeinregel op één plek.
   */
  adresProbleem: (adres: string) => string | null;
  /** Alles klopt: er is een Aan-adres en elk actief adres mag verstuurd worden. */
  magVerder: boolean;
  wisselActief: (veld: Veld, id: string) => void;
  wijzigAdres: (veld: Veld, id: string, adres: string) => void;
  voegToe: (veld: Veld, adres: string) => void;
  verwijder: (veld: Veld, id: string) => void;
  herstel: () => void;
}

export function useEmailSelectie(
  instellingen: EmailInstellingen,
): EmailSelectieApi {
  const [selectie, setSelectie] = useState<AdresSelectie>(() =>
    beginSelectie(instellingen),
  );

  const pasAan = useCallback(
    (veld: Veld, verwerk: (adressen: Adres[]) => Adres[]) => {
      setSelectie((vorig) => ({ ...vorig, [veld]: verwerk(vorig[veld]) }));
    },
    [],
  );

  const wisselActief = useCallback(
    (veld: Veld, id: string) => {
      pasAan(veld, (adressen) =>
        adressen.map((a) => (a.id === id ? { ...a, actief: !a.actief } : a)),
      );
    },
    [pasAan],
  );

  const wijzigAdres = useCallback(
    (veld: Veld, id: string, adres: string) => {
      pasAan(veld, (adressen) =>
        adressen.map((a) => (a.id === id ? { ...a, adres } : a)),
      );
    },
    [pasAan],
  );

  const voegToe = useCallback(
    (veld: Veld, adres: string) => {
      const schoon = adres.trim();
      if (!schoon) return;
      pasAan(veld, (adressen) =>
        adressen.some((a) => a.adres.toLowerCase() === schoon.toLowerCase())
          ? adressen
          : [
              ...adressen,
              { id: volgendeId(), adres: schoon, actief: true, bron: "extra" },
            ],
      );
    },
    [pasAan],
  );

  const verwijder = useCallback(
    (veld: Veld, id: string) => {
      pasAan(veld, (adressen) => adressen.filter((a) => a.id !== id));
    },
    [pasAan],
  );

  const herstel = useCallback(() => {
    setSelectie(beginSelectie(instellingen));
  }, [instellingen]);

  const actieveSelectie = useMemo<EmailSelectie>(
    () => ({
      to: selectie.to.filter((a) => a.actief).map((a) => a.adres.trim()),
      cc: selectie.cc.filter((a) => a.actief).map((a) => a.adres.trim()),
      bcc: selectie.bcc.filter((a) => a.actief).map((a) => a.adres.trim()),
    }),
    [selectie],
  );

  const probleem = useMemo(
    () =>
      actieveSelectie.to.length === 0
        ? "Er moet minstens één Aan-adres aangevinkt zijn."
        : null,
    [actieveSelectie.to.length],
  );

  const domeinen = useMemo(
    () => instellingen.domeinen ?? [],
    [instellingen.domeinen],
  );

  // Adressen die al uit .env komen mogen altijd, ook buiten de allowlist —
  // net als in email_allowlist.py. Anders zou een krappe lijst de gewone
  // ontvangers blokkeren.
  const vasteOntvangers = useMemo(
    () =>
      new Set(
        [
          ...instellingen.to,
          ...instellingen.cc,
          ...instellingen.bcc,
          ...(instellingen.uitgevinkt ?? []),
        ].map((adres) => adres.trim().toLowerCase()),
      ),
    [instellingen],
  );

  const adresProbleem = useCallback(
    (adres: string): string | null => {
      if (!isGeldigAdres(adres)) return "Dit is geen geldig e-mailadres.";
      if (vasteOntvangers.has(adres.trim().toLowerCase())) return null;
      if (!domeinToegestaan(adres, domeinen)) {
        return `Het rapport mag alleen naar ${domeinen
          .map((d) => `@${d}`)
          .join(", ")}.`;
      }
      return null;
    },
    [domeinen, vasteOntvangers],
  );

  const actieveAdressen = useMemo(
    () => [
      ...actieveSelectie.to,
      ...actieveSelectie.cc,
      ...actieveSelectie.bcc,
    ],
    [actieveSelectie],
  );

  const ongeldigeAdressen = useMemo(
    () => actieveAdressen.filter((adres) => !isGeldigAdres(adres)),
    [actieveAdressen],
  );

  const geweigerdeAdressen = useMemo(
    () =>
      actieveAdressen.filter(
        (adres) => isGeldigAdres(adres) && adresProbleem(adres) !== null,
      ),
    [actieveAdressen, adresProbleem],
  );

  const magVerder =
    probleem === null &&
    ongeldigeAdressen.length === 0 &&
    geweigerdeAdressen.length === 0;

  return {
    selectie,
    actieveSelectie,
    probleem,
    ongeldigeAdressen,
    geweigerdeAdressen,
    adresProbleem,
    magVerder,
    wisselActief,
    wijzigAdres,
    voegToe,
    verwijder,
    herstel,
  };
}
