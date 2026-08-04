/** HTTP-endpoints van het dashboard. */

import { Router } from "express";

import type { VerzamelorderOverzicht } from "../shared/types.js";
import {
  AlBezigFout,
  isHergeneratieBezig,
  metHergeneratieSlot,
  RunnerFout,
  voerRunnerUit,
} from "./python.js";
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

    // Slot vóór het streamen: zolang we nog geen NDJSON hebben gestuurd kunnen
    // we een nette 409 geven in plaats van een fout in de stream.
    if (isHergeneratieBezig(idResultaat.data)) {
      res.status(409).json({ fout: new AlBezigFout(idResultaat.data).message });
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

    // Bewust GEEN afbreken als de gebruiker het tabblad sluit.
    //
    // kill() is op Windows een harde TerminateProcess: het except-blok in
    // web_runner.py draait dan niet meer. Gebeurt dat na stap 3, dan bestaan de
    // nieuwe én de oude verzamelorder zonder rollback. De run mag daarom gewoon
    // afmaken; de gebruiker ziet het resultaat niet, maar MendriX blijft heel.
    // Het logbestand (handmatig_*.log) legt vast wat er is gebeurd.

    try {
      const data = await metHergeneratieSlot(idResultaat.data, () =>
        voerRunnerUit(
          {
            command: "regenereer",
            orderId: idResultaat.data,
            email: verzoek.data.email,
            naam: verzoek.data.naam,
            dryRun: verzoek.data.dryRun,
          },
          { onGebeurtenis: stuur },
        ),
      );
      stuur({ type: "resultaat", data });
    } catch (err) {
      if (err instanceof AlBezigFout) {
        // Onbereikbaar zolang de controle hierboven en het zetten van het slot
        // door alleen synchrone code gescheiden blijven. Staat er als vangnet
        // voor als die volgorde ooit wijzigt; de 409 hierboven is de echte weg.
        stuur({ type: "fout", bericht: err.message });
      } else {
        const isRunnerFout = err instanceof RunnerFout;
        console.error(
          `Regenereren van order ${idResultaat.data} mislukt:`,
          err,
        );
        stuur({
          type: "fout",
          bericht: isRunnerFout
            ? err.message
            : "Onverwachte fout tijdens het genereren.",
          details: isRunnerFout ? err.details : String(err),
          logbestand: isRunnerFout ? err.logbestand : undefined,
        });
      }
    } finally {
      res.end();
    }
  });

  return router;
}
