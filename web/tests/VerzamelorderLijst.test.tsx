/** Tests voor het overzicht: factuurgrendel, factuurnummer en kopieerknoppen. */

import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { Verzamelorder } from "../src/shared/types.js";
import { VerzamelorderLijst } from "../src/client/components/VerzamelorderLijst.js";

function maakOrder(overrides: Partial<Verzamelorder> = {}): Verzamelorder {
  return {
    orderId: 1267614,
    aangemaakt: "2026-08-04T12:07:39",
    weeknummer: 31,
    jaar: 2026,
    handmatig: true,
    notities: "",
    totaalColli: 32,
    totaalBedrag: 238.13,
    label: "dinsdag 04 augustus 2026 (handmatig)",
    hergenereerdDoor: null,
    herkomstTekst: null,
    gefactureerd: false,
    factuurNummer: null,
    factuurSleutel: null,
    factuurVoorlopig: false,
    factuurKopieerwaarde: null,
    factuurOmschrijving: null,
    ...overrides,
  };
}

/** Definitief gefactureerd, met een echt factuurnummer. */
const metFactuur = maakOrder({
  orderId: 1246311,
  gefactureerd: true,
  factuurNummer: 31511432,
  factuurSleutel: 154055,
  factuurVoorlopig: false,
  factuurKopieerwaarde: 31511432,
  factuurOmschrijving: "factuur 31511432",
  handmatig: false,
  label: "dinsdag 23 juni 2026 (automatisch)",
  hergenereerdDoor: null,
  herkomstTekst: null,
});

/** Wel op een factuurrun, maar nog zonder definitief nummer.
 *  Kopiëren geeft dan de sleutel (InvKey), want een nummer bestaat nog niet. */
const voorlopigeFactuur = maakOrder({
  orderId: 1262688,
  gefactureerd: true,
  factuurNummer: null,
  factuurSleutel: 154793,
  factuurVoorlopig: true,
  factuurKopieerwaarde: 154793,
  factuurOmschrijving: "voorlopige factuur 154793",
  handmatig: false,
  label: "zondag 26 juli 2026 (automatisch)",
  hergenereerdDoor: null,
  herkomstTekst: null,
});

beforeEach(() => {
  document.execCommand = vi.fn(() => true);
  Object.defineProperty(navigator, "clipboard", {
    value: undefined,
    configurable: true,
    writable: true,
  });
});

