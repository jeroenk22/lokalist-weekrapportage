/** Tests voor de regenereer-modal: bevestiging, ontvangers en afronding. */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { EmailInstellingen, Verzamelorder } from "../src/shared/types.js";

const regenereer = vi.fn();
vi.mock("../src/client/api.js", () => ({
  regenereer: (...args: unknown[]) => regenereer(...args),
}));

const { RegenereerModal } =
  await import("../src/client/components/RegenereerModal.js");

const ORDER: Verzamelorder = {
  orderId: 1266289,
  aangemaakt: "2026-08-02T23:30:04",
  weeknummer: 31,
  jaar: 2026,
  handmatig: false,
  notities: "",
  totaalColli: 32,
  totaalBedrag: 238.13,
  label: "zondag 02 augustus 2026 (automatisch)",
  hergenereerdDoor: null,
  herkomstTekst: null,
  gefactureerd: false,
  factuurNummer: null,
  factuurSleutel: null,
  factuurVoorlopig: false,
  factuurKopieerwaarde: null,
  factuurOmschrijving: null,
};

const EMAIL: EmailInstellingen = {
  to: ["info@lokalist.nl"],
  cc: ["planning@ophaaldienstmiedema.nl"],
  bcc: ["jeroenkrajenbrink@gmail.com"],
  uitgevinkt: [],
  afzender: "miedemaophaaldienst@gmail.com",
  provider: "smtp",
};

function toon(props: Partial<Parameters<typeof RegenereerModal>[0]> = {}) {
  const onSluit = vi.fn();
  const onGeslaagd = vi.fn();
  render(
    <RegenereerModal
      order={ORDER}
      emailInstellingen={EMAIL}
      onSluit={onSluit}
      onGeslaagd={onGeslaagd}
      {...props}
    />,
  );
  return { onSluit, onGeslaagd };
}

/** Vult het verplichte naamveld; zonder naam blijft Verder uit. */
async function vulNaamIn(
  gebruiker: ReturnType<typeof userEvent.setup>,
  naam = "Jeroen",
) {
  await gebruiker.type(
    screen.getByLabelText(/Wie genereert dit rapport/i),
    naam,
  );
}

beforeEach(() => {
  regenereer.mockReset();
  regenereer.mockResolvedValue({
    dryRun: false,
    oudeOrderId: 1266289,
    nieuweOrderId: 1266400,
    weeknummer: 31,
    jaar: 2026,
    pdf: "output/lokalist_week31_2026.pdf",
    colli: 32,
    bedrag: 238.13,
    notitie: "[HANDMATIG HERGENEREERD] …",
  });
});

