/** Test voor een mislukte schrijfactie naar stdin van het Python-proces.
 *
 * Sterft Python voordat de opdracht in de pipe staat (ontbrekende venv,
 * importfout), dan geeft de stream een asynchrone 'error' — EPIPE of
 * ERR_STREAM_DESTROYED. Een stream zonder 'error'-listener gooit die als
 * uncaught exception, en dat legt het hele Express-proces om: één kapotte venv
 * zou dus het dashboard voor iedereen offline halen.
 *
 * Het kind wordt hier nagebootst, omdat de timing van een echte EPIPE (schrijft
 * de ouder vóór of ná het sterven van het kind?) per platform verschilt en de
 * test anders wisselvallig wordt.
 */

import { EventEmitter } from "node:events";
import { afterEach, describe, expect, it, vi } from "vitest";

// vi.hoisted draait vóór de mock-factory. Een gewone const komt te laat: de
// factory wordt al uitgevoerd zodra iets node:child_process importeert, en
// grijpt dan mis op een variabele die nog niet bestaat.
const { kind } = vi.hoisted(() => {
  const { EventEmitter: EE } = require("node:events") as typeof import("node:events");

  /** Stdin die faalt zoals een echte pipe: asynchroon, ná de write. */
  class NepStdin extends EE {
    geschreven = false;

    write(): boolean {
      this.geschreven = true;
      process.nextTick(() =>
        this.emit(
          "error",
          Object.assign(new Error("write EPIPE"), { code: "EPIPE" }),
        ),
      );
      return false;
    }

    end(): void {}
  }

  const nep = new EE() as EventEmitter & Record<string, never>;
  for (const naam of ["stdout", "stderr"]) {
    const stroom = new EE() as EventEmitter & Record<string, never>;
    (stroom as Record<string, unknown>).setEncoding = () => stroom;
    (nep as Record<string, unknown>)[naam] = stroom;
  }
  (nep as Record<string, unknown>).stdin = new NepStdin();
  (nep as Record<string, unknown>).kill = () => true;
  return { kind: nep };
});

// De default-export moet er ook zijn: de interop van de bundler pakt die aan.
vi.mock("node:child_process", () => {
  const spawn = () => kind;
  return { spawn, default: { spawn } };
});

/** Het stdin-object van het nagebootste kind. */
const stdin = (kind as unknown as { stdin: EventEmitter & { geschreven: boolean } })
  .stdin;

const { voerRunnerUit, RunnerFout } = await import("../src/server/python.js");

afterEach(() => {
  vi.restoreAllMocks();
});

describe("mislukte schrijfactie naar stdin", () => {
  it("vangt de fout af en laat de run afronden op de exitcode", async () => {
    const waarschuwing = vi.spyOn(console, "warn").mockImplementation(() => {});

    const belofte = voerRunnerUit({ command: "lijst" });
    // Twee ticks: één voor de emit uit write(), één om die te verwerken.
    await new Promise((r) => setImmediate(r));
    kind.emit("close", 1);

    // De EPIPE zelf mag de melding niet bepalen; die zegt niets over de oorzaak.
    await expect(belofte).rejects.toThrow(/stopte onverwacht/i);
    await expect(belofte).rejects.toBeInstanceOf(RunnerFout);

    expect(stdin.geschreven).toBe(true);
    expect(waarschuwing).toHaveBeenCalledWith(
      expect.stringContaining("schrijven naar stdin mislukt"),
    );
  });

  it("laat het proces niet omvallen op een ongevangen streamfout", () => {
    // Zonder listener zou de emit hierboven een uncaught exception zijn, en dat
    // legt in productie het hele Express-proces om. Dat er een listener staat
    // is precies wat deze test bewaakt.
    expect(stdin.listenerCount("error")).toBeGreaterThan(0);
  });
});
