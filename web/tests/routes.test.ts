/** Tests voor de HTTP-laag. De Python-runner wordt gemockt: hier gaat het om
 * validatie, foutafhandeling en het doorgeven van de NDJSON-stream. */

import express from "express";
import request from "supertest";
import { beforeEach, describe, expect, it, vi } from "vitest";

const voerRunnerUit = vi.fn();

// Alleen het starten van Python vervangen. Het gelijktijdigheidsslot en
// RunnerFout blijven echt, zodat we dat gedrag toetsen en geen namaak ervan.
vi.mock("../src/server/python.js", async (origineel) => {
  const echt = await origineel<typeof import("../src/server/python.js")>();
  return {
    ...echt,
    voerRunnerUit: (...args: unknown[]) => voerRunnerUit(...args),
  };
});

const { maakRouter } = await import("../src/server/routes.js");
const { RunnerFout } = await import("../src/server/python.js");

function maakTestApp() {
  const app = express();
  app.use(express.json());
  app.use("/api", maakRouter());
  return app;
}

const OVERZICHT = {
  verzamelorders: [
    {
      orderId: 1266289,
      aangemaakt: "2026-08-02T23:30:04",
      weeknummer: 31,
      jaar: 2026,
      handmatig: false,
      notities: "",
      totaalColli: 32,
      totaalBedrag: 238.13,
      label: "zondag 02 augustus 2026 (automatisch)",
      hergenereerdDoor: null,
      herkomstTekst: null,
      gefactureerd: false,
      factuurNummer: null,
      factuurSleutel: null,
      factuurVoorlopig: false,
      factuurKopieerwaarde: null,
      factuurOmschrijving: null,
    },
  ],
  email: {
    to: ["info@lokalist.nl"],
    cc: [],
    bcc: ["jeroenkrajenbrink@gmail.com"],
    uitgevinkt: [],
    allowlist: [],
    afzender: "miedemaophaaldienst@gmail.com",
    provider: "smtp",
  },
};

const GELDIG_VERZOEK = {
  bevestigd: true,
  dryRun: false,
  naam: "Jeroen",
  email: { to: ["info@lokalist.nl"], cc: [], bcc: [] },
};

beforeEach(() => {
  voerRunnerUit.mockReset();
});

describe("GET /api/verzamelorders", () => {
  it("geeft het overzicht terug", async () => {
    voerRunnerUit.mockResolvedValue(OVERZICHT);

    const res = await request(maakTestApp()).get("/api/verzamelorders");

    expect(res.status).toBe(200);
    expect(res.body.verzamelorders).toHaveLength(1);
    expect(res.body.verzamelorders[0].label).toBe(
      "zondag 02 augustus 2026 (automatisch)",
    );
    expect(voerRunnerUit).toHaveBeenCalledWith({ command: "lijst" });
  });

  it("geeft 502 met de melding van de runner bij een fout", async () => {
    voerRunnerUit.mockRejectedValue(new RunnerFout("Database niet bereikbaar"));

    const res = await request(maakTestApp()).get("/api/verzamelorders");

    expect(res.status).toBe(502);
    expect(res.body.fout).toBe("Database niet bereikbaar");
  });

  it("geeft 502 bij een onverwacht antwoordformaat", async () => {
    voerRunnerUit.mockResolvedValue({ onzin: true });

    const res = await request(maakTestApp()).get("/api/verzamelorders");

    expect(res.status).toBe(500);
  });

  it("faalt hard als de allowlist ontbreekt in het antwoord", async () => {
    // Het veld heette eerder `domeinen`. Zonder deze harde eis zou een runner
    // met de oude naam een lege allowlist opleveren: een UI die niets meer
    // waarschuwt, zonder dat iemand het merkt.
    const { allowlist: _weg, ...zonderAllowlist } = OVERZICHT.email;
    voerRunnerUit.mockResolvedValue({
      ...OVERZICHT,
      email: zonderAllowlist,
    });

    const res = await request(maakTestApp()).get("/api/verzamelorders");

    expect(res.status).toBe(500);
  });

  it("faalt hard als uitgevinkt ontbreekt in het antwoord", async () => {
    // Een stille lege lijst zou betekenen dat adressen die uitgevinkt hadden
    // moeten staan juist aangevinkt in de modal verschijnen — en dan gaat het
    // rapport naar mensen die er buiten moesten blijven.
    const { uitgevinkt: _weg, ...zonderUitgevinkt } = OVERZICHT.email;
    voerRunnerUit.mockResolvedValue({
      ...OVERZICHT,
      email: zonderUitgevinkt,
    });

    const res = await request(maakTestApp()).get("/api/verzamelorders");

    expect(res.status).toBe(500);
  });
});

