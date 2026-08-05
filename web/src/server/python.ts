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

/** Wordt gegooid als er al een run bezig is voor dezelfde verzamelorder. */
export class AlBezigFout extends Error {
  constructor(readonly orderId: number) {
    super(
      `Er is al een hergeneratie bezig voor verzamelorder ${orderId}. ` +
        `Wacht tot die klaar is en ververs daarna het dashboard.`,
    );
    this.name = "AlBezigFout";
  }
}

/**
 * Lopende hergeneraties, per order-ID.
 *
 * Zonder inlogscherm kunnen twee collega's dezelfde order tegelijk oppakken.
 * Beide komen dan langs de factuurcontrole, beide maken een order aan, en de
 * tweede verwijdering draait op een al verwijderde order — netto twee
 * verzamelorders voor dezelfde week.
 *
 * Eén Express-proces, dus een Map volstaat. De controle en het zetten gebeuren
 * zonder await ertussen, waardoor er geen gat zit waar een tweede verzoek
 * doorheen glipt.
 */
const lopendeHergeneraties = new Map<number, Promise<unknown>>();

export function isHergeneratieBezig(orderId: number): boolean {
  return lopendeHergeneraties.has(orderId);
}

/** Voert `taak` uit, maar weigert als er al een run loopt voor dit order-ID. */
export function metHergeneratieSlot<T>(
  orderId: number,
  taak: () => Promise<T>,
): Promise<T> {
  if (lopendeHergeneraties.has(orderId)) {
    return Promise.reject(new AlBezigFout(orderId));
  }
  const belofte = taak().finally(() => {
    lopendeHergeneraties.delete(orderId);
  });
  lopendeHergeneraties.set(orderId, belofte);
  return belofte;
}

export interface RunnerOpties {
  /** Wordt aangeroepen voor elke gebeurtenis die de runner uitstuurt. */
  onGebeurtenis?: (gebeurtenis: RunnerGebeurtenis) => void;
  signal?: AbortSignal;
}

/**
 * Vanaf deze stap heeft de runner iets in MendriX aangemaakt.
 *
 * Stap 3 maakt de nieuwe verzamelorder aan. Het proces daarna doden is
 * levensgevaarlijk: op Windows is kill() een harde TerminateProcess, waardoor
 * het except-blok in web_runner.py — en dus de rollback — niet meer draait.
 * Je houdt dan de nieuwe én de oude order over, zonder dat iemand het merkt.
 */
const EERSTE_STAP_MET_GEVOLGEN = 3;

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
    let laatsteStap = 0;

    /**
     * Breekt de run af, maar alleen zolang dat veilig is.
     *
     * Zodra stap 3 gestart is bestaat er een order in MendriX en moet de runner
     * zijn eigen rollback kunnen doen. Dan laten we het proces uitlopen; de
     * gebruiker ziet het resultaat weliswaar niet meer, maar er blijft geen
     * weesorder achter.
     *
     * LET OP — bewust geaccepteerd restrisico: vanaf stap 3 biedt de timeout
     * hieronder GEEN dekking meer. Blijft het Python-proces echt hangen, dan
     * settelt deze promise nooit, draait de .finally() van het
     * gelijktijdigheidsslot niet, en blijft dat order-ID op slot tot Node
     * herstart wordt — plus een lekkend childproces.
     *
     * Dat is aanvaard omdat elke externe aanroep in de keten zelf een timeout
     * heeft: SOAP 30s, dossier-upload 60s, SMTP 60s, Graph 30s. Een oneindige
     * hang is daardoor onwaarschijnlijk. Wie hier iets verandert: ga er niet
     * van uit dat de timeout je nog opvangt.
     */
    const probeerAfTeBreken = (reden: string) => {
      if (laatsteStap >= EERSTE_STAP_MET_GEVOLGEN) {
        console.warn(
          `[runner] ${reden}, maar stap ${laatsteStap} is al bezig — proces blijft ` +
            `doorlopen zodat de rollback in Python kan afronden.`,
        );
        return;
      }
      foutmelding = new RunnerFout(reden);
      kind.kill();
    };

    const timeout = setTimeout(() => {
      probeerAfTeBreken(
        `De bewerking duurde langer dan ${TIMEOUT_MS / 60000} minuten en is afgebroken.`,
      );
    }, TIMEOUT_MS);

    const afbreken = () => probeerAfTeBreken("De bewerking is afgebroken.");
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
      if (gebeurtenis.type === "stap") laatsteStap = gebeurtenis.nummer;
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

    // Sterft het proces voordat de opdracht erin staat (ontbrekende venv,
    // importfout), dan geeft de pipe een EPIPE/ERR_STREAM_DESTROYED. Zonder
    // listener is dat een ongevangen fout die het hele Express-proces omlegt.
    // De echte melding komt uit de 'error'- of 'close'-handler hierboven.
    kind.stdin.on("error", (err) => {
      console.warn(`[runner] schrijven naar stdin mislukt: ${err.message}`);
    });

    kind.stdin.write(JSON.stringify(opdracht));
    kind.stdin.end();
  });
}
