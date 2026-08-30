"""Laden und Pruefen der Woerterbuecher aus ``logic/dictionaries/``.

Bisher: ``document_types.yaml`` – welche Belegart (BLART) eine Rechnung, eine Gutschrift,
eine Zahlung oder ein Storno ist. Zwei Stellen brauchen dieselbe Auskunft: die Relevanz
(``volume_12m`` = Rechnungen minus Gutschriften, D-051) und die Regeln, die auf
Gutschriften netten (AP-LEA-001, D-082). Die Liste steht deshalb genau einmal.

Wie beim Mapping wird die Datei vollstaendig geprueft, bevor eine Zeile Daten fliesst:
eine unbekannte Klasse, eine unbekannte Seite oder eine Belegart in zwei Klassen sind
Fehler mit Namen, keine stille Vorgabe (Regel 4). Die Engine reicht die Listen den Regeln
als ``params`` zu – Regel-SQL liest nur das kanonische Schema (Regel 5).
"""

from dataclasses import dataclass
from pathlib import Path

import yaml

from mdq import DOCUMENT_TYPES

#: Seiten, die das Woerterbuch kennt – dieselben Kuerzel wie im Finding (``side``)
SIDES = ("AR", "AP")

#: Klassen je Seite. ``reversal`` darf leer sein, solange kein Export eine
#: Stornobelegart geliefert hat (D-082); ``invoice`` und ``credit_memo`` nicht.
CLASSES = ("invoice", "credit_memo", "payment", "reversal")

#: Klassen, die ohne Eintrag ein Fehler waeren: ohne sie waere ``volume_12m`` keine Zahl,
#: sondern eine Vermutung
REQUIRED_CLASSES = ("invoice", "credit_memo")

#: Rolle im kanonischen Modell -> Seite im Woerterbuch
ROLE_SIDE = {"CUSTOMER": "AR", "VENDOR": "AP"}


class DictionaryError(ValueError):
    """Ein Woerterbuch ist unvollstaendig, widerspruechlich oder nicht lesbar."""


@dataclass(frozen=True)
class DocumentTypes:
    """Belegarten je Seite und Klasse."""

    version: str
    #: (Seite, Klasse) -> Belegarten in der Reihenfolge der Datei
    classes: dict[tuple[str, str], tuple[str, ...]]
    path: Path

    def of(self, side: str, *class_names: str) -> tuple[str, ...]:
        """Die Belegarten einer oder mehrerer Klassen, sortiert und ohne Dubletten.

        Sortiert, weil die Liste in SQL und in Findings landet und zwei Laeufe dieselbe
        Reihenfolge zeigen muessen (Regel 9).
        """
        if side not in SIDES:
            raise DictionaryError(
                f"{side}: unbekannte Seite in {self.path.name}; erlaubt sind {list(SIDES)}."
            )
        unknown = [name for name in class_names if name not in CLASSES]
        if unknown:
            raise DictionaryError(
                f"{unknown}: unbekannte Klasse in {self.path.name}; erlaubt sind {list(CLASSES)}."
            )
        values: set[str] = set()
        for name in class_names:
            values.update(self.classes[(side, name)])
        return tuple(sorted(values))

    def for_role(self, role: str, *class_names: str) -> tuple[str, ...]:
        """Wie :meth:`of`, aber ueber die kanonische Rolle (``CUSTOMER``/``VENDOR``)."""
        try:
            side = ROLE_SIDE[role]
        except KeyError:
            raise DictionaryError(
                f"{role}: unbekannte Rolle; erlaubt sind {sorted(ROLE_SIDE)}."
            ) from None
        return self.of(side, *class_names)


def parse_document_types(document: object, path: Path) -> DocumentTypes:
    """Prueft ein geladenes Woerterbuch und meldet alle Probleme gemeinsam."""
    if not isinstance(document, dict):
        raise DictionaryError(f"{path.name}: enthaelt kein Objekt")

    errors: list[str] = []
    unknown_sections = sorted(set(document) - {"version", "sides"})
    if unknown_sections:
        errors.append(f"unbekannte Abschnitte: {unknown_sections}")

    version = document.get("version")
    if not isinstance(version, str) or not version.strip():
        errors.append("version: muss ein nicht-leerer Text sein")
        version = ""

    classes: dict[tuple[str, str], tuple[str, ...]] = {}
    raw_sides = document.get("sides")
    if not isinstance(raw_sides, dict):
        errors.append("sides: muss Seite -> Klassen abbilden")
        raw_sides = {}

    unknown_sides = sorted(set(raw_sides) - set(SIDES))
    if unknown_sides:
        errors.append(f"sides: unbekannte Seiten {unknown_sides}, erlaubt {list(SIDES)}")

    for side in SIDES:
        spec = raw_sides.get(side)
        if not isinstance(spec, dict):
            errors.append(f"sides.{side}: fehlt oder ist kein Objekt")
            spec = {}
        unknown_classes = sorted(set(spec) - set(CLASSES))
        if unknown_classes:
            errors.append(
                f"sides.{side}: unbekannte Klassen {unknown_classes}, erlaubt {list(CLASSES)}"
            )
        seen: dict[str, str] = {}
        for class_name in CLASSES:
            entries = spec.get(class_name)
            if entries is None:
                entries = []
            if not isinstance(entries, list) or not all(
                isinstance(entry, str) and entry.strip() for entry in entries
            ):
                errors.append(f"sides.{side}.{class_name}: muss eine Liste von Belegarten sein")
                entries = []
            if class_name in REQUIRED_CLASSES and not entries:
                errors.append(
                    f"sides.{side}.{class_name}: darf nicht leer sein – ohne sie waere "
                    "volume_12m eine Vermutung (D-051)"
                )
            for entry in entries:
                if entry in seen:
                    errors.append(
                        f"sides.{side}: Belegart {entry} steht in {seen[entry]} und "
                        f"{class_name} – eine Belegart hat genau eine Klasse"
                    )
                else:
                    seen[entry] = class_name
            classes[(side, class_name)] = tuple(entries)

    if errors:
        joined = "\n    ".join(errors)
        raise DictionaryError(f"{path.name}:\n    {joined}")

    return DocumentTypes(version=version, classes=classes, path=path)


def load_document_types(path: Path = DOCUMENT_TYPES) -> DocumentTypes:
    """Liest und prueft ``document_types.yaml``."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise DictionaryError(
            f"{path.name}: nicht als UTF-8 lesbar ({type(exc).__name__})"
        ) from exc
    try:
        document = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise DictionaryError(f"{path.name}: kein gueltiges YAML ({type(exc).__name__})") from exc
    return parse_document_types(document, path)
