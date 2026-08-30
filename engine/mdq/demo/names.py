"""Erfundene Firmennamen und Straßen durch Kombinatorik.

Keine echten Firmen, Personen oder Marken (CLAUDE.md Regel 8, D-008): ein Name entsteht
als Silbenpaar + Branchenwort + Rechtsform, zum Beispiel "Bernbach Fördertechnik GmbH".

Die Rechtsformen stammen aus `logic/dictionaries/legal_forms.yaml`; hier steht nur die
**Schreibweise im Export**, der Bestand an Formen bleibt im Wörterbuch. Ein Test prüft,
dass jede hier benutzte Form dort als kanonischer Schlüssel existiert.

Eindeutigkeit: der Basis-Mandant darf keine Dublette enthalten, sonst meldet AR-DUP-001
Treffer, die kein Defekt gesetzt hat. :func:`normalize_core` normalisiert dafür
**gröber** als das spätere Matching (Rechtsform und Branchenwort fallen weg, nur der
Kernname bleibt) – wer danach verschieden ist, ist es unter jeder feineren
Normalisierung erst recht.
"""

import re
import unicodedata
from functools import lru_cache
from typing import NamedTuple

import yaml

from mdq import LOGIC_DIR

_PREFIXES = (
    "Alt", "Ahorn", "Berg", "Bern", "Birken", "Brand", "Buchen", "Dorn", "Eich", "Erlen",
    "Espen", "Falken", "Feld", "Fichten", "Grün", "Hasel", "Hart", "Hoch", "Holunder",
    "Kastanien", "Kiefern", "Klein", "Lang", "Lärchen", "Linden", "Mühl", "Neu", "Nord",
    "Ost", "Rein", "Rhein", "Rot", "Sand", "Stein", "Süd", "Tal", "Ulmen", "Wald",
    "Weiden", "Weiß", "West", "Zeder",
)

_SUFFIXES = (
    "au", "bach", "berg", "brück", "burg", "dorf", "feld", "fels", "furt", "grund",
    "haus", "heim", "hof", "mark", "ried", "see", "stein", "tal", "wald", "weg",
)

_INDUSTRY = (
    "Anlagenbau", "Antriebstechnik", "Apparatebau", "Armaturen", "Aufzugstechnik",
    "Bauelemente", "Baustoffe", "Bedachungen", "Behälterbau", "Chemie", "Dichtungstechnik",
    "Druckguss", "Elektrotechnik", "Fahrzeugteile", "Fördertechnik", "Formenbau",
    "Getränke", "Handel", "Haustechnik", "Hydraulik", "Industrieservice", "Klimatechnik",
    "Kunststofftechnik", "Lagertechnik", "Lebensmittel", "Logistik", "Maschinenbau",
    "Messtechnik", "Metallbau", "Möbelwerke", "Oberflächentechnik", "Papier",
    "Präzisionsteile", "Pumpen", "Recycling", "Sanitärtechnik", "Schleiftechnik",
    "Schweißtechnik", "Speditionen", "Stahlbau", "Systemtechnik", "Textilien",
    "Umformtechnik", "Verpackungen", "Werkzeugbau", "Zerspanung",
)

#: Rechtsform je Sitzland: (kanonischer Schlüssel aus legal_forms.yaml, Schreibweise)
LEGAL_FORMS_BY_COUNTRY: dict[str, tuple[tuple[str, str], ...]] = {
    "DE": (
        ("gmbh", "GmbH"),
        ("gmbh_co_kg", "GmbH & Co. KG"),
        ("ag", "AG"),
        ("kg", "KG"),
        ("ohg", "OHG"),
        ("ek", "e.K."),
        ("ug", "UG (haftungsbeschränkt)"),
        ("se", "SE"),
        ("eg", "eG"),
        ("kgaa", "KGaA"),
    ),
    "AT": (("gmbh", "GmbH"), ("ag", "AG"), ("kg", "KG")),
    "CH": (("ag", "AG"), ("gmbh", "GmbH")),
    "NL": (("bv", "B.V."), ("nv", "N.V.")),
    "FR": (("sarl", "S.A.R.L."), ("sas", "S.A.S."), ("sa", "S.A.")),
    "IT": (("srl", "S.r.l."), ("spa", "S.p.A.")),
    "PL": (("sp_z_oo", "Sp. z o.o."), ("sa", "S.A.")),
    "US": (("inc", "Inc."), ("llc", "LLC"), ("corp", "Corp.")),
}

