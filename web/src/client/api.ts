/** HTTP-laag richting de Express-backend. */

import type {
  EmailSelectie,
  RegenereerResultaat,
  RunnerGebeurtenis,
  VerzamelorderOverzicht,
} from "../shared/types.js";

async function leesFout(
  response: Response,
  standaard: string,
): Promise<string> {
  try {
    const body = (await response.json()) as { fout?: string; details?: string };
    return body.fout ?? standaard;
  } catch {
    return standaard;
  }
}

export async function haalOverzichtOp(): Promise<VerzamelorderOverzicht> {
  const response = await fetch("/api/verzamelorders");
  if (!response.ok) {
    throw new Error(
      await leesFout(response, "Kon de verzamelorders niet ophalen."),
    );
  }
  return (await response.json()) as VerzamelorderOverzicht;
}

/** Gebeurtenissen die de stream aan de UI doorgeeft. */
export type StreamGebeurtenis =
  RunnerGebeurtenis | { type: "resultaat"; data: RegenereerResultaat };

export interface RegenereerOpties {
  orderId: number;
  email: EmailSelectie;
  /** Wie het rapport opnieuw genereert; komt in de order-notitie terecht. */
  naam: string;
  dryRun?: boolean;
  onGebeurtenis: (gebeurtenis: StreamGebeurtenis) => void;
  signal?: AbortSignal;
}

/**
 * Start het opnieuw genereren en leest de NDJSON-stream regel voor regel uit.
 *
 * Geeft het eindresultaat terug, of gooit een Error met de melding die in de
 * modal getoond moet worden.
 */
export async function regenereer(
  opties: RegenereerOpties,
): Promise<RegenereerResultaat> {
  const {
    orderId,
    email,
    naam,
    dryRun = false,
    onGebeurtenis,
    signal,
  } = opties;

  const response = await fetch(`/api/verzamelorders/${orderId}/regenereer`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, naam, dryRun, bevestigd: true }),
    signal,
  });

  if (!response.ok || !response.body) {
    throw new Error(
      await leesFout(
        response,
        "Het opnieuw genereren kon niet gestart worden.",
      ),
    );
  }

  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
  let rest = "";
  let resultaat: RegenereerResultaat | undefined;
  let fout: Error | undefined;

  const verwerk = (regel: string) => {
    const getrimd = regel.trim();
    if (!getrimd) return;

    let gebeurtenis: StreamGebeurtenis;
    try {
      gebeurtenis = JSON.parse(getrimd) as StreamGebeurtenis;
    } catch {
      return;
    }

    onGebeurtenis(gebeurtenis);
    if (gebeurtenis.type === "resultaat") {
      resultaat = gebeurtenis.data;
    } else if (gebeurtenis.type === "fout") {
      fout = new Error(gebeurtenis.bericht);
    }
  };

  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    rest += value;
    const regels = rest.split("\n");
    rest = regels.pop() ?? "";
    for (const regel of regels) verwerk(regel);
  }
  if (rest.trim()) verwerk(rest);

  if (fout) throw fout;
  if (!resultaat) {
    throw new Error("De verbinding viel weg voordat het genereren klaar was.");
  }
  return resultaat;
}
