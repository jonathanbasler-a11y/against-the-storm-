"""Felder im Spielstand finden, ohne die Pfade auswendig zu kennen.

Phase 0 hat gezeigt, wie die Felder heissen -- `time`, `reputationPenalty`,
`hostility` als Dictionary -- aber nicht durchgaengig, wo genau sie stehen.
Und die Spec verlangt Robustheit gegen Formataenderungen: unbekannte Felder
ignorieren, fehlende Felder zu None machen, kein harter Abbruch.

Deshalb sucht dieses Modul jedes Feld zweistufig: erst an den bekannten
Pfaden, dann als flachster Schluessel mit passendem Namen. Woher ein Wert
stammt, wird protokolliert -- damit steht nach dem ersten echten Lauf fest,
welche Pfade sich festnageln lassen.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable

# Eine Ware heisst im Save "[Food Raw] Meat". Praefixe koennen sich stapeln:
# "[SSE] [BIOME] Storm Penalty" stand so im Spielstand. Ein Abschneider, der
# genau einmal zuschlaegt, legt zwei Schluessel fuer dieselbe Sache an.
PREFIX_RE = re.compile(r"^\s*\[([^\]]+)\]\s*")


def strip_prefixes(name: str) -> tuple[str, list[str]]:
    """'[SSE] [BIOME] Storm Penalty' -> ('Storm Penalty', ['SSE', 'BIOME'])."""
    prefixes: list[str] = []
    rest = name
    while True:
        m = PREFIX_RE.match(rest)
        if not m:
            return rest.strip(), prefixes
        prefixes.append(m.group(1).strip())
        rest = rest[m.end():]


@dataclass
class Resolution:
    """Woher ein Feld kam. Fuer das Protokoll, nicht fuer die Logik."""

    field: str
    path: str | None
    how: str  # "pfad", "suche", "fehlt" oder "form_unbekannt"
    depth: int | None = None
    # Nur bei "form_unbekannt": Schluessel und Typen des Gefundenen, keine
    # Werte. Damit laesst sich aus einer Zeile ablesen, wie das Spiel es
    # wirklich ablegt.
    form: str | None = None


@dataclass
class KeyIndex:
    """Flachster Fund je Schluesselname, plus Trefferzahl."""

    by_name: dict[str, tuple[str, Any, int]] = field(default_factory=dict)
    counts: dict[str, int] = field(default_factory=dict)

    def add(self, name: str, path: str, value: Any, depth: int) -> None:
        self.counts[name] = self.counts.get(name, 0) + 1
        seen = self.by_name.get(name)
        if seen is None or depth < seen[2]:
            self.by_name[name] = (path, value, depth)

    def get(self, name: str) -> tuple[str, Any, int] | None:
        return self.by_name.get(name)


def index_keys(data: Any, max_nodes: int = 3_000_000) -> KeyIndex:
    """Einmal durch den Baum, flachster Fund je Schluesselname gewinnt."""
    idx = KeyIndex()
    stack: list[tuple[Any, str, int]] = [(data, "$", 0)]
    nodes = 0
    while stack:
        node, path, depth = stack.pop()
        nodes += 1
        if nodes > max_nodes:
            break
        if isinstance(node, dict):
            for k, v in node.items():
                idx.add(k, f"{path}.{k}", v, depth + 1)
                if isinstance(v, (dict, list)):
                    stack.append((v, f"{path}.{k}", depth + 1))
        elif isinstance(node, list):
            for i, v in enumerate(node[:400]):
                if isinstance(v, (dict, list)):
                    stack.append((v, f"{path}[{i}]", depth + 1))
    return idx


def by_path(data: Any, dotted: str) -> tuple[bool, Any]:
    """Punktpfad aufloesen, ohne bei fehlenden Zwischenstufen zu scheitern."""
    cur = data
    for part in dotted.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return False, None
    return True, cur


def resolve(
    data: Any,
    idx: KeyIndex,
    name: str,
    paths: Iterable[str] = (),
    keys: Iterable[str] = (),
    want: type | tuple[type, ...] | None = None,
) -> tuple[Any, Resolution]:
    """Erst die bekannten Pfade, dann die Namenssuche, sonst None."""
    for dotted in paths:
        found, value = by_path(data, dotted)
        if found and (want is None or isinstance(value, want)):
            return value, Resolution(name, f"$.{dotted}", "pfad")

    best: tuple[str, Any, int] | None = None
    for key in keys:
        hit = idx.get(key)
        if hit is None:
            continue
        if want is not None and not isinstance(hit[1], want):
            continue
        if best is None or hit[2] < best[2]:
            best = hit
    if best is not None:
        return best[1], Resolution(name, best[0], "suche", best[2])

    return None, Resolution(name, None, "fehlt")
