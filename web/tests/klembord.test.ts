/** Tests voor het kopiëren naar het klembord.
 *
 * Het belangrijkste geval is de fallback: collega's openen het dashboard via
 * http:// op het LAN, en daar bestaat navigator.clipboard niet.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { kopieerNaarKlembord } from "../src/client/klembord.js";

const origineleClipboard = navigator.clipboard;
const origineleSecureContext = window.isSecureContext;

function zetContext(opties: { clipboard: unknown; secure: boolean }) {
  Object.defineProperty(navigator, "clipboard", {
    value: opties.clipboard,
    configurable: true,
    writable: true,
  });
  Object.defineProperty(window, "isSecureContext", {
    value: opties.secure,
    configurable: true,
    writable: true,
  });
}

beforeEach(() => {
  document.execCommand = vi.fn(() => true);
});

afterEach(() => {
  zetContext({ clipboard: origineleClipboard, secure: origineleSecureContext });
  vi.restoreAllMocks();
});

describe("kopieerNaarKlembord", () => {
  it("gebruikt de Clipboard-API in een secure context", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    zetContext({ clipboard: { writeText }, secure: true });

    expect(await kopieerNaarKlembord("1267614")).toBe(true);
    expect(writeText).toHaveBeenCalledWith("1267614");
    expect(document.execCommand).not.toHaveBeenCalled();
  });

  it("valt terug op execCommand over gewoon http", async () => {
    // Zoals op http://192.168.4.105:3000 — geen secure context.
    zetContext({ clipboard: undefined, secure: false });

    expect(await kopieerNaarKlembord("31511432")).toBe(true);
    expect(document.execCommand).toHaveBeenCalledWith("copy");
  });

  it("valt terug als de Clipboard-API geweigerd wordt", async () => {
    const writeText = vi.fn().mockRejectedValue(new Error("geweigerd"));
    zetContext({ clipboard: { writeText }, secure: true });

    expect(await kopieerNaarKlembord("1267614")).toBe(true);
    expect(document.execCommand).toHaveBeenCalledWith("copy");
  });

  it("meldt netjes als ook de fallback niet lukt", async () => {
    zetContext({ clipboard: undefined, secure: false });
    document.execCommand = vi.fn(() => false);

    expect(await kopieerNaarKlembord("1267614")).toBe(false);
  });

  it("laat geen hulpelement achter in de pagina", async () => {
    zetContext({ clipboard: undefined, secure: false });

    await kopieerNaarKlembord("1267614");

    expect(document.querySelectorAll("textarea")).toHaveLength(0);
  });
});
