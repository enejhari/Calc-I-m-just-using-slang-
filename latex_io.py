"""
Bridge between the web editor (MathLive, which speaks LaTeX) and the engine in calc.py.

    latex_to_expr(r"\frac{1+i}{2}", deg)  ->  "((1+i)/(2))"    (text the calc.py parser understands)
    value_latex(value)                    ->  r"\frac{1}{2}+\frac{7}{2}i"
"""

import re

from calc import FUNCS, CalcError, value_parts

_SIMPLE = {
    "cdot": "*", "times": "*", "ast": "*", "div": "/", "pi": "pi", "mathrm{e}": "e",
    "imaginaryI": "i", "imaginaryJ": "i", "exponentialE": "e", "lparen": "(", "rparen": ")",
    "lbrack": "(", "rbrack": ")", "{": "(", "}": ")", "%": "*0.01",
}
_SPACES = {",", ";", ":", "!", " ", "quad", "qquad", "enspace", "thinspace", "colon"}
_TEXT_CMDS = {"mathrm", "operatorname", "text", "textrm", "mathit", "mathbf", "mathnormal", "mathsf"}
_SIZE_CMDS = {"left", "right", "bigl", "bigr", "Bigl", "Bigr", "biggl", "biggr", "big", "Big",
              "middle"}
_FRACS = {"frac", "dfrac", "tfrac", "cfrac"}
_BARS = {"|", "\\vert", "\\lvert", "\\rvert", "\\mid"}


def latex_to_expr(latex, deg=False):
    """Translate MathLive LaTeX into a linear expression for calc.Evaluator."""
    s = latex.replace("{,}", ".")
    toks = re.findall(r"\\[a-zA-Z]+|\\.|\S", s)
    pos = 0
    bar_open = [False]

    def peek(k=0):
        return toks[pos + k] if pos + k < len(toks) else None

    def take():
        nonlocal pos
        if pos >= len(toks):
            raise CalcError("Expression is incomplete")
        pos += 1
        return toks[pos - 1]

    def seq(stop=None):
        out = []
        while True:
            t = peek()
            if t is None:
                if stop is not None:
                    raise CalcError("Expression is incomplete")
                return "".join(out)
            if t == stop:
                take()
                return "".join(out)
            out.append(one())

    def arg():
        if peek() == "{":
            take()
            return seq("}")
        return one()

    def degree():
        return "" if deg else "*(pi/180)"

    def one():
        t = take()
        if t == "{":
            g = seq("}")
            return f"({g})" if g else ""
        if t == "^":
            if peek() == "\\circ":
                take()
                return degree()
            if peek() == "{" and peek(1) == "\\circ" and peek(2) == "}":
                take(), take(), take()
                return degree()
            return f"^({arg()})"
        if t == "_":                      # stray subscript: ignore
            arg()
            return ""
        if t == "|":
            bar_open[0] = not bar_open[0]
            return "abs(" if bar_open[0] else ")"
        if not t.startswith("\\"):
            return t
        name = t[1:]
        if name in _FRACS:
            a = arg()
            b = arg()
            return f"(({a})/({b}))"
        if name == "sqrt":
            n = None
            if peek() == "[":
                take()
                n = seq("]")
            a = arg()
            return f"sqrt({a})" if n is None else f"root({a},{n})"
        if name in _SIZE_CMDS:
            d = take()
            if d in _BARS:
                return "abs(" if name.endswith(("left", "l")) else ")"
            if d == ".":
                return ""
            return _SIMPLE.get(d.lstrip("\\"), d)
        if name in _TEXT_CMDS:
            return f" {arg()} "
        if name == "log" and peek() == "_":
            take()
            return f" (1/ln({arg()}))ln "
        if name in ("degree", "circ"):
            return degree()
        if name == "placeholder":
            if peek() == "[":
                take()
                seq("]")
            arg()
            raise CalcError("Fill in the empty boxes first")
        if name in _SIMPLE:
            return _SIMPLE[name]
        if name in _SPACES:
            return ""
        if name in FUNCS or name == "arg":
            return f" {name} "
        raise CalcError(f"Unsupported symbol \\{name}")

    return seq().strip()


# ---- results as LaTeX ----

def _part_latex(s):
    """'5√2/2', '-π/4', '3/10', '1.5E-5' -> LaTeX."""
    sign = ""
    if s.startswith("-"):
        sign, s = "-", s[1:]
    m = re.fullmatch(r"([\d.]+)E(-?\d+)", s)
    if m:
        return rf"{sign}{m.group(1)}\times10^{{{m.group(2)}}}"
    num, _, den = s.partition("/")

    def conv(t):
        t = re.sub(r"√(\d+)", r"\\sqrt{\1}", t)
        return t.replace("π", r"\pi ")

    num, den = conv(num), conv(den)
    return sign + (rf"\frac{{{num}}}{{{den}}}" if den else num)


def value_latex(v):
    re_, im_, fmt = value_parts(v)
    if im_ == 0:
        return _part_latex(fmt(re_))
    s = fmt(abs(im_))
    im_l = "i" if s == "1" else _part_latex(s) + "i"
    if re_ == 0:
        return ("-" if im_ < 0 else "") + im_l
    return f"{_part_latex(fmt(re_))}{'-' if im_ < 0 else '+'}{im_l}"
