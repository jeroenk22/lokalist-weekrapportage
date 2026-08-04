/** Eén e-mailveld (Aan, CC of BCC) met aan/uit-vinkjes en toevoegmogelijkheid.
 *
 * Validatie volgt in alle drie de velden dezelfde regel:
 *   1. tijdens het typen wordt er nooit een fout getoond;
 *   2. bij focus verlies kleurt een ingevuld maar ongeldig adres rood;
 *   3. zodra je corrigeert verdwijnt de melding meteen weer.
 *
 * De Toevoegen-knop blijft in alle velden onbeschikbaar tot het adres klopt.
 */

import { useState } from "react";

import type { Adres, EmailSelectieApi, Veld } from "../useEmailSelectie.js";

/**
 * De melding die getoond mag worden, of null.
 *
 * Volgt de regel hierboven: een leeg of nog niet verlaten veld meldt niets.
 * Wát er mis is bepaalt de hook — vorm of toegestaan domein.
 */
function foutmelding(
  waarde: string,
  aangeraakt: boolean,
  api: EmailSelectieApi,
): string | null {
  if (!aangeraakt || waarde.trim() === "") return null;
  return api.adresProbleem(waarde);
}

const VELD_BASIS =
  "min-w-0 flex-1 rounded border px-2 py-1 text-sm disabled:bg-slate-100 focus:outline-none focus:ring-2";
const VELD_GOED = "border-slate-300 focus:ring-miedema-goud";
const VELD_FOUT = "border-red-500 bg-red-50 focus:ring-red-400";

interface AdresRegelProps {
  veld: Veld;
  adres: Adres;
  bewerkbaar: boolean;
  api: EmailSelectieApi;
  uitgeschakeld: boolean;
}

function AdresRegel({
  veld,
  adres,
  bewerkbaar,
  api,
  uitgeschakeld,
}: AdresRegelProps) {
  const [aangeraakt, setAangeraakt] = useState(false);
  const melding =
    bewerkbaar && adres.actief
      ? foutmelding(adres.adres, aangeraakt, api)
      : null;
  const fout = melding !== null;

  return (
    <li>
      <div className="flex items-center gap-2">
        <input
          type="checkbox"
          id={adres.id}
          checked={adres.actief}
          disabled={uitgeschakeld}
          aria-label={`${adres.adres} meesturen`}
          onChange={() => api.wisselActief(veld, adres.id)}
          className="size-4 shrink-0 rounded border-slate-400 accent-miedema-goud disabled:opacity-50"
        />
        {bewerkbaar ? (
          <input
            type="email"
            value={adres.adres}
            disabled={uitgeschakeld}
            aria-label={`Adres ${adres.adres}`}
            aria-invalid={fout}
            onChange={(e) => {
              api.wijzigAdres(veld, adres.id, e.target.value);
              // Corrigeren mag de melding meteen laten verdwijnen.
              if (aangeraakt && api.adresProbleem(e.target.value) === null)
                setAangeraakt(false);
            }}
            onBlur={() => setAangeraakt(true)}
            className={`${VELD_BASIS} ${fout ? VELD_FOUT : VELD_GOED} ${
              adres.actief ? "" : "text-slate-400 line-through"
            }`}
          />
        ) : (
          <label
            htmlFor={adres.id}
            className={`min-w-0 flex-1 truncate text-sm ${
              adres.actief ? "text-slate-800" : "text-slate-400 line-through"
            }`}
          >
            {adres.adres}
          </label>
        )}
        {adres.bron === "extra" && (
          <button
            type="button"
            disabled={uitgeschakeld}
            onClick={() => api.verwijder(veld, adres.id)}
            aria-label={`${adres.adres} verwijderen`}
            className="shrink-0 rounded px-2 text-sm text-slate-500 hover:bg-red-50 hover:text-red-600 disabled:opacity-50"
          >
            ×
          </button>
        )}
      </div>
      {melding && <p className="mt-1 ml-6 text-xs text-red-600">{melding}</p>}
    </li>
  );
}

