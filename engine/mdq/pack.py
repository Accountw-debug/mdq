"""Version und Nachweis des Regelpakets ``logic/``.

Zwei Auskünfte, die jeder Lauf mitschreibt:

* ``pack_version`` und ``dict_version`` aus ``logic/pack.yaml`` – von Hand gepflegte
  Nummern. Sie sagen, was gemeint war, und stehen in jedem Finding bzw. in ``run.json``.
* ``pack_hash`` – ein sha256 über **alle** Dateien unter ``logic/``, in der Reihenfolge
  ihrer relativen Pfade, jeweils Pfad und Inhalt. Er sagt, ob das Paket wirklich
  unverändert war. Eine Nummer allein taete das nicht: sie bleibt stehen, wenn jemand
  eine Regel ändert und das Hochzählen vergisst (D-096).

Der Hash geht bewusst **nicht** in den ``run_id`` (D-093): der benennt die Daten und die
Frage, nicht den Code. Er steht in ``run.json`` und in ``run_meta``, damit ein Lauf sich
gegen sein Paket ausweisen kann.
"""

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from mdq import LOGIC_DIR, PACK_FILE

#: Schluessel auf oberster Ebene von ``pack.yaml``
TOP_LEVEL_KEYS = ("version", "pack_version", "dict_version")

#: Dateinamen, die nie Teil des Pakets sind – Betriebssystem- und Editor-Reste
IGNORED_NAMES = (".DS_Store", "Thumbs.db")


class PackError(ValueError):
    """``logic/pack.yaml`` fehlt, ist unlesbar oder unvollstaendig."""


@dataclass(frozen=True)
class Pack:
    """Das Regelpaket eines Laufs: gepflegte Nummern und der Nachweis darueber."""

    pack_version: str
    dict_version: str
    pack_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "pack": self.pack_version,
            "dict": self.dict_version,
            "pack_hash": self.pack_hash,
        }


def pack_files(logic_dir: Path = LOGIC_DIR) -> list[Path]:
    """Alle Dateien des Pakets, sortiert nach relativem Pfad (Regel 9)."""
    return sorted(
        (
            path
            for path in logic_dir.rglob("*")
            if path.is_file() and path.name not in IGNORED_NAMES
        ),
        key=lambda path: path.relative_to(logic_dir).as_posix(),
    )


def pack_hash(logic_dir: Path = LOGIC_DIR) -> str:
    """sha256 ueber Pfad **und** Inhalt jeder Paketdatei.

    Der Pfad geht mit ein, damit eine umbenannte Regel den Hash aendert – sonst waere
    ``AR-VAL-001`` unter neuem Namen dasselbe Paket. Gelesen wird binaer: eine Datei mit
    anderem Zeilenende ist ein anderes Paket, und genau das soll der Hash zeigen.
    """
    digest = hashlib.sha256()
    for path in pack_files(logic_dir):
        digest.update(path.relative_to(logic_dir).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def parse_pack(document: Any, path: Path, logic_dir: Path = LOGIC_DIR) -> Pack:
    """Prueft ein geladenes ``pack.yaml`` und meldet alle Probleme gemeinsam."""
    if not isinstance(document, dict):
        raise PackError(f"{path.name}: enthaelt kein Objekt")

    errors: list[str] = []
    unknown = sorted(set(document) - set(TOP_LEVEL_KEYS))
    if unknown:
        errors.append(f"unbekannte Schluessel: {unknown}")
    values: dict[str, str] = {}
    for key in TOP_LEVEL_KEYS:
        value = document.get(key)
        if not isinstance(value, str) or not value.strip():
            errors.append(f"{key}: muss ein nicht-leerer Text sein")
        else:
            values[key] = value
    if errors:
        joined = "\n    ".join(errors)
        raise PackError(f"{path.name}:\n    {joined}")

    return Pack(
        pack_version=values["pack_version"],
        dict_version=values["dict_version"],
        pack_hash=pack_hash(logic_dir),
    )


def load_pack(path: Path = PACK_FILE, logic_dir: Path = LOGIC_DIR) -> Pack:
    """Liest ``logic/pack.yaml`` und bildet den Paket-Hash."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise PackError(
            f"{path.name}: nicht als UTF-8 lesbar ({type(exc).__name__}) – ohne die Datei "
            "kennt der Lauf seine Paketversion nicht."
        ) from exc
    try:
        document = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise PackError(f"{path.name}: kein gueltiges YAML ({type(exc).__name__})") from exc
    return parse_pack(document, path, logic_dir)
