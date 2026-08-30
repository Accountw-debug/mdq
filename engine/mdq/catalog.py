"""Lesen des fachlichen Regelkatalogs ``logic/rules/CATALOG.md``.

Der Katalog ist Victors Arbeitsstand: eine Markdown-Tabelle je Seite (AR, AP, CROSS), eine
Zeile je geplanter Regel. Er ist die Klammer zwischen drei Staenden, die auseinanderlaufen
koennen -- den Regeldateien in ``logic/rules/``, den Defekten in ``defects.yaml`` und der
Planung. Deshalb wird er hier geparst statt gelesen: ``engine/tests/test_catalog.py`` prueft
die drei Staende gegeneinander.

Streng geprueft werden nur die Spalten, an denen etwas haengt: ``ID``, ``Status`` und
``Testdaten``. Der Rest der Zeile (Titel, Schwere, Stufe, Tabellen, SAP) wird als Rohtext
mitgefuehrt -- die Stufen-Spalte enthaelt bewusst Fliesstext wie
``B (Soll = meistgenutzte ZTERM aus Belegen)``. Ein Abgleich dieser Felder mit dem Regelkopf
braucht erst eine Konvention dafuer und gehoert nach Sprint 3.
"""

import re
from dataclasses import dataclass
from pathlib import Path

from mdq import CATALOG_MD

#: Reifegrad einer Regel: nur Zeile / freigegeben / gebaut
STATUSES = ("draft", "spec", "impl")

#: Datenlage: erzeugt `defects.yaml` einen Fall fuer diese Regel?
TESTDATA_MARKS = ("Defekt", "ohne Testfall")

#: Spalten der Katalogtabellen, in dieser Reihenfolge
COLUMNS = (
    "ID",
    "Titel",
    "Kategorie",
    "Schwere",
    "SK",
    "Stufe",
    "Aktion",
    "Tabellen",
    "SAP",
    "Status",
    "Testdaten",
)

_ID_RE = re.compile(r"\A(AR|AP|CROSS)-(COM|VAL|CON|HYG|RSK|DUP|LEA)-([0-9]{3})\Z")
_SEPARATOR_RE = re.compile(r"\A\|[-|]+\|\Z")


class CatalogError(ValueError):
    """Der Katalog ist nicht lesbar, eine Zeile ist unvollstaendig oder widerspruechlich."""


@dataclass(frozen=True)
class CatalogEntry:
    """Eine Katalogzeile."""

    rule_id: str
    title: str
    category: str
    severity: str
    damage_class: str
    tier: str
    action: str
    tables: str
    sap: str
    status: str
    testdata: str
    line_no: int

    @property
    def has_defect(self) -> bool:
        """Erzeugt `defects.yaml` laut Katalog einen Fall fuer diese Regel?"""
        return self.testdata == "Defekt"


def _split_row(line: str) -> list[str]:
    """Zerlegt eine Markdown-Tabellenzeile in ihre Zellen."""
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def parse_catalog(text: str, source: str = "CATALOG.md") -> tuple[CatalogEntry, ...]:
    """Parst den Katalog. Sammelt alle Probleme und meldet sie gemeinsam."""
    entries: list[CatalogEntry] = []
    errors: list[str] = []
    seen: dict[str, int] = {}
    in_table = False

    for line_no, line in enumerate(text.split("\n"), start=1):
        stripped = line.strip()
        if not stripped.startswith("|"):
            in_table = False
            continue
        if _SEPARATOR_RE.match(stripped):
            continue

        cells = _split_row(stripped)
        if tuple(cells) == COLUMNS:
            in_table = True
            continue
        if cells and cells[0] == "ID":
            errors.append(
                f"Zeile {line_no}: Kopfzeile weicht ab, erwartet sind die Spalten {list(COLUMNS)}"
            )
            in_table = False
            continue
        if not in_table:
            # Eine Tabellenzeile ausserhalb der Katalogtabellen (z. B. in einem Beispiel)
            # ist keine Regelzeile - aber auch nichts, was hier stillschweigend verschwindet.
            errors.append(f"Zeile {line_no}: Tabellenzeile ohne vorangehende Kopfzeile")
            continue

        if len(cells) != len(COLUMNS):
            errors.append(
                f"Zeile {line_no}: {len(cells)} Spalten statt {len(COLUMNS)} "
                f"({cells[0] or '<ohne ID>'})"
            )
            continue

        entry = CatalogEntry(*cells, line_no=line_no)
        if not _ID_RE.match(entry.rule_id):
            errors.append(
                f"Zeile {line_no}: '{entry.rule_id}' ist keine Regel-ID "
                "<AR|AP|CROSS>-<COM|VAL|CON|HYG|RSK|DUP|LEA>-<NNN>"
            )
            continue
        if entry.rule_id in seen:
            errors.append(
                f"Zeile {line_no}: {entry.rule_id} steht schon in Zeile {seen[entry.rule_id]}"
            )
            continue
        if entry.status not in STATUSES:
            errors.append(
                f"Zeile {line_no}: {entry.rule_id} hat Status '{entry.status}', "
                f"erlaubt sind {list(STATUSES)}"
            )
            continue
        if entry.testdata not in TESTDATA_MARKS:
            errors.append(
                f"Zeile {line_no}: {entry.rule_id} hat Testdaten '{entry.testdata}', "
                f"erlaubt sind {list(TESTDATA_MARKS)}"
            )
            continue

        seen[entry.rule_id] = line_no
        entries.append(entry)

    if errors:
        joined = "\n    ".join(errors)
        raise CatalogError(f"{source}:\n    {joined}")
    if not entries:
        raise CatalogError(f"{source}: keine Regelzeile gefunden")

    # Nach ID sortiert, damit Vergleiche und Ausgaben deterministisch sind (Regel 9).
    return tuple(sorted(entries, key=lambda entry: entry.rule_id))


def load_catalog(path: Path = CATALOG_MD) -> tuple[CatalogEntry, ...]:
    """Liest und prueft den Katalog."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise CatalogError(f"{path.name}: nicht als UTF-8 lesbar ({type(exc).__name__})") from exc
    return parse_catalog(text, path.name)
