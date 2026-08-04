/** Types die door zowel de Express-backend als de React-client gebruikt worden.
 *
 * Deze vormen het contract met scripts/web_runner.py. De vorm staat in
 * shared/schemas.ts; hier worden de types daarvan afgeleid, zodat schema en
 * type niet handmatig gelijk gehouden hoeven te worden. Wijzigt web_runner.py
 * van vorm, dan is er één plek die mee moet.
 *
 * De import is bewust type-only: zod blijft daardoor buiten de browserbundel.
 */

import type { z } from "zod";

import type {
  emailInstellingenSchema,
  gebeurtenisSchema,
  overzichtSchema,
  verzamelorderSchema,
} from "./schemas.js";

/** Eén verzamelorder zoals getoond in het dashboardoverzicht. */
export type Verzamelorder = z.infer<typeof verzamelorderSchema>;

/** Standaard e-mailinstellingen uit .env. */
export type EmailInstellingen = z.infer<typeof emailInstellingenSchema>;

export type VerzamelorderOverzicht = z.infer<typeof overzichtSchema>;

/** NDJSON-gebeurtenissen die web_runner.py naar stdout schrijft. */
export type RunnerGebeurtenis = z.infer<typeof gebeurtenisSchema>;

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

export const TOTAAL_STAPPEN = 7;

/**
 * Maximale lengte van de naam die in de order wordt vastgelegd.
 *
 * dbo.Orders.Diversen is varchar(250) en de hele notitie moet daarin passen.
 * 80 is ruim voor een volledige naam en houdt genoeg marge over.
 *
 * Spiegelt NAAM_MAXLENGTE in src/lokalist_weekrapportage/verzamelorder.py, waar
 * web_runner.py een te lange naam alsnog weigert. Wijzigt de ene waarde, dan
 * moet de andere mee.
 */
export const NAAM_MAXLENGTE = 80;
