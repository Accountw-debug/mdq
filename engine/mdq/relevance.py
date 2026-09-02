"""BP-360: ``bp_relevance`` materialisieren, Hauswaehrung des Laufs bestimmen.

Die vierte Stufe zwischen kanonischem Modell und Regeln. Sie beantwortet je
Geschaeftspartner drei Fragen, die fast jedes Finding braucht, um gewichtet werden zu
koennen: Wie viel steht offen? Wie viel Geschaeft lief in zwoelf Monaten? Wann hat sich
das Konto zuletzt bewegt?

Die Definitionen stehen im Glossar und sind hier eins zu eins umgesetzt:

* ``open_items_local`` – Summe der am Datenstand nicht ausgeglichenen Posten.
* ``volume_12m_local`` – Rechnungen brutto minus Gutschriften mit Buchungsdatum im
  Relevanzfenster, **unabhaengig vom Ausgleich** (D-051). Was eine Rechnung und was eine
  Gutschrift ist, sagt ``logic/dictionaries/document_types.yaml`` – nicht eine Liste in
  diesem Modul (D-084).
* ``last_activity_on`` – spaetestes Datum aus Buchungs- und Ausgleichsdatum; ein Konto
  ohne Posten hat keines (D-062). Gezaehlt wird nur, was **am Datenstand** schon
  geschehen war: eine Bewegung nach ``data_as_of`` ist zu diesem Datenstand keine
  Aktivitaet (D-087, D-206).
* ``activity_status`` – ``active``, ``dormant`` oder ``never_posted`` nach D-086. Er
  liest ``last_activity_on`` und misst damit dasselbe Fenster wie ``volume_12m``:
  ``]window_from, data_as_of]``, links offen, rechts geschlossen.

Beide Betraege stehen in der Fachlogik ihrer Seite: eine Forderung und eine
Verbindlichkeit sind beide positiv (D-085). Die Waehrung steht daneben und wird nicht
umgerechnet (Regel 2, D-030); sie kommt aus ``company_code`` und damit aus T001 (D-083).
Fehlt diese Tabelle, bricht die Stufe ab – ein Betrag ohne Waehrung waere die
stillschweigend falsch etikettierte Zahl, die D-030 verhindern soll.
"""

import calendar
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

import duckdb

from mdq.dictionaries import DocumentTypes, load_document_types

#: Laenge des Relevanzfensters in Monaten. Ein Aktualitaetsbegriff, nicht zwei:
#: ``volume_12m`` und ``activity_status`` messen dasselbe Fenster (D-086).
WINDOW_MONTHS = 12

#: Die drei Aktivitaetsstufen – wie im CHECK von ``bp_relevance.activity_status``
STATUS_ACTIVE = "active"
STATUS_DORMANT = "dormant"
STATUS_NEVER_POSTED = "never_posted"
STATUS_ORDER = (STATUS_ACTIVE, STATUS_DORMANT, STATUS_NEVER_POSTED)

#: Quelle des Datenstands, so wie sie im Report steht
SOURCE_GIVEN = "--data-as-of"
SOURCE_DERIVED = "spaetestes Buchungs-/Ausgleichsdatum der Posten"


class RelevanceError(ValueError):
    """Die Relevanzstufe kann nicht gebildet werden – der Lauf bricht ab."""


def multiple_currencies_message(currencies: list[str]) -> str:
    """Die eine Meldung zu mehreren Hauswaehrungen – hier, damit sie nur einmal existiert."""
    return (
        f"Mehrere Hauswaehrungen im Scope des Laufs: {currencies}. "
        "V1 rechnet nicht um – Lauf je Hauswaehrung getrennt starten "
        "(--company-codes einschraenken). Umrechnung ueber TCURR ist V2 (D-030)."
    )


@dataclass(frozen=True)
class RelevanceResult:
    """Was die Stufe gebildet hat – die Zahlen des Run-Reports."""

    data_as_of: date
    data_as_of_source: str
    house_currency: str
    window_from: date
    partners: int
    by_status: tuple[tuple[str, int], ...]
    open_items_total: str
    volume_12m_total: str
    warnings: tuple[str, ...] = ()

    @property
    def window_months_text(self) -> str:
        """Fensterlaenge im Klartext – der Report nennt sie neben den Datumsgrenzen."""
        return f"{WINDOW_MONTHS} Monate"

    def to_dict(self) -> dict[str, Any]:
        return {
            "data_as_of": self.data_as_of.isoformat(),
            "data_as_of_source": self.data_as_of_source,
            "house_currency": self.house_currency,
            "window_from": self.window_from.isoformat(),
            "window_months": WINDOW_MONTHS,
            "partners": self.partners,
            "by_status": [
                {"status": status, "partners": count} for status, count in self.by_status
            ],
            "open_items_total": self.open_items_total,
            "volume_12m_total": self.volume_12m_total,
            "warnings": list(self.warnings),
        }


def _table_exists(con: duckdb.DuckDBPyConnection, name: str) -> bool:
    rows = con.execute("SELECT table_name FROM duckdb_tables()").fetchall()
    return name in {row[0] for row in rows}


