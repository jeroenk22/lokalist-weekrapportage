/** Zod-schema's voor alles wat scripts/web_runner.py naar buiten stuurt.
 *
 * Dit is de enige plek waar die vorm staat: shared/types.ts leidt de TypeScript-
 * types hiervan af met z.infer, zodat schema en type niet uit elkaar kunnen
 * lopen. De veldtoelichtingen staan daarom hier.
 *
 * De client importeert de types alleen als `import type`, dus zod komt niet in
 * de browserbundel terecht.
 */

import { z } from "zod";

/** Eén verzamelorder zoals getoond in het dashboardoverzicht. */
export const verzamelorderSchema = z.object({
  orderId: z.number(),
  /** ISO-8601 aanmaakmoment (dbo.Orders.Moment). */
  aangemaakt: z.string(),
  weeknummer: z.number(),
  jaar: z.number(),
  /** true als dit rapport handmatig via het dashboard is hergenereerd. */
  handmatig: z.boolean(),
  notities: z.string(),
  totaalColli: z.number(),
  totaalBedrag: z.number(),
  /** "zondag 02 augustus 2026 (automatisch)" — opgemaakt door Python. */
  label: z.string(),
  /** Naam uit de notitie; null bij automatische of oudere handmatige runs. */
  hergenereerdDoor: z.string().nullable(),
  /** Tooltip bij de handmatig-badge, of null bij een automatische run. */
  herkomstTekst: z.string().nullable(),
  /** true als er een factuur naar deze order verwijst; dan is hergenereren geblokkeerd. */
  gefactureerd: z.boolean(),
  /**
   * Het factuurnummer dat Miedema hanteert (invoices.InvNo), bijv. 31511432.
   * null zolang de factuur voorlopig is — MendriX kent het nummer pas toe
   * zodra de factuur definitief gemaakt wordt.
   */
  factuurNummer: z.number().nullable(),
  /** Interne sleutel (Orders.InvKey); hiermee vind je een voorlopige factuur terug. */
  factuurSleutel: z.number().nullable(),
  /** true als er wel een factuur is, maar nog zonder definitief nummer. */
  factuurVoorlopig: z.boolean(),
  /** Wat er bij een klik gekopieerd wordt: InvNo als die er is, anders InvKey. */
  factuurKopieerwaarde: z.number().nullable(),
  /** "factuur 31511432" of "voorlopige factuur 154793"; null zonder factuur. */
  factuurOmschrijving: z.string().nullable(),
});

/** Standaard e-mailinstellingen uit .env. */
export const emailInstellingenSchema = z.object({
  to: z.array(z.string()),
  cc: z.array(z.string()),
  bcc: z.array(z.string()),
  /**
   * Adressen die wel in de modal staan maar niet vooraf aangevinkt zijn
   * (DASHBOARD_EMAIL_UITGEVINKT). De gebruiker kan ze alsnog aanzetten.
   */
  uitgevinkt: z.array(z.string()).default([]),
  /**
   * Wie het rapport mag ontvangen (DASHBOARD_EMAIL_DOMEINEN). Elke regel is
   * een domein (`lokalist.nl`) of één volledig adres (`jeroen@gmail.com`);
   * het onderscheid zit in de apenstaart. Leeg betekent: geen begrenzing.
   *
   * Dit is een kopie voor de UI, zodat een verkeerd adres al bij het typen
   * opvalt. De echte grendel staat in web_runner.py.
   *
   * Bewust ZONDER .default([]): dit veld heette eerder `domeinen`. Met een
   * default zou een runner die de oude naam stuurt stilzwijgend een lege
   * allowlist opleveren — een UI die niets meer waarschuwt, zonder foutmelding.
   * Nu faalt dat hard bij het parsen, en dat is precies wat je wilt zien.
   */
  allowlist: z.array(z.string()),
  afzender: z.string().nullable(),
  provider: z.string(),
});

export const overzichtSchema = z.object({
  verzamelorders: z.array(verzamelorderSchema),
  email: emailInstellingenSchema,
});

/** NDJSON-gebeurtenissen die web_runner.py naar stdout schrijft. */
export const gebeurtenisSchema = z.discriminatedUnion("type", [
  z.object({
    type: z.literal("stap"),
    nummer: z.number(),
    totaal: z.number(),
    bericht: z.string(),
  }),
  z.object({
    type: z.literal("log"),
    niveau: z.enum(["info", "warning", "error"]),
    bericht: z.string(),
  }),
  z.object({
    type: z.literal("klaar"),
    data: z.unknown(),
    logbestand: z.string(),
  }),
  z.object({
    type: z.literal("fout"),
    bericht: z.string(),
    details: z.string().optional(),
    logbestand: z.string().optional(),
  }),
]);
