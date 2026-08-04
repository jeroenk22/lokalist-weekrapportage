/** Brug naar scripts/web_runner.py.
 *
 * Het dashboard bouwt de rapportage niet zelf na: het start dezelfde
 * Python-engine die de zondagrun gebruikt en streamt de voortgang door.
 * Daarmee is de uitvoer per definitie identiek aan de automatische run.
 *
 * Protocol: JSON naar stdin, NDJSON terug over stdout. stderr bevat de
 * gewone logging en wordt bewaard voor foutrapportage.
 */

import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import type { RunnerGebeurtenis } from "../shared/types.js";
import { gebeurtenisSchema } from "./schemas.js";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

/** Projectroot, drie niveaus omhoog.
 *
 * Ontwikkeling: web/src/server → web/src → web → root
 * Gebouwd:      web/dist/server → web/dist → web → root
 */
export const PROJECT_ROOT = path.resolve(__dirname, "..", "..", "..");

const RUNNER_SCRIPT = path.join(PROJECT_ROOT, "scripts", "web_runner.py");

/** Hoe lang een opdracht maximaal mag duren voordat we het proces afbreken. */
const TIMEOUT_MS = 10 * 60 * 1000;

/**
 * Bepaalt welke Python gebruikt wordt.
 *
 * De venv heeft voorrang: die bevat pyodbc, reportlab en zeep. Valt de venv
 * weg, dan proberen we de Python uit PATH, zodat een verkeerd ingerichte
 * machine een duidelijke fout geeft in plaats van een importfout.
 */
export function pythonPad(): string {
  const venv =
    process.platform === "win32"
      ? path.join(PROJECT_ROOT, ".venv", "Scripts", "python.exe")
      : path.join(PROJECT_ROOT, ".venv", "bin", "python");

  if (existsSync(venv)) return venv;

  // PYTHON mag zowel naar de executable als naar een installatiemap wijzen.
  const uitOmgeving = process.env.PYTHON?.trim();
  if (uitOmgeving) {
    const exe = process.platform === "win32" ? "python.exe" : "python";
    if (existsSync(path.join(uitOmgeving, exe)))
      return path.join(uitOmgeving, exe);
    if (existsSync(uitOmgeving)) return uitOmgeving;
  }

  return process.platform === "win32" ? "python" : "python3";
}

export class RunnerFout extends Error {
  constructor(
    message: string,
    readonly details?: string,
    readonly logbestand?: string,
  ) {
    super(message);
    this.name = "RunnerFout";
  }
}

export interface RunnerOpties {
  /** Wordt aangeroepen voor elke gebeurtenis die de runner uitstuurt. */
  onGebeurtenis?: (gebeurtenis: RunnerGebeurtenis) => void;
  signal?: AbortSignal;
}

/**
 * Voert één opdracht uit en geeft de `data` van de klaar-gebeurtenis terug.
 *
 * Gooit een RunnerFout bij een fout-gebeurtenis, een crash van het proces of
 * een overschreden timeout.
 */
export function voerRunnerUit<T = unknown>(
  opdracht: Record<string, unknown>,
  opties: RunnerOpties = {},
): Promise<T> {
  const { onGebeurtenis, signal } = opties;

  return new Promise<T>((resolve, reject) => {
    if (!existsSync(RUNNER_SCRIPT)) {
      reject(new RunnerFout(`Runner-script niet gevonden: ${RUNNER_SCRIPT}`));
      return;
    }

    const kind = spawn(pythonPad(), [RUNNER_SCRIPT], {
      cwd: PROJECT_ROOT,
      // PYTHONIOENCODING borgt dat accenten en het €-teken correct over de pipe gaan.
      env: { ...process.env, PYTHONIOENCODING: "utf-8", PYTHONUNBUFFERED: "1" },
      windowsHide: true,
    });

    let stdoutRest = "";
    let stderrBuffer = "";
    let resultaat: T | undefined;
    let afgerond = false;
    let foutmelding: RunnerFout | undefined;

    const timeout = setTimeout(() => {
      foutmelding = new RunnerFout(
        `De bewerking duurde langer dan ${TIMEOUT_MS / 60000} minuten en is afgebroken.`,
      );
      kind.kill();
    }, TIMEOUT_MS);

    const afbreken = () => {
      foutmelding = new RunnerFout("De bewerking is afgebroken.");
      kind.kill();
    };
    signal?.addEventListener("abort", afbreken, { once: true });

    const verwerkRegel = (regel: string) => {
      const getrimd = regel.trim();
      if (!getrimd) return;

      let ruw: unknown;
      try {
        ruw = JSON.parse(getrimd);
      } catch {
        // Geen JSON op stdout: duidt op een print() in de Python-keten.
        console.warn(
          "[runner] niet-JSON op stdout genegeerd:",
          getrimd.slice(0, 200),
        );
        return;
      }

      const parsed = gebeurtenisSchema.safeParse(ruw);
      if (!parsed.success) {
        console.warn(
          "[runner] onbekende gebeurtenis genegeerd:",
          getrimd.slice(0, 200),
        );
        return;
      }

      const gebeurtenis = parsed.data as RunnerGebeurtenis;
      onGebeurtenis?.(gebeurtenis);

      if (gebeurtenis.type === "klaar") {
        resultaat = gebeurtenis.data as T;
        afgerond = true;
      } else if (gebeurtenis.type === "fout") {
        foutmelding = new RunnerFout(
          gebeurtenis.bericht,
          gebeurtenis.details,
          gebeurtenis.logbestand,
        );
      }
    };

    kind.stdout.setEncoding("utf-8");
    kind.stdout.on("data", (brok: string) => {
      stdoutRest += brok;
      const regels = stdoutRest.split("\n");
      stdoutRest = regels.pop() ?? "";
      for (const regel of regels) verwerkRegel(regel);
    });

    kind.stderr.setEncoding("utf-8");
    kind.stderr.on("data", (brok: string) => {
      stderrBuffer += brok;
      // Begrens het geheugengebruik bij een lange run.
      if (stderrBuffer.length > 200_000) {
        stderrBuffer = stderrBuffer.slice(-100_000);
      }
    });

    kind.on("error", (err) => {
      clearTimeout(timeout);
      signal?.removeEventListener("abort", afbreken);
      reject(
        new RunnerFout(
          `Kon Python niet starten (${pythonPad()}). Controleer of de venv is aangemaakt.`,
          err.message,
        ),
      );
    });

    kind.on("close", (code) => {
      clearTimeout(timeout);
      signal?.removeEventListener("abort", afbreken);
      if (stdoutRest.trim()) verwerkRegel(stdoutRest);

      if (foutmelding) {
        reject(foutmelding);
        return;
      }
      if (afgerond) {
        resolve(resultaat as T);
        return;
      }
      reject(
        new RunnerFout(
          `De Python-runner stopte onverwacht (exitcode ${code}).`,
          stderrBuffer.slice(-4000),
        ),
      );
    });

    kind.stdin.write(JSON.stringify(opdracht));
    kind.stdin.end();
  });
}
