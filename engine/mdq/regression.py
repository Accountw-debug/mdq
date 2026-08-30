"""Vergleich eines Laufs mit einer erwarteten Findings-Liste.

Der Demo-Mandant und ``testdata/expected/expected_findings.yaml`` sind zusammen die Spec:
gleicher Input, exakt diese Findings -- nicht mehr, nicht weniger (D-010). Dieses Modul
vergleicht beide Seiten und sortiert die Abweichungen in sechs Toepfe, drei davon Fehler.

Es liegt bewusst in ``mdq/`` und nicht in den Tests: derselbe Vergleich ist beim Kunden
nuetzlich, sobald ein Lauf gegen einen freigegebenen Stand geprueft werden soll. Die Pfade
kommen deshalb von aussen.

Alle Meldungen nennen nur Regel-ID, bp_key, Buchungskreis, finding_key und Defekt-ID --
niemals Namen, IBAN oder Adressen (CLAUDE.md, Regel 8).
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from mdq import EXPECTED_FINDINGS

#: Pflichtfelder je Zeile in `expected_findings.yaml`
REQUIRED_FIELDS = ("rule_id", "bp_key", "defect")

#: Felder, die eine Zeile haben darf, aber nicht muss
OPTIONAL_FIELDS = ("company_code", "document_no", "finding_key", "from_rule_version")

#: Der Vergleichsschluessel: (rule_id, bp_key, company_code, finding_key).
#: `document_no` gehoert bewusst nicht dazu -- es ist ein Hinweis fuer den Menschen; was ein
#: Finding von einem anderen derselben Regel und desselben BP unterscheidet, entscheidet die
#: Regel ueber ihre `finding_key`-Spalte (D-068).
MatchKey = tuple[str, str, str | None, str | None]


class RegressionError(ValueError):
    """Die erwartete Liste ist nicht lesbar oder in sich widerspruechlich."""


def parse_version(text: str) -> tuple[int, ...]:
    """``"1.10"`` -> ``(1, 10)``. Als Text verglichen waere 1.10 kleiner als 1.9."""
    try:
        return tuple(int(part) for part in text.split("."))
    except ValueError as exc:
        raise RegressionError(f"Version '{text}': erwartet Zahlen mit Punkt, etwa '1.0'") from exc


@dataclass(frozen=True)
class ExpectedFinding:
    """Eine Zeile aus `expected_findings.yaml`."""

    rule_id: str
    bp_key: str
    defect: str
    company_code: str | None = None
    document_no: str | None = None
    finding_key: str | None = None
    from_rule_version: str | None = None

    @property
    def match_key(self) -> MatchKey:
        return (self.rule_id, self.bp_key, self.company_code, self.finding_key)


@dataclass(frozen=True)
class ActualFinding:
    """Ein Finding aus dem Lauf, reduziert auf den Vergleichsschluessel."""

    rule_id: str
    bp_key: str
    company_code: str | None = None
    finding_key: str | None = None

    @property
    def match_key(self) -> MatchKey:
        return (self.rule_id, self.bp_key, self.company_code, self.finding_key)


@dataclass(frozen=True)
class Deviation:
    """Gleiche Regel und gleicher BP, aber anderer Buchungskreis oder finding_key.

    Ein eigener Topf, weil ein falscher Buchungskreis sonst als ein Fehlend *und* ein
    Unerwartet erschiene -- zwei Zeilen, die die Ursache verstecken.
    """

    expected: ExpectedFinding
    actual: ActualFinding

    @property
    def differing_fields(self) -> tuple[str, ...]:
        fields = []
        if self.expected.company_code != self.actual.company_code:
            fields.append("company_code")
        if self.expected.finding_key != self.actual.finding_key:
            fields.append("finding_key")
        return tuple(fields)


def _sort_key(item: ExpectedFinding | ActualFinding) -> tuple[str, str, str, str]:
    key = item.match_key
    return (key[0], key[1], key[2] or "", key[3] or "")


def _label(item: ExpectedFinding | ActualFinding) -> str:
    parts = [item.rule_id, item.bp_key]
    if item.company_code:
        parts.append(f"BUKRS {item.company_code}")
    if item.finding_key:
        parts.append(f"key {item.finding_key}")
    if isinstance(item, ExpectedFinding):
        parts.append(f"({item.defect})")
    return " ".join(parts)


@dataclass(frozen=True)
class Comparison:
    """Das Ergebnis: drei Fehler-Toepfe, drei Hinweis-Toepfe."""

    #: Erwartet, Regel gebaut, Version reicht -- aber nicht geliefert.
    missing: tuple[ExpectedFinding, ...] = ()
    #: Geliefert, aber nicht erwartet.
    unexpected: tuple[ActualFinding, ...] = ()
    #: Gleiche Regel und gleicher BP, anderer Buchungskreis oder finding_key.
    deviating: tuple[Deviation, ...] = ()
    #: Erst ab einer hoeheren Regelversion Pflicht und (noch) nicht geliefert (D-054).
    known_open: tuple[ExpectedFinding, ...] = ()
    #: Erst ab einer hoeheren Regelversion Pflicht -- aber schon geliefert.
    early: tuple[ExpectedFinding, ...] = ()
    #: Erwartet fuer eine Regel, die es als Datei noch nicht gibt.
    rule_missing: tuple[ExpectedFinding, ...] = field(default=())

    @property
    def ok(self) -> bool:
        """Nur die drei Fehler-Toepfe entscheiden ueber Erfolg."""
        return not (self.missing or self.unexpected or self.deviating)

    def render(self) -> str:
        """Menschenlesbarer Bericht, deterministisch sortiert, ohne Partnerdaten."""
        lines: list[str] = []

        if self.missing:
            lines.append(f"Fehlend ({len(self.missing)}) – erwartet, aber nicht geliefert:")
            lines += [f"  - {_label(item)}" for item in self.missing]
        if self.unexpected:
            lines.append(f"Unerwartet ({len(self.unexpected)}) – geliefert, aber nicht erwartet:")
            lines += [f"  - {_label(item)}" for item in self.unexpected]
        if self.deviating:
            lines.append(f"Abweichend ({len(self.deviating)}) – gleiche Regel, gleicher BP:")
            for deviation in self.deviating:
                fields = ", ".join(deviation.differing_fields) or "?"
                lines.append(
                    f"  - {deviation.expected.rule_id} {deviation.expected.bp_key}: "
                    f"{fields} weicht ab | erwartet: {_label(deviation.expected)} "
                    f"| geliefert: {_label(deviation.actual)}"
                )

        if self.known_open:
            lines.append(
                f"Bekannt offen ({len(self.known_open)}) – erst ab hoeherer Regelversion "
                "Pflicht (D-054):"
            )
            lines += [
                f"  - {_label(item)} ab Version {item.from_rule_version}"
                for item in self.known_open
            ]
        if self.early:
            lines.append(
                f"Vorzeitig erfuellt ({len(self.early)}) – die Regel findet den Fall schon "
                "unter der angegebenen Version. from_rule_version in defects.yaml pruefen "
                "und absenken:"
            )
            lines += [
                f"  - {_label(item)} steht auf Version {item.from_rule_version}"
                for item in self.early
            ]
        if self.rule_missing:
            rules = sorted({item.rule_id for item in self.rule_missing})
            lines.append(
                f"Regel fehlt ({len(self.rule_missing)} Findings, {len(rules)} Regeln) – "
                f"noch nicht gebaut: {', '.join(rules)}"
            )

        if not lines:
            return "Lauf und Erwartung stimmen ueberein."
        return "\n".join(lines)


def _parse_entry(entry: Any, position: int) -> ExpectedFinding:
    if not isinstance(entry, dict):
        raise RegressionError(f"Eintrag {position}: erwartet ein Objekt")

    missing = [key for key in REQUIRED_FIELDS if not entry.get(key)]
    if missing:
        raise RegressionError(f"Eintrag {position}: Pflichtfelder fehlen: {missing}")

    unknown = sorted(set(entry) - set(REQUIRED_FIELDS) - set(OPTIONAL_FIELDS))
    if unknown:
        raise RegressionError(
            f"Eintrag {position} ({entry['rule_id']} {entry['bp_key']}): "
            f"unbekannte Felder {unknown}"
        )

    version = entry.get("from_rule_version")
    if version is not None:
        parse_version(str(version))

    return ExpectedFinding(
        rule_id=entry["rule_id"],
        bp_key=entry["bp_key"],
        defect=entry["defect"],
        company_code=entry.get("company_code"),
        document_no=entry.get("document_no"),
        finding_key=entry.get("finding_key"),
        from_rule_version=str(version) if version is not None else None,
    )


def load_expected(path: Path = EXPECTED_FINDINGS) -> tuple[ExpectedFinding, ...]:
    """Liest und prueft die erwartete Liste. Sie wird nie an den Code angepasst (Regel 1)."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise RegressionError(f"{path.name}: nicht als UTF-8 lesbar ({type(exc).__name__})") from exc

    try:
        document = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise RegressionError(f"{path.name}: kein gueltiges YAML ({type(exc).__name__})") from exc

    if not isinstance(document, dict) or not isinstance(document.get("findings"), list):
        raise RegressionError(f"{path.name}: erwartet ein Objekt mit der Liste 'findings'")

    expected = tuple(
        _parse_entry(entry, position)
        for position, entry in enumerate(document["findings"], start=1)
    )

    seen: dict[MatchKey, ExpectedFinding] = {}
    for item in expected:
        previous = seen.get(item.match_key)
        if previous is not None:
            raise RegressionError(
                f"{path.name}: {_label(item)} und {_label(previous)} haben denselben "
                "Vergleichsschluessel. Der Regel fehlt eine finding_key-Spalte."
            )
        seen[item.match_key] = item
    return expected