def house_currency(con: duckdb.DuckDBPyConnection) -> str:
    """Die eine Hauswaehrung des Laufs, aus ``company_code`` (T001, D-083).

    Kein Ersatzwert und kein Schalter: die Hauswaehrung ist eine Stammdatenauskunft des
    Mandanten, keine Angabe des Anwenders. Fehlt T001, sagt die Meldung genau das.
    Mehrere Waehrungen im Scope brechen den Lauf ab (D-030).
    """
    if not _table_exists(con, "company_code"):
        raise RelevanceError(
            "Tabelle company_code fehlt – die Stufe canonical wurde nicht gebaut."
        )
    rows = con.execute(
        "SELECT DISTINCT currency FROM company_code WHERE currency IS NOT NULL ORDER BY currency"
    ).fetchall()
    currencies = [row[0] for row in rows]
    if not currencies:
        raise RelevanceError(
            "Keine Hauswaehrung im Scope: die Exportdatei T001 fehlt oder enthaelt keinen "
            "der gewaehlten Buchungskreise. T001 (BUKRS, BUTXT, WAERS, LAND1) mitliefern – "
            "ohne sie ist DMBTR ein Betrag ohne Waehrung (Regel 2, D-083)."
        )
    if len(currencies) > 1:
        raise RelevanceError(multiple_currencies_message(currencies))
    return currencies[0]


def resolve_data_as_of(
    con: duckdb.DuckDBPyConnection, given: date | None = None
) -> tuple[date, str]:
    """Datenstand des Laufs und woher er kommt – nie eine stille Annahme.

    Ohne ``--data-as-of`` gilt das spaeteste Buchungs- oder Ausgleichsdatum der Posten:
    ein Export kann keine Bewegung nach seinem Ziehungsdatum enthalten. Gibt es keinen
    Posten, gibt es auch kein ableitbares Datum – dann ist die Angabe Pflicht.
    """
    if given is not None:
        return given, SOURCE_GIVEN
    if not _table_exists(con, "fi_item"):
        raise RelevanceError(
            "Tabelle fi_item fehlt – der Datenstand laesst sich nicht ableiten. "
            "--data-as-of angeben."
        )
    latest = con.execute(
        "SELECT max(greatest(posting_date, coalesce(clearing_date, posting_date))) FROM fi_item"
    ).fetchone()[0]
    if latest is None:
        raise RelevanceError(
            "Kein Posten im Lauf – der Datenstand laesst sich nicht aus den Daten "
            "ableiten. --data-as-of JJJJ-MM-TT angeben."
        )
    return latest, SOURCE_DERIVED


def _literal_list(values: tuple[str, ...]) -> str:
    """Werteliste fuer ``IN``; leer wird zu ``NULL``, das nie trifft."""
    if not values:
        return "NULL"
    return ", ".join("'" + value.replace("'", "''") + "'" for value in values)


def _unclassified(
    con: duckdb.DuckDBPyConnection, doc_types: DocumentTypes
) -> list[str]:
    """Belegarten in den Posten, die das Woerterbuch keiner Klasse zuordnet.

    Sie zaehlen nicht in ``volume_12m`` – das darf nicht stillschweigend passieren
    (Regel 4). Belegarten sind Customizing, keine Geschaeftspartnerdaten (Regel 8).
    """
    warnings: list[str] = []
    for role in ("CUSTOMER", "VENDOR"):
        known = doc_types.for_role(role, "invoice", "credit_memo", "payment", "reversal")
        rows = con.execute(
            "SELECT i.doc_type, count(*) FROM fi_item i JOIN business_partner bp "
            "ON bp.bp_key = i.bp_key WHERE bp.role = ? AND i.doc_type IS NOT NULL "
            f"AND i.doc_type NOT IN ({_literal_list(known)}) "
            "GROUP BY 1 ORDER BY 1",
            [role],
        ).fetchall()
        if rows:
            named = ", ".join(f"{doc_type} ({count})" for doc_type, count in rows)
            warnings.append(
                f"bp_relevance: Belegarten ohne Klasse in {role}: {named}. Sie zaehlen nicht "
                "in volume_12m – Klasse in logic/dictionaries/document_types.yaml ergaenzen."
            )
    return warnings


def _amount(value: Any) -> str:
    """Betrag als Text mit zwei Dezimalen – nie als float (Regel 2)."""
    return format(Decimal(value if value is not None else 0), ".2f")


