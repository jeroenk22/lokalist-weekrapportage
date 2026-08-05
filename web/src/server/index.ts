/** Express-server voor het Lokalist-weekrapportagedashboard.
 *
 * Draait op de 105. Collega's openen het dashboard in hun browser; er is geen
 * Python of andere installatie op hun eigen machine nodig.
 */

import express from "express";
import { existsSync } from "node:fs";
import path from "node:path";

import { PROJECT_ROOT, pythonPad } from "./python.js";
import { maakRouter } from "./routes.js";

const POORT = Number(process.env.DASHBOARD_POORT ?? 3000);

/** Standaard 0.0.0.0 zodat collega's op het LAN erbij kunnen. */
const HOST = process.env.DASHBOARD_HOST ?? "0.0.0.0";

export function maakApp(): express.Express {
  const app = express();

  app.use(express.json({ limit: "1mb" }));
  app.use("/api", maakRouter());

  // Gebouwde React-app serveren (na `npm run build`).
  const clientDir = path.join(PROJECT_ROOT, "web", "dist", "client");
  if (existsSync(clientDir)) {
    app.use(express.static(clientDir));
    app.get(/^\/(?!api\/).*/, (_req, res) => {
      res.sendFile(path.join(clientDir, "index.html"));
    });
  }

  return app;
}

// Alleen starten wanneer dit bestand direct wordt uitgevoerd (niet in tests).
if (process.env.NODE_ENV !== "test") {
  const app = maakApp();
  app.listen(POORT, HOST, () => {
    console.log(
      `Lokalist-weekrapportagedashboard draait op http://${HOST}:${POORT}`,
    );
    console.log(`Python: ${pythonPad()}`);
    console.log(`Projectmap: ${PROJECT_ROOT}`);
  });
}