#: Gewichte für die Rechtsform in Deutschland – GmbH dominiert wie in der Realität
_DE_LEGAL_FORM_WEIGHTS = (40, 18, 8, 8, 4, 8, 6, 2, 3, 3)

_STREET_STEMS = (
    "Ahorn", "Amsel", "Bahnhof", "Birken", "Brunnen", "Burg", "Dom", "Eichen", "Erlen",
    "Fasanen", "Feld", "Garten", "Hafen", "Hasel", "Heide", "Industrie", "Kirsch",
    "Lerchen", "Linden", "Markt", "Mühlen", "Nelken", "Nussbaum", "Pappel", "Post",
    "Quellen", "Raiffeisen", "Rosen", "Schul", "Sonnen", "Tannen", "Ulmen", "Wiesen",
    "Zeppelin",
)

_STREET_TYPES = ("straße", "weg", "allee", "ring", "platz", "gasse", "damm")


class Company(NamedTuple):
    """Ein erfundener Firmenname mit seinen Bestandteilen."""

    name1: str
    search_term: str
    legal_form: str


@lru_cache(maxsize=1)
def known_legal_form_keys() -> frozenset[str]:
    """Kanonische Rechtsform-Schlüssel aus dem Wörterbuch."""
    text = (LOGIC_DIR / "dictionaries" / "legal_forms.yaml").read_text(encoding="utf-8")
    return frozenset(yaml.safe_load(text)["legal_forms"])


@lru_cache(maxsize=1)
def transliterations() -> tuple[tuple[str, str], ...]:
    """Umlaut-Abbildung aus dem Wörterbuch – dieselbe Quelle wie das spätere Matching."""
    text = (LOGIC_DIR / "dictionaries" / "legal_forms.yaml").read_text(encoding="utf-8")
    return tuple(sorted(yaml.safe_load(text)["transliteration"].items()))


_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def normalize_core(text: str) -> str:
    """Grobe Normalisierung des Kernnamens: nur Buchstaben und Ziffern, klein, ohne Umlaut.

    Bewusst ohne Rechtsform- und Rauschbehandlung – der Kernname wird vor dem Anhängen
    von Branchenwort und Rechtsform geprüft. Was hier verschieden ist, bleibt auch nach
    einer feineren Normalisierung verschieden.
    """
    lowered = text.lower()
    for source, target in transliterations():
        lowered = lowered.replace(source, target)
    lowered = unicodedata.normalize("NFKD", lowered)
    lowered = "".join(char for char in lowered if not unicodedata.combining(char))
    return _NON_ALNUM.sub("", lowered)


class NameFactory:
    """Erzeugt eindeutige Firmennamen und Straßen aus einem Zufallsstrom."""

    def __init__(self, rng) -> None:
        self._rng = rng
        self._used_cores: set[str] = set()

    def company(self, country: str) -> Company:
        """Firmenname für ein Sitzland; der Kernname ist über alle Partner eindeutig."""
        forms = LEGAL_FORMS_BY_COUNTRY[country]
        weights = _DE_LEGAL_FORM_WEIGHTS if country == "DE" else None
        _, legal_form = self._rng.choices(forms, weights=weights, k=1)[0]

        while True:
            stem = self._rng.choice(_PREFIXES) + self._rng.choice(_SUFFIXES)
            industry = self._rng.choice(_INDUSTRY)
            core = normalize_core(f"{stem} {industry}")
            if core not in self._used_cores:
                self._used_cores.add(core)
                break

        name1 = f"{stem} {industry} {legal_form}"
        return Company(name1=name1, search_term=stem.upper()[:10], legal_form=legal_form)

    def street(self) -> str:
        """Straße mit Hausnummer, zum Beispiel "Lindenweg 14"."""
        # Alle Typen sind im Deutschen Zusammensetzungen: Lindenstraße, Lindenweg, Lindenring
        name = self._rng.choice(_STREET_STEMS) + self._rng.choice(_STREET_TYPES)
        number = self._rng.randint(1, 199)
        suffix = self._rng.choice(("", "", "", "", "a", "b"))
        return f"{name} {number}{suffix}"
