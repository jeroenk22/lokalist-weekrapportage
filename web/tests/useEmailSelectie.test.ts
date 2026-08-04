/** Tests voor het beheer van ontvangers in de regenereer-modal. */

import { act, renderHook } from "@testing-library/react";
import { existsSync, readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

import type { EmailInstellingen } from "../src/shared/types.js";
import {
  isGeldigAdres,
  isToegestaan,
  omschrijfAllowlist,
  useEmailSelectie,
} from "../src/client/useEmailSelectie.js";

const INSTELLINGEN: EmailInstellingen = {
  to: ["info@lokalist.nl"],
  cc: ["planning@ophaaldienstmiedema.nl"],
  bcc: ["jeroenkrajenbrink@gmail.com"],
  uitgevinkt: [],
  allowlist: [],
  afzender: "miedemaophaaldienst@gmail.com",
  provider: "smtp",
};

describe("isGeldigAdres", () => {
  it.each(["a@b.nl", "info@lokalist.nl", "jan.jansen+tag@voorbeeld.co.uk"])(
    "accepteert %s",
    (adres) => {
      expect(isGeldigAdres(adres)).toBe(true);
    },
  );

  it.each(["", "geen-apenstaart", "a@b", "a@@b.nl", "spatie in@adres.nl"])(
    "weigert %s",
    (adres) => {
      expect(isGeldigAdres(adres)).toBe(false);
    },
  );
});

describe("isToegestaan", () => {
  it("laat alles door zonder allowlist", () => {
    expect(isToegestaan("wie@dan.ook.com", [])).toBe(true);
  });

  it.each(["nieuw@lokalist.nl", "Nieuw@Lokalist.NL", " nieuw@lokalist.nl "])(
    "accepteert %s",
    (adres) => {
      expect(isToegestaan(adres, ["lokalist.nl"])).toBe(true);
    },
  );

  it.each(["jeroen@prive.nl", "info@mail.lokalist.nl", "geen-apenstaart"])(
    "weigert %s",
    (adres) => {
      expect(isToegestaan(adres, ["lokalist.nl"])).toBe(false);
    },
  );

  it("accepteert een domein met leidende @ in de lijst", () => {
    expect(isToegestaan("nieuw@lokalist.nl", ["@lokalist.nl"])).toBe(true);
  });

  describe("losse adressen in de lijst", () => {
    const LIJST = ["lokalist.nl", "jeroen@gmail.com"];

    it("staat het genoemde adres toe", () => {
      expect(isToegestaan("jeroen@gmail.com", LIJST)).toBe(true);
    });

    it("vergelijkt hoofdletterongevoelig", () => {
      expect(isToegestaan(" JEROEN@Gmail.com ", LIJST)).toBe(true);
    });

    it("laat de rest van dat domein dicht", () => {
      // Precies het punt van deze vorm: niet heel gmail.com openzetten.
      expect(isToegestaan("iemand.anders@gmail.com", LIJST)).toBe(false);
    });

    it("blijft het domein uit dezelfde lijst toestaan", () => {
      expect(isToegestaan("nieuw@lokalist.nl", LIJST)).toBe(true);
    });
  });

});

describe("gedeelde waarheidstabel", () => {
  // Dezelfde fixture wordt ingelezen door tests/unit/test_email_allowlist.py.
  // Loopt één van beide implementaties weg, dan valt daar of hier een test om.
  // Een handmatig bijgehouden lijst deed dat niet: die bleef groen terwijl de
  // Python-kant veranderde. Zelfde gedachte als test_verzamelorder_drift.py.
  // import.meta.url is hier geen file:-URL (jsdom-omgeving), dus zoeken we de
  // fixture omhoog vanaf de werkmap. Vitest start vanuit web/src/client, maar
  // dat mag geen aanname zijn.
  const fixturePad = (): string => {
    let map = process.cwd();
    for (let stap = 0; stap < 6; stap++) {
      const kandidaat = path.join(
        map,
        "tests",
        "fixtures",
        "allowlist_gevallen.json",
      );
      if (existsSync(kandidaat)) return kandidaat;
      map = path.dirname(map);
    }
    throw new Error(
      "tests/fixtures/allowlist_gevallen.json niet gevonden vanaf " +
        process.cwd(),
    );
  };

  const fixture = JSON.parse(readFileSync(fixturePad(), "utf-8")) as {
    scenarios: {
      naam: string;
      regels: string[];
      gevallen: { adres: string; toegestaan: boolean }[];
    }[];
  };

  const gevallen = fixture.scenarios.flatMap((scenario) =>
    scenario.gevallen.map((geval) => ({
      naam: scenario.naam,
      regels: scenario.regels,
      adres: geval.adres,
      toegestaan: geval.toegestaan,
    })),
  );

  it("bevat gevallen", () => {
    // Vangt een leeg of stukgelopen fixture-bestand af.
    expect(gevallen.length).toBeGreaterThanOrEqual(15);
  });

  it.each(gevallen)(
    "$naam | $adres -> $toegestaan",
    ({ regels, adres, toegestaan: verwacht }) => {
      expect(isToegestaan(adres, regels)).toBe(verwacht);
    },
  );
});

describe("omschrijfAllowlist", () => {
  it("zet een @ voor domeinen en laat adressen staan", () => {
    expect(omschrijfAllowlist(["lokalist.nl", "jeroen@gmail.com"])).toBe(
      "@lokalist.nl, jeroen@gmail.com",
    );
  });

  it("normaliseert een leidende @ en hoofdletters", () => {
    expect(omschrijfAllowlist(["@Lokalist.NL"])).toBe("@lokalist.nl");
  });

  it("geeft lege tekst bij een lege lijst", () => {
    expect(omschrijfAllowlist([])).toBe("");
  });
});

describe("useEmailSelectie", () => {
  it("neemt de adressen uit .env over als aangevinkt", () => {
    const { result } = renderHook(() => useEmailSelectie(INSTELLINGEN));

    expect(result.current.actieveSelectie).toEqual({
      to: ["info@lokalist.nl"],
      cc: ["planning@ophaaldienstmiedema.nl"],
      bcc: ["jeroenkrajenbrink@gmail.com"],
    });
    expect(result.current.probleem).toBeNull();
  });

  describe("standaard uitgevinkt", () => {
    const metUitgevinkt: EmailInstellingen = {
      ...INSTELLINGEN,
      cc: ["facturen@ophaaldienstmiedema.nl", "johannes@lokalist.nl"],
      uitgevinkt: ["johannes@lokalist.nl"],
    };

    it("start met het adres zichtbaar maar niet aangevinkt", () => {
      const { result } = renderHook(() => useEmailSelectie(metUitgevinkt));

      // Beide staan in de lijst...
      expect(result.current.selectie.cc).toHaveLength(2);
      // ...maar alleen facturen@ gaat mee in de mailing.
      expect(result.current.actieveSelectie.cc).toEqual([
        "facturen@ophaaldienstmiedema.nl",
      ]);
    });

    it("is alsnog aan te vinken door de gebruiker", () => {
      const { result } = renderHook(() => useEmailSelectie(metUitgevinkt));
      const johannesId = result.current.selectie.cc[1]!.id;

      act(() => result.current.wisselActief("cc", johannesId));

      expect(result.current.actieveSelectie.cc).toContain(
        "johannes@lokalist.nl",
      );
    });

    it("vergelijkt hoofdletterongevoelig", () => {
      const { result } = renderHook(() =>
        useEmailSelectie({
          ...metUitgevinkt,
          uitgevinkt: ["  JOHANNES@Lokalist.NL  "],
        }),
      );

      expect(result.current.actieveSelectie.cc).toEqual([
        "facturen@ophaaldienstmiedema.nl",
      ]);
    });

    it("blokkeert versturen als het enige Aan-adres uitgevinkt is", () => {
      const { result } = renderHook(() =>
        useEmailSelectie({ ...INSTELLINGEN, uitgevinkt: ["info@lokalist.nl"] }),
      );

      expect(result.current.probleem).toMatch(/minstens één Aan-adres/i);
    });

    it("herstellen zet het adres weer op uitgevinkt", () => {
      const { result } = renderHook(() => useEmailSelectie(metUitgevinkt));
      const johannesId = result.current.selectie.cc[1]!.id;
      act(() => result.current.wisselActief("cc", johannesId));

      act(() => result.current.herstel());

      expect(result.current.actieveSelectie.cc).toEqual([
        "facturen@ophaaldienstmiedema.nl",
      ]);
    });
  });

  it("laat een uitgevinkt adres weg uit de mailing", () => {
    const { result } = renderHook(() => useEmailSelectie(INSTELLINGEN));
    const ccId = result.current.selectie.cc[0]!.id;

    act(() => result.current.wisselActief("cc", ccId));

    expect(result.current.actieveSelectie.cc).toEqual([]);
    // Het adres blijft zichtbaar in de lijst, alleen niet actief.
    expect(result.current.selectie.cc).toHaveLength(1);
    expect(result.current.selectie.cc[0]!.actief).toBe(false);
  });

  it("staat toe het Aan-adres aan te passen naar een priveadres", () => {
    const { result } = renderHook(() => useEmailSelectie(INSTELLINGEN));
    const toId = result.current.selectie.to[0]!.id;

    act(() => result.current.wijzigAdres("to", toId, "jeroen@prive.nl"));

    expect(result.current.actieveSelectie.to).toEqual(["jeroen@prive.nl"]);
    expect(result.current.probleem).toBeNull();
  });

  it("voegt een extra adres toe", () => {
    const { result } = renderHook(() => useEmailSelectie(INSTELLINGEN));

    act(() => result.current.voegToe("cc", "extra@voorbeeld.nl"));

    expect(result.current.actieveSelectie.cc).toContain("extra@voorbeeld.nl");
    expect(result.current.selectie.cc.at(-1)!.bron).toBe("extra");
  });

  it("voegt een dubbel adres niet nogmaals toe", () => {
    const { result } = renderHook(() => useEmailSelectie(INSTELLINGEN));

    act(() => result.current.voegToe("cc", "PLANNING@ophaaldienstmiedema.nl"));

    expect(result.current.selectie.cc).toHaveLength(1);
  });

  it("verwijdert alleen zelf toegevoegde adressen", () => {
    const { result } = renderHook(() => useEmailSelectie(INSTELLINGEN));
    act(() => result.current.voegToe("bcc", "tijdelijk@voorbeeld.nl"));
    const extraId = result.current.selectie.bcc.at(-1)!.id;

    act(() => result.current.verwijder("bcc", extraId));

    expect(result.current.actieveSelectie.bcc).toEqual([
      "jeroenkrajenbrink@gmail.com",
    ]);
  });

  it("meldt een probleem als er geen enkel Aan-adres over is", () => {
    const { result } = renderHook(() => useEmailSelectie(INSTELLINGEN));
    const toId = result.current.selectie.to[0]!.id;

    act(() => result.current.wisselActief("to", toId));

    expect(result.current.probleem).toMatch(/minstens één Aan-adres/i);
  });

  it("blokkeert doorgaan bij een ongeldig actief adres", () => {
    const { result } = renderHook(() => useEmailSelectie(INSTELLINGEN));
    const toId = result.current.selectie.to[0]!.id;

    act(() => result.current.wijzigAdres("to", toId, "kapot-adres"));

    expect(result.current.ongeldigeAdressen).toEqual(["kapot-adres"]);
    expect(result.current.magVerder).toBe(false);
  });

  it("zet géén melding in de balk over een ongeldig adres", () => {
    // Die fout hoort bij het veld zelf, dat hem pas bij focus verlies toont.
    // Twee meldingen over hetzelfde met verschillende timing was verwarrend.
    const { result } = renderHook(() => useEmailSelectie(INSTELLINGEN));
    const toId = result.current.selectie.to[0]!.id;

    act(() => result.current.wijzigAdres("to", toId, "jeroen"));

    expect(result.current.probleem).toBeNull();
  });

  it("negeert een ongeldig adres dat is uitgevinkt", () => {
    const { result } = renderHook(() => useEmailSelectie(INSTELLINGEN));
    act(() => result.current.voegToe("cc", "nog@geldig.nl"));
    const ccId = result.current.selectie.cc[0]!.id;

    act(() => result.current.wijzigAdres("cc", ccId, "kapot"));
    act(() => result.current.wisselActief("cc", ccId));

    expect(result.current.probleem).toBeNull();
    expect(result.current.ongeldigeAdressen).toEqual([]);
    expect(result.current.magVerder).toBe(true);
  });

  it("staat doorgaan toe zodra alles klopt", () => {
    const { result } = renderHook(() => useEmailSelectie(INSTELLINGEN));

    expect(result.current.magVerder).toBe(true);
    expect(result.current.probleem).toBeNull();
    expect(result.current.ongeldigeAdressen).toEqual([]);
  });

  describe("domein-allowlist", () => {
    const METALLOWLIST: EmailInstellingen = {
      ...INSTELLINGEN,
      allowlist: ["lokalist.nl"],
    };

    it("weigert een toegevoegd adres buiten de allowlist", () => {
      const { result } = renderHook(() => useEmailSelectie(METALLOWLIST));

      act(() => result.current.voegToe("cc", "jeroen@prive.nl"));

      expect(result.current.geweigerdeAdressen).toEqual(["jeroen@prive.nl"]);
      expect(result.current.magVerder).toBe(false);
    });

    it("staat een adres binnen de allowlist toe", () => {
      const { result } = renderHook(() => useEmailSelectie(METALLOWLIST));

      act(() => result.current.voegToe("cc", "nieuw@lokalist.nl"));

      expect(result.current.geweigerdeAdressen).toEqual([]);
      expect(result.current.magVerder).toBe(true);
    });

    it("laat de adressen uit .env altijd door", () => {
      // planning@ en jeroenkrajenbrink@ vallen buiten de lijst, maar staan al
      // in .env — net als in email_allowlist.py mogen die gewoon.
      const { result } = renderHook(() => useEmailSelectie(METALLOWLIST));

      expect(result.current.geweigerdeAdressen).toEqual([]);
      expect(result.current.magVerder).toBe(true);
    });

    it("negeert een geweigerd adres dat is uitgevinkt", () => {
      const { result } = renderHook(() => useEmailSelectie(METALLOWLIST));
      act(() => result.current.voegToe("cc", "jeroen@prive.nl"));
      const extraId = result.current.selectie.cc.at(-1)!.id;

      act(() => result.current.wisselActief("cc", extraId));

      expect(result.current.geweigerdeAdressen).toEqual([]);
      expect(result.current.magVerder).toBe(true);
    });

    it("zonder allowlist blijft elk geldig adres toegestaan", () => {
      const { result } = renderHook(() => useEmailSelectie(INSTELLINGEN));

      act(() => result.current.voegToe("cc", "wie.dan.ook@internet.com"));

      expect(result.current.geweigerdeAdressen).toEqual([]);
      expect(result.current.magVerder).toBe(true);
    });

    it("meldt per adres wat er mis is", () => {
      const { result } = renderHook(() => useEmailSelectie(METALLOWLIST));

      expect(result.current.adresProbleem("kapot")).toMatch(
        /geen geldig e-mailadres/i,
      );
      expect(result.current.adresProbleem("jeroen@prive.nl")).toMatch(
        /alleen naar @lokalist\.nl/i,
      );
      expect(result.current.adresProbleem("nieuw@lokalist.nl")).toBeNull();
    });

    it("zet géén melding in de balk over een geweigerd domein", () => {
      // Zelfde afweging als bij een ongeldig adres: het veld meldt het zelf.
      const { result } = renderHook(() => useEmailSelectie(METALLOWLIST));

      act(() => result.current.voegToe("cc", "jeroen@prive.nl"));

      expect(result.current.probleem).toBeNull();
    });
  });

  it("herstelt de oorspronkelijke selectie", () => {
    const { result } = renderHook(() => useEmailSelectie(INSTELLINGEN));
    act(() => result.current.voegToe("to", "extra@voorbeeld.nl"));

    act(() => result.current.herstel());

    expect(result.current.actieveSelectie.to).toEqual(["info@lokalist.nl"]);
  });
});