def window_start(as_of: date, months: int = WINDOW_MONTHS) -> date:
    """Beginn des Relevanzfensters: ``months`` Monate vor dem Datenstand, **exklusiv**.

    Das Fenster ist links offen und rechts geschlossen (D-087): der Beleg vom selben Tag
    ein Jahr zuvor gehoert sonst in zwei aufeinanderfolgende Fenster. Gibt es den Tag im
    Zielmonat nicht (29. Februar), gilt der letzte Tag des Monats.
    """
    year, month = divmod(as_of.year * 12 + as_of.month - 1 - months, 12)
    month += 1
    day = min(as_of.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def build_relevance(
    con: duckdb.DuckDBPyConnection,
    data_as_of: date | None = None,
    doc_types: DocumentTypes | None = None,
) -> RelevanceResult:
    """Fuellt ``bp_relevance`` fuer jeden Partner des kanonischen Modells.

    Jeder Partner bekommt eine Zeile, auch der ohne einen einzigen Posten: eine fehlende
    Zeile waere im Finding eine fehlende Relevanz und damit ein stiller Unterschied
    zwischen "null Umsatz" und "nicht berechnet" (Regel 4).
    """
    for required in ("business_partner", "fi_item", "bp_relevance"):
        if not _table_exists(con, required):
            raise RelevanceError(
                f"Tabelle {required} fehlt – die Stufe canonical wurde nicht gebaut."
            )

    currency = house_currency(con)
    as_of, source = resolve_data_as_of(con, data_as_of)
    types = doc_types or load_document_types()
    window_from = window_start(as_of)

    volume_classes = ("invoice", "credit_memo")
    ar_types = _literal_list(types.for_role("CUSTOMER", *volume_classes))
    ap_types = _literal_list(types.for_role("VENDOR", *volume_classes))

    con.execute("DELETE FROM bp_relevance")
    con.execute(
        f"""
        INSERT INTO bp_relevance
            (bp_key, open_items_local, volume_12m_local, currency,
             last_activity_on, activity_status)
        WITH item AS (
            SELECT i.bp_key,
                   bp.role,
                   i.is_open,
                   i.amount_signed_local,
                   i.posting_date,
                   i.clearing_date,
                   -- Forderung und Verbindlichkeit sind beide positiv (D-085): beim
                   -- Kreditor sind Rechnungen Haben und damit negativ signiert.
                   CASE WHEN bp.role = 'VENDOR' THEN -1 ELSE 1 END AS side_sign,
                   CASE
                       WHEN bp.role = 'CUSTOMER' THEN i.doc_type IN ({ar_types})
                       ELSE i.doc_type IN ({ap_types})
                   END AS counts_for_volume
            FROM fi_item i
            JOIN business_partner bp ON bp.bp_key = i.bp_key
        ),
        agg AS (
            SELECT bp_key,
                   sum(CASE WHEN is_open THEN side_sign * amount_signed_local ELSE 0 END)
                       AS open_items,
                   sum(CASE
                           WHEN counts_for_volume
                            AND posting_date > $window_from
                            AND posting_date <= $as_of
                           THEN side_sign * amount_signed_local ELSE 0
                       END) AS volume_12m,
                   -- Die letzte Aktivitaet **am Datenstand**: eine Bewegung nach dem
                   -- Datenstand hat es zu diesem Datenstand noch nicht gegeben (D-087).
                   -- Gekappt wird je Datum und nicht am Ergebnis: eine Rechnung, die im
                   -- Fenster gebucht und erst nach dem Datenstand ausgeglichen wurde,
                   -- bleibt mit ihrem Buchungsdatum eine Aktivitaet. `greatest` uebergeht
                   -- NULL, `max` ebenso - ein Posten ganz jenseits des Datenstands traegt
                   -- damit gar nichts bei.
                   max(greatest(
                       CASE WHEN posting_date <= $as_of THEN posting_date END,
                       CASE WHEN clearing_date <= $as_of THEN clearing_date END
                   )) AS last_activity_on
            FROM item
            GROUP BY bp_key
        )
        SELECT bp.bp_key,
               CAST(coalesce(a.open_items, 0) AS DECIMAL(15,2)),
               CAST(coalesce(a.volume_12m, 0) AS DECIMAL(15,2)),
               $currency,
               a.last_activity_on,
               CASE
                   -- Kein Posten, aber im Fenster angelegt: das Konto konnte sich noch
                   -- gar nicht bewegen (D-086).
                   WHEN a.bp_key IS NULL AND bp.created_on IS NOT NULL
                        AND bp.created_on > $window_from THEN '{STATUS_NEVER_POSTED}'
                   WHEN a.last_activity_on IS NULL
                        OR a.last_activity_on <= $window_from THEN '{STATUS_DORMANT}'
                   ELSE '{STATUS_ACTIVE}'
               END
        FROM business_partner bp
        LEFT JOIN agg a ON a.bp_key = bp.bp_key
        ORDER BY bp.bp_key
        """,
        {"window_from": window_from, "as_of": as_of, "currency": currency},
    )

    partners, open_total, volume_total = con.execute(
        "SELECT count(*), sum(open_items_local), sum(volume_12m_local) FROM bp_relevance"
    ).fetchone()
    counted = dict(
        con.execute(
            "SELECT activity_status, count(*) FROM bp_relevance GROUP BY 1"
        ).fetchall()
    )
    return RelevanceResult(
        data_as_of=as_of,
        data_as_of_source=source,
        house_currency=currency,
        window_from=window_from,
        partners=partners,
        by_status=tuple((status, counted.get(status, 0)) for status in STATUS_ORDER),
        open_items_total=_amount(open_total),
        volume_12m_total=_amount(volume_total),
        warnings=tuple(_unclassified(con, types)),
    )


