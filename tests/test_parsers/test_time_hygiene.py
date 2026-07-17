"""Guard: parsers must not read wall-clock time outside a freezable `_now()`.

A parser calling ``datetime.now()`` / ``utcnow()`` / ``date.today()`` / ``time.time()``
inline makes its output depend on the calendar, which silently re-introduces the
New-Year snapshot time-bomb (a December log parsed today vs. next year gets a
different inferred year, breaking `real_examples/**/*.expected.json`). The fix is a
module-level ``_now()`` indirection that the snapshot suite freezes
(`tests/test_real_examples/conftest.py`). This test fails the moment a parser
bypasses that indirection, so the convention is enforced, not just documented.
"""
from __future__ import annotations

import ast
from pathlib import Path

PARSERS_DIR = Path(__file__).resolve().parent.parent.parent / "backend" / "parsers"

# (object, attr) pairs that read the wall clock.
_WALLCLOCK = {
    ("datetime", "now"),
    ("datetime", "utcnow"),
    ("datetime", "today"),
    ("date", "today"),
    ("time", "time"),
    ("time", "monotonic"),
}


def _wallclock_calls_outside_now(tree: ast.AST) -> list[int]:
    now_funcs = [
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.FunctionDef) and n.name == "_now"
    ]

    def inside_now(lineno: int) -> bool:
        return any(
            f.lineno <= lineno <= (f.end_lineno or f.lineno) for f in now_funcs
        )

    hits: list[int] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            base = node.func.value
            if (
                isinstance(base, ast.Name)
                and (base.id, node.func.attr) in _WALLCLOCK
                and not inside_now(node.lineno)
            ):
                hits.append(node.lineno)
    return hits


def test_parsers_route_wallclock_through_now():
    offenders: dict[str, list[int]] = {}
    for path in sorted(PARSERS_DIR.glob("*.py")):
        if path.name in {"__init__.py", "registry.py"}:
            continue
        hits = _wallclock_calls_outside_now(ast.parse(path.read_text()))
        if hits:
            offenders[path.name] = hits
    assert not offenders, (
        "Parser(s) read wall-clock time outside a freezable _now() indirection "
        f"(snapshot time-bomb risk): {offenders}. Move the call into a module-level "
        "def _now(); tests/test_real_examples/conftest.py freezes every parser _now()."
    )
