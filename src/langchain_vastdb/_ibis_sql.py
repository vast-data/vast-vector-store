"""Convert ibis deferred predicates to SQL WHERE fragments.

# TODO: Replace this hand-rolled ibis AST walker with the upstream VastDB
# SQLAlchemy dialect once it is available:
# https://git.vastdata.com/genai/sqlalchemy-vastdb
#
# That dialect compiles ibis expressions through SQLAlchemy's standard
# compilation path, which is more robust and covers the full ibis expression
# language without relying on private ibis resolver internals.
"""

from __future__ import annotations

import math
import operator as _operator

import ibis

_IBIS_COMPARISON_OPS: dict[object, str] = {
    _operator.eq: "=",
    _operator.ne: "!=",
    _operator.lt: "<",
    _operator.le: "<=",
    _operator.gt: ">",
    _operator.ge: ">=",
}


def _ibis_literal_to_sql(val: object) -> str:
    if val is None:
        return "NULL"
    if isinstance(val, bool):
        return "TRUE" if val else "FALSE"
    if isinstance(val, str):
        return "'" + val.replace("'", "''") + "'"
    if isinstance(val, (int, float)):
        if isinstance(val, float) and not math.isfinite(val):
            raise ValueError(f"Non-finite float {val!r} is not a valid SQL literal")
        return str(val)
    raise TypeError(
        f"Unsupported filter literal type {type(val).__name__!r}: {val!r}"
    )


def _ibis_col_sql(item_node: object) -> str:
    """Return a quoted SQL identifier from an ibis resolver Item node."""
    name: str = item_node.indexer.value  # type: ignore[attr-defined]
    return '"' + name.replace('"', '""') + '"'


def _ibis_resolver_to_sql(node: object) -> str:
    """Recursively convert an ibis ``_resolver`` node to a SQL WHERE fragment."""
    t = type(node).__name__
    if t == "BinaryOperator":
        f = node.func  # type: ignore[attr-defined]
        if f is _operator.and_:
            return (
                f"({_ibis_resolver_to_sql(node.left)})"  # type: ignore[attr-defined]
                f" AND "
                f"({_ibis_resolver_to_sql(node.right)})"  # type: ignore[attr-defined]
            )
        if f is _operator.or_:
            return (
                f"({_ibis_resolver_to_sql(node.left)})"  # type: ignore[attr-defined]
                f" OR "
                f"({_ibis_resolver_to_sql(node.right)})"  # type: ignore[attr-defined]
            )
        if f in _IBIS_COMPARISON_OPS:
            return (
                f"{_ibis_resolver_to_sql(node.left)}"  # type: ignore[attr-defined]
                f" {_IBIS_COMPARISON_OPS[f]} "
                f"{_ibis_resolver_to_sql(node.right)}"  # type: ignore[attr-defined]
            )
        raise TypeError(f"Unsupported ibis binary operator: {f!r}")
    if t == "UnaryOperator":
        if node.func is _operator.invert:  # type: ignore[attr-defined]
            return f"NOT ({_ibis_resolver_to_sql(node.arg)})"  # type: ignore[attr-defined]
        raise TypeError(f"Unsupported ibis unary operator: {node.func!r}")  # type: ignore[attr-defined]
    if t == "Call":
        method: str = node.func.name.value  # type: ignore[attr-defined]  # Attr.name is a Just
        col_sql = _ibis_col_sql(node.func.obj)  # type: ignore[attr-defined]  # Attr.obj is an Item
        seq = node.args[0]  # type: ignore[attr-defined]  # Sequence node
        sql_vals = [_ibis_literal_to_sql(v.value) for v in seq.values]
        if method == "isin":
            return "1=0" if not sql_vals else "(" + " OR ".join(f"{col_sql} = {v}" for v in sql_vals) + ")"
        if method == "notin":
            return "1=1" if not sql_vals else "(" + " AND ".join(f"{col_sql} != {v}" for v in sql_vals) + ")"
        raise TypeError(f"Unsupported ibis method call: {method!r}")
    if t == "Item":
        return _ibis_col_sql(node)
    if t == "Just":
        return _ibis_literal_to_sql(node.value)  # type: ignore[attr-defined]
    raise TypeError(f"Unsupported ibis resolver node type {t!r}: {node!r}")


def predicate_to_sql_where(predicate: ibis.Expr) -> str:
    """Convert an ``ibis._`` deferred predicate to a SQL WHERE fragment (no leading WHERE).

    Supports: ``==``, ``!=``, ``<``, ``<=``, ``>``, ``>=``, ``&`` (AND),
    ``|`` (OR), ``~`` (NOT), ``.isin()`` (OR equality chain), and
    ``.notin()`` (AND inequality chain).

    Args:
        predicate: An ibis deferred filter expression built with ``ibis._``.

    Returns:
        A SQL string suitable for insertion after ``WHERE``.

    Raises:
        TypeError: If the predicate is not a deferred ibis expression or contains
            an unsupported node type or operator.
    """
    if not hasattr(predicate, "_resolver"):
        raise TypeError(
            "predicate must be a deferred ibis expression built with ibis._, "
            f"got {type(predicate).__name__!r}"
        )
    return _ibis_resolver_to_sql(predicate._resolver)  # type: ignore[attr-defined]
