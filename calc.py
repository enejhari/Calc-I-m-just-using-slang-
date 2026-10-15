#!/usr/bin/env python3
"""
calc.py - a calculator with full complex-number support.

Run it:
    python calc.py                     open the GUI (fractions, roots and powers are drawn
                                       like on paper: type / for a fraction, ^ for a power)
    python calc.py "(2+3i)*(1-i)"      evaluate once and print the result
    python calc.py --cli               interactive terminal mode
    python calc.py --deg "sin(30)"     same, with angles in degrees

Syntax:
    + - * / ^  ( )  !          (also × ÷ − √ ∛ π ² ³ are understood)
    i or j                     imaginary unit         e.g.  3+4i, 2i(1-i)
    pi, π, e, ans              constants / last answer
    2E5                        scientific notation (capital E; lowercase e is Euler's number)
    2π, 3(1+i), (1+i)(1-i)     implicit multiplication
    sqrt cbrt root(x,n) abs arg re im conj exp ln log log(x,b) log2
    sin cos tan asin acos atan sinh cosh tanh asinh acosh atanh
    polar(r,θ) floor ceil round

Exact rational arithmetic is used wherever possible (1/3 + 1/6 = 1/2,
sqrt(-4) = 2i, sqrt(3+4i) = 2+i, (1+i)^8 = 16).  Otherwise results use
principal complex values (e.g. ln(-1) = πi, i^i = e^(-π/2)).
Note: ∛ / root(x,n) of a negative real with odd n returns the real root.
"""

import cmath
import copy
import math
import re
import sys
from fractions import Fraction


class CalcError(Exception):
    pass


# --------------------------------------------------------------------------
# Number model: exact complex rationals (Q) or Python complex floats
# --------------------------------------------------------------------------

class Q:
    """Exact complex number re + im*i with rational parts."""
    __slots__ = ("re", "im")

    def __init__(self, re_, im_=0):
        self.re = Fraction(re_)
        self.im = Fraction(im_)

    def __complex__(self):
        return complex(float(self.re), float(self.im))

    def is_zero(self):
        return self.re == 0 and self.im == 0


def C(v):
    """Convert to a Python complex, normalising -0.0 so branch cuts are standard."""
    z = complex(v)
    return complex(z.real + 0.0, z.imag + 0.0)


def is_real(v):
    return v.im == 0 if isinstance(v, Q) else v.imag == 0


def real_part(v):
    """Real part as Fraction (exact) or float."""
    return v.re if isinstance(v, Q) else v.real


def add(a, b):
    if isinstance(a, Q) and isinstance(b, Q):
        return Q(a.re + b.re, a.im + b.im)
    return C(a) + C(b)


def neg(a):
    return Q(-a.re, -a.im) if isinstance(a, Q) else -C(a)


def sub(a, b):
    return add(a, neg(b))


def mul(a, b):
    if isinstance(a, Q) and isinstance(b, Q):
        return Q(a.re * b.re - a.im * b.im, a.re * b.im + a.im * b.re)
    return C(a) * C(b)


def div(a, b):
    if isinstance(b, Q) and b.is_zero() or not isinstance(b, Q) and b == 0:
        raise ZeroDivisionError
    if isinstance(a, Q) and isinstance(b, Q):
        d = b.re * b.re + b.im * b.im
        return Q((a.re * b.re + a.im * b.im) / d, (a.im * b.re - a.re * b.im) / d)
    return C(a) / C(b)


def _qpow(a, n):
    result = Q(1)
    while n:
        if n & 1:
            result = mul(result, a)
        n >>= 1
        if n:
            a = mul(a, a)
    return result


def _isqrt_frac(f):
    """Exact square root of a non-negative Fraction, or None."""
    if f < 0:
        return None
    n, d = f.numerator, f.denominator
    rn, rd = math.isqrt(n), math.isqrt(d)
    if rn * rn == n and rd * rd == d:
        return Fraction(rn, rd)
    return None


def _iroot_int(n, k):
    """Exact integer k-th root of n >= 0, or None."""
    if n < 2:
        return n
    try:
        r = int(round(n ** (1.0 / k)))
    except OverflowError:
        return None
    for c in (r - 1, r, r + 1):
        if c >= 0 and c ** k == n:
            return c
    return None


def exact_sqrt(q):
    """Principal square root of an exact Q if it is again exact, else None."""
    if q.im == 0:
        if q.re >= 0:
            r = _isqrt_frac(q.re)
            return Q(r) if r is not None else None
        r = _isqrt_frac(-q.re)
        return Q(0, r) if r is not None else None
    m = _isqrt_frac(q.re * q.re + q.im * q.im)
    if m is None:
        return None
    x = _isqrt_frac((m + q.re) / 2)
    y = _isqrt_frac((m - q.re) / 2)
    if x is None or y is None:
        return None
    return Q(x, y if q.im > 0 else -y)


# ---- trig with exact values at multiples of 30° ----

_SIN30 = [0, Fraction(1, 2), None, 1, None, Fraction(1, 2),
          0, Fraction(-1, 2), None, -1, None, Fraction(-1, 2)]


def _sin_deg_exact(d):
    """sin(d degrees) as an exact Fraction when d is a multiple of 30° with a rational sine."""
    if isinstance(d, Fraction):
        k = d / 30
        if k.denominator != 1:
            return None
        k = int(k)
    else:
        k = d / 30
        kr = round(k)
        if abs(k - kr) > 1e-10 * max(1.0, abs(k)):
            return None
        k = int(kr)
    v = _SIN30[k % 12]
    return None if v is None else Fraction(v)


def trig_real(kind, x, deg):
    """sin/cos/tan of a real x (Fraction or float); snaps to exact values where possible."""
    if deg:
        d = x
        rad = float(x) * math.pi / 180
    else:
        d = float(x) * 180 / math.pi
        rad = float(x)
    s = _sin_deg_exact(d)
    c = _sin_deg_exact(d + 90)
    if kind == "sin":
        return Q(s) if s is not None else complex(math.sin(rad))
    if kind == "cos":
        return Q(c) if c is not None else complex(math.cos(rad))
    if c == 0:
        raise CalcError("tan is undefined here (cos = 0)")
    if s is not None and c is not None:
        return Q(s / c)
    return complex(math.tan(rad))


def exp_(v):
    if isinstance(v, Q) and v.is_zero():
        return Q(1)
    z = C(v)
    m = math.exp(z.real)
    if z.imag == 0:
        return complex(m)
    c = C(trig_real("cos", z.imag, False)).real
    s = C(trig_real("sin", z.imag, False)).real
    return complex(m * c, m * s)


def ln_(v):
    if isinstance(v, Q) and v.re == 1 and v.im == 0:
        return Q(0)
    z = C(v)
    if z == 0:
        raise CalcError("ln(0) is undefined")
    if z.imag == 0 and z.real > 0:
        return complex(math.log(z.real))
    return cmath.log(z)


def power(a, b):
    if isinstance(a, Q) and isinstance(b, Q) and b.im == 0:
        e = b.re
        if e.denominator == 1 and abs(e) <= 10000:
            n = int(e)
            if a.is_zero():
                if n < 0:
                    raise CalcError("0 cannot be raised to a negative power")
                return Q(1) if n == 0 else Q(0)
            r = _qpow(a, abs(n))
            return div(Q(1), r) if n < 0 else r
        if e.denominator == 2:
            s = exact_sqrt(a)
            if s is not None:
                return power(s, Q(e.numerator))
    za, zb = C(a), C(b)
    if za == 0:
        if zb == 0:
            return Q(1)
        if zb.real > 0:
            return Q(0)
        raise CalcError("0 cannot be raised to this power")
    if za.imag == 0 and zb.imag == 0 and (za.real > 0 or zb.real.is_integer()):
        return complex(math.pow(za.real, zb.real))
    return exp_(mul(b, ln_(a)))


def sqrt_(ev, v):
    if isinstance(v, Q):
        s = exact_sqrt(v)
        if s is not None:
            return s
    z = C(v)
    if z.imag == 0:
        if z.real >= 0:
            return complex(math.sqrt(z.real))
        return complex(0, math.sqrt(-z.real))
    return cmath.sqrt(z)


def root_(ev, x, n):
    if not (isinstance(n, Q) and n.im == 0 and n.re.denominator == 1):
        if not is_real(n):
            return power(x, div(Q(1), n))
        nf = real_part(n)
        if float(nf).is_integer():
            n = Q(int(nf))
        else:
            return power(x, div(Q(1), n))
    k = int(n.re)
    if k == 0:
        raise CalcError("0th root is undefined")
    if is_real(x):
        xr = real_part(x)
        if xr >= 0 or k % 2 == 1:
            sign = -1 if xr < 0 else 1
            if isinstance(x, Q):
                f = abs(x.re)
                rn = _iroot_int(f.numerator, abs(k))
                rd = _iroot_int(f.denominator, abs(k))
                if rn is not None and rd is not None:
                    r = Q(sign * Fraction(rn, rd))
                    return div(Q(1), r) if k < 0 else r
            r = sign * abs(float(xr)) ** (1.0 / abs(k))
            return complex(1 / r if k < 0 else r)
    return power(x, div(Q(1), n))


