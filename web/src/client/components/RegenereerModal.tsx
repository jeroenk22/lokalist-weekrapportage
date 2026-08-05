/** Modal om het rapport van een bestaande verzamelorder opnieuw te genereren. */

import { useCallback, useEffect, useRef, useState } from "react";

import { regenereer } from "../api.js";
import type {
  EmailInstellingen,
  RegenereerResultaat,
  Verzamelorder,
} from "../../shared/types.js";
import { NAAM_MAXLENGTE } from "../../shared/types.js";
import { useEmailSelectie } from "../useEmailSelectie.js";
import { EmailVeld } from "./EmailVeld.js";
import { Voortgang, type Regel } from "./Voortgang.js";

type Fase = "formulier" | "bevestigen" | "bezig" | "klaar" | "fout";

/**
 * Stap 3 maakt de nieuwe verzamelorder aan.
 *
 * Let op de timing: web_runner.py meldt stap 3 vóór de SOAP-create en start het
 * rollback-vangnet pas ná een geslaagde create. "Laatste stap = 3" betekent dus
 * dat het aanmaken zelf is mislukt — er is niets aangemaakt en er is geen
 * rollback geprobeerd. Pas vanaf stap 4 staat vast dat er een order is.
 */
const STAP_ORDER_AANMAKEN = 3;

/** Stap 7 verwijdert de oude order; alles daarvóór is dan al gelukt. */
const STAP_OUDE_VERWIJDEREN = 7;

/**
 * Wat er met de orders in MendriX gebeurd is, afgeleid van de laatst bereikte stap.
 *
 * Eén vaste zin volstaat hier niet. Faalt stap 7, dan is het rapport juist wél
 * volledig verwerkt en verstuurd, en is alleen het opruimen van de oude order
 * blijven liggen. De melding "de oorspronkelijke verzamelorder is niet
 * verwijderd" zette in dat geval aan tot nog een run — en dus tot een derde
 * order voor dezelfde week.
 */
export function foutToelichting(stap: number, oudeOrderId: number): string {
  if (stap >= STAP_OUDE_VERWIJDEREN) {
    return (
      `Let op: het nieuwe rapport is wél volledig aangemaakt, in het dossier gezet en ` +
      `verstuurd. Alleen het verwijderen van de oude verzamelorder ${oudeOrderId} is ` +
      `mislukt. Verwijder die handmatig in MendriX — start dit rapport niet nog een ` +
      `keer opnieuw, dan ontstaat er een derde order voor dezelfde week.`
    );
  }
  if (stap > STAP_ORDER_AANMAKEN) {
    return (
      `De zojuist aangemaakte order is teruggedraaid en verzamelorder ${oudeOrderId} ` +
      `bestaat nog. Controleer in het logbestand of het terugdraaien gelukt is voordat ` +
      `je het opnieuw probeert.`
    );
  }
  if (stap === STAP_ORDER_AANMAKEN) {
    // Bewust voorzichtiger geformuleerd dan de andere takken: meestal is er
    // niets aangemaakt, maar als het antwoord van MendriX onderweg wegviel kan
    // de order er tóch zijn — en dan is er geen rollback geweest.
    return (
      `Het aanmaken van de nieuwe verzamelorder is mislukt en verzamelorder ` +
      `${oudeOrderId} bestaat nog. Meestal is er dan niets aangemaakt en kun je het ` +
      `gewoon opnieuw proberen; controleer eerst in het logbestand of er toch een ` +
      `nieuw ordernummer is teruggekomen.`
    );
  }
  return (
    `Er is nog niets in MendriX aangemaakt of verwijderd; verzamelorder ` +
    `${oudeOrderId} staat er ongewijzigd. Je kunt het gewoon opnieuw proberen.`
  );
}

interface RegenereerModalProps {
  order: Verzamelorder;
  emailInstellingen: EmailInstellingen;
  onSluit: () => void;
  /** Wordt aangeroepen zodra de run geslaagd is, zodat het dashboard herlaadt. */
  onGeslaagd: () => void;
}

