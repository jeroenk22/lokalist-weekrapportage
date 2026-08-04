/** Tests voor de validatie in de ontvangervelden.
 *
 * Het gaat er hier vooral om dat Aan, CC en BCC zich identiek gedragen — dat
 * was eerder niet zo: alleen Aan gaf feedback, en meteen per toetsaanslag.
 */

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { useEmailSelectie } from "../src/client/useEmailSelectie.js";
import { EmailVeld } from "../src/client/components/EmailVeld.js";
import type { EmailInstellingen } from "../src/shared/types.js";
import type { Veld } from "../src/client/useEmailSelectie.js";

const INSTELLINGEN: EmailInstellingen = {
  to: ["info@lokalist.nl"],
  cc: ["facturen@ophaaldienstmiedema.nl"],
  bcc: ["tomas@ophaaldienstmiedema.nl"],
  uitgevinkt: [],
  domeinen: [],
  afzender: "miedemaophaaldienst@gmail.com",
  provider: "smtp",
};

function Proef({
  veld,
  bewerkbaar = false,
}: {
  veld: Veld;
  bewerkbaar?: boolean;
}) {
  const api = useEmailSelectie(INSTELLINGEN);
  return (
    <EmailVeld
      veld={veld}
      label={veld.toUpperCase()}
      bewerkbaar={bewerkbaar}
      api={api}
      uitgeschakeld={false}
    />
  );
}

const VELDEN: Veld[] = ["to", "cc", "bcc"];

describe("EmailVeld — validatie is in alle velden gelijk", () => {
  it.each(VELDEN)("toont in %s geen fout tijdens het typen", async (veld) => {
    const gebruiker = userEvent.setup();
    render(<Proef veld={veld} />);

    await gebruiker.type(
      screen.getByLabelText(/Extra adres toevoegen/i),
      "half@adres",
    );

    expect(
      screen.queryByText(/geen geldig e-mailadres/i),
    ).not.toBeInTheDocument();
  });

  it.each(VELDEN)("toont in %s wel een fout na focus verlies", async (veld) => {
    const gebruiker = userEvent.setup();
    render(<Proef veld={veld} />);

    const invoer = screen.getByLabelText(/Extra adres toevoegen/i);
    await gebruiker.type(invoer, "half@adres");
    await gebruiker.tab();

    expect(screen.getByText(/geen geldig e-mailadres/i)).toBeInTheDocument();
    expect(invoer).toHaveAttribute("aria-invalid", "true");
  });

  it.each(VELDEN)("meldt in %s niets bij een leeg veld", async (veld) => {
    const gebruiker = userEvent.setup();
    render(<Proef veld={veld} />);

    await gebruiker.click(screen.getByLabelText(/Extra adres toevoegen/i));
    await gebruiker.tab();

    expect(
      screen.queryByText(/geen geldig e-mailadres/i),
    ).not.toBeInTheDocument();
  });

  it.each(VELDEN)(
    "laat de fout in %s verdwijnen zodra je corrigeert",
    async (veld) => {
      const gebruiker = userEvent.setup();
      render(<Proef veld={veld} />);

      const invoer = screen.getByLabelText(/Extra adres toevoegen/i);
      await gebruiker.type(invoer, "half@adres");
      await gebruiker.tab();
      expect(screen.getByText(/geen geldig e-mailadres/i)).toBeInTheDocument();

      await gebruiker.click(invoer);
      await gebruiker.type(invoer, ".nl");

      expect(
        screen.queryByText(/geen geldig e-mailadres/i),
      ).not.toBeInTheDocument();
    },
  );

  it.each(VELDEN)(
    "houdt de Toevoegen-knop in %s uit tot het adres klopt",
    async (veld) => {
      const gebruiker = userEvent.setup();
      render(<Proef veld={veld} />);

      const knop = screen.getByRole("button", { name: "Toevoegen" });
      expect(knop).toBeDisabled();

      await gebruiker.type(
        screen.getByLabelText(/Extra adres toevoegen/i),
        "half@adres",
      );
      expect(knop).toBeDisabled();

      await gebruiker.type(
        screen.getByLabelText(/Extra adres toevoegen/i),
        ".nl",
      );
      expect(knop).toBeEnabled();
    },
  );

  it.each(VELDEN)(
    "toont in %s de fout direct bij Enter op een ongeldig adres",
    async (veld) => {
      const gebruiker = userEvent.setup();
      render(<Proef veld={veld} />);

      await gebruiker.type(
        screen.getByLabelText(/Extra adres toevoegen/i),
        "half@adres{Enter}",
      );

      expect(screen.getByText(/geen geldig e-mailadres/i)).toBeInTheDocument();
    },
  );

  it.each(VELDEN)(
    "voegt in %s een geldig adres toe met Enter",
    async (veld) => {
      const gebruiker = userEvent.setup();
      render(<Proef veld={veld} />);

      await gebruiker.type(
        screen.getByLabelText(/Extra adres toevoegen/i),
        "extra@voorbeeld.nl{Enter}",
      );

      expect(
        screen.getByLabelText(/extra@voorbeeld.nl meesturen/i),
      ).toBeChecked();
      expect(
        screen.queryByText(/geen geldig e-mailadres/i),
      ).not.toBeInTheDocument();
    },
  );
});