def factorial_(v):
    if isinstance(v, Q) and v.im == 0 and v.re.denominator == 1:
        n = int(v.re)
        if n < 0:
            raise CalcError("factorial of a negative integer is undefined")
        if n > 3000:
            raise OverflowError
        return Q(math.factorial(n))
    if not is_real(v):
        raise CalcError("factorial of a complex number is not supported")
    x = float(real_part(v))
    if x < 0 and x.is_integer():
        raise CalcError("factorial of a negative integer is undefined")
    return complex(math.gamma(x + 1))


# ---- function table ----

def _angle_in(ev, v):
    """Convert an angle argument to radians (complex)."""
    z = C(v)
    return z * math.pi / 180 if ev.deg else z


def _angle_out(ev, z):
    return C(z) * 180 / math.pi if ev.deg else C(z)


def _trig(kind):
    def f(ev, v):
        if is_real(v):
            return trig_real(kind, real_part(v), ev.deg)
        return getattr(cmath, kind)(_angle_in(ev, v))
    return f


def _inv_trig(kind):
    def f(ev, v):
        z = C(v)
        if z.imag == 0 and (kind == "atan" or -1 <= z.real <= 1):
            r = complex(getattr(math, kind)(z.real))
        else:
            r = getattr(cmath, kind)(z)
        return _angle_out(ev, r)
    return f


def _hyp(kind, domain=lambda x: True):
    def f(ev, v):
        z = C(v)
        if z.imag == 0 and domain(z.real):
            return complex(getattr(math, kind)(z.real))
        return getattr(cmath, kind)(z)
    return f


def abs_(ev, v):
    if isinstance(v, Q):
        s = exact_sqrt(Q(v.re * v.re + v.im * v.im))
        if s is not None:
            return s
    return complex(abs(C(v)))


def arg_(ev, v):
    z = C(v)
    if z == 0:
        raise CalcError("arg(0) is undefined")
    if isinstance(v, Q):
        a, b = v.re, v.im
        exact = None
        if b == 0:
            exact = 0 if a > 0 else 180
        elif a == 0:
            exact = 90 if b > 0 else -90
        elif abs(a) == abs(b):
            exact = (45 if a > 0 else 135) * (1 if b > 0 else -1)
        if exact is not None:
            return Q(exact) if ev.deg else complex(exact * math.pi / 180)
    return _angle_out(ev, math.atan2(z.imag, z.real))


def log_(ev, x, base=None):
    if base is None:
        z = C(x)
        if z.imag == 0 and z.real > 0:
            return complex(math.log10(z.real))
        return div(ln_(x), complex(math.log(10)))
    lb = ln_(base)
    if C(lb) == 0:
        raise CalcError("log base 1 is undefined")
    return div(ln_(x), lb)


def log2_(ev, x):
    z = C(x)
    if z.imag == 0 and z.real > 0:
        return complex(math.log2(z.real))
    return div(ln_(x), complex(math.log(2)))


def _real_only(name, fn):
    def f(ev, v):
        if not is_real(v):
            raise CalcError(f"{name} needs a real number")
        r = real_part(v)
        return Q(fn(r)) if isinstance(r, Fraction) else complex(fn(r))
    return f


def polar_(ev, r, theta):
    if is_real(theta):
        c = trig_real("cos", real_part(theta), ev.deg)
        s = trig_real("sin", real_part(theta), ev.deg)
    else:
        t = _angle_in(ev, theta)
        c, s = cmath.cos(t), cmath.sin(t)
    return mul(r, add(c, mul(Q(0, 1), s)))


FUNCS = {
    # name: (function(ev, *args), min_args, max_args)
    "sqrt": (sqrt_, 1, 1),
    "cbrt": (lambda ev, x: root_(ev, x, Q(3)), 1, 1),
    "root": (root_, 2, 2),
    "abs": (abs_, 1, 1),
    "arg": (arg_, 1, 1),
    "re": (lambda ev, v: Q(v.re) if isinstance(v, Q) else complex(C(v).real), 1, 1),
    "im": (lambda ev, v: Q(v.im) if isinstance(v, Q) else complex(C(v).imag), 1, 1),
    "conj": (lambda ev, v: Q(v.re, -v.im) if isinstance(v, Q) else C(v).conjugate(), 1, 1),
    "exp": (lambda ev, v: exp_(v), 1, 1),
    "ln": (lambda ev, v: ln_(v), 1, 1),
    "log": (log_, 1, 2),
    "log2": (log2_, 1, 1),
    "sin": (_trig("sin"), 1, 1),
    "cos": (_trig("cos"), 1, 1),
    "tan": (_trig("tan"), 1, 1),
    "asin": (_inv_trig("asin"), 1, 1),
    "acos": (_inv_trig("acos"), 1, 1),
    "atan": (_inv_trig("atan"), 1, 1),
    "sinh": (_hyp("sinh"), 1, 1),
    "cosh": (_hyp("cosh"), 1, 1),
    "tanh": (_hyp("tanh"), 1, 1),
    "asinh": (_hyp("asinh"), 1, 1),
    "acosh": (_hyp("acosh", lambda x: x >= 1), 1, 1),
    "atanh": (_hyp("atanh", lambda x: -1 < x < 1), 1, 1),
    "polar": (polar_, 2, 2),
    "floor": (_real_only("floor", math.floor), 1, 1),
    "ceil": (_real_only("ceil", math.ceil), 1, 1),
    "round": (_real_only("round", round), 1, 1),
}
FUNCS["arcsin"], FUNCS["arccos"], FUNCS["arctan"] = FUNCS["asin"], FUNCS["acos"], FUNCS["atan"]
FUNCS["real"], FUNCS["imag"] = FUNCS["re"], FUNCS["im"]

CONSTS = {
    "pi": lambda ev: complex(math.pi),
    "e": lambda ev: complex(math.e),
    "i": lambda ev: Q(0, 1),
    "j": lambda ev: Q(0, 1),
    "ans": lambda ev: ev.ans,
}

_KNOWN = sorted(set(FUNCS) | set(CONSTS), key=len, reverse=True)


# --------------------------------------------------------------------------
# Tokenizer and parser
# --------------------------------------------------------------------------

_SYMBOLS = [("**", "^"), ("×", "*"), ("·", "*"), ("⋅", "*"), ("÷", "/"), ("−", "-"),
            ("–", "-"), ("√", " sqrt "), ("∛", " cbrt "), ("π", " pi "), ("²", "^2"),
            ("³", "^3"), ("[", "("), ("]", ")"), ("{", "("), ("}", ")")]

_TOKEN_RE = re.compile(r"\s*(?:(?P<num>(?:\d+\.?\d*|\.\d+)(?:E[+-]?\d+)?)"
                       r"|(?P<name>[A-Za-z_]+)|(?P<op>[-+*/^(),!]))")


def tokenize(s):
    for a, b in _SYMBOLS:
        s = s.replace(a, b)
    s = s.rstrip().rstrip("=")
    tokens, pos = [], 0
    while pos < len(s):
        m = _TOKEN_RE.match(s, pos)
        if not m:
            rest = s[pos:].lstrip()
            if not rest:
                break
            raise CalcError(f"Unexpected character '{rest[0]}'")
        pos = m.end()
        if m.group("num"):
            if tokens and tokens[-1][0] == "num":
                raise CalcError("Missing operator between two numbers")
            text = re.sub(r"\.(?=E|$)", ".0", m.group("num"))
            tokens.append(("num", Fraction(text)))
        elif m.group("name"):
            run = m.group("name").lower()
            while run:
                for name in _KNOWN:
                    if run.startswith(name):
                        tokens.append(("name", name))
                        run = run[len(name):]
                        break
                else:
                    raise CalcError(f"Unknown name '{run}'")
        else:
            tokens.append(("op", m.group("op")))
    tokens.append(("end", None))
    return tokens