describe("VerzamelorderLijst", () => {
  it("toont een melding als er geen orders zijn", () => {
    render(<VerzamelorderLijst orders={[]} onKies={vi.fn()} />);
    expect(
      screen.getByText(/Geen verzamelorders gevonden/),
    ).toBeInTheDocument();
  });

  it("toont het aanmaakmoment achter het ordernummer", () => {
    render(<VerzamelorderLijst orders={[maakOrder()]} onKies={vi.fn()} />);

    expect(screen.getByText("1267614")).toBeInTheDocument();
    expect(
      screen.getByText("dinsdag 04 augustus 2026 (handmatig)"),
    ).toBeInTheDocument();
  });

  it("onderscheidt handmatig en automatisch", () => {
    render(
      <VerzamelorderLijst
        orders={[
          maakOrder({ orderId: 1, handmatig: true }),
          maakOrder({ orderId: 2 }),
        ]}
        onKies={vi.fn()}
      />,
    );

    expect(screen.getAllByText("handmatig").length).toBeGreaterThan(0);
  });

  it("opent de modal bij een ongefactureerde order", async () => {
    const gebruiker = userEvent.setup();
    const onKies = vi.fn();
    render(<VerzamelorderLijst orders={[maakOrder()]} onKies={onKies} />);

    await gebruiker.click(
      screen.getByRole("button", { name: /opnieuw genereren/i }),
    );

    expect(onKies).toHaveBeenCalledTimes(1);
    expect(onKies.mock.calls[0]![0].orderId).toBe(1267614);
  });

  describe("wie heeft hergenereerd", () => {
    const doorJeroen = maakOrder({
      handmatig: true,
      hergenereerdDoor: "Jeroen",
      herkomstTekst: "Op dinsdag 04 augustus 12:07 hergenereerd door Jeroen",
    });

    it("toont de naam en het tijdstip in een tooltip op de badge", () => {
      render(<VerzamelorderLijst orders={[doorJeroen]} onKies={vi.fn()} />);

      expect(screen.getByText("handmatig")).toHaveAttribute(
        "title",
        "Op dinsdag 04 augustus 12:07 hergenereerd door Jeroen",
      );
    });

    it("meldt het als er geen naam is vastgelegd", () => {
      const zonderNaam = maakOrder({
        handmatig: true,
        hergenereerdDoor: null,
        herkomstTekst:
          "Op dinsdag 04 augustus 12:07 hergenereerd (naam niet vastgelegd)",
      });
      render(<VerzamelorderLijst orders={[zonderNaam]} onKies={vi.fn()} />);

      expect(screen.getByText("handmatig")).toHaveAttribute(
        "title",
        expect.stringContaining("naam niet vastgelegd"),
      );
    });

    it("geeft een automatische order geen tooltip", () => {
      render(
        <VerzamelorderLijst
          orders={[maakOrder({ handmatig: false })]}
          onKies={vi.fn()}
        />,
      );

      expect(screen.getByText("automatisch")).not.toHaveAttribute("title");
    });
  });

  describe("factuurnummer", () => {
    it("toont het echte factuurnummer, niet de interne sleutel", () => {
      render(<VerzamelorderLijst orders={[metFactuur]} onKies={vi.fn()} />);

      expect(screen.getByText("31511432")).toBeInTheDocument();
      // De interne InvKey (154055) hoort nergens te staan.
      expect(screen.queryByText(/154055/)).not.toBeInTheDocument();
    });

    it("toont 'voorlopige factuur' zolang er nog geen nummer is", () => {
      render(
        <VerzamelorderLijst orders={[voorlopigeFactuur]} onKies={vi.fn()} />,
      );

      expect(screen.getAllByText(/voorlopige factuur/).length).toBeGreaterThan(
        0,
      );
      // "concept" is bewust vervangen door "voorlopig" in de hele UI.
      expect(screen.queryByText(/concept/i)).not.toBeInTheDocument();
    });

    it("toont bij een voorlopige factuur de sleutel", () => {
      render(
        <VerzamelorderLijst orders={[voorlopigeFactuur]} onKies={vi.fn()} />,
      );

      expect(screen.getByText("154793")).toBeInTheDocument();
    });

    it("legt uit hoe je een voorlopige factuur in MendriX terugvindt", () => {
      render(
        <VerzamelorderLijst orders={[voorlopigeFactuur]} onKies={vi.fn()} />,
      );

      const hint = screen.getByText(/nog geen factuurnummer/);
      expect(hint).toHaveTextContent(/Ctrl\+Shift\+K/);
      expect(hint).toHaveTextContent(/Kies op sleutel/);
    });

    it("toont die uitleg niet bij een definitieve factuur", () => {
      render(<VerzamelorderLijst orders={[metFactuur]} onKies={vi.fn()} />);

      expect(screen.queryByText(/Ctrl\+Shift\+K/)).not.toBeInTheDocument();
    });
  });

  describe("kopiëren naar klembord", () => {
    it("kopieert het ordernummer bij een klik", async () => {
      const gebruiker = userEvent.setup();
      render(<VerzamelorderLijst orders={[maakOrder()]} onKies={vi.fn()} />);

      await gebruiker.click(
        screen.getByRole("button", { name: /Ordernummer 1267614 kopiëren/i }),
      );

      expect(document.execCommand).toHaveBeenCalledWith("copy");
      expect(await screen.findByText("Gekopieerd")).toBeInTheDocument();
    });

    it("kopieert het factuurnummer bij een klik", async () => {
      const gebruiker = userEvent.setup();
      render(<VerzamelorderLijst orders={[metFactuur]} onKies={vi.fn()} />);

      await gebruiker.click(
        screen.getByRole("button", {
          name: /Factuurnummer 31511432 kopiëren/i,
        }),
      );

      expect(document.execCommand).toHaveBeenCalledWith("copy");
      expect(await screen.findByText("Gekopieerd")).toBeInTheDocument();
    });

    it("opent de modal niet als je het ordernummer kopieert", async () => {
      const gebruiker = userEvent.setup();
      const onKies = vi.fn();
      render(<VerzamelorderLijst orders={[maakOrder()]} onKies={onKies} />);

      await gebruiker.click(
        screen.getByRole("button", { name: /Ordernummer 1267614 kopiëren/i }),
      );

      expect(onKies).not.toHaveBeenCalled();
    });

    it("meldt het als kopiëren niet lukt", async () => {
      const gebruiker = userEvent.setup();
      document.execCommand = vi.fn(() => false);
      render(<VerzamelorderLijst orders={[maakOrder()]} onKies={vi.fn()} />);

      await gebruiker.click(
        screen.getByRole("button", { name: /Ordernummer 1267614 kopiëren/i }),
      );

      expect(await screen.findByText("Niet gelukt")).toBeInTheDocument();
    });

    it("kopieert bij een voorlopige factuur de sleutel, niet een leeg nummer", async () => {
      const gebruiker = userEvent.setup();
      const geschreven: string[] = [];
      document.execCommand = vi.fn(() => {
        geschreven.push(
          (document.querySelector("textarea") as HTMLTextAreaElement | null)
            ?.value ?? "",
        );
        return true;
      });
      render(
        <VerzamelorderLijst orders={[voorlopigeFactuur]} onKies={vi.fn()} />,
      );

      await gebruiker.click(
        screen.getByRole("button", { name: /Factuursleutel 154793 kopiëren/i }),
      );

      expect(geschreven).toEqual(["154793"]);
    });

    it("kopieert bij een definitieve factuur het InvNo en niet de InvKey", async () => {
      const gebruiker = userEvent.setup();
      const geschreven: string[] = [];
      document.execCommand = vi.fn(() => {
        geschreven.push(
          (document.querySelector("textarea") as HTMLTextAreaElement | null)
            ?.value ?? "",
        );
        return true;
      });
      render(<VerzamelorderLijst orders={[metFactuur]} onKies={vi.fn()} />);

      await gebruiker.click(
        screen.getByRole("button", {
          name: /Factuurnummer 31511432 kopiëren/i,
        }),
      );

      // 154055 is de interne InvKey en mag hier juist NIET gekopieerd worden.
      expect(geschreven).toEqual(["31511432"]);
    });

    it("kopieert ook als je op het woord in de badge klikt, niet alleen op het nummer", async () => {
      const gebruiker = userEvent.setup();
      render(
        <VerzamelorderLijst orders={[voorlopigeFactuur]} onKies={vi.fn()} />,
      );

      // De hele badge is één knop; het label hoort er dus binnen te vallen.
      const badge = screen.getByRole("button", {
        name: /Factuursleutel 154793 kopiëren/i,
      });
      expect(badge).toHaveTextContent("voorlopige factuur");
      expect(badge).toHaveTextContent("154793");

      await gebruiker.click(
        within(badge).getByText("voorlopige factuur", { exact: false }),
      );

      expect(document.execCommand).toHaveBeenCalledWith("copy");
    });

    it("laat een gefactureerde order het ordernummer wel kopiëren", async () => {
      const gebruiker = userEvent.setup();
      render(<VerzamelorderLijst orders={[metFactuur]} onKies={vi.fn()} />);

      await gebruiker.click(
        screen.getByRole("button", { name: /Ordernummer 1246311 kopiëren/i }),
      );

      expect(document.execCommand).toHaveBeenCalledWith("copy");
    });
  });

  describe("factuurgrendel", () => {
    it("biedt geen 'opnieuw genereren' bij een gefactureerde order", () => {
      render(<VerzamelorderLijst orders={[metFactuur]} onKies={vi.fn()} />);

      expect(
        screen.queryByRole("button", { name: /opnieuw genereren/i }),
      ).not.toBeInTheDocument();
    });

    it("legt uit waarom de order vergrendeld is", () => {
      render(<VerzamelorderLijst orders={[metFactuur]} onKies={vi.fn()} />);

      const uitleg = screen.getByText(/Vergrendeld/);
      expect(uitleg).toHaveTextContent(/staat op een factuur \(31511432\)/);
      expect(uitleg).toHaveTextContent(/administratie/);
    });

    it("laat ongefactureerde orders ernaast gewoon werken", async () => {
      const gebruiker = userEvent.setup();
      const onKies = vi.fn();
      render(
        <VerzamelorderLijst
          orders={[maakOrder(), metFactuur]}
          onKies={onKies}
        />,
      );

      const genereerKnoppen = screen.getAllByRole("button", {
        name: /opnieuw genereren/i,
      });
      expect(genereerKnoppen).toHaveLength(1);

      await gebruiker.click(genereerKnoppen[0]!);
      expect(onKies.mock.calls[0]![0].orderId).toBe(1267614);
    });

    it("toont alle orders, ook de vergrendelde", () => {
      render(
        <VerzamelorderLijst
          orders={[maakOrder(), metFactuur, voorlopigeFactuur]}
          onKies={vi.fn()}
        />,
      );

      const regels = screen.getAllByRole("listitem");
      expect(regels).toHaveLength(3);
      expect(within(regels[1]!).getByText("1246311")).toBeInTheDocument();
    });
  });
});
