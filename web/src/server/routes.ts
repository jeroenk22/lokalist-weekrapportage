/** HTTP-endpoints van het dashboard. */

import { Router } from "express";

import type { VerzamelorderOverzicht } from "../shared/types.js";
import { RunnerFout, voerRunnerUit } from "./python.js";
import {
  orderIdSchema,
  overzichtSchema,
  regenereerVerzoekSchema,
} from "./schemas.js";

export function maakRouter(): Router {
  const router = Router();

  router.get("/health", (_req, res) => {
    res.json({ status: "ok" });
  });

  /** Alle actieve verzamelorders + de standaard e-mailinstellingen uit .env. */
  router.get("/verzamelorders", async (_req, res) => {
    try {
      const ruw = await voerRunnerUit({ command: "lijst" });
      const overzicht = overzichtSchema.parse(ruw) as VerzamelorderOverzicht;
      res.json(overzicht);
    } catch (err) {
      const isRunnerFout = err instanceof RunnerFout;
      console.error("Ophalen verzamelorders mislukt:", err);
      res.status(isRunnerFout ? 502 : 500).json({
        fout: isRunnerFout
          ? err.message
          : "Onverwachte fout bij het ophalen van de verzamelorders.",
        details: isRunnerFout ? err.details : undefined,
      });
    }
  });

  /**
   * Genereert het rapport van een bestaande verzamelorder opnieuw.
   *
   * Antwoordt met een NDJSON-stream zodat de modal live de voortgang toont.
   * De HTTP-status is daardoor altijd 200; een fout komt als fout-gebeurtenis
   * in de stream, met de melding die de gebruiker moet zien.
   */
  router.post("/verzamelorders/:orderId/regenereer", async (req, res) => {
    const idResultaat = orderIdSchema.safeParse(req.params.orderId);
    if (!idResultaat.success) {
      res.status(400).json({ fout: "Ongeldig order-ID." });
      return;
    }

    const verzoek = regenereerVerzoekSchema.safeParse(req.body);
    if (!verzoek.success) {
      res.status(400).json({
        fout: "Ongeldige aanvraag.",
        details: verzoek.error.issues
          .map((i) => `${i.path.join(".")}: ${i.message}`)
          .join("; "),
      });
      return;
    }

    res.status(200);
    res.setHeader("Content-Type", "application/x-ndjson; charset=utf-8");
    res.setHeader("Cache-Control", "no-cache, no-transform");
    res.setHeader("X-Accel-Buffering", "no");
    res.flushHeaders?.();

    const stuur = (gebeurtenis: unknown) => {
      if (!res.writableEnded) res.write(JSON.stringify(gebeurtenis) + "\n");
    };

    // Breekt de Python-run af als de gebruiker het tabblad sluit.
    //
    // Let op: dit moet op de RESPONSE en niet op de request. Node stuurt
    // req 'close' zodra de request-body volledig gelezen is — dat gebeurt hier
    // meteen, waardoor elke run zichzelf zou afbreken. res 'close' vuurt pas
    // als de verbinding echt weg is; is het antwoord netjes afgerond, dan staat
    // writableEnded al op true en breken we niets af.
    const controller = new AbortController();
    res.on("close", () => {
      if (!res.writableEnded) controller.abort();
    });

    try {
      const data = await voerRunnerUit(
        {
          command: "regenereer",
          orderId: idResultaat.data,
          email: verzoek.data.email,
          naam: verzoek.data.naam,
          dryRun: verzoek.data.dryRun,
        },
        { onGebeurtenis: stuur, signal: controller.signal },
      );
      stuur({ type: "resultaat", data });
    } catch (err) {
      const isRunnerFout = err instanceof RunnerFout;
      console.error(`Regenereren van order ${idResultaat.data} mislukt:`, err);
      stuur({
        type: "fout",
        bericht: isRunnerFout
          ? err.message
          : "Onverwachte fout tijdens het genereren.",
        details: isRunnerFout ? err.details : String(err),
        logbestand: isRunnerFout ? err.logbestand : undefined,
      });
    } finally {
      res.end();
    }
  });

  return router;
}