class Parser:
    def __init__(self, tokens, ev):
        self.t, self.i, self.ev = tokens, 0, ev

    def peek(self):
        return self.t[self.i]

    def take(self):
        tok = self.t[self.i]
        self.i += 1
        return tok

    def is_op(self, ch):
        k, v = self.peek()
        return k == "op" and v == ch

    def at_end(self):
        return self.peek()[0] == "end"

    def parse(self):
        if self.at_end():
            raise CalcError("Empty expression")
        v = self.expr()
        if not self.at_end():
            raise CalcError(f"Unexpected '{self.peek()[1]}'")
        return v

    def expr(self):
        v = self.term()
        while True:
            if self.is_op("+"):
                self.take()
                v = add(v, self.term())
            elif self.is_op("-"):
                self.take()
                v = sub(v, self.term())
            else:
                return v

    def term(self):
        v = self.unary()
        while True:
            k, val = self.peek()
            if k == "op" and val in "*/":
                self.take()
                r = self.unary()
                v = mul(v, r) if val == "*" else div(v, r)
            elif k in ("num", "name") or (k == "op" and val == "("):
                v = mul(v, self.power())          # implicit multiplication
            else:
                return v

    def unary(self):
        if self.is_op("-"):
            self.take()
            return neg(self.unary())
        if self.is_op("+"):
            self.take()
            return self.unary()
        return self.power()

    def power(self):
        base = self.postfix()
        if self.is_op("^"):
            self.take()
            return power(base, self.unary())     # right-associative, allows 2^-1
        return base

    def postfix(self):
        v = self.primary()
        while self.is_op("!"):
            self.take()
            v = factorial_(v)
        return v

    def close(self):
        if self.is_op(")"):
            self.take()
        elif not self.at_end():                  # missing ')' at the very end is forgiven
            raise CalcError(f"Expected ')' but found '{self.peek()[1]}'")

    def func_arg(self):
        if self.is_op("-"):
            self.take()
            return neg(self.func_arg())
        if self.is_op("+"):
            self.take()
            return self.func_arg()
        return self.postfix()

    def primary(self):
        k, val = self.take()
        if k == "num":
            return Q(val)
        if k == "op" and val == "(":
            v = self.expr()
            self.close()
            return v
        if k == "name":
            if val in CONSTS:
                return CONSTS[val](self.ev)
            fn, lo, hi = FUNCS[val]
            if self.is_op("("):
                self.take()
                args = []
                if not self.is_op(")") and not self.at_end():
                    args.append(self.expr())
                    while self.is_op(","):
                        self.take()
                        args.append(self.expr())
                self.close()
            else:
                if self.at_end():
                    raise CalcError(f"{val} needs an argument")
                args = [self.func_arg()]
            if not lo <= len(args) <= hi:
                want = str(lo) if lo == hi else f"{lo}-{hi}"
                raise CalcError(f"{val} expects {want} argument{'s' if hi > 1 else ''}")
            return fn(self.ev, *args)
        if k == "end":
            raise CalcError("Expression is incomplete")
        raise CalcError(f"Unexpected '{val}'")


class Evaluator:
    def __init__(self):
        self.deg = False
        self.ans = Q(0)

    def evaluate(self, text):
        try:
            v = Parser(tokenize(text), self).parse()
        except CalcError:
            raise
        except ZeroDivisionError:
            raise CalcError("Division by zero")
        except OverflowError:
            raise CalcError("Number too large")
        except RecursionError:
            raise CalcError("Expression nested too deeply")
        except (ValueError, ArithmeticError):
            raise CalcError("Undefined (outside the function's domain)")
        if isinstance(v, Q):
            try:
                complex(v)
            except OverflowError:
                raise CalcError("Number too large (beyond ~1E308)")
        else:
            z = complex(v)
            if not (math.isfinite(z.real) and math.isfinite(z.imag)):
                raise CalcError("Result is undefined or too large")
        return v


def mat_mul(a, b):
    """Product of two matrices given as lists of rows of numbers; exact where the entries are."""
    if not a or not b or len(a[0]) != len(b):
        raise CalcError("A needs as many columns as B has rows")
    out = []
    for row in a:
        new_row = []
        for j in range(len(b[0])):
            s = Q(0)
            for k, x in enumerate(row):
                s = add(s, mul(x, b[k][j]))
            new_row.append(s)
        out.append(new_row)
    return out


# --------------------------------------------------------------------------
# Output formatting
# --------------------------------------------------------------------------

def fmt_float(x):
    if x == 0:
        return "0"
    s = format(x, ".12g")
    if "e" in s:
        mant, ex = s.split("e")
        s = f"{mant}E{int(ex)}"
    return s


def fmt_frac(f):
    if abs(f.numerator) > 10 ** 15 or f.denominator > 10 ** 15:
        return fmt_float(float(f))
    return str(f.numerator) if f.denominator == 1 else f"{f.numerator}/{f.denominator}"


def _square_split(n):
    """n = k^2 * m with m square-free; returns (k, m)."""
    k, d = 1, 2
    while d * d <= n:
        while n % (d * d) == 0:
            n //= d * d
            k *= d
        d += 1
    return k, n


def nice_float(x):
    """Recognise rationals, rational·√m and rational·π in a float; fall back to decimal."""
    if x == 0 or not math.isfinite(x):
        return fmt_float(x)
    sign = "-" if x < 0 else ""
    ax = abs(x)
    f = Fraction(ax).limit_denominator(1000)
    if abs(float(f) - ax) < 1e-11 * max(1.0, ax):
        return sign + fmt_frac(f) if f != 0 else fmt_float(x)
    if ax < 1e6:
        f2 = Fraction(ax * ax).limit_denominator(1000)
        if f2 > 0 and abs(float(f2) - ax * ax) < 1e-10 * max(1.0, ax * ax):
            p, q = f2.numerator, f2.denominator
            k, m = _square_split(p * q)
            if 1 < m < 10000:
                g = math.gcd(k, q)
                k, q = k // g, q // g
                return sign + (str(k) if k != 1 else "") + f"√{m}" + (f"/{q}" if q != 1 else "")
        fp = Fraction(ax / math.pi).limit_denominator(100)
        if fp != 0 and abs(float(fp) * math.pi - ax) < 1e-11 * max(1.0, ax):
            p, q = fp.numerator, fp.denominator
            return sign + (str(p) if p != 1 else "") + "π" + (f"/{q}" if q != 1 else "")
    return fmt_float(x)


def complex_str(re_, im_, fmt):
    if im_ == 0:
        return fmt(re_)
    im_s = fmt(abs(im_))
    if im_s == "1":
        im_s = "i"
    elif "/" in im_s:
        im_s = f"({im_s})i"
    else:
        im_s += "i"
    if re_ == 0:
        return ("-" if im_ < 0 else "") + im_s
    return f"{fmt(re_)} {'-' if im_ < 0 else '+'} {im_s}"


def value_parts(v):
    """(real part, imaginary part, formatter) for display."""
    if isinstance(v, Q):
        return v.re, v.im, fmt_frac
    z = complex(v)
    re_, im_ = z.real, z.imag
    # drop numerical noise far below the precision of the other part
    if abs(im_) < 1e-14 * abs(re_):
        im_ = 0.0
    if abs(re_) < 1e-14 * abs(im_):
        re_ = 0.0
    return re_, im_, nice_float


def format_value(v, deg=False):
    """Return (main, decimal or None, polar or None) strings for a value."""
    re_, im_, fmt = value_parts(v)
    main = complex_str(re_, im_, fmt)
    z = complex(float(re_), float(im_))
    decimal = complex_str(z.real, z.imag, fmt_float)
    polar = None
    if z.imag != 0:
        r = nice_float(abs(z))
        th = math.atan2(z.imag, z.real)
        th_s = fmt_float(math.degrees(th)) + "°" if deg else nice_float(th)
        polar = f"{r} ∠ {th_s}"
    return main, (decimal if decimal != main else None), polar


# --------------------------------------------------------------------------
# GUI: a 2-D math editor where fractions, roots and powers look hand-written
# --------------------------------------------------------------------------

THEME = dict(bg="#1d1f27", panel="#252833", display="#2c303d", text="#f1f3f8", dim="#959bb0",
             err="#ff7070", res="#8be09a", digit="#3b4052", op="#4a5d8f", func="#323747",
             const="#5b4a8a", nav="#3d4a52", eq="#2f9a5a", clear="#a14444",
             ph="#6f7690", sel="#3d4d7a", cursor="#ffd166")


# ---- expression tree: what the editor shows ----

class Row:
    """A horizontal run of items (Char, Frac, Root, Power)."""
    def __init__(self, items=None):
        self.items = list(items or [])


class Char:
    def __init__(self, ch):
        self.ch = ch


class Frac:
    def __init__(self, num=None, den=None):
        self.num, self.den = num or Row(), den or Row()

    def slots(self):
        return [self.num, self.den]


class Root:
    def __init__(self, body=None, index=None):
        self.body, self.index = body or Row(), index

    def slots(self):
        return [self.index, self.body] if self.index is not None else [self.body]