describe("EmailVeld — inklapbaar", () => {
  function ProefInklapbaar() {
    const api = useEmailSelectie(INSTELLINGEN);
    return (
      <EmailVeld
        veld="bcc"
        label="BCC"
        inklapbaar
        api={api}
        uitgeschakeld={false}
      />
    );
  }

  it("staat dichtgeklapt bij het openen", () => {
    render(<ProefInklapbaar />);
    expect(screen.getByRole("group")).not.toHaveAttribute("open");
  });

  it("toont het aantal actieve adressen ook als hij dicht is", () => {
    // Anders zou je ongemerkt iemand kunnen meesturen.
    render(<ProefInklapbaar />);
    expect(screen.getByText("1 actief")).toBeInTheDocument();
  });

  it("klapt open bij een klik op de kop", async () => {
    const gebruiker = userEvent.setup();
    render(<ProefInklapbaar />);

    await gebruiker.click(screen.getByText("BCC"));

    expect(screen.getByRole("group")).toHaveAttribute("open");
  });

  it("laat de adressen gewoon beheren zodra hij open is", async () => {
    const gebruiker = userEvent.setup();
    render(<ProefInklapbaar />);
    await gebruiker.click(screen.getByText("BCC"));

    await gebruiker.click(
      screen.getByLabelText(/tomas@ophaaldienstmiedema.nl meesturen/i),
    );

    expect(screen.getByText("0 actief")).toBeInTheDocument();
  });
});

describe("EmailVeld — bewerkbaar Aan-adres", () => {
  it("meldt pas bij focus verlies dat het adres ongeldig is", async () => {
    const gebruiker = userEvent.setup();
    render(<Proef veld="to" bewerkbaar />);

    const invoer = screen.getByLabelText(/Adres info@lokalist.nl/i);
    await gebruiker.clear(invoer);
    await gebruiker.type(invoer, "kapot");

    // Nog tijdens het typen: geen fout.
    expect(
      screen.queryByText(/geen geldig e-mailadres/i),
    ).not.toBeInTheDocument();

    await gebruiker.tab();
    expect(screen.getByText(/geen geldig e-mailadres/i)).toBeInTheDocument();
  });

  it("meldt niets over een adres dat je hebt uitgevinkt", async () => {
    const gebruiker = userEvent.setup();
    render(<Proef veld="to" bewerkbaar />);

    const invoer = screen.getByLabelText(/Adres info@lokalist.nl/i);
    await gebruiker.clear(invoer);
    await gebruiker.type(invoer, "kapot");
    await gebruiker.tab();
    expect(screen.getByText(/geen geldig e-mailadres/i)).toBeInTheDocument();

    await gebruiker.click(screen.getByLabelText(/kapot meesturen/i));

    expect(
      screen.queryByText(/geen geldig e-mailadres/i),
    ).not.toBeInTheDocument();
  });
});
