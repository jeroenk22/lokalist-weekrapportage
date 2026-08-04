/** Types die door zowel de Express-backend als de React-client gebruikt worden.
 *
 * Deze vormen het contract met scripts/web_runner.py. Wijzigt dat script van
 * vorm, dan moeten deze types mee — de Zod-schema's in server/schemas.ts
 * bewaken dat tijdens runtime.
 */

/** Eén verzamelorder zoals getoond in het dashboardoverzicht. */
export interface Verzamelorder {
  orderId: number;
  /** ISO-8601 aanmaakmoment (dbo.Orders.Moment). */
  aangemaakt: string;
  weeknummer: number;
  jaar: number;
  /** true als dit rapport handmatig via het dashboard is hergenereerd. */
  handmatig: boolean;
  notities: string;
  totaalColli: number;
  totaalBedrag: number;
  /** "zondag 02 augustus 2026 (automatisch)" — opgemaakt door Python. */
  label: string;
  /** Naam uit de notitie; null bij automatische of oudere handmatige runs. */
  hergenereerdDoor: string | null;
  /** Tooltip bij de handmatig-badge, of null bij een automatische run. */
  herkomstTekst: string | null;
  /** true als er een factuur naar deze order verwijst; dan is hergenereren geblokkeerd. */
  gefactureerd: boolean;
  /**
   * Het factuurnummer dat Miedema hanteert (invoices.InvNo), bijv. 31511432.
   * null zolang de factuur voorlopig is — MendriX kent het nummer pas toe
   * zodra de factuur definitief gemaakt wordt.
   */
  factuurNummer: number | null;
  /** Interne sleutel (Orders.InvKey); hiermee vind je een voorlopige factuur terug. */
  factuurSleutel: number | null;
  /** true als er wel een factuur is, maar nog zonder definitief nummer. */
  factuurVoorlopig: boolean;
  /** Wat er bij een klik gekopieerd wordt: InvNo als die er is, anders InvKey. */
  factuurKopieerwaarde: number | null;
  /** "factuur 31511432" of "voorlopige factuur 154793"; null zonder factuur. */
  factuurOmschrijving: string | null;
}

/** Standaard e-mailinstellingen uit .env. */
export interface EmailInstellingen {
  to: string[];
  cc: string[];
  bcc: string[];
  /**
   * Adressen die wel in de modal staan maar niet vooraf aangevinkt zijn
   * (DASHBOARD_EMAIL_UITGEVINKT). De gebruiker kan ze alsnog aanzetten.
   */
  uitgevinkt: string[];
  afzender: string | null;
  provider: string;
}

export interface VerzamelorderOverzicht {
  verzamelorders: Verzamelorder[];
  email: EmailInstellingen;
}

/** Adressen zoals de gebruiker ze in de modal heeft samengesteld. */
export interface EmailSelectie {
  to: string[];
  cc: string[];
  bcc: string[];
}

/** Resultaat van een geslaagde hergeneratie. */
export interface RegenereerResultaat {
  dryRun: boolean;
  oudeOrderId: number;
  nieuweOrderId?: number;
  weeknummer: number;
  jaar: number;
  pdf: string;
  colli: number;
  bedrag: number;
  notitie: string;
}

/** NDJSON-gebeurtenissen die web_runner.py naar stdout schrijft. */
export type RunnerGebeurtenis =
  | { type: "stap"; nummer: number; totaal: number; bericht: string }
  | { type: "log"; niveau: "info" | "warning" | "error"; bericht: string }
  | { type: "klaar"; data: unknown; logbestand: string }
  | { type: "fout"; bericht: string; details?: string; logbestand?: string };

export const TOTAAL_STAPPEN = 7;

/**
 * Maximale lengte van de naam die in de order wordt vastgelegd.
 *
 * dbo.Orders.Diversen is varchar(250) en de hele notitie moet daarin passen.
 * 80 is ruim voor een volledige naam en houdt genoeg marge over.
 */
export const NAAM_MAXLENGTE = 80;