class Power:
    """An exponent; its base is whatever item precedes it."""
    def __init__(self, exp=None):
        self.exp = exp or Row()

    def slots(self):
        return [self.exp]


def chars(s):
    return [Char(c) for c in s]


def is_box(it):
    return not isinstance(it, Char)


def _is_ch(it, options):
    return isinstance(it, Char) and it.ch in options


def box_empty(box):
    return all(not r.items for r in box.slots())


def group_items(items):
    """Wrap items in parentheses unless they already form a single operand."""
    items = list(items)
    if len(items) <= 1 or all(_is_ch(c, "0123456789.") for c in items):
        return items
    return [Char("(")] + items + [Char(")")]


def strip_parens(items):
    if len(items) >= 2 and _is_ch(items[0], "(") and _is_ch(items[-1], ")"):
        depth = 0
        for k, c in enumerate(items):
            if _is_ch(c, "("):
                depth += 1
            elif _is_ch(c, ")"):
                depth -= 1
                if depth == 0:
                    return items[1:-1] if k == len(items) - 1 else items
    return items


def _has_open_paren(items):
    depth = 0
    for c in items:
        if _is_ch(c, "("):
            depth += 1
        elif _is_ch(c, ")"):
            depth = max(0, depth - 1)
    return depth > 0


def operand_start(items, i):
    """Index where the operand ending at position i begins (used when '/' is typed)."""
    j = i
    while j > 0:
        c = items[j - 1]
        if _is_ch(c, ")"):
            # take the whole bracket group (and a function name in front of it)
            depth = 0
            while j > 0:
                j -= 1
                if _is_ch(items[j], ")"):
                    depth += 1
                elif _is_ch(items[j], "("):
                    depth -= 1
                    if depth == 0:
                        break
            while j > 0 and isinstance(items[j - 1], Char) and items[j - 1].ch.isalpha():
                j -= 1
        elif is_box(c) or c.ch.isalnum() or c.ch in ".!π":
            j -= 1
        else:
            break
    return j


def _read_operand(s, k):
    if k < len(s) and s[k] == "(":
        depth = 0
        for j in range(k, len(s)):
            if s[j] == "(":
                depth += 1
            elif s[j] == ")":
                depth -= 1
                if depth == 0:
                    return s[k + 1:j], j + 1
        return s[k + 1:], len(s)
    m = re.match(r"[-+]?[\w.π]*", s[k:])
    return m.group(0), k + m.end()


def text_to_items(s):
    """Convert linear text like '(1+i)/2 + √3^2' into editor items."""
    s = s.replace("**", "^").replace("*", "×").replace(" ", "")
    items, k = [], 0
    while k < len(s):
        c = s[k]
        if c in "^/√∛":
            sub, k = _read_operand(s, k + 1)
            inner = text_to_items(sub)
            if c == "^":
                items.append(Power(Row(inner)))
            elif c == "√":
                items.append(Root(Row(inner)))
            elif c == "∛":
                items.append(Root(Row(inner), Row(chars("3"))))
            else:
                j = operand_start(items, len(items))
                num = strip_parens(items[j:])
                del items[j:]
                items.append(Frac(Row(num), Row(inner)))
        else:
            items.append(Char(c))
            k += 1
    return items


def to_expr(row):
    """Serialise the tree to text for the parser."""
    out = []
    for it in row.items:
        if isinstance(it, Char):
            out.append(it.ch)
        elif isinstance(it, Frac):
            out.append(f"(({to_expr(it.num)})/({to_expr(it.den)}))")
        elif isinstance(it, Root):
            b = to_expr(it.body)
            out.append(f"root({b},{to_expr(it.index)})" if it.index is not None else f"sqrt({b})")
        else:
            out.append(f"^({to_expr(it.exp)})")
    return "".join(out)


def to_text(row):
    """Readable one-line form (history list, clipboard)."""
    def grp(r):
        t = to_text(r)
        single = len(r.items) == 1 and isinstance(r.items[0], Char)
        return t if single or all(_is_ch(c, "0123456789.") for c in r.items) else f"({t})"
    out = []
    for k, it in enumerate(row.items):
        if isinstance(it, Char):
            out.append(it.ch)
        elif isinstance(it, Frac):
            f = f"{grp(it.num)}/{grp(it.den)}"
            nxt = row.items[k + 1] if k + 1 < len(row.items) else None
            out.append(f"({f})" if isinstance(nxt, Power) else f)
        elif isinstance(it, Root):
            if it.index is None:
                out.append(f"√{grp(it.body)}")
            elif to_text(it.index) == "3":
                out.append(f"∛{grp(it.body)}")
            else:
                out.append(f"root({to_text(it.body)},{to_text(it.index)})")
        else:
            out.append(f"^{grp(it.exp)}")
    return "".join(out)


def _part_items(s):
    m = re.fullmatch(r"(-?)([\d.]+)E(-?\d+)", s)
    if m:
        return chars(m.group(1) + m.group(2) + "×10") + [Power(Row(chars(m.group(3))))]
    return text_to_items(s)


def value_items(v):
    """A result as editor items, with real fractions instead of a/b text."""
    re_, im_, fmt = value_parts(v)
    if im_ == 0:
        return _part_items(fmt(re_))
    s = fmt(abs(im_))
    im_items = [Char("i")] if s == "1" else _part_items(s) + [Char("i")]
    if re_ == 0:
        return ([Char("-")] if im_ < 0 else []) + im_items
    return _part_items(fmt(re_)) + [Char("-" if im_ < 0 else "+")] + im_items


# ---- layout and drawing ----

_SPACED = "+-×÷"
_DISPLAY = {"-": "−", "*": "×"}


