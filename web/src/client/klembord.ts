/** Tekst naar het klembord kopiëren.
 *
 * Browsers stellen `navigator.clipboard` alleen beschikbaar in een "secure
 * context": https, of localhost. Collega's benaderen het dashboard via
 * http://192.168.4.105:3000 en dáár bestaat die API dus niet. Daarom valt deze
 * functie terug op de oude execCommand-methode, die ook over gewoon http werkt.
 */
export async function kopieerNaarKlembord(tekst: string): Promise<boolean> {
  if (navigator.clipboard && window.isSecureContext) {
    try {
      await navigator.clipboard.writeText(tekst);
      return true;
    } catch {
      // Geweigerd of niet beschikbaar — probeer hieronder de fallback.
    }
  }

  try {
    const veld = document.createElement("textarea");
    veld.value = tekst;
    veld.setAttribute("readonly", "");
    // Buiten beeld, maar wel selecteerbaar; `display:none` werkt niet.
    veld.style.position = "fixed";
    veld.style.top = "-1000px";
    veld.style.opacity = "0";
    document.body.appendChild(veld);
    veld.select();
    veld.setSelectionRange(0, veld.value.length);
    const gelukt = document.execCommand("copy");
    document.body.removeChild(veld);
    return gelukt;
  } catch {
    return false;
  }
}