describe("RegenereerModal", () => {
  it("toont de ordergegevens en de standaardontvangers", () => {
    toon();

    expect(screen.getByText(/Order 1266289/)).toBeInTheDocument();
    expect(
      screen.getByText("zondag 02 augustus 2026 (automatisch)"),
    ).toBeInTheDocument();
    expect(screen.getByDisplayValue("info@lokalist.nl")).toBeInTheDocument();
    expect(
      screen.getByText("planning@ophaaldienstmiedema.nl"),
    ).toBeInTheDocument();
  });

  it("genereert niet zonder bevestigingsstap", async () => {
    const gebruiker = userEvent.setup();
    toon();

    await vulNaamIn(gebruiker);

    await gebruiker.click(screen.getByRole("button", { name: "Verder" }));

    // Nu staat de bevestiging in beeld, maar er is nog niets gestart.
    expect(screen.getByText("Weet je het zeker?")).toBeInTheDocument();
    expect(regenereer).not.toHaveBeenCalled();
  });

  it("waarschuwt expliciet dat de oude order verwijderd wordt", async () => {
    const gebruiker = userEvent.setup();
    toon();

    await vulNaamIn(gebruiker);

    await gebruiker.click(screen.getByRole("button", { name: "Verder" }));

    const waarschuwing = screen.getByRole("heading", {
      name: "Weet je het zeker?",
    }).parentElement!;
    expect(waarschuwing).toHaveTextContent(/Verzamelorder\s+1266289/);
    expect(waarschuwing).toHaveTextContent(/wordt\s+verwijderd\s+uit MendriX/);
    expect(waarschuwing).toHaveTextContent(/handmatig is hergenereerd/);
  });

  it("start pas na bevestiging en ververst daarna het dashboard", async () => {
    const gebruiker = userEvent.setup();
    const { onGeslaagd } = toon();

    await vulNaamIn(gebruiker);

    await gebruiker.click(screen.getByRole("button", { name: "Verder" }));
    await gebruiker.click(
      screen.getByRole("button", {
        name: /Ja, verwijderen en opnieuw genereren/,
      }),
    );

    await waitFor(() => expect(regenereer).toHaveBeenCalledTimes(1));
    expect(regenereer.mock.calls[0]![0]).toMatchObject({
      orderId: 1266289,
      email: {
        to: ["info@lokalist.nl"],
        cc: ["planning@ophaaldienstmiedema.nl"],
        bcc: ["jeroenkrajenbrink@gmail.com"],
      },
    });
    await waitFor(() => expect(onGeslaagd).toHaveBeenCalledTimes(1));
    expect(
      await screen.findByText(/Klaar — alles is verwerkt/),
    ).toBeInTheDocument();
  });

  it("stuurt uitgevinkte adressen niet mee", async () => {
    const gebruiker = userEvent.setup();
    toon();

    await gebruiker.click(
      screen.getByLabelText(/planning@ophaaldienstmiedema.nl/i),
    );
    await vulNaamIn(gebruiker);
    await gebruiker.click(screen.getByRole("button", { name: "Verder" }));
    await gebruiker.click(
      screen.getByRole("button", {
        name: /Ja, verwijderen en opnieuw genereren/,
      }),
    );

    await waitFor(() => expect(regenereer).toHaveBeenCalled());
    expect(regenereer.mock.calls[0]![0].email.cc).toEqual([]);
  });

  it("meldt tijdens het typen niets in de balk onderin", async () => {
    // Eerder verscheen hier per toetsaanslag "Ongeldig e-mailadres: jeroen",
    // terwijl het veld zelf pas bij focus verlies reageerde. Nu meldt alleen
    // het veld het, en pas na focus verlies.
    const gebruiker = userEvent.setup();
    toon();

    const invoer = screen.getByDisplayValue("info@lokalist.nl");
    await gebruiker.clear(invoer);
    await gebruiker.type(invoer, "jeroen");

    expect(screen.queryByText(/Ongeldig e-mailadres/i)).not.toBeInTheDocument();
    expect(
      screen.queryByText(/geen geldig e-mailadres/i),
    ).not.toBeInTheDocument();
    // Doorgaan kan wel al niet, want het adres klopt niet.
    expect(screen.getByRole("button", { name: "Verder" })).toBeDisabled();
  });

  it("meldt na focus verlies alleen bij het veld zelf", async () => {
    const gebruiker = userEvent.setup();
    toon();

    const invoer = screen.getByDisplayValue("info@lokalist.nl");
    await gebruiker.clear(invoer);
    await gebruiker.type(invoer, "jeroen");
    await gebruiker.tab();

    expect(screen.getByText(/geen geldig e-mailadres/i)).toBeInTheDocument();
    // Geen tweede melding met dezelfde strekking in de balk.
    expect(
      screen.queryByText(/Ongeldig e-mailadres:/i),
    ).not.toBeInTheDocument();
  });

  describe("verplichte naam", () => {
    it("houdt Verder uit zolang er geen naam staat", () => {
      toon();

      expect(screen.getByLabelText(/Wie genereert dit rapport/i)).toHaveValue(
        "",
      );
      expect(screen.getByRole("button", { name: "Verder" })).toBeDisabled();
    });

    it("meldt pas na focus verlies dat de naam ontbreekt", async () => {
      const gebruiker = userEvent.setup();
      toon();

      const veld = screen.getByLabelText(/Wie genereert dit rapport/i);
      await gebruiker.click(veld);
      expect(screen.queryByText("Vul je naam in.")).not.toBeInTheDocument();

      await gebruiker.tab();
      expect(screen.getByText("Vul je naam in.")).toBeInTheDocument();
    });

    it("laat de melding verdwijnen zodra je typt", async () => {
      const gebruiker = userEvent.setup();
      toon();

      const veld = screen.getByLabelText(/Wie genereert dit rapport/i);
      await gebruiker.click(veld);
      await gebruiker.tab();
      expect(screen.getByText("Vul je naam in.")).toBeInTheDocument();

      await gebruiker.type(veld, "Jeroen");
      expect(screen.queryByText("Vul je naam in.")).not.toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Verder" })).toBeEnabled();
    });

    it("stuurt de naam mee naar de server", async () => {
      const gebruiker = userEvent.setup();
      toon();

      await vulNaamIn(gebruiker, "Christiaan van der Meulen-Bergsma");
      await gebruiker.click(screen.getByRole("button", { name: "Verder" }));
      await gebruiker.click(
        screen.getByRole("button", {
          name: /Ja, verwijderen en opnieuw genereren/,
        }),
      );

      await waitFor(() => expect(regenereer).toHaveBeenCalled());
      expect(regenereer.mock.calls[0]![0].naam).toBe(
        "Christiaan van der Meulen-Bergsma",
      );
    });

    it("stuurt de naam zonder omringende spaties mee", async () => {
      const gebruiker = userEvent.setup();
      toon();

      await vulNaamIn(gebruiker, "  Jeroen  ");
      await gebruiker.click(screen.getByRole("button", { name: "Verder" }));
      await gebruiker.click(
        screen.getByRole("button", {
          name: /Ja, verwijderen en opnieuw genereren/,
        }),
      );

      await waitFor(() => expect(regenereer).toHaveBeenCalled());
      expect(regenereer.mock.calls[0]![0].naam).toBe("Jeroen");
    });
  });

  it("blokkeert Verder als er geen Aan-adres over is", async () => {
    const gebruiker = userEvent.setup();
    toon();

    await gebruiker.click(
      screen.getByRole("checkbox", { name: /info@lokalist.nl meesturen/i }),
    );

    expect(screen.getByRole("button", { name: "Verder" })).toBeDisabled();
    expect(screen.getByText(/minstens één Aan-adres/i)).toBeInTheDocument();
  });

  it("toont de foutmelding en meldt dat de oude order blijft bestaan", async () => {
    const gebruiker = userEvent.setup();
    regenereer.mockRejectedValue(new Error("SOAP-fout: verbinding geweigerd"));
    const { onGeslaagd } = toon();

    await vulNaamIn(gebruiker);

    await gebruiker.click(screen.getByRole("button", { name: "Verder" }));
    await gebruiker.click(
      screen.getByRole("button", {
        name: /Ja, verwijderen en opnieuw genereren/,
      }),
    );

    expect(
      await screen.findByText("SOAP-fout: verbinding geweigerd"),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/oorspronkelijke verzamelorder is niet verwijderd/i),
    ).toBeInTheDocument();
    expect(onGeslaagd).not.toHaveBeenCalled();
  });
});