class MathRenderer:
    def __init__(self, family, min_px):
        self.family, self.min_px, self._fonts = family, min_px, {}

    def font(self, px):
        from tkinter import font as tkfont
        px = max(6, int(round(px)))
        if px not in self._fonts:
            self._fonts[px] = tkfont.Font(family=self.family, size=-px)
        return self._fonts[px]

    def layout(self, row, px):
        row.px = px
        items, stack = row.items, []
        for k, it in enumerate(items):
            prev = items[k - 1] if k else None
            if isinstance(it, Char):
                self._layout_char(it, px, prev)
                if it.ch == "(":
                    stack.append(k)
                elif it.ch == ")" and stack:
                    self._stretch(items, stack.pop(), k, px)
            elif isinstance(it, Frac):
                cpx = max(self.min_px, px * 0.9)
                self.layout(it.num, cpx)
                self.layout(it.den, cpx)
                it.gap, it.pad, it.axis = max(2, px * 0.1), px * 0.14, px * 0.3
                it.lw = max(1, round(px / 16))
                it.w = max(it.num.w, it.den.w) + 2 * it.pad
                it.asc = it.axis + it.gap + it.num.desc + it.num.asc
                it.desc = it.gap + it.den.asc + it.den.desc - it.axis
            elif isinstance(it, Root):
                b = it.body
                self.layout(b, px)
                it.gap, it.sw, it.lw = max(2, px * 0.1), px * 0.6, max(1.5, px / 15)
                it.top = b.asc + it.gap
                it.ix = 0.0
                it.asc, it.desc = it.top + it.lw + 1, b.desc + 1
                if it.index is not None:
                    self.layout(it.index, max(self.min_px, px * 0.55))
                    it.ix = max(0.0, it.index.w - it.sw * 0.45)
                    ya = b.desc - (b.desc + it.top) * 0.45
                    it.asc = max(it.asc, -(ya - px * 0.1 - it.index.desc - it.index.asc))
                it.w = it.ix + it.sw + b.w + px * 0.12
            else:
                self.layout(it.exp, max(self.min_px, px * 0.7))
                ptop = prev.asc if prev is not None else px * 0.8
                h = it.exp.asc + it.exp.desc
                it.shift = max(px * 0.38, ptop - 0.55 * h)
                it.w = it.exp.w + px * 0.08
                it.asc = it.shift + it.exp.asc
                it.desc = max(0.0, it.exp.desc - it.shift)
        offs = [0.0]
        for it in items:
            offs.append(offs[-1] + it.w)
        row.offs = offs
        row.w = offs[-1] if items else px * 0.55
        row.asc = max([px * 0.8] + [it.asc for it in items])
        row.desc = max([px * 0.25] + [it.desc for it in items])

    def _layout_char(self, it, px, prev):
        it.text = _DISPLAY.get(it.ch, it.ch)
        it.ppx, it.stretched = px, False
        spaced = it.ch == "=" or (it.ch in _SPACED and prev is not None
                                  and not _is_ch(prev, "(,+-×÷E^"))
        it.lpad = px * 0.18 if spaced else 0.0
        it.rpad = px * 0.18 if spaced else (px * 0.25 if it.ch == "," else 0.0)
        it.w = self.font(px).measure(it.text) + it.lpad + it.rpad
        it.asc, it.desc = px * 0.8, px * 0.25

    def _stretch(self, items, a, b, px):
        """Grow a pair of parentheses to the height of what they enclose."""
        inner = items[a + 1:b]
        asc = max([px * 0.8] + [c.asc for c in inner])
        desc = max([px * 0.25] + [c.desc for c in inner])
        if asc <= px * 0.85 and desc <= px * 0.3:
            return
        ppx = (asc + desc) / 1.05
        for c in (items[a], items[b]):
            c.stretched, c.ppx = True, ppx
            c.asc, c.desc = asc + px * 0.05, desc + px * 0.05
            c.mid = (desc - asc) / 2
            c.w = self.font(ppx).measure(c.text) + c.lpad + c.rpad

    def draw(self, cv, row, x, base, color, rec, sel=None, top=False):
        """Draw a laid-out row; records (row, cursor xs, top, bottom) into rec."""
        px = row.px
        rec.append((row, [x + o for o in row.offs], base - row.asc, base + row.desc))
        if not row.items:
            if not top:
                cv.create_rectangle(x + 1, base - px * 0.72, x + row.w - 1, base + px * 0.18,
                                    outline=THEME["ph"], dash=(2, 2))
            return
        if sel is not None and sel[0] is row:
            cv.create_rectangle(x + row.offs[sel[1]], base - row.asc, x + row.offs[sel[2]],
                                base + row.desc, fill=THEME["sel"], outline="")
        for k, it in enumerate(row.items):
            ix = x + row.offs[k]
            if isinstance(it, Char):
                f = self.font(it.ppx)
                if it.stretched:
                    cv.create_text(ix + it.lpad, base + it.mid, text=it.text, anchor="w",
                                   font=f, fill=color)
                else:
                    cv.create_text(ix + it.lpad, base - f.metrics("ascent"), text=it.text,
                                   anchor="nw", font=f, fill=color)
            elif isinstance(it, Frac):
                by = base - it.axis
                cv.create_line(ix + it.pad * 0.4, by, ix + it.w - it.pad * 0.4, by,
                               width=it.lw, fill=color)
                self.draw(cv, it.num, ix + (it.w - it.num.w) / 2, by - it.gap - it.num.desc,
                          color, rec, sel)
                self.draw(cv, it.den, ix + (it.w - it.den.w) / 2, by + it.gap + it.den.asc,
                          color, rec, sel)
            elif isinstance(it, Root):
                b, sx, sw = it.body, ix + it.ix, it.sw
                bottom, topy = base + b.desc, base - it.top
                ya = bottom - (bottom - topy) * 0.45
                cv.create_line(sx, ya, sx + sw * 0.22, ya - px * 0.05, sx + sw * 0.5, bottom,
                               sx + sw * 0.92, topy, sx + sw + b.w + px * 0.08, topy,
                               width=it.lw, fill=color, joinstyle="round", capstyle="round")
                if it.index is not None:
                    self.draw(cv, it.index, sx + sw * 0.45 - it.index.w,
                              ya - px * 0.1 - it.index.desc, color, rec, sel)
                self.draw(cv, b, sx + sw, base, color, rec, sel)
            else:
                self.draw(cv, it.exp, ix, base - it.shift, color, rec, sel)


# ---- the editor ----

OPS = "+-*/^!×÷"