export function RegenereerModal({
  order,
  emailInstellingen,
  onSluit,
  onGeslaagd,
}: RegenereerModalProps) {
  const [fase, setFase] = useState<Fase>("formulier");
  const [regels, setRegels] = useState<Regel[]>([]);
  const [stap, setStap] = useState(0);
  const [fout, setFout] = useState<string | null>(null);
  const [resultaat, setResultaat] = useState<RegenereerResultaat | null>(null);
  const regelTeller = useRef(0);
  const dialoogRef = useRef<HTMLDivElement>(null);

  const [naam, setNaam] = useState("");
  const email = useEmailSelectie(emailInstellingen);
  const bezig = fase === "bezig";

  const voegRegelToe = useCallback((soort: Regel["soort"], tekst: string) => {
    setRegels((vorig) => [
      ...vorig,
      { id: ++regelTeller.current, soort, tekst },
    ]);
  }, []);

  // Escape sluit de modal, behalve tijdens een lopende run.
  useEffect(() => {
    const opToets = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !bezig) onSluit();
    };
    document.addEventListener("keydown", opToets);
    dialoogRef.current?.focus();
    return () => document.removeEventListener("keydown", opToets);
  }, [bezig, onSluit]);

  // Kleine drempel bij het sluiten van het tabblad tijdens een run.
  //
  // Er gaat hierdoor niets meer verloren: de server breekt de run niet af als
  // de verbinding wegvalt, dus MendriX komt hoe dan ook goed en handmatig_*.log
  // legt de afloop vast. Je verliest alleen zicht op het resultaat, en dat is
  // bij een order aanmaken plus mailen genoeg reden voor een bevestiging.
  //
  // De tekst is niet aan te passen: browsers negeren een eigen bericht en tonen
  // hun eigen standaardzin.
  useEffect(() => {
    if (!bezig) return;
    const waarschuw = (e: BeforeUnloadEvent) => e.preventDefault();
    window.addEventListener("beforeunload", waarschuw);
    return () => window.removeEventListener("beforeunload", waarschuw);
  }, [bezig]);

  const start = async () => {
    setFase("bezig");
    setRegels([]);
    setStap(0);
    setFout(null);
    regelTeller.current = 0;

    try {
      const uitkomst = await regenereer({
        orderId: order.orderId,
        email: email.actieveSelectie,
        naam: naam.trim(),
        onGebeurtenis: (gebeurtenis) => {
          switch (gebeurtenis.type) {
            case "stap":
              setStap(gebeurtenis.nummer);
              voegRegelToe("stap", gebeurtenis.bericht);
              break;
            case "log":
              voegRegelToe(
                gebeurtenis.niveau === "info" ? "info" : gebeurtenis.niveau,
                gebeurtenis.bericht,
              );
              break;
            case "fout":
              voegRegelToe("error", gebeurtenis.bericht);
              break;
            default:
              break;
          }
        },
      });
      setResultaat(uitkomst);
      setStap(7);
      setFase("klaar");
      // Dashboard direct verversen zodat de nieuwe order zichtbaar is.
      onGeslaagd();
    } catch (err) {
      setFout(err instanceof Error ? err.message : "Onbekende fout.");
      setFase("fout");
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-slate-900/50 p-4 sm:items-center"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget && !bezig) onSluit();
      }}
    >
      <div
        ref={dialoogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="modal-titel"
        tabIndex={-1}
        className="w-full max-w-2xl rounded-xl bg-white shadow-2xl outline-none"
      >
        <header className="flex items-start justify-between border-b border-slate-200 px-6 py-4">
          <div>
            <h2
              id="modal-titel"
              className="text-lg font-semibold text-slate-900"
            >
              Rapport opnieuw genereren
            </h2>
            <p className="mt-0.5 text-sm text-slate-600">
              Order {order.orderId} — week {order.weeknummer} {order.jaar}
            </p>
          </div>
          <button
            type="button"
            onClick={onSluit}
            disabled={bezig}
            aria-label="Sluiten"
            className="rounded p-1 text-2xl leading-none text-slate-400 hover:bg-slate-100 hover:text-slate-700 disabled:opacity-30"
          >
            ×
          </button>
        </header>

        <div className="max-h-[65vh] overflow-y-auto px-6 py-4">
          {fase === "formulier" && (
            <FormulierInhoud
              order={order}
              email={email}
              naam={naam}
              setNaam={setNaam}
            />
          )}

          {fase === "bevestigen" && (
            <BevestigInhoud order={order} email={email} />
          )}

          {(fase === "bezig" || fase === "klaar" || fase === "fout") && (
            <div className="space-y-4">
              <Voortgang stap={stap} regels={regels} />

              {fase === "klaar" && resultaat && (
                <div className="rounded-lg border border-green-300 bg-green-50 p-4 text-sm">
                  <p className="font-semibold text-green-900">
                    Klaar — alles is verwerkt.
                  </p>
                  <ul className="mt-2 space-y-0.5 text-green-900">
                    <li>Nieuwe verzamelorder: {resultaat.nieuweOrderId}</li>
                    <li>
                      Oude verzamelorder {resultaat.oudeOrderId} is verwijderd.
                    </li>
                    <li>
                      {resultaat.colli} colli — €{resultaat.bedrag.toFixed(2)}
                    </li>
                  </ul>
                </div>
              )}

              {fase === "fout" && (
                <div className="rounded-lg border border-red-300 bg-red-50 p-4 text-sm">
                  <p className="font-semibold text-red-900">Er ging iets mis</p>
                  <p className="mt-1 text-red-800">{fout}</p>
                  <p className="mt-2 text-xs text-red-700">
                    {foutToelichting(stap, order.orderId)}
                  </p>
                  <p className="mt-1 text-xs text-red-700">
                    Het logbestand in de map <code>logs/</code> bevat de
                    volledige melding.
                  </p>
                </div>
              )}
            </div>
          )}
        </div>

        <footer className="flex flex-wrap justify-end gap-2 border-t border-slate-200 px-6 py-4">
          {fase === "formulier" && (
            <>
              <button
                type="button"
                onClick={onSluit}
                className="rounded-lg px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100"
              >
                Annuleren
              </button>
              <button
                type="button"
                onClick={() => setFase("bevestigen")}
                disabled={!email.magVerder || naam.trim() === ""}
                className="rounded-lg bg-miedema-goud px-4 py-2 text-sm font-semibold text-white hover:brightness-95 disabled:opacity-40"
              >
                Verder
              </button>
            </>
          )}

          {fase === "bevestigen" && (
            <>
              <button
                type="button"
                onClick={() => setFase("formulier")}
                className="rounded-lg px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100"
              >
                Terug
              </button>
              <button
                type="button"
                onClick={start}
                className="rounded-lg bg-red-600 px-4 py-2 text-sm font-semibold text-white hover:bg-red-700"
              >
                Ja, verwijderen en opnieuw genereren
              </button>
            </>
          )}

          {fase === "bezig" && (
            <p className="text-sm text-slate-500">
              Bezig — dit venster niet sluiten…
            </p>
          )}

          {(fase === "klaar" || fase === "fout") && (
            <button
              type="button"
              onClick={onSluit}
              className="rounded-lg bg-slate-800 px-4 py-2 text-sm font-semibold text-white hover:bg-slate-900"
            >
              Sluiten
            </button>
          )}
        </footer>
      </div>
    </div>
  );
}

