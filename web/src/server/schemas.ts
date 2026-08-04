/** Runtime-validatie van alles wat de server binnenkrijgt of doorgeeft.
 *
 * De backend vertrouwt noch de browser (gebruikersinvoer) noch de Python-runner
 * (extern proces). Beide kanten worden met Zod gevalideerd, zodat een fout zich
 * meldt op de grens in plaats van pas ergens diep in de UI.
 */

import { z } from "zod";

import { NAAM_MAXLENGTE } from "../shared/types.js";

/** Bewust streng: voorkomt dat een typefout stilzwijgend een mail mist. */
export const emailAdresSchema = z
  .string()
  .trim()
  .min(1, "E-mailadres mag niet leeg zijn")
  .email("Ongeldig e-mailadres");

export const emailSelectieSchema = z.object({
  to: z.array(emailAdresSchema).min(1, "Er moet minstens één Aan-adres zijn"),
  cc: z.array(emailAdresSchema).default([]),
  bcc: z.array(emailAdresSchema).default([]),
});

export const regenereerVerzoekSchema = z.object({
  email: emailSelectieSchema,
  /** Wie het rapport opnieuw genereert; wordt in de order vastgelegd. */
  naam: z
    .string()
    .trim()
    .min(1, "Vul in wie het rapport opnieuw genereert")
    .max(NAAM_MAXLENGTE, `Maximaal ${NAAM_MAXLENGTE} tekens`),
  /** Alleen voor testen: doorloopt de keten zonder iets te wijzigen. */
  dryRun: z.boolean().default(false),
  /** Verplichte bevestiging — de oude order wordt immers verwijderd. */
  bevestigd: z.literal(true, {
    errorMap: () => ({ message: "Bevestiging ontbreekt" }),
  }),
});

export const orderIdSchema = z.coerce
  .number()
  .int("Order-ID moet een geheel getal zijn")
  .positive("Order-ID moet positief zijn");

/* -------------------------------------------------------------------------- */
/* Uitvoer van web_runner.py                                                   */
/* -------------------------------------------------------------------------- */

export const verzamelorderSchema = z.object({
  orderId: z.number(),
  aangemaakt: z.string(),
  weeknummer: z.number(),
  jaar: z.number(),
  handmatig: z.boolean(),
  notities: z.string(),
  totaalColli: z.number(),
  totaalBedrag: z.number(),
  label: z.string(),
  hergenereerdDoor: z.string().nullable(),
  herkomstTekst: z.string().nullable(),
  gefactureerd: z.boolean(),
  factuurNummer: z.number().nullable(),
  factuurSleutel: z.number().nullable(),
  factuurVoorlopig: z.boolean(),
  factuurKopieerwaarde: z.number().nullable(),
  factuurOmschrijving: z.string().nullable(),
});

export const overzichtSchema = z.object({
  verzamelorders: z.array(verzamelorderSchema),
  email: z.object({
    to: z.array(z.string()),
    cc: z.array(z.string()),
    bcc: z.array(z.string()),
    uitgevinkt: z.array(z.string()).default([]),
    afzender: z.string().nullable(),
    provider: z.string(),
  }),
});

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

export type RegenereerVerzoek = z.infer<typeof regenereerVerzoekSchema>;