class MathEditor:
    """A canvas that edits an expression tree, drawn the way you'd write it by hand."""

    def __init__(self, parent, renderer, px, app):
        import tkinter as tk
        self.R, self.px, self.app = renderer, px, app
        self.cv = tk.Canvas(parent, bg=THEME["display"], highlightthickness=2,
                            highlightcolor=THEME["op"], highlightbackground=THEME["panel"],
                            height=px * 2, takefocus=1, cursor="xterm")
        self.root = Row()
        self.row, self.idx, self.anchor = self.root, 0, None
        self.rec, self.xoff, self.height = [], 0.0, 0
        self.cursor_id, self.press, self.reenter = None, None, None
        self.cv.bind("<Key>", self.on_key)
        self.cv.bind("<Button-1>", self.on_click)
        self.cv.bind("<B1-Motion>", self.on_drag)
        self.cv.bind("<Configure>", lambda e: self.render())
        self._blink()

    # ---- state helpers ----
    def focus(self):
        self.cv.focus_set()

    def _set(self, row, idx):
        self.row, self.idx, self.anchor = row, idx, None

    def set_row(self, row):
        self.root = row
        self._set(row, len(row.items))
        self.xoff = 0.0

    def select_all(self):
        self.row, self.anchor, self.idx = self.root, 0, len(self.root.items)

    def _parent(self, row):
        """(box, parent_row, index of box) that contains `row`, or None for the top row."""
        def walk(r):
            for k, it in enumerate(r.items):
                if is_box(it):
                    for s in it.slots():
                        if s is row:
                            return it, r, k
                        found = walk(s)
                        if found:
                            return found
            return None
        return None if row is self.root else walk(self.root)

    def _selection(self):
        if self.anchor is None or self.anchor == self.idx:
            return None
        lo, hi = sorted((self.anchor, self.idx))
        return self.row, lo, hi

    def _take_selection(self):
        sel = self._selection()
        self.anchor = None
        if sel is None:
            return None
        _, lo, hi = sel
        items = self.row.items[lo:hi]
        del self.row.items[lo:hi]
        self.idx = lo
        return items

    def _insert(self, items):
        self.row.items[self.idx:self.idx] = items
        self.idx += len(items)

    # ---- movement ----
    def right(self):
        r, i = self.row, self.idx
        if i < len(r.items):
            it = r.items[i]
            self._set(it.slots()[0], 0) if is_box(it) else self._set(r, i + 1)
            return
        p = self._parent(r)
        if p:
            box, pr, k = p
            slots = box.slots()
            n = slots.index(r)
            self._set(slots[n + 1], 0) if n + 1 < len(slots) else self._set(pr, k + 1)

    def left(self):
        r, i = self.row, self.idx
        if i > 0:
            it = r.items[i - 1]
            if is_box(it):
                last = it.slots()[-1]
                self._set(last, len(last.items))
            else:
                self._set(r, i - 1)
            return
        p = self._parent(r)
        if p:
            box, pr, k = p
            slots = box.slots()
            n = slots.index(r)
            if n > 0:
                self._set(slots[n - 1], len(slots[n - 1].items))
            else:
                self._set(pr, k)

    def extend(self, d):
        if self.anchor is None:
            self.anchor = self.idx
        self.idx = max(0, min(len(self.row.items), self.idx + d))

    def _cursor_x(self):
        for r, xs, _, _ in self.rec:
            if r is self.row:
                return xs[min(self.idx, len(xs) - 1)]
        return 0

    def _nearest(self, row, x):
        for r, xs, _, _ in self.rec:
            if r is row:
                return min(range(len(xs)), key=lambda j: abs(xs[j] - x))
        return 0

    def vertical(self, d):
        """Up/Down between numerator and denominator. Returns False if there is nowhere to go."""
        x, r = self._cursor_x(), self.row
        while True:
            p = self._parent(r)
            if not p:
                return False
            box, pr, k = p
            if isinstance(box, Frac):
                if d > 0 and r is box.num:
                    self._set(box.den, self._nearest(box.den, x))
                    return True
                if d < 0 and r is box.den:
                    self._set(box.num, self._nearest(box.num, x))
                    return True
            if isinstance(box, Power) and d > 0:
                self._set(pr, k + 1)
                return True
            r = pr

    def tab(self, d):
        """Jump to the next/previous slot: past ',' or ')', out of a box, into the next box."""
        r, i = self.row, self.idx
        if d > 0:
            for j in range(i + 1, len(r.items) + 1):
                if _is_ch(r.items[j - 1], ",)"):
                    self._set(r, j)
                    return
            for j in range(i, len(r.items)):
                if is_box(r.items[j]):
                    self._set(r, j)
                    self.right()
                    return
            if i < len(r.items):
                self._set(r, len(r.items))
            else:
                self.right()
        else:
            for j in range(i - 1, 0, -1):
                if _is_ch(r.items[j - 1], "(,"):
                    self._set(r, j)
                    return
            if i > 0:
                self._set(r, 0)
            else:
                self.left()

    # ---- editing ----
    def backspace(self):
        if self._take_selection() is not None:
            return
        r, i = self.row, self.idx
        if i > 0:
            it = r.items[i - 1]
            if is_box(it) and not box_empty(it):
                last = it.slots()[-1]
                self._set(last, len(last.items))
                return
            del r.items[i - 1]
            i -= 1
            if _is_ch(it, "(") and i < len(r.items) and _is_ch(r.items[i], ")"):
                del r.items[i]
            self._set(r, i)
            return
        p = self._parent(r)
        if not p:
            return
        box, pr, k = p
        slots = box.slots()
        n = slots.index(r)
        if n > 0:
            self._set(slots[n - 1], len(slots[n - 1].items))
            return
        # at the very start of a box: remove the box but keep what was inside
        if isinstance(box, Frac):
            inner = group_items(box.num.items)
            if box.den.items:
                inner += [Char("÷")] + group_items(box.den.items)
        elif isinstance(box, Root):
            inner = box.body.items
        else:
            inner = box.exp.items
        pr.items[k:k + 1] = inner
        self._set(pr, k)

    def delete(self):
        if self._take_selection() is not None:
            return
        r, i = self.row, self.idx
        if i < len(r.items):
            it = r.items[i]
            if is_box(it) and not box_empty(it):
                self._set(it.slots()[0], 0)
            else:
                del r.items[i]

    def type_char(self, ch):
        ch = {"*": "×", "−": "-", ":": "÷"}.get(ch, ch)
        back, self.reenter = self.reenter, None
        if ch in "^!" and back and self.row is back[1] and self.idx == back[2]:
            # '^' right after closing a bracketed denominator/exponent applies inside it,
            # just like (1+i)/(2-i)^2 means (1+i)/((2-i)^2)
            slot = back[0]
            slot.items[:] = group_items(slot.items)
            self._set(slot, len(slot.items))
        if ch in "+-×÷/" and self.row.items and self.idx == len(self.row.items):
            # typed fractions/powers end where a linear calculator would end them: 1/2+3, 2^3+1
            p = self._parent(self.row)
            if p and getattr(p[0], "auto", False) and self.row is p[0].slots()[-1]:
                self._set(p[1], p[2] + 1)
        if ch in "/÷":
            return self.fraction(grab=True)
        if ch == "^":
            return self.power(auto=True)
        sel = self._take_selection()
        if ch == "(":
            if sel is not None:
                self._insert([Char("(")] + sel + [Char(")")])
            else:
                self._insert([Char("("), Char(")")])
                self.idx -= 1
            return
        if ch == ")" and sel is None:
            # a ')' with no '(' to close inside this box closes one further out
            while not _has_open_paren(self.row.items[:self.idx]) and not (
                    self.idx < len(self.row.items) and _is_ch(self.row.items[self.idx], ")")):
                p = self._parent(self.row)
                if not p:
                    break
                self._set(p[1], p[2] + 1)
            r = self.row
            if not (self.idx < len(r.items) and _is_ch(r.items[self.idx], ")")):
                r.items.insert(self.idx, Char(")"))
            close = self.idx
            self.idx += 1
            # a bracket group filling a whole fraction part / exponent / root: the box already
            # groups it, so drop the brackets and step out of the box (like typing 2^(1/3)+1)
            p = self._parent(r)
            if p and close == len(r.items) - 1 and strip_parens(r.items) is not r.items:
                box, pr, k = p
                r.items[:] = r.items[1:-1]
                if r is box.slots()[-1]:
                    self._set(pr, k + 1)
                    self.reenter = (r, pr, k + 1)
                else:
                    self._set(r, len(r.items))
            return
        self._insert([Char(ch)])
        self._autoreplace()

    def _autoreplace(self):
        r, i = self.row, self.idx
        tail = "".join(c.ch if isinstance(c, Char) else "\0" for c in r.items[max(0, i - 4):i])
        if tail.endswith("pi"):
            r.items[i - 2:i] = [Char("π")]
            self.idx = i - 1
        elif tail.endswith("sqrt"):
            del r.items[i - 4:i]
            self.idx = i - 4
            self.root_()
            self._parent(self.row)[0].auto = True

    def insert_items(self, items):
        self._take_selection()
        self._insert(items)

    def fraction(self, grab=False):
        sel = self._take_selection()
        r = self.row
        if sel is None and grab:
            j = operand_start(r.items, self.idx)
            sel = strip_parens(r.items[j:self.idx]) or None
            del r.items[j:self.idx]
            self.idx = j
        f = Frac(Row(sel or []))
        f.auto = grab
        self._insert([f])
        self._set(f.den, 0) if sel else self._set(f.num, 0)

    def reciprocal(self):
        sel = self._take_selection()
        f = Frac(Row(chars("1")), Row(sel or []))
        self._insert([f])
        if not sel:
            self._set(f.den, 0)

    def root_(self, index=None):
        sel = self._take_selection()
        rt = Root(Row(sel or []), Row(chars(index)) if index is not None else None)
        self._insert([rt])
        if not sel:
            self._set(rt.index if index == "" else rt.body, 0)

    def power(self, exp=None, auto=False):
        sel = self._take_selection()
        p = Power(Row(chars(exp or "")))
        p.auto = auto
        self._insert(group_items(sel or []) + [p])
        if exp is None:
            self._set(p.exp, 0)

    def power_of(self, base):
        sel = self._take_selection()
        p = Power(Row(sel or []))
        self._insert(chars(base) + [p])
        if not sel:
            self._set(p.exp, 0)

    def factorial(self):
        sel = self._take_selection()
        self._insert(group_items(sel or []) + [Char("!")])

    def func(self, name, extra=""):
        sel = self._take_selection()
        self._insert(chars(name) + [Char("(")])
        if sel:
            self._insert(sel + chars(extra))
            if not extra:
                self._insert([Char(")")])
                return
        self.row.items[self.idx:self.idx] = chars(extra) + [Char(")")]

    # ---- input events ----
    def on_key(self, e):
        ks, app = e.keysym, self.app
        printable = bool(e.char) and e.char.isprintable()
        ctrl = bool(e.state & 0x4) and not printable      # AltGr characters stay typable
        shift = bool(e.state & 0x1)
        if ks in ("Return", "KP_Enter"):
            app.evaluate()
            return "break"
        if ks == "Escape":
            app.clear()
            return "break"
        if ctrl:
            k = ks.lower()
            if k == "c":
                self.cv.clipboard_clear()
                self.cv.clipboard_append(to_text(self.root))
                return "break"
            app.before_input({"r": "wrap", "f": "wrap", "v": "atom"}.get(k, "nav"))
            if k == "r":
                self.root_()
            elif k == "f":
                self.fraction()
            elif k == "p":
                self.insert_items([Char("π")])
            elif k == "a":
                self.select_all()
            elif k == "v":
                try:
                    self.insert_items(text_to_items(self.cv.clipboard_get()))
                except Exception:
                    pass
            else:
                return None
        elif ks in ("Left", "Right"):
            app.before_input("nav")
            d = 1 if ks == "Right" else -1
            sel = self._selection()
            if shift:
                self.extend(d)
            elif sel:
                self._set(self.row, sel[2] if d > 0 else sel[1])
            else:
                self.right() if d > 0 else self.left()
        elif ks in ("Up", "Down"):
            app.before_input("nav")
            if not self.vertical(1 if ks == "Down" else -1):
                app.history_nav(1 if ks == "Down" else -1)
                return "break"
        elif ks in ("Home", "End"):
            app.before_input("nav")
            self._set(self.row, 0 if ks == "Home" else len(self.row.items))
        elif ks == "BackSpace":
            app.before_input("nav")
            self.backspace()
        elif ks == "Delete":
            app.before_input("nav")
            self.delete()
        elif ks in ("Tab", "ISO_Left_Tab"):
            app.before_input("nav")
            self.tab(-1 if shift or ks == "ISO_Left_Tab" else 1)
        elif printable and e.char != " ":
            app.before_input("op" if e.char in OPS else "atom")
            self.type_char(e.char)
        else:
            return None
        self.changed()
        return "break"

    def _hit(self, x, y):
        best, score = None, None
        for row, xs, top, bot in self.rec:
            dy = 0 if top <= y <= bot else min(abs(y - top), abs(y - bot))
            for j, px in enumerate(xs):
                s = abs(px - x) + 3 * dy + (bot - top) * 0.02
                if score is None or s < score:
                    best, score = (row, j), s
        return best

    def on_click(self, e):
        self.focus()
        self.app.before_input("nav")
        hit = self._hit(e.x, e.y)
        if hit:
            self._set(*hit)
            self.press = hit
            self.render()

    def on_drag(self, e):
        hit = self._hit(e.x, e.y)
        if hit and self.press and hit[0] is self.press[0]:
            self.row, self.anchor, self.idx = hit[0], self.press[1], hit[1]
            self.render()

    def changed(self):
        self.render()
        self.app.update_preview()

    # ---- drawing ----
    def render(self):
        cv, pad = self.cv, 12
        self.R.layout(self.root, self.px)
        h = int(self.root.asc + self.root.desc + 2 * pad)
        if h != self.height:
            self.height = h
            cv.config(height=h)
        base = pad + self.root.asc
        width = cv.winfo_width()
        if self.root.w < width - 2 * pad:
            self.xoff = 0.0
        for _ in range(3):
            cv.delete("all")
            self.rec = []
            self.R.draw(cv, self.root, pad - self.xoff, base, THEME["text"], self.rec,
                        self._selection(), top=True)
            cx = self._cursor_x()
            if width > 50 and cx > width - pad:
                self.xoff += cx - (width - pad) + 40
            elif cx < pad and self.xoff > 0:
                self.xoff = max(0.0, self.xoff - (pad - cx) - 40)
            else:
                break
        for r, xs, top, bot in self.rec:
            if r is self.row:
                x = xs[min(self.idx, len(xs) - 1)] + (2 if not r.items else 0)
                self.cursor_id = cv.create_line(x, top, x, bot, width=2, fill=THEME["cursor"])
                break

    def _blink(self):
        if self.cursor_id is not None:
            try:
                state = self.cv.itemcget(self.cursor_id, "state")
                self.cv.itemconfig(self.cursor_id, state="hidden" if state != "hidden" else "normal")
            except Exception:
                pass
        self.cv.after(530, self._blink)