/* -------------------------------------------------------------------------- */

/** Verplicht naamveld; volgt dezelfde validatieregel als de e-mailvelden:
 *  geen melding tijdens typen, wel na focus verlies. */
function NaamVeld({
  naam,
  setNaam,
}: {
  naam: string;
  setNaam: (waarde: string) => void;
}) {
  const [aangeraakt, setAangeraakt] = useState(false);
  const fout = aangeraakt && naam.trim() === "";

  return (
    <div>
      <label
        htmlFor="naam-veld"
        className="text-sm font-semibold text-slate-800"
      >
        Wie genereert dit rapport opnieuw?{" "}
        <span aria-hidden="true" className="text-red-600">
          *
        </span>
      </label>
      <input
        id="naam-veld"
        type="text"
        value={naam}
        maxLength={NAAM_MAXLENGTE}
        required
        autoComplete="name"
        placeholder="je voornaam"
        aria-invalid={fout}
        onChange={(e) => {
          setNaam(e.target.value);
          if (aangeraakt && e.target.value.trim() !== "") setAangeraakt(false);
        }}
        onBlur={() => setAangeraakt(true)}
        className={`mt-1 w-full rounded border px-2 py-1.5 text-sm focus:ring-2 focus:outline-none ${
          fout
            ? "border-red-500 bg-red-50 focus:ring-red-400"
            : "border-slate-300 focus:ring-miedema-goud"
        }`}
      />
      {fout ? (
        <p className="mt-1 text-xs text-red-600">Vul je naam in.</p>
      ) : (
        <p className="mt-1 text-xs text-slate-500">
          Wordt vastgelegd in de order, zodat later terug te vinden is wie het
          rapport opnieuw heeft gedraaid.
        </p>
      )}
    </div>
  );
}

