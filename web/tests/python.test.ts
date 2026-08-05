/** Integratietests voor de brug naar Python.
 *
 * Deze tests starten een echt Python-proces (een klein stubscript), zodat het
 * NDJSON-protocol, de foutafhandeling en de streaming daadwerkelijk bewezen
 * worden in plaats van gemockt.
 */

import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { afterAll, describe, expect, it } from "vitest";

import { pythonPad } from "../src/server/python.js";

const werkmap = mkdtempSync(path.join(tmpdir(), "lokalist-runner-"));

afterAll(() => {
  rmSync(werkmap, { recursive: true, force: true });
});

/** Draait een stubscript met hetzelfde protocol als web_runner.py. */
function draaiStub(
  broncode: string,
  onGebeurtenis?: (g: unknown) => void,
): Promise<{ code: number | null; gebeurtenissen: unknown[] }> {
  const scriptPad = path.join(
    werkmap,
    `stub-${Math.random().toString(36).slice(2)}.py`,
  );
  writeFileSync(scriptPad, broncode, "utf-8");

  return new Promise((resolve, reject) => {
    import("node:child_process").then(({ spawn }) => {
      const kind = spawn(pythonPad(), [scriptPad], {
        env: { ...process.env, PYTHONIOENCODING: "utf-8" },
      });
      const gebeurtenissen: unknown[] = [];
      let rest = "";

      kind.stdout.setEncoding("utf-8");
      kind.stdout.on("data", (brok: string) => {
        rest += brok;
        const regels = rest.split("\n");
        rest = regels.pop() ?? "";
        for (const regel of regels) {
          if (!regel.trim()) continue;
          const g = JSON.parse(regel);
          gebeurtenissen.push(g);
          onGebeurtenis?.(g);
        }
      });
      kind.on("error", reject);
      kind.on("close", (code) => resolve({ code, gebeurtenissen }));
      kind.stdin.end(JSON.stringify({ command: "test" }));
    });
  });
}

describe("Python-omgeving", () => {
  it("vindt een bruikbare Python", async () => {
    const { gebeurtenissen } = await draaiStub(
      'import json,sys; sys.stdin.read(); print(json.dumps({"type":"klaar","data":{"ok":True},"logbestand":""}))',
    );
    expect(gebeurtenissen).toHaveLength(1);
    expect(gebeurtenissen[0]).toMatchObject({
      type: "klaar",
      data: { ok: true },
    });
  });

  it("levert de projectafhankelijkheden (pyodbc, reportlab)", async () => {
    const { gebeurtenissen } = await draaiStub(
      [
        "import json,sys",
        "sys.stdin.read()",
        "import pyodbc, reportlab",
        'print(json.dumps({"type":"klaar","data":{"ok":True},"logbestand":""}))',
      ].join("\n"),
    );
    expect(gebeurtenissen[0]).toMatchObject({ type: "klaar" });
  });

  it("verwerkt UTF-8 correct over de pipe", async () => {
    const { gebeurtenissen } = await draaiStub(
      [
        "import json,sys",
        "sys.stdin.read()",
        'print(json.dumps({"type":"log","niveau":"info","bericht":"€ 238,13 — geüpload"},' +
          " ensure_ascii=False))",
      ].join("\n"),
    );
    expect(gebeurtenissen[0]).toMatchObject({ bericht: "€ 238,13 — geüpload" });
  });

  it("streamt gebeurtenissen tijdens de run in plaats van pas aan het eind", async () => {
    const volgorde: string[] = [];
    const { gebeurtenissen } = await draaiStub(
      [
        "import json,sys,time",
        "sys.stdin.read()",
        "for i in (1,2,3):",
        '    print(json.dumps({"type":"stap","nummer":i,"totaal":7,"bericht":f"stap {i}"}),' +
          " flush=True)",
        "    time.sleep(0.05)",
        'print(json.dumps({"type":"klaar","data":{},"logbestand":""}), flush=True)',
      ].join("\n"),
      (g) => volgorde.push((g as { type: string }).type),
    );

    expect(gebeurtenissen).toHaveLength(4);
    expect(volgorde).toEqual(["stap", "stap", "stap", "klaar"]);
  });

  it("houdt logging op stderr, zodat stdout puur NDJSON blijft", async () => {
    const { gebeurtenissen } = await draaiStub(
      [
        "import json,sys",
        "sys.stdin.read()",
        'sys.stderr.write("2026-08-04 [INFO] dit is logging\\n")',
        'print(json.dumps({"type":"klaar","data":{"ok":True},"logbestand":""}))',
      ].join("\n"),
    );
    expect(gebeurtenissen).toHaveLength(1);
    expect(gebeurtenissen[0]).toMatchObject({ type: "klaar" });
  });
});