# ---- buttons and the main window ----

HELP = ("Type with the keyboard.  /  makes a fraction (what's left of the cursor goes on top),  ^  makes an "
        "exponent.  ←/→ move through everything,  ↑/↓ jump between top and bottom of a fraction,  "
        "Tab = next box,  Backspace at the start of a box removes the box.\n"
        "Shift+←/→ or drag the mouse to select, then click a function to wrap the selection.  "
        "Enter = solve · Esc = clear · ↑/↓ outside fractions = history · Ctrl+R √ · Ctrl+P π · "
        "Ctrl+C/V copy/paste · i or j = imaginary unit · E = ×10ⁿ")


def _lighten(color, amt=0.18):
    c = color.lstrip("#")
    r, g, b = (int(c[i:i + 2], 16) for i in (0, 2, 4))
    r, g, b = (int(x + (255 - x) * amt) for x in (r, g, b))
    return f"#{r:02x}{g:02x}{b:02x}"


class CalculatorApp:
    def __init__(self, root):
        import tkinter as tk
        from tkinter import font as tkfont
        self.tk, self.root = tk, root
        self.ev = Evaluator()
        self.history = []          # (expression tree, text, result text, result items)
        self.hist_idx = None
        self.just_evaluated = False
        self.result_items = None

        scale = root.winfo_fpixels("1i") / 72.0
        families = set(tkfont.families(root))
        family = next((f for f in ("Cambria", "Times New Roman", "DejaVu Serif", "Times")
                       if f in families), "Times")
        self.R = MathRenderer(family, round(10 * scale))
        self.res_px = round(22 * scale)

        root.title("Complex Calculator")
        root.configure(bg=THEME["bg"])
        root.minsize(1000, 680)
        root.columnconfigure(0, weight=3)
        root.columnconfigure(1, weight=1)
        root.rowconfigure(0, weight=1)

        self.f_btn = ("Segoe UI", 13)
        self.f_btn_big = ("Segoe UI", 15, "bold")

        main = tk.Frame(root, bg=THEME["bg"], padx=12, pady=10)
        main.grid(row=0, column=0, sticky="nsew")
        main.columnconfigure(0, weight=1)
        main.rowconfigure(5, weight=1)

        # --- top bar ---
        top = tk.Frame(main, bg=THEME["bg"])
        top.grid(row=0, column=0, sticky="ew")
        tk.Label(top, text="Expression", bg=THEME["bg"], fg=THEME["dim"],
                 font=("Segoe UI", 10)).pack(side="left")
        self.mode_btn = tk.Button(top, text="RAD", width=6, command=self.toggle_mode,
                                  bg=THEME["const"], fg=THEME["text"], relief="flat", bd=0,
                                  activebackground=_lighten(THEME["const"]),
                                  activeforeground=THEME["text"], takefocus=0,
                                  font=("Segoe UI", 10, "bold"), cursor="hand2")
        self.mode_btn.pack(side="right")
        tk.Label(top, text="Angle mode:", bg=THEME["bg"], fg=THEME["dim"],
                 font=("Segoe UI", 10)).pack(side="right", padx=6)

        # --- display ---
        self.ed = MathEditor(main, self.R, round(26 * scale), self)
        self.ed.cv.grid(row=1, column=0, sticky="ew", pady=(4, 2))

        self.preview = tk.Label(main, text="", anchor="w", bg=THEME["bg"], fg=THEME["dim"],
                                font=("Consolas", 12))
        self.preview.grid(row=2, column=0, sticky="ew")

        self.res_cv = tk.Canvas(main, bg=THEME["bg"], highlightthickness=0,
                                height=self.res_px * 1.4, cursor="hand2")
        self.res_cv.grid(row=3, column=0, sticky="ew", pady=(4, 0))
        self.res_cv.bind("<Button-1>", lambda e: self.result_items and self.insert_result(self.result_items))

        self.detail = tk.Label(main, text="", anchor="w", bg=THEME["bg"], fg=THEME["dim"],
                               font=("Consolas", 12), justify="left")
        self.detail.grid(row=4, column=0, sticky="ew", pady=(0, 8))

        # --- buttons ---
        pad = tk.Frame(main, bg=THEME["bg"])
        pad.grid(row=5, column=0, sticky="nsew")
        pad.columnconfigure(0, weight=6, uniform="pad")
        pad.columnconfigure(1, weight=5, uniform="pad")
        pad.rowconfigure(0, weight=1)

        E = self.ed
        fn = lambda name, extra="": ("wrap", lambda: E.func(name, extra))
        put = lambda s: ("atom", lambda: E.insert_items(chars(s)))
        typ = lambda ch, kind="atom": (kind, lambda: E.type_char(ch))
        func_buttons = [
            [("√x", ("wrap", E.root_)), ("∛x", ("wrap", lambda: E.root_("3"))),
             ("ⁿ√x", ("wrap", lambda: E.root_(""))), ("x²", ("wrap", lambda: E.power("2"))),
             ("xʸ", ("wrap", E.power)), ("a/b", ("wrap", E.fraction))],
            [("π", put("π")), ("e", put("e")), ("i", put("i")), ("|x|", fn("abs")),
             ("1/x", ("wrap", E.reciprocal)), ("n!", ("wrap", E.factorial))],
            [("sin", fn("sin")), ("cos", fn("cos")), ("tan", fn("tan")), ("ln", fn("ln")),
             ("log", fn("log")), ("eˣ", ("wrap", lambda: E.power_of("e")))],
            [("sin⁻¹", fn("asin")), ("cos⁻¹", fn("acos")), ("tan⁻¹", fn("atan")),
             ("logₐ", fn("log", ",")), ("10ˣ", ("wrap", lambda: E.power_of("10"))),
             ("EE", typ("E"))],
            [("sinh", fn("sinh")), ("cosh", fn("cosh")), ("tanh", fn("tanh")),
             ("Re", fn("re")), ("Im", fn("im")), ("conj", fn("conj"))],
            [("arg", fn("arg")), ("polar", fn("polar", ",")), ("ans", put("ans")),
             ("(", typ("(")), (")", typ(")")), (",", typ(","))],
        ]
        colors = {"π": "const", "e": "const", "i": "const", "ans": "const"}
        funcs = tk.Frame(pad, bg=THEME["bg"])
        funcs.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        for r, row in enumerate(func_buttons):
            funcs.rowconfigure(r, weight=1, uniform="f")
            for c, (label, (kind, action)) in enumerate(row):
                funcs.columnconfigure(c, weight=1, uniform="f")
                self._button(funcs, label, lambda k=kind, a=action: self.do(k, a),
                             THEME[colors.get(label, "func")], r, c)

        keys = tk.Frame(pad, bg=THEME["bg"])
        keys.grid(row=0, column=1, sticky="nsew")
        d = lambda ch: (lambda: self.do("atom", lambda: E.type_char(ch)))
        o = lambda ch: (lambda: self.do("op", lambda: E.type_char(ch)))
        nav = lambda f: (lambda: self.do("nav", f))
        layout = [
            [("7", d("7"), "digit"), ("8", d("8"), "digit"), ("9", d("9"), "digit"),
             ("÷", o("/"), "op"), ("⌫", nav(E.backspace), "clear")],
            [("4", d("4"), "digit"), ("5", d("5"), "digit"), ("6", d("6"), "digit"),
             ("×", o("×"), "op"), ("C", self.clear, "clear")],
            [("1", d("1"), "digit"), ("2", d("2"), "digit"), ("3", d("3"), "digit"),
             ("−", o("-"), "op"), ("(", d("("), "op")],
            [("0", d("0"), "digit"), (".", d("."), "digit"), ("i", d("i"), "const"),
             ("+", o("+"), "op"), (")", d(")"), "op")],
            [("◀", nav(E.left), "nav"), ("▶", nav(E.right), "nav"),
             ("⇥", nav(lambda: E.tab(1)), "nav"), ("=", self.evaluate, "eq", 2)],
        ]
        for r, row in enumerate(layout):
            keys.rowconfigure(r, weight=1, uniform="k")
            c = 0
            for item in row:
                label, cmd, col = item[:3]
                span = item[3] if len(item) > 3 else 1
                big = self.f_btn_big if col in ("digit", "eq", "op") else self.f_btn
                self._button(keys, label, cmd, THEME[col], r, c, span, big)
                c += span
        for c in range(5):
            keys.columnconfigure(c, weight=1, uniform="k")

        tk.Label(main, text=HELP, bg=THEME["bg"], fg=THEME["dim"], justify="left", anchor="w",
                 wraplength=640, font=("Segoe UI", 9)).grid(row=6, column=0, sticky="ew", pady=(8, 0))

        # --- history ---
        side = tk.Frame(root, bg=THEME["panel"], padx=10, pady=10)
        side.grid(row=0, column=1, sticky="nsew")
        side.rowconfigure(1, weight=1)
        side.columnconfigure(0, weight=1)
        tk.Label(side, text="History  (click = insert result, double-click = edit)",
                 bg=THEME["panel"], fg=THEME["dim"], font=("Segoe UI", 9),
                 anchor="w").grid(row=0, column=0, columnspan=2, sticky="ew")
        self.hist_box = tk.Listbox(side, bg=THEME["display"], fg=THEME["text"], relief="flat",
                                   font=("Consolas", 11), activestyle="none", takefocus=0,
                                   selectbackground=THEME["op"], highlightthickness=0)
        self.hist_box.grid(row=1, column=0, sticky="nsew", pady=6)
        sb = tk.Scrollbar(side, command=self.hist_box.yview)
        sb.grid(row=1, column=1, sticky="ns", pady=6)
        self.hist_box.config(yscrollcommand=sb.set)
        self.hist_box.bind("<ButtonRelease-1>", self.on_history_click)
        self.hist_box.bind("<Double-Button-1>", self.on_history_double)
        self._button(side, "Clear history", self.clear_history, THEME["func"], 2, 0, 2)

        self.show_result()
        self.ed.focus()

    def _button(self, parent, text, cmd, color, r, c, colspan=1, font=None):
        tk = self.tk
        b = tk.Button(parent, text=text, command=cmd, bg=color, fg=THEME["text"],
                      activebackground=_lighten(color, 0.3), activeforeground=THEME["text"],
                      relief="flat", bd=0, takefocus=0, font=font or self.f_btn, cursor="hand2")
        b.grid(row=r, column=c, columnspan=colspan, sticky="nsew", padx=2, pady=2, ipady=4)
        b.bind("<Enter>", lambda e: b.config(bg=_lighten(color)))
        b.bind("<Leave>", lambda e: b.config(bg=color))
        return b

    # ---- editing glue ----
    def before_input(self, kind):
        """After '=': an operator continues from ans; anything else edits/replaces the expression
        (the whole expression is selected, so typing replaces it and functions wrap it)."""
        if not self.just_evaluated:
            return
        self.just_evaluated = False
        if kind == "op":
            self.ed.set_row(Row(chars("ans")))

    def do(self, kind, action):
        self.before_input(kind)
        action()
        self.ed.focus()
        self.ed.changed()

    def insert_result(self, items):
        items = copy.deepcopy(items)
        if any(_is_ch(c, "+-") for c in items):
            items = [Char("(")] + items + [Char(")")]
        self.do("atom", lambda: self.ed.insert_items(items))

    def clear(self):
        self.ed.set_row(Row())
        self.just_evaluated = False
        self.hist_idx = None
        self.result_items = None
        self.show_result()
        self.detail.config(text="")
        self.preview.config(text="")
        self.ed.focus()
        self.ed.render()

    def toggle_mode(self):
        self.ev.deg = not self.ev.deg
        self.mode_btn.config(text="DEG" if self.ev.deg else "RAD")
        self.update_preview()
        self.ed.focus()

    # ---- evaluation ----
    def show_result(self, items=None, error=None):
        cv = self.res_cv
        cv.delete("all")
        if error:
            cv.create_text(6, 8, anchor="nw", text=error, fill=THEME["err"],
                           font=("Segoe UI", 16, "bold"))
            cv.config(height=self.res_px * 1.6)
            return
        if not items:
            cv.config(height=self.res_px * 1.6)
            return
        row = Row([Char("=")] + items)
        self.R.layout(row, self.res_px)
        cv.config(height=row.asc + row.desc + 12)
        self.R.draw(cv, row, 6, 6 + row.asc, THEME["res"], [], top=True)

    def update_preview(self):
        if not self.ed.root.items or self.just_evaluated:
            self.preview.config(text="")
            return
        try:
            main, _, _ = format_value(self.ev.evaluate(to_expr(self.ed.root)), self.ev.deg)
            self.preview.config(text="= " + main)
        except CalcError:
            self.preview.config(text="…")

    def evaluate(self):
        if not self.ed.root.items:
            return
        try:
            v = self.ev.evaluate(to_expr(self.ed.root))
        except CalcError as err:
            self.show_result(error=f"Error: {err}")
            self.detail.config(text="")
            self.preview.config(text="")
            self.result_items = None
            return
        main, decimal, polar = format_value(v, self.ev.deg)
        extra = []
        if decimal:
            extra.append(f"decimal: {decimal}")
        if polar:
            extra.append(f"polar: {polar}")
        self.result_items = value_items(v)
        self.show_result(self.result_items)
        self.detail.config(text="     ".join(extra))
        self.preview.config(text="")
        self.ev.ans = v
        text = to_text(self.ed.root)
        self.history.append((copy.deepcopy(self.ed.root), text, main,
                             copy.deepcopy(self.result_items)))
        self.hist_box.insert("end", f"{text}  =  {main}")
        self.hist_box.see("end")
        self.hist_idx = None
        self.ed.select_all()
        self.just_evaluated = True
        self.ed.render()

    # ---- history ----
    def history_nav(self, d):
        if not self.history:
            return
        if self.hist_idx is None:
            if d > 0:
                return
            self.hist_idx = len(self.history) - 1
        else:
            self.hist_idx += d
        if self.hist_idx >= len(self.history):
            self.hist_idx = None
            self.ed.set_row(Row())
        else:
            self.hist_idx = max(0, self.hist_idx)
            self.ed.set_row(copy.deepcopy(self.history[self.hist_idx][0]))
        self.just_evaluated = False
        self.ed.changed()

    def on_history_click(self, event):
        sel = self.hist_box.curselection()
        if sel:
            self.insert_result(self.history[sel[0]][3])

    def on_history_double(self, event):
        sel = self.hist_box.curselection()
        if sel:
            self.ed.set_row(copy.deepcopy(self.history[sel[0]][0]))
            self.just_evaluated = False
            self.ed.focus()
            self.ed.changed()

    def clear_history(self):
        self.history.clear()
        self.hist_box.delete(0, "end")
        self.hist_idx = None
        self.ed.focus()


def run_gui():
    import tkinter as tk
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    root = tk.Tk()
    CalculatorApp(root)
    root.mainloop()


# --------------------------------------------------------------------------
# Terminal mode
# --------------------------------------------------------------------------

def print_result(ev, text):
    try:
        v = ev.evaluate(text)
    except CalcError as err:
        print(f"Error: {err}")
        return
    ev.ans = v
    main, decimal, polar = format_value(v, ev.deg)
    print(f"= {main}")
    if decimal:
        print(f"  decimal: {decimal}")
    if polar:
        print(f"  polar:   {polar}")


def run_cli(args):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    ev = Evaluator()
    if "--deg" in args:
        ev.deg = True
        args = [a for a in args if a != "--deg"]
    if args and args[0] != "--cli":
        print_result(ev, " ".join(args))
        return
    print("Complex calculator - type an expression, 'deg'/'rad' to switch angles, 'quit' to exit.")
    while True:
        try:
            line = input("calc> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if line in ("quit", "exit", "q"):
            break
        if line in ("deg", "rad"):
            ev.deg = line == "deg"
            print(f"Angle mode: {line.upper()}")
        elif line:
            print_result(ev, line)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        run_cli(sys.argv[1:])
    else:
        run_gui()
