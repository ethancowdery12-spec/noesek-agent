"""calc: safe, instant arithmetic for the chat (Ethan's ask, Sep 24).

Quick math ("18% of 240", "37 x 412", monthly payment on a mortgage) should
not need a code-interpreter spin-up or an LLM doing arithmetic in its head -
it is a deterministic AST eval over a whitelist. Stdlib only, zero deps,
own implementation.

Safety shape: expressions parse to a small node whitelist (numbers, + - * /
// % **, parentheses, unary signs, whitelisted math functions, pi/e/tau).
No names, attributes, calls outside the whitelist, or comprehensions ever
evaluate. Pow and factorial are capped so 9**9**9 or factorial(10**9)
cannot burn the process.
"""
from __future__ import annotations

import ast
import math
import operator

from pydantic import BaseModel, Field

_MAX_LEN = 300
_MAX_DEPTH = 40
_MAX_POW_EXP = 999
_MAX_FACTORIAL = 5000

_FUNCS = {n: getattr(math, n) for n in
          ("sqrt", "log", "log2", "log10", "exp", "sin", "cos", "tan",
           "asin", "acos", "atan", "floor", "ceil", "fabs", "gcd", "factorial", "comb", "perm")}
_FUNCS.update({"abs": abs, "round": round, "min": min, "max": max})
_CONSTS = {"pi": math.pi, "e": math.e, "tau": math.tau}
_BIN = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
        ast.Div: operator.truediv, ast.FloorDiv: operator.floordiv,
        ast.Mod: operator.mod, ast.Pow: operator.pow}


class CalcInput(BaseModel):
    expression: str = Field(min_length=1, max_length=_MAX_LEN,
                            description="Arithmetic expression, e.g. 0.18*240, 37*412, sqrt(2_000_000), "
                                        "10000*(1+0.05/12)**36. Percent: write 18% as 0.18. "
                                        "Functions: sqrt log log2 log10 exp sin cos tan asin acos atan floor ceil abs round min max gcd factorial comb perm. Constants: pi e tau.")
    precision: int = Field(default=10, ge=1, le=15, description="Significant digits in the result")


class _CalcError(ValueError):
    pass


def _eval(node: ast.AST, depth: int = 0):
    if depth > _MAX_DEPTH:
        raise _CalcError("expression nested too deep")
    if isinstance(node, ast.Expression):
        return _eval(node.body, depth + 1)
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
            raise _CalcError("only numeric literals allowed")
        return node.value
    if isinstance(node, ast.Name):
        if node.id in _CONSTS:
            return _CONSTS[node.id]
        raise _CalcError(f"unknown name {node.id!r} - constants: pi, e, tau")
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        v = _eval(node.operand, depth + 1)
        return v if isinstance(node.op, ast.UAdd) else -v
    if isinstance(node, ast.BinOp) and type(node.op) in _BIN:
        left, right = _eval(node.left, depth + 1), _eval(node.right, depth + 1)
        if isinstance(node.op, ast.Pow):
            if abs(right) > _MAX_POW_EXP or (abs(left) > 1e15 and abs(right) > 2):
                raise _CalcError("exponent too large")
        if isinstance(node.op, (ast.Div, ast.FloorDiv, ast.Mod)) and right == 0:
            raise _CalcError("division by zero")
        return _BIN[type(node.op)](left, right)
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _FUNCS:
        if node.keywords:
            raise _CalcError("keyword arguments not supported")
        args = [_eval(a, depth + 1) for a in node.args]
        if node.func.id == "factorial":
            if len(args) != 1 or not isinstance(args[0], int) or args[0] < 0 or args[0] > _MAX_FACTORIAL:
                raise _CalcError(f"factorial needs an integer 0..{_MAX_FACTORIAL}")
        if node.func.id in ("comb", "perm", "gcd"):
            if not all(isinstance(a, int) for a in args):
                raise _CalcError(f"{node.func.id} needs integer arguments")
        try:
            return _FUNCS[node.func.id](*args)
        except OverflowError:
            raise _CalcError("result too large")
        except ValueError as e:
            raise _CalcError(str(e))
    raise _CalcError("only arithmetic and whitelisted math functions are allowed")


def calc(inp: CalcInput) -> dict:
    try:
        tree = ast.parse(inp.expression.strip(), mode="eval")
    except SyntaxError:
        return {"error": f"could not parse {inp.expression!r} - use * for multiply, / for divide, ** for powers"}
    try:
        result = _eval(tree)
    except _CalcError as e:
        return {"error": str(e)}
    if isinstance(result, float):
        if math.isnan(result) or math.isinf(result):
            return {"error": "result is not a finite number"}
        # collapse float noise at the requested precision (0.18*240 -> 43.2, not 43.199...)
        result = float(f"{result:.{inp.precision}g}")
        if result == int(result) and abs(result) < 1e15:
            result = int(result)
    return {"expression": inp.expression, "result": result}
