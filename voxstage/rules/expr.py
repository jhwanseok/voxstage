"""A small expression language for flows (ADR 0010). Parsed with `ast`, checked against a whitelist at load time,
evaluated by a tree walker. Never `eval`.

Allowed: constants (str, int, float, bool, None); names; attribute access on mappings (`result.balance`) and
constant-index access (`items[0]`); comparisons (== != < <= > >= in not in); and / or / not; + - * / // %;
conditional expressions; list and tuple literals (so `in` has a right-hand side); calls only to the whitelisted
functions. Everything else is a load-time error that names the file, node and column.
"""

from __future__ import annotations

import ast
from collections.abc import Mapping
from typing import Any

FUNCTIONS = {"len": len, "lower": lambda s: str(s).lower(), "upper": lambda s: str(s).upper(),
             "int": int, "str": str}
RESERVED_NAMES = frozenset({"slots", "customer", "policy", "result"})

_BIN = {ast.Add: lambda a, b: a + b, ast.Sub: lambda a, b: a - b, ast.Mult: lambda a, b: a * b,
        ast.Div: lambda a, b: a / b, ast.FloorDiv: lambda a, b: a // b, ast.Mod: lambda a, b: a % b}
_CMP = {ast.Eq: lambda a, b: a == b, ast.NotEq: lambda a, b: a != b, ast.Lt: lambda a, b: a < b,
        ast.LtE: lambda a, b: a <= b, ast.Gt: lambda a, b: a > b, ast.GtE: lambda a, b: a >= b,
        ast.In: lambda a, b: a in b, ast.NotIn: lambda a, b: a not in b}


class ExprError(ValueError):
    """The expression is not allowed (load time) or could not be evaluated (run time)."""


class MissingAttribute(ExprError):
    """A field a flow reads is not there (`result.fee` absent). The flow fails visibly or uses an explicit default."""


class Expr:
    def __init__(self, source: str, tree: ast.Expression, where: str):
        self.source, self.tree, self.where = source, tree, where

    def evaluate(self, env: Mapping) -> Any:
        try:
            return _eval(self.tree.body, env)
        except ExprError:
            raise
        except Exception as exc:  # division by zero, missing key, type errors: say where
            raise ExprError(f"{self.where}: cannot evaluate `{self.source}`: {type(exc).__name__}: {exc}") from exc


def compile_expr(source: str, where: str, names: frozenset = frozenset()) -> Expr:
    """Parse and check. `names` are the identifiers the flow may use besides RESERVED_NAMES (its slots)."""
    try:
        tree = ast.parse(source.strip(), mode="eval")
    except SyntaxError as exc:
        raise ExprError(f"{where}: syntax error in `{source}` (column {exc.offset})") from exc
    allowed_names = RESERVED_NAMES | names
    called = {id(n.func) for n in ast.walk(tree) if isinstance(n, ast.Call)}
    for node in ast.walk(tree):
        _check(node, source, where, allowed_names)
        if isinstance(node, ast.Name) and node.id in FUNCTIONS and id(node) not in called:
            raise ExprError(f"{where}: function `{node.id}` must be called in `{source}`")
    return Expr(source, tree, where)


def _check(node: ast.AST, source: str, where: str, names: frozenset) -> None:
    def bad(what):
        col = getattr(node, "col_offset", 0) + 1
        raise ExprError(f"{where}: {what} is not allowed in `{source}` (column {col})")

    match node:
        case ast.Expression() | ast.BoolOp() | ast.IfExp() | ast.Load() | ast.And() | ast.Or() | ast.Not() \
                | ast.USub() | ast.UAdd() | ast.List() | ast.Tuple() | ast.Attribute():
            pass
        case ast.UnaryOp(op=ast.Not() | ast.USub() | ast.UAdd()):
            pass
        case ast.BinOp(op=op) if type(op) in _BIN:
            pass
        case op if type(op) in _BIN or type(op) in _CMP:
            pass
        case ast.Compare():
            pass
        case ast.Constant(value=v):
            if not (v is None or isinstance(v, (str, int, float, bool))):
                bad("this constant type")
        case ast.Name(id=name):
            if name not in names and name not in FUNCTIONS:
                bad(f"the name `{name}` (known: {sorted(names)})")
        case ast.Subscript(slice=sl):
            if not isinstance(sl, ast.Constant):
                bad("a non-constant index")
        case ast.Call(func=func, keywords=kws, args=args):
            if not (isinstance(func, ast.Name) and func.id in FUNCTIONS) or kws \
                    or any(isinstance(a, ast.Starred) for a in args):
                bad(f"this call (only {sorted(FUNCTIONS)} may be called, with plain arguments)")
        case _:
            bad(f"`{type(node).__name__}`")
    if isinstance(node, ast.Attribute) and node.attr.startswith("_"):
        bad("an attribute starting with an underscore")
    if isinstance(node, ast.UnaryOp) and type(node.op) not in (ast.Not, ast.USub, ast.UAdd):
        bad("this unary operator")


def _eval(node: ast.AST, env: Mapping) -> Any:
    match node:
        case ast.Constant(value=v):
            return v
        case ast.Name(id=name):
            if name in FUNCTIONS:
                raise ExprError(f"function `{name}` used without a call")
            if name not in env:
                raise ExprError(f"`{name}` has no value yet")
            return env[name]
        case ast.Attribute(value=value, attr=attr):
            base = _eval(value, env)
            if not isinstance(base, Mapping) or attr not in base:
                raise MissingAttribute(f"no field `{attr}`")
            return base[attr]
        case ast.Subscript(value=value, slice=ast.Constant(value=index)):
            return _eval(value, env)[index]
        case ast.BoolOp(op=op, values=values):
            result = None
            for v in values:
                result = _eval(v, env)
                if isinstance(op, ast.And) and not result:
                    return result
                if isinstance(op, ast.Or) and result:
                    return result
            return result
        case ast.UnaryOp(op=op, operand=operand):
            v = _eval(operand, env)
            return (not v) if isinstance(op, ast.Not) else (-v if isinstance(op, ast.USub) else +v)
        case ast.BinOp(left=left, op=op, right=right):
            return _BIN[type(op)](_eval(left, env), _eval(right, env))
        case ast.Compare(left=left, ops=ops, comparators=comps):
            cur = _eval(left, env)
            for op, comp in zip(ops, comps):
                nxt = _eval(comp, env)
                if not _CMP[type(op)](cur, nxt):
                    return False
                cur = nxt
            return True
        case ast.IfExp(test=test, body=body, orelse=orelse):
            return _eval(body if _eval(test, env) else orelse, env)
        case ast.List(elts=elts) | ast.Tuple(elts=elts):
            return [_eval(e, env) for e in elts]
        case ast.Call(func=ast.Name(id=name), args=args):
            return FUNCTIONS[name](*[_eval(a, env) for a in args])
    raise ExprError(f"cannot evaluate `{type(node).__name__}`")