function FormulierInhoud({
  order,
  email,
  naam,
  setNaam,
}: {
  order: Verzamelorder;
  email: ReturnType<typeof useEmailSelectie>;
  naam: string;
  setNaam: (waarde: string) => void;
}) {
  return (
    <div className="space-y-4">
      <dl className="grid grid-cols-2 gap-x-4 gap-y-1 rounded-lg bg-slate-50 p-3 text-sm">
        <dt className="text-slate-500">Aangemaakt</dt>
        <dd className="text-slate-900">{order.label}</dd>
        <dt className="text-slate-500">Colli</dt>
        <dd className="text-slate-900">{order.totaalColli}</dd>
        <dt className="text-slate-500">Bedrag</dt>
        <dd className="text-slate-900">€{order.totaalBedrag.toFixed(2)}</dd>
      </dl>

      <div>
        <h3 className="mb-2 text-sm font-semibold text-slate-800">
          Ontvangers
        </h3>
        {/* De toegestane ontvangers worden hier bewust NIET opgesomd: in die
            lijst kunnen privéadressen staan, en het dashboard is voor iedereen
            op het interne netwerk zichtbaar. */}
        <p className="mb-3 text-xs text-slate-500">
          Vink adressen uit om ze over te slaan, of voeg extra adressen toe. Het
          Aan-adres kun je aanpassen, bijvoorbeeld naar je eigen adres om eerst
          te testen.
        </p>
        <div className="space-y-3">
          {/* Geen aparte toelichting: de alinea hierboven zegt al dat het
              Aan-adres aanpasbaar is, en welk adres mag hangt van de allowlist
              af — dat weet het veld zelf, niet een vaste tekst. */}
          <EmailVeld
            veld="to"
            label="Aan"
            bewerkbaar
            api={email}
            uitgeschakeld={false}
          />
          <EmailVeld veld="cc" label="CC" api={email} uitgeschakeld={false} />
          {/* BCC wordt zelden gebruikt; dichtgeklapt houdt de modal kort. */}
          <EmailVeld
            veld="bcc"
            label="BCC"
            inklapbaar
            api={email}
            uitgeschakeld={false}
          />
        </div>
      </div>

      <NaamVeld naam={naam} setNaam={setNaam} />

      {email.probleem && (
        <p className="rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">
          {email.probleem}
        </p>
      )}
    </div>
  );
}

function BevestigInhoud({
  order,
  email,
}: {
  order: Verzamelorder;
  email: ReturnType<typeof useEmailSelectie>;
}) {
  const { to, cc, bcc } = email.actieveSelectie;

  return (
    <div className="space-y-4">
      <div className="rounded-lg border border-red-300 bg-red-50 p-4">
        <h3 className="font-semibold text-red-900">Weet je het zeker?</h3>
        <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-red-900">
          <li>
            Verzamelorder <strong>{order.orderId}</strong> ({order.label}) wordt{" "}
            <strong>verwijderd</strong> uit MendriX.
          </li>
          <li>
            Er wordt een nieuwe verzamelorder aangemaakt voor week{" "}
            {order.weeknummer} {order.jaar}, met PDF en ordernummers in het
            dossier.
          </li>
          <li>
            In de notities komt te staan dat het rapport handmatig is
            hergenereerd.
          </li>
          <li>
            Het rapport wordt per e-mail verstuurd naar onderstaande adressen.
          </li>
        </ul>
        <p className="mt-3 text-xs text-red-800">
          De nieuwe order wordt eerst volledig aangemaakt. Pas als dat lukt,
          wordt de oude verwijderd — gaat er iets mis, dan blijft de huidige
          order gewoon bestaan.
        </p>
      </div>

      <dl className="space-y-2 rounded-lg border border-slate-200 p-3 text-sm">
        <div>
          <dt className="font-semibold text-slate-700">Aan</dt>
          <dd className="text-slate-800">{to.join(", ")}</dd>
        </div>
        {cc.length > 0 && (
          <div>
            <dt className="font-semibold text-slate-700">CC</dt>
            <dd className="text-slate-800">{cc.join(", ")}</dd>
          </div>
        )}
        {bcc.length > 0 && (
          <div>
            <dt className="font-semibold text-slate-700">BCC</dt>
            <dd className="text-slate-800">{bcc.join(", ")}</dd>
          </div>
        )}
        {cc.length === 0 && bcc.length === 0 && (
          <p className="text-xs text-slate-500">
            Geen CC- of BCC-ontvangers geselecteerd.
          </p>
        )}
      </dl>
    </div>
  );
}