def actual_from_findings(rows: list[tuple[dict[str, Any], str | None]]) -> list[ActualFinding]:
    """Baut die Ist-Seite aus dem, was ``execute_rule_rows`` liefert."""
    return [
        ActualFinding(
            rule_id=finding["rule_id"],
            bp_key=finding["entity"]["bp_key"],
            company_code=finding["entity"].get("company_code"),
            finding_key=finding_key,
        )
        for finding, finding_key in rows
    ]


def compare(
    expected: tuple[ExpectedFinding, ...] | list[ExpectedFinding],
    actual: list[ActualFinding] | tuple[ActualFinding, ...],
    rule_versions: dict[str, str],
) -> Comparison:
    """Vergleicht Erwartung und Lauf.

    ``rule_versions`` bildet Regel-ID auf die Version der gebauten Regel ab. Eine Regel, die
    dort fehlt, gibt es als Datei noch nicht: ihre erwarteten Findings sind kein Fehler,
    sondern offene Arbeit (Topf ``rule_missing``).
    """
    by_key: dict[MatchKey, ActualFinding] = {}
    for item in actual:
        if item.match_key in by_key:
            raise RegressionError(
                f"Lauf liefert {_label(item)} doppelt – der Regel fehlt eine finding_key-Spalte."
            )
        by_key[item.match_key] = item

    missing: list[ExpectedFinding] = []
    known_open: list[ExpectedFinding] = []
    early: list[ExpectedFinding] = []
    rule_missing: list[ExpectedFinding] = []
    matched: set[MatchKey] = set()

    for item in expected:
        built = rule_versions.get(item.rule_id)
        if built is None:
            rule_missing.append(item)
            continue

        delivered = item.match_key in by_key
        if delivered:
            matched.add(item.match_key)

        if item.from_rule_version and parse_version(item.from_rule_version) > parse_version(built):
            # Bekannt-offen (D-054): unter dieser Version ist das Finding weder Pflicht
            # noch verboten. Taucht es trotzdem auf, ist die Angabe zu hoch gegriffen.
            (early if delivered else known_open).append(item)
            continue

        if not delivered:
            missing.append(item)

    unexpected = [item for key, item in by_key.items() if key not in matched]

    # Fehlend und Unerwartet, die sich (rule_id, bp_key) teilen, sind in Wahrheit ein
    # abweichendes Finding -- als zwei Zeilen waere die Ursache nicht zu sehen.
    deviating: list[Deviation] = []
    unexpected_by_bp: dict[tuple[str, str], list[ActualFinding]] = {}
    for item in unexpected:
        unexpected_by_bp.setdefault((item.rule_id, item.bp_key), []).append(item)

    still_missing: list[ExpectedFinding] = []
    for item in missing:
        candidates = unexpected_by_bp.get((item.rule_id, item.bp_key))
        if candidates:
            deviating.append(Deviation(expected=item, actual=candidates.pop(0)))
        else:
            still_missing.append(item)

    still_unexpected = [item for items in unexpected_by_bp.values() for item in items]

    return Comparison(
        missing=tuple(sorted(still_missing, key=_sort_key)),
        unexpected=tuple(sorted(still_unexpected, key=_sort_key)),
        deviating=tuple(sorted(deviating, key=lambda d: _sort_key(d.expected))),
        known_open=tuple(sorted(known_open, key=_sort_key)),
        early=tuple(sorted(early, key=_sort_key)),
        rule_missing=tuple(sorted(rule_missing, key=_sort_key)),
    )
