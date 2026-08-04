/** Tests voor het afbreken van een lopende run.
 *
 * Kernpunt: zodra stap 3 gestart is bestaat er een verzamelorder in MendriX.
 * Het proces dan doden is op Windows een harde TerminateProcess, waardoor het
 * except-blok in web_runner.py — en dus de rollback — niet meer draait. Je
 * houdt dan de nieuwe én de oude order over. Dat mag nooit gebeuren.
 *
 * Deze tests draaien een echt Python-stubproces, zodat het gedrag bewezen wordt
 * en niet alleen gemockt.
 */

import { mkdirSync, rmSync, writeFileSync } from "node:fs";
import { afterAll, beforeEach, describe, expect, it, vi } from "vitest";

// vi.hoisted draait vóór de mock-factory; een gewone const zou te laat komen.
const { werkmap, stubScript } = vi.hoisted(() => {
  const os = require("node:os") as typeof import("node:os");
  const p = require("node:path") as typeof import("node:path");
  const map = p.join(os.tmpdir(), `lokalist-afbreken-${process.pid}`);
  return { werkmap: map, stubScript: p.join(map, "web_runner.py") };
});

mkdirSync(werkmap, { recursive: true });
afterAll(() => rmSync(werkmap, { recursive: true, force: true }));

// De brug zoekt scripts/web_runner.py in de projectroot; hier wijzen we die
// naar een stub die we per test zelf schrijven.
vi.mock("node:path", async (origineel) => {
  const echt = await origineel<typeof import("node:path")>();
  // Alleen het pad naar web_runner.py omleiden; al het andere (projectroot,
  // venv-pad) moet gewoon door de echte join blijven lopen.
  const join = (...delen: string[]) =>
    delen.at(-1) === "web_runner.py" ? stubScript : echt.join(...delen);
  // python.ts doet `import path from "node:path"`, dus de default-export moet
  // óók de aangepaste join hebben.
  return { ...echt, join, default: { ...echt, join } };
});

const { voerRunnerUit } = await import("../src/server/python.js");

/** Stub die tot en met `totStap` meldt en daarna blijft hangen. */
function schrijfStub(totStap: number, hangSeconden = 5) {
  writeFileSync(
    stubScript,
    [
      "import json,sys,time",
      "sys.stdin.read()",
      `for i in range(1, ${totStap} + 1):`,
      '    print(json.dumps({"type":"stap","nummer":i,"totaal":7,"bericht":f"stap {i}"}),' +
        " flush=True)",
      `time.sleep(${hangSeconden})`,
      'print(json.dumps({"type":"klaar","data":{"afgerond":True},"logbestand":""}), flush=True)',
    ].join("\n"),
    "utf-8",
  );
}

beforeEach(() => {
  vi.restoreAllMocks();
});

describe("afbreken van een lopende run", () => {
  it("breekt wél af zolang er nog niets is aangemaakt", async () => {
    // Stap 1 en 2 lezen alleen data en maken een PDF; daar valt niets te verliezen.
    schrijfStub(2);
    const controller = new AbortController();
    const gezien: number[] = [];

    const run = voerRunnerUit(
      { command: "regenereer" },
      {
        signal: controller.signal,
        onGebeurtenis: (g) => {
          if (g.type === "stap") {
            gezien.push(g.nummer);
            if (g.nummer === 2) controller.abort();
          }
        },
      },
    );

    await expect(run).rejects.toThrow(/afgebroken/i);
    expect(gezien).toEqual([1, 2]);
  }, 20000);

  it("breekt NIET af zodra stap 3 een order heeft aangemaakt", async () => {
    // Dit is het scenario uit de review: killen na stap 3 laat een weesorder
    // achter omdat de rollback in Python niet meer draait.
    schrijfStub(3, 2);
    const controller = new AbortController();

    const run = voerRunnerUit<{ afgerond: boolean }>(
      { command: "regenereer" },
      {
        signal: controller.signal,
        onGebeurtenis: (g) => {
          if (g.type === "stap" && g.nummer === 3) controller.abort();
        },
      },
    );

    // De run loopt gewoon door en rondt zelf af.
    await expect(run).resolves.toEqual({ afgerond: true });
  }, 20000);

  it("laat een run na stap 3 ook bij een latere afbreking uitlopen", async () => {
    schrijfStub(6, 2);
    const controller = new AbortController();

    const run = voerRunnerUit<{ afgerond: boolean }>(
      { command: "regenereer" },
      {
        signal: controller.signal,
        onGebeurtenis: (g) => {
          if (g.type === "stap" && g.nummer === 6) controller.abort();
        },
      },
    );

    await expect(run).resolves.toEqual({ afgerond: true });
  }, 20000);

  it("waarschuwt in de console als afbreken geweigerd wordt", async () => {
    schrijfStub(3, 1);
    const waarschuwing = vi.spyOn(console, "warn").mockImplementation(() => {});
    const controller = new AbortController();

    await voerRunnerUit(
      { command: "regenereer" },
      {
        signal: controller.signal,
        onGebeurtenis: (g) => {
          if (g.type === "stap" && g.nummer === 3) controller.abort();
        },
      },
    );

    expect(waarschuwing).toHaveBeenCalledWith(
      expect.stringMatching(/stap 3 is al bezig.*rollback/is),
    );
  }, 20000);
});
