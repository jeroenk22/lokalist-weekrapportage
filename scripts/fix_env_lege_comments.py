r"""Repareert regels in .env waar een lege waarde gevolgd wordt door een
inline # comment, bijv. `EMAIL_CC=    # optioneel, kommagescheiden`.

python-dotenv strip die comment niet als de waarde leeg is - de
commenttekst wordt dan letterlijk de waarde (zie #21).

Gebruik:
    python scripts/fix_env_lege_comments.py               -- toont wat er zou wijzigen
    python scripts/fix_env_lege_comments.py --apply        -- past .env aan (maakt eerst een .bak)
    python scripts/fix_env_lege_comments.py --apply C:\pad\naar\.env
"""

import re
import shutil
import sys
from datetime import datetime

_PATROON = re.compile(r"^(\w+)=\s*#.*$")


def _vind_wijzigingen(regels: list[str]) -> list[tuple[int, str, str]]:
    wijzigingen = []
    for i, regel in enumerate(regels):
        match = _PATROON.match(regel.rstrip("\n"))
        if match:
            nieuw = f"{match.group(1)}=\n"
            wijzigingen.append((i, regel, nieuw))
    return wijzigingen


def main() -> None:
    apply = "--apply" in sys.argv
    paden = [a for a in sys.argv[1:] if a != "--apply"]
    env_pad = paden[0] if paden else ".env"

    with open(env_pad, encoding="utf-8") as f:
        regels = f.readlines()

    wijzigingen = _vind_wijzigingen(regels)
    if not wijzigingen:
        print(f"{env_pad}: niets te repareren.")
        return

    print(f"{env_pad}: {len(wijzigingen)} regel(s) met lege waarde + comment gevonden:\n")
    for _, oud, nieuw in wijzigingen:
        print(f"  - {oud.rstrip()!r}\n    -> {nieuw.rstrip()!r}")

    if not apply:
        print("\nDry-run — niets aangepast. Voeg --apply toe om dit echt te repareren.")
        return

    backup_pad = f"{env_pad}.bak-{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    shutil.copyfile(env_pad, backup_pad)
    print(f"\nBackup weggeschreven: {backup_pad}")

    for i, _, nieuw in wijzigingen:
        regels[i] = nieuw
    with open(env_pad, "w", encoding="utf-8") as f:
        f.writelines(regels)
    print(f"{env_pad} aangepast ({len(wijzigingen)} regel(s)).")


if __name__ == "__main__":
    main()
