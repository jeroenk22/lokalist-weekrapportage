/** Tests voor het gelijktijdigheidsslot op hergeneraties.
 *
 * Zonder inlogscherm kunnen twee collega's dezelfde order tegelijk oppakken.
 * Beide zouden dan langs de factuurcontrole komen en een order aanmaken, en de
 * tweede verwijdering draait op een al verwijderde order — netto twee
 * verzamelorders voor dezelfde week.
 */

import { describe, expect, it } from "vitest";

import {
  AlBezigFout,
  isHergeneratieBezig,
  metHergeneratieSlot,
} from "../src/server/python.js";

/** Belofte die je van buitenaf kunt afronden. */
function uitgesteld<T>() {
  let afronden!: (waarde: T) => void;
  let afwijzen!: (reden: unknown) => void;
  const belofte = new Promise<T>((res, rej) => {
    afronden = res;
    afwijzen = rej;
  });
  return { belofte, afronden, afwijzen };
}

describe("metHergeneratieSlot", () => {
  it("laat een run voor een vrije order gewoon door", async () => {
    await expect(metHergeneratieSlot(1, async () => "klaar")).resolves.toBe(
      "klaar",
    );
  });

  it("weigert een tweede run voor dezelfde order", async () => {
    const eerste = uitgesteld<string>();
    const lopend = metHergeneratieSlot(2, () => eerste.belofte);

    await expect(
      metHergeneratieSlot(2, async () => "tweede"),
    ).rejects.toBeInstanceOf(AlBezigFout);

    eerste.afronden("eerste");
    await expect(lopend).resolves.toBe("eerste");
  });

  it("start de tweede taak niet eens", async () => {
    const eerste = uitgesteld<string>();
    const lopend = metHergeneratieSlot(3, () => eerste.belofte);
    let tweedeGestart = false;

    await metHergeneratieSlot(3, async () => {
      tweedeGestart = true;
      return "tweede";
    }).catch(() => {});

    expect(tweedeGestart).toBe(false);
    eerste.afronden("eerste");
    await lopend;
  });

  it("noemt het ordernummer in de melding", async () => {
    const eerste = uitgesteld<string>();
    const lopend = metHergeneratieSlot(1266289, () => eerste.belofte);

    await expect(metHergeneratieSlot(1266289, async () => "x")).rejects.toThrow(
      /1266289/,
    );

    eerste.afronden("");
    await lopend;
  });

  it("blokkeert een andere order niet", async () => {
    const eerste = uitgesteld<string>();
    const lopend = metHergeneratieSlot(10, () => eerste.belofte);

    await expect(metHergeneratieSlot(11, async () => "andere")).resolves.toBe(
      "andere",
    );

    eerste.afronden("");
    await lopend;
  });

  it("geeft het slot vrij na een geslaagde run", async () => {
    await metHergeneratieSlot(20, async () => "eerste");

    expect(isHergeneratieBezig(20)).toBe(false);
    await expect(metHergeneratieSlot(20, async () => "tweede")).resolves.toBe(
      "tweede",
    );
  });

  it("geeft het slot ook vrij als de run faalt", async () => {
    // Anders blijft de order voorgoed op slot na één storing.
    await expect(
      metHergeneratieSlot(21, async () => {
        throw new Error("SOAP stuk");
      }),
    ).rejects.toThrow("SOAP stuk");

    expect(isHergeneratieBezig(21)).toBe(false);
    await expect(metHergeneratieSlot(21, async () => "daarna")).resolves.toBe(
      "daarna",
    );
  });

  it("meldt of er een run bezig is", async () => {
    const eerste = uitgesteld<string>();
    expect(isHergeneratieBezig(30)).toBe(false);

    const lopend = metHergeneratieSlot(30, () => eerste.belofte);
    expect(isHergeneratieBezig(30)).toBe(true);

    eerste.afronden("");
    await lopend;
    expect(isHergeneratieBezig(30)).toBe(false);
  });
});