interface EmailVeldProps {
  veld: Veld;
  label: string;
  toelichting?: string;
  /** Alleen het Aan-veld is vrij aanpasbaar (bijv. naar een priveadres). */
  bewerkbaar?: boolean;
  /**
   * Toont het veld dichtgeklapt, om de modal kort te houden. Het aantal actieve
   * adressen staat wél in de kop, zodat je nooit ongemerkt iemand meestuurt.
   */
  inklapbaar?: boolean;
  api: EmailSelectieApi;
  uitgeschakeld: boolean;
}

export function EmailVeld({
  veld,
  label,
  toelichting,
  bewerkbaar = false,
  inklapbaar = false,
  api,
  uitgeschakeld,
}: EmailVeldProps) {
  const [nieuw, setNieuw] = useState("");
  const [aangeraakt, setAangeraakt] = useState(false);
  const adressen = api.selectie[veld];
  // Ook de allowlist telt hier mee: een adres buiten de toegestane domeinen
  // wordt door de server geweigerd, dus toevoegen heeft geen zin.
  const kanToevoegen = api.adresProbleem(nieuw) === null;
  const melding = foutmelding(nieuw, aangeraakt, api);
  const fout = melding !== null;
  const aantalActief = api.actieveSelectie[veld].length;

  const voegToe = () => {
    if (!kanToevoegen) return;
    api.voegToe(veld, nieuw);
    setNieuw("");
    setAangeraakt(false);
  };

  const kop = (
    <>
      {label}
      <span className="ml-2 font-normal text-slate-500">
        {aantalActief} actief
      </span>
    </>
  );

  const inhoud = (
    <>
      {toelichting && (
        <p className="mb-2 text-xs text-slate-500">{toelichting}</p>
      )}

      {adressen.length === 0 ? (
        <p className="mb-2 text-sm text-slate-400 italic">
          Geen adressen ingesteld.
        </p>
      ) : (
        <ul className="mb-2 space-y-1.5">
          {adressen.map((adres) => (
            <AdresRegel
              key={adres.id}
              veld={veld}
              adres={adres}
              bewerkbaar={bewerkbaar}
              api={api}
              uitgeschakeld={uitgeschakeld}
            />
          ))}
        </ul>
      )}

      <div className="flex gap-2">
        <input
          type="email"
          value={nieuw}
          disabled={uitgeschakeld}
          placeholder="extra adres toevoegen…"
          aria-label={`Extra adres toevoegen aan ${label}`}
          aria-invalid={fout}
          onChange={(e) => {
            setNieuw(e.target.value);
            if (aangeraakt && api.adresProbleem(e.target.value) === null)
              setAangeraakt(false);
          }}
          onBlur={() => setAangeraakt(true)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              // Enter op een ongeldig adres moet wél meteen de fout tonen.
              setAangeraakt(true);
              voegToe();
            }
          }}
          className={`${VELD_BASIS} ${fout ? VELD_FOUT : VELD_GOED}`}
        />
        <button
          type="button"
          onClick={voegToe}
          disabled={!kanToevoegen || uitgeschakeld}
          className="shrink-0 rounded bg-slate-700 px-3 py-1 text-sm font-medium text-white hover:bg-slate-800 disabled:opacity-40"
        >
          Toevoegen
        </button>
      </div>
      {melding && <p className="mt-1 text-xs text-red-600">{melding}</p>}
    </>
  );

  if (inklapbaar) {
    return (
      <details className="rounded-lg border border-slate-200 bg-slate-50 [&[open]>summary]:mb-2">
        <summary className="cursor-pointer rounded-lg p-3 text-sm font-semibold text-slate-700 select-none hover:bg-slate-100">
          {kop}
        </summary>
        <div className="px-3 pb-3">{inhoud}</div>
      </details>
    );
  }

  return (
    <fieldset className="rounded-lg border border-slate-200 bg-slate-50 p-3">
      <legend className="px-1 text-sm font-semibold text-slate-700">
        {kop}
      </legend>
      {inhoud}
    </fieldset>
  );
}
