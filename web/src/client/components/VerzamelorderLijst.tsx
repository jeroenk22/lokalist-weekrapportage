/** Overzicht van alle verzamelorders in MendriX. */

import type { Verzamelorder } from "../../shared/types.js";
import { KopieerbaarNummer } from "./KopieerbaarNummer.js";

interface VerzamelorderLijstProps {
  orders: Verzamelorder[];
  onKies: (order: Verzamelorder) => void;
}

/** Wat je kopieert verschilt per soort factuur.
 *
 * Definitief → het factuurnummer (InvNo), waarmee je in MendriX gewoon zoekt.
 * Voorlopig  → de sleutel (InvKey); een nummer bestaat dan nog niet, dus zoeken
 *              gaat via Snelkiezen facturen met "Kies op sleutel".
 */
function FactuurBadge({ order }: { order: Verzamelorder }) {
  if (!order.gefactureerd || order.factuurKopieerwaarde === null) return null;

  const voorlopig = order.factuurVoorlopig;

  // De hele badge is de kopieerknop, niet alleen het nummer erin.
  const kleur = voorlopig
    ? "bg-factuur-voorlopig text-factuur-voorlopig-tekst hover:brightness-95"
    : "bg-factuur-definitief text-factuur-definitief-tekst hover:brightness-95";

  return (
    <KopieerbaarNummer
      waarde={order.factuurKopieerwaarde}
      omschrijving={voorlopig ? "Factuursleutel" : "Factuurnummer"}
      toelichting={
        voorlopig
          ? 'In MendriX zoeken met Ctrl+Shift+K en een vinkje bij "Kies op sleutel".'
          : undefined
      }
      className={`pointer-events-auto rounded-full px-2 py-0.5 text-xs font-medium ${kleur}`}
    >
      {voorlopig ? "voorlopige factuur" : "factuur"}{" "}
      <span className="font-semibold">{order.factuurKopieerwaarde}</span>
    </KopieerbaarNummer>
  );
}

function Rij({ order }: { order: Verzamelorder }) {
  return (
    <>
      <KopieerbaarNummer
        waarde={order.orderId}
        omschrijving="Ordernummer"
        className="pointer-events-auto -mx-1 rounded px-1 font-mono text-base font-semibold text-slate-900 hover:bg-slate-200/70"
      />

      <span className="text-sm text-slate-600">{order.label}</span>

      {/* Bij een handmatige run vertelt de tooltip wie hem gedraaid heeft en wanneer. */}
      <span
        title={order.herkomstTekst ?? undefined}
        className={`rounded-full px-2 py-0.5 text-xs font-medium ${
          order.handmatig
            ? "pointer-events-auto cursor-help bg-miedema-goud-licht text-miedema-goud"
            : "bg-lokalist-groen-licht text-lokalist-groen"
        }`}
      >
        {order.handmatig ? "handmatig" : "automatisch"}
      </span>

      <FactuurBadge order={order} />

      <span className="ml-auto flex items-center gap-4 text-sm text-slate-500">
        <span>
          week {order.weeknummer} · {order.jaar}
        </span>
        <span>{order.totaalColli} colli</span>
        <span className="font-medium text-slate-700">
          €{order.totaalBedrag.toFixed(2)}
        </span>
      </span>
    </>
  );
}

export function VerzamelorderLijst({
  orders,
  onKies,
}: VerzamelorderLijstProps) {
  if (orders.length === 0) {
    return (
      <p className="rounded-xl border border-slate-200 bg-white p-8 text-center text-slate-500">
        Geen verzamelorders gevonden in MendriX.
      </p>
    );
  }

  return (
    <ul className="space-y-2">
      {orders.map((order) => {
        const vergrendeld = order.gefactureerd;

        return (
          <li
            key={order.orderId}
            className={`relative rounded-xl border p-4 transition ${
              vergrendeld
                ? "border-slate-200 bg-slate-50"
                : "border-slate-200 bg-white hover:border-miedema-goud hover:shadow-md"
            }`}
          >
            {/* Stretched link: de hele rij is klikbaar zonder dat de kopieerknoppen
                in een knop genest raken — dat zou ongeldige HTML zijn. Deze knop
                ligt eronder; de inhoud erboven vangt zijn eigen klikken af. */}
            {!vergrendeld && (
              <button
                type="button"
                onClick={() => onKies(order)}
                className="absolute inset-0 z-0 cursor-pointer rounded-xl focus:ring-2 focus:ring-miedema-goud focus:outline-none"
              >
                <span className="sr-only">
                  Rapport van order {order.orderId} opnieuw genereren
                </span>
              </button>
            )}

            <div
              className={`pointer-events-none relative z-10 flex flex-wrap items-center gap-x-3 gap-y-1 ${
                vergrendeld ? "opacity-70" : ""
              }`}
            >
              <Rij order={order} />
            </div>

            {vergrendeld && (
              <div className="relative z-10 mt-1 space-y-0.5 text-xs text-slate-500">
                <p>
                  Vergrendeld — staat op een{" "}
                  {order.factuurVoorlopig
                    ? `voorlopige factuur (sleutel ${order.factuurSleutel})`
                    : `factuur (${order.factuurNummer})`}
                  . Neem contact op met de administratie als dit rapport toch
                  aangepast moet worden.
                </p>
                {order.factuurVoorlopig && (
                  <p className="text-amber-700">
                    Een voorlopige factuur heeft nog geen factuurnummer. Zoek
                    hem in MendriX op met{" "}
                    <kbd className="font-sans font-semibold">Ctrl</kbd>+
                    <kbd className="font-sans font-semibold">Shift</kbd>+
                    <kbd className="font-sans font-semibold">K</kbd> en zet een
                    vinkje bij “Kies op sleutel”.
                  </p>
                )}
              </div>
            )}
          </li>
        );
      })}
    </ul>
  );
}
