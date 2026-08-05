/** Runtime-validatie van alles wat de server binnenkrijgt of doorgeeft.
 *
 * De backend vertrouwt noch de browser (gebruikersinvoer) noch de Python-runner
 * (extern proces). Beide kanten worden met Zod gevalideerd, zodat een fout zich
 * meldt op de grens in plaats van pas ergens diep in de UI.
 *
 * Hier staan alleen de schema's voor binnenkomende verzoeken. De uitvoer van
 * web_runner.py staat in shared/schemas.ts, omdat shared/types.ts daar de
 * TypeScript-types van afleidt.
 */

import { z } from "zod";

import { NAAM_MAXLENGTE } from "../shared/types.js";

export {
  emailInstellingenSchema,
  gebeurtenisSchema,
  overzichtSchema,
  verzamelorderSchema,
} from "../shared/schemas.js";

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

export type RegenereerVerzoek = z.infer<typeof regenereerVerzoekSchema>;