describe("POST /api/verzamelorders/:orderId/regenereer", () => {
  it("weigert een verzoek zonder bevestiging", async () => {
    const res = await request(maakTestApp())
      .post("/api/verzamelorders/1266289/regenereer")
      .send({ ...GELDIG_VERZOEK, bevestigd: false });

    expect(res.status).toBe(400);
    expect(voerRunnerUit).not.toHaveBeenCalled();
  });

  it("weigert een verzoek zonder Aan-adres", async () => {
    const res = await request(maakTestApp())
      .post("/api/verzamelorders/1266289/regenereer")
      .send({ ...GELDIG_VERZOEK, email: { to: [], cc: [], bcc: [] } });

    expect(res.status).toBe(400);
    expect(res.body.details).toMatch(/Aan-adres/i);
    expect(voerRunnerUit).not.toHaveBeenCalled();
  });

  it("weigert een ongeldig e-mailadres", async () => {
    const res = await request(maakTestApp())
      .post("/api/verzamelorders/1266289/regenereer")
      .send({ ...GELDIG_VERZOEK, email: { to: ["kapot"], cc: [], bcc: [] } });

    expect(res.status).toBe(400);
    expect(voerRunnerUit).not.toHaveBeenCalled();
  });

  it("weigert een ongeldig order-ID", async () => {
    const res = await request(maakTestApp())
      .post("/api/verzamelorders/nietnumeriek/regenereer")
      .send(GELDIG_VERZOEK);

    expect(res.status).toBe(400);
    expect(voerRunnerUit).not.toHaveBeenCalled();
  });

  it("streamt voortgang en sluit af met het resultaat", async () => {
    voerRunnerUit.mockImplementation(async (_opdracht, opties) => {
      opties.onGebeurtenis({
        type: "stap",
        nummer: 1,
        totaal: 7,
        bericht: "orders ophalen",
      });
      opties.onGebeurtenis({
        type: "log",
        niveau: "info",
        bericht: "11 rijen",
      });
      return { nieuweOrderId: 1266400, oudeOrderId: 1266289 };
    });

    const res = await request(maakTestApp())
      .post("/api/verzamelorders/1266289/regenereer")
      .send(GELDIG_VERZOEK);

    expect(res.status).toBe(200);
    const gebeurtenissen = res.text
      .trim()
      .split("\n")
      .map((r) => JSON.parse(r));

    expect(gebeurtenissen[0]).toMatchObject({ type: "stap", nummer: 1 });
    expect(gebeurtenissen[1]).toMatchObject({
      type: "log",
      bericht: "11 rijen",
    });
    expect(gebeurtenissen.at(-1)).toMatchObject({
      type: "resultaat",
      data: { nieuweOrderId: 1266400 },
    });
  });

  it("geeft de fout van de runner door in de stream", async () => {
    voerRunnerUit.mockRejectedValue(
      new RunnerFout(
        "Geen orders gevonden voor week 31 2026",
        "traceback",
        "logs/x.log",
      ),
    );

    const res = await request(maakTestApp())
      .post("/api/verzamelorders/1266289/regenereer")
      .send(GELDIG_VERZOEK);

    // Bewust 200: de fout hoort in de stream, niet in de statuscode.
    expect(res.status).toBe(200);
    const laatste = JSON.parse(res.text.trim().split("\n").at(-1)!);
    expect(laatste).toMatchObject({
      type: "fout",
      bericht: "Geen orders gevonden voor week 31 2026",
      logbestand: "logs/x.log",
    });
  });

  it("geeft geen afbreeksignaal mee aan de runner", async () => {
    // Bewust: kill() is op Windows een harde TerminateProcess, waardoor de
    // rollback in web_runner.py niet meer draait. Een run die na stap 3 wordt
    // afgekapt laat dan zowel de nieuwe als de oude verzamelorder achter.
    let meegegevenOpties: { signal?: AbortSignal } | undefined;
    voerRunnerUit.mockImplementation(async (_opdracht, opties) => {
      meegegevenOpties = opties;
      return { nieuweOrderId: 1266400 };
    });

    const res = await request(maakTestApp())
      .post("/api/verzamelorders/1266289/regenereer")
      .send(GELDIG_VERZOEK);

    expect(meegegevenOpties?.signal).toBeUndefined();
    expect(JSON.parse(res.text.trim().split("\n").at(-1)!)).toMatchObject({
      type: "resultaat",
    });
  });

  describe("gelijktijdigheid", () => {
    /** Belofte die de test zelf afrondt, zodat een run "bezig" blijft. */
    function uitgesteld() {
      let afronden!: (waarde: unknown) => void;
      const belofte = new Promise((res) => {
        afronden = res;
      });
      return { belofte, afronden };
    }

    it("weigert een tweede run voor dezelfde order met 409", async () => {
      // Zonder slot zouden beide runs een order aanmaken en zou de tweede
      // verwijdering op een al verwijderde order draaien.
      const eerste = uitgesteld();
      voerRunnerUit.mockReturnValueOnce(eerste.belofte);
      const app = maakTestApp();

      const lopend = request(app)
        .post("/api/verzamelorders/1266289/regenereer")
        .send(GELDIG_VERZOEK)
        .then((r) => r);
      await new Promise((r) => setTimeout(r, 60));

      const tweede = await request(app)
        .post("/api/verzamelorders/1266289/regenereer")
        .send(GELDIG_VERZOEK);

      expect(tweede.status).toBe(409);
      expect(tweede.body.fout).toMatch(/al een hergeneratie bezig/i);
      expect(tweede.body.fout).toMatch(/1266289/);
      // De Python-runner is maar één keer gestart.
      expect(voerRunnerUit).toHaveBeenCalledTimes(1);

      eerste.afronden({ nieuweOrderId: 1266400 });
      await lopend;
    });

    it("laat een andere order wél gewoon starten", async () => {
      const eerste = uitgesteld();
      voerRunnerUit.mockReturnValueOnce(eerste.belofte);
      voerRunnerUit.mockResolvedValueOnce({ nieuweOrderId: 1 });
      const app = maakTestApp();

      const lopend = request(app)
        .post("/api/verzamelorders/1266289/regenereer")
        .send(GELDIG_VERZOEK)
        .then((r) => r);
      await new Promise((r) => setTimeout(r, 60));

      const andere = await request(app)
        .post("/api/verzamelorders/1262688/regenereer")
        .send(GELDIG_VERZOEK);

      expect(andere.status).toBe(200);
      eerste.afronden({ nieuweOrderId: 1266400 });
      await lopend;
    });

    it("geeft de order weer vrij als de run klaar is", async () => {
      voerRunnerUit.mockResolvedValue({ nieuweOrderId: 1266400 });
      const app = maakTestApp();

      await request(app)
        .post("/api/verzamelorders/1266289/regenereer")
        .send(GELDIG_VERZOEK);
      const tweede = await request(app)
        .post("/api/verzamelorders/1266289/regenereer")
        .send(GELDIG_VERZOEK);

      expect(tweede.status).toBe(200);
    });

    it("geeft de order ook vrij als de run faalt", async () => {
      // Anders blijft een order na één storing voorgoed op slot staan.
      voerRunnerUit.mockRejectedValueOnce(new RunnerFout("SOAP stuk"));
      voerRunnerUit.mockResolvedValueOnce({ nieuweOrderId: 1266400 });
      const app = maakTestApp();

      await request(app)
        .post("/api/verzamelorders/1266289/regenereer")
        .send(GELDIG_VERZOEK);
      const tweede = await request(app)
        .post("/api/verzamelorders/1266289/regenereer")
        .send(GELDIG_VERZOEK);

      expect(tweede.status).toBe(200);
    });
  });

  it("geeft de gekozen adressen ongewijzigd door aan de runner", async () => {
    voerRunnerUit.mockResolvedValue({});

    await request(maakTestApp())
      .post("/api/verzamelorders/1266289/regenereer")
      .send({
        bevestigd: true,
        dryRun: false,
        naam: "Jeroen",
        email: { to: ["jeroen@prive.nl"], cc: ["a@b.nl"], bcc: [] },
      });

    expect(voerRunnerUit).toHaveBeenCalledWith(
      expect.objectContaining({
        command: "regenereer",
        orderId: 1266289,
        email: { to: ["jeroen@prive.nl"], cc: ["a@b.nl"], bcc: [] },
      }),
      expect.anything(),
    );
  });
});
