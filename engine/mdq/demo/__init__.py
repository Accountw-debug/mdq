"""Generator für den synthetischen Demo-Mandanten (docs/specs/SPRINT-2.md).

Grundidee des Sprints: **Fehler sind Daten, nicht Code.** Dieses Paket erzeugt einen
*sauberen* Basis-Mandanten; die Defekte kommen in Aufgabe 2 aus `defects.yaml` obendrauf.
Deshalb gilt hier die Invariante: **auf dem Basis-Mandanten darf keine Regel greifen.**
Was dafür nötig ist, steht als Kommentar an der jeweiligen Stelle und wird getestet.

Determinismus (CLAUDE.md Regel 9): kein `datetime.now()`, kein globales `random`, keine
Iteration über ungeordnete Mengen. Jede Phase zieht ihren eigenen Zufallsstrom über
:func:`random_for`, damit eine neue Phase die Ströme der anderen nicht verschiebt.

Alle Namen, Adressen, Bankleitzahlen und Steuernummern sind erfunden (CLAUDE.md Regel 8,
D-008). IBAN-Prüfziffern sind gültig, die Banken dahinter existieren nicht.
"""

import hashlib
import random
from datetime import date
from decimal import Decimal

#: Version des Generators – steht im Manifest neben Seed und Datenstand
GENERATOR_VERSION = "0.1"

#: Vorgabe-Seed; jeder Lauf mit diesem Seed erzeugt byte-identische Dateien
DEFAULT_SEED = 20260830

MANDT = "100"
COMPANY_CODES = ("1000", "2000")

#: Namen und Sitzland der Buchungskreise (T001). Der Mandant ist erfunden; das sind
#: keine Geschäftspartnerdaten, sondern die eigenen Buchungskreise des Demo-Kunden.
COMPANY_CODE_NAMES = {
    "1000": ("MDQ Demo Industrie AG", "DE"),
    "2000": ("MDQ Demo Vertrieb GmbH", "DE"),
}

#: V1 kennt genau eine Hauswährung (D-030); mehrere würden den Lauf abbrechen
LOCAL_CURRENCY = "EUR"

#: Postenfenster. Das Ende ist zugleich der Datenstand: ein Export kann keine Belege
#: enthalten, die nach dem Ziehungsdatum gebucht wurden (Victor, 2026-08-30).
WINDOW_START = date(2024, 9, 1)
WINDOW_END = date(2026, 8, 28)
DATA_AS_OF = WINDOW_END

#: Frühestes Anlagedatum der Stammsätze – ein gewachsener Mandant, die meisten Konten
#: sind älter als das Postenfenster. Für die Hygiene-Regeln ist das ungefährlich: jeder
#: Partner im Basis-Mandanten hat Posten im Fenster, und AR-HYG-001/AP-HYG-001 verlangen
#: "kein Posten im Fenster **und** ERDAT vor Fensterbeginn", AR-HYG-002 "ERDAT im Fenster,
#: älter als 12 Monate, kein Posten". Die Löschkandidaten entstehen erst in Aufgabe 2.
CREATED_FROM = date(2019, 1, 2)

CUSTOMER_COUNT = 2000
VENDOR_COUNT = 1500

#: Nummernkreise, zehnstellig mit führenden Nullen (D-009). Bewusst weiter als die
#: Anzahl der Konten, damit Lücken entstehen wie in einem gewachsenen Mandanten.
CUSTOMER_RANGE = (100000, 102999)
VENDOR_RANGE = (200000, 201999)

#: Konten der sechs Ankerfälle aus SPRINT-2.md. Sie werden hier schon als saubere
#: Partner angelegt; Aufgabe 2 überschreibt nur ihre Werte.
ANCHOR_CUSTOMERS = ("0000100234", "0000100987", "0000101502")
ANCHOR_VENDORS = ("0000200117", "0000200845", "0000201330")

#: Kontengruppen: die zweite ist jeweils die CpD-Gruppe (XCPDK = X)
CUSTOMER_ACCOUNT_GROUPS = ("DEBI", "KUNA")
VENDOR_ACCOUNT_GROUPS = ("KRED", "LIEF")
ONE_TIME_SHARE = 0.08

CUSTOMER_BANK_SHARE = 0.85
VENDOR_BANK_SHARE = 0.98

#: Zahlungsbedingungen. ZB01 und ZB02 sind gegenüber der ersten Fassung von SPRINT-2.md
#: getauscht (Victor, 2026-08-30): 14 Tage 2 % ist ZB02, damit das Beispiel-Finding
#: F-005 unverändert wahr bleibt (CLAUDE.md Regel 1).
#: (Schlüssel, Skontotage, Skontoprozent, Nettotage, Text)
PAYMENT_TERMS = (
    ("ZB00", 0, Decimal("0.000"), 0, "Sofort ohne Abzug"),
    ("ZB01", 10, Decimal("3.000"), 30, "10 Tage 3 % Skonto, 30 Tage netto"),
    ("ZB02", 14, Decimal("2.000"), 30, "14 Tage 2 % Skonto, 30 Tage netto"),
    ("ZB03", 0, Decimal("0.000"), 30, "30 Tage netto"),
    ("ZB04", 0, Decimal("0.000"), 60, "60 Tage netto"),
)

#: Verteilung der Zahlungsbedingungen auf die Stammsätze (Victor, 2026-08-30):
#: 2 % / 14 Tage ist die verbreitete Skontobedingung, 3 % / 10 Tage die seltenere;
#: die Kreditorenseite ist skontolastiger, damit AP-LEA-002 genug Fälle bekommt.
CUSTOMER_TERMS_WEIGHTS = {"ZB03": 50, "ZB02": 15, "ZB04": 15, "ZB01": 10, "ZB00": 10}
VENDOR_TERMS_WEIGHTS = {"ZB03": 40, "ZB02": 20, "ZB04": 20, "ZB01": 15, "ZB00": 5}

#: Zahlerprofil je Geschäftspartner (Victor, 2026-08-30). Das Profil hängt am Partner,
#: nicht am einzelnen Beleg – sonst verteilte sich der Skontoverlust über alle Kreditoren
#: und AP-LEA-002 träfe den halben Basis-Mandanten.
#: (Name, Anteil, mittlerer Verzug ab Nettofälligkeit in Tagen, Streuung)
PAYER_PROFILES = (
    ("skontotreu", 0.40, -2, 3),
    ("puenktlich", 0.45, 1, 4),
    ("schleppend", 0.15, 18, 8),
)

#: Anteil der Partner je Buchungskreis-Zuschnitt
COMPANY_CODE_SPLIT = ((("1000",), 0.70), (("2000",), 0.20), (("1000", "2000"), 0.10))

#: Wahrscheinlichkeit, dass eine Rechnung am Datenstand noch offen ist, nach Alter in
#: Tagen. Realistische Alterung statt einer festen Quote: junge Rechnungen sind meist
#: offen, alte meist ausgeglichen. Über alle Rechnungen ergibt das rund ein Drittel
#: offene Posten – die "~65 % ausgeglichen" aus SPRINT-2.md beziehen sich auf Rechnungen.
OPEN_PROBABILITY_BY_AGE = ((30, 0.85), (60, 0.55), (180, 0.35), (10_000, 0.28))

#: Anteil Gutschriften an den Rechnungen
CREDIT_MEMO_SHARE = 0.03

#: Obergrenze für entgangenes Skonto je Kreditor in 12 Monaten. AP-LEA-002 meldet ab
#: 1.000,00; der Basis-Mandant bleibt mit Sicherheitsabstand darunter, indem ein Zahler
#: das Skonto ausnahmsweise doch zieht, wenn die Grenze sonst gerissen würde.
SKONTO_LOSS_LIMIT = Decimal("500.00")

#: Belegartenkreise: (Belegart, Präfix der Belegnummer)
DOC_TYPES = {
    "customer_invoice": ("DR", "18"),
    "customer_payment": ("DZ", "14"),
    "customer_credit": ("DG", "16"),
    "vendor_invoice": ("KR", "19"),
    "vendor_payment": ("KZ", "15"),
    "vendor_credit": ("KG", "17"),
}

#: Abstimmkonten
RECON_ACCOUNT_CUSTOMER = "0000140000"
RECON_ACCOUNT_VENDOR = "0000160000"

#: Technische Anleger – Benutzerkennungen, keine Geschäftspartnerdaten (Regel 8)
SAP_USERS = ("SAPUSER1", "SAPUSER2", "SAPUSER3", "SAPUSER4", "SAPUSER5")

#: Reihenfolge, in der die Dateien geschrieben werden – zugleich die Reihenfolge im
#: Manifest, damit dessen Inhalt deterministisch ist.
TABLES = (
    "KNA1", "KNB1", "KNBK", "KNVP", "KNB5",
    "LFA1", "LFB1", "LFBK", "TIBAN",
    "BSID", "BSAD", "BSIK", "BSAK",
    "T001", "T052", "T052U",
)


def random_for(seed: int, label: str) -> random.Random:
    """Eigener Zufallsstrom je Phase, abgeleitet aus Seed und Bezeichner.

    Über sha1 statt `hash()`: der eingebaute Hash von Texten ist je Prozess anders
    (PYTHONHASHSEED) und wäre damit nicht deterministisch. Über getrennte Ströme
    verschiebt eine neue Phase die Ergebnisse der bestehenden nicht – wichtig, wenn
    Aufgabe 2 die Defektschicht ergänzt.
    """
    digest = hashlib.sha1(f"{seed}:{label}".encode()).hexdigest()
    return random.Random(int(digest[:16], 16))


#: Anzahl Rechnungen je Partner über das Fenster, nach Größenklasse (min, max)
INVOICE_COUNTS = {
    "CUSTOMER": {"klein": (4, 10), "mittel": (10, 22), "gross": (18, 40)},
    "VENDOR": {"klein": (2, 7), "mittel": (6, 14), "gross": (12, 28)},
}

#: Rechnungsbeträge je Größenklasse in Cent (min, max) – gezogen wird in Cent, damit
#: der Betrag ohne Umweg über float als Decimal entsteht (Regel 2)
INVOICE_AMOUNT_CENTS = {
    "klein": (20_000, 300_000),
    "mittel": (100_000, 2_500_000),
    "gross": (500_000, 12_000_000),
}
