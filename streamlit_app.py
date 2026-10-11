import itertools
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

from calc import CalcError, Evaluator, Q, format_value
from latex_io import latex_to_expr, value_latex

st.set_page_config(page_title="Complex Calculator", page_icon="🧮", layout="centered")

math_input = components.declare_component(
    "math_input", path=str(Path(__file__).parent / "math_input"))

ss = st.session_state
ss.setdefault("history", [])          # dicts: expr_latex, result_latex, main, value
ss.setdefault("ans", Q(0))
ss.setdefault("result", None)         # dict for the last "=" press
ss.setdefault("last_eval", None)
ss.setdefault("insert", None)         # something to push into the editor
_ids = ss.setdefault("_ids", itertools.count(1))


def push_to_editor(latex, mode):
    """Button callback: send something into the editor on the next run."""
    if mode == "insert" and (latex.startswith("-") or any(ch in latex[1:] for ch in "+-")):
        latex = rf"\left({latex}\right)"
    ss.insert = {"latex": latex, "mode": mode, "nonce": next(_ids)}


def clear_history():
    ss.history = []


def evaluate(latex, deg):
    ev = Evaluator()
    ev.deg, ev.ans = deg, ss.ans
    return ev.evaluate(latex_to_expr(latex, deg))


# ---- header ----
left, right = st.columns([3, 2], vertical_alignment="bottom")
left.markdown("### 🧮 Complex Calculator")
mode = right.radio("Angles", ["RAD", "DEG"], horizontal=True, label_visibility="collapsed")
deg = mode == "DEG"

# ---- editor ----
val = math_input(insert=ss.insert, key="editor", default=None)
latex = (val or {}).get("latex", "")

if val and val.get("action") == "eval" and val.get("nonce") != ss.last_eval:
    ss.last_eval = val["nonce"]
    try:
        v = evaluate(latex, deg)
        main, decimal, polar = format_value(v, deg)
        res = {"latex": value_latex(v), "main": main, "decimal": decimal, "polar": polar}
        ss.ans = v
        ss.history.insert(0, {"expr": latex, "result": res["latex"], "main": main})
    except CalcError as err:
        res = {"error": str(err)}
    ss.result = res

# ---- live preview + result ----
preview = ""
if latex.strip() and not (val and val.get("action") == "eval"):
    try:
        preview = "= " + format_value(evaluate(latex, deg), deg)[0]
    except CalcError:
        preview = "…"
st.caption(preview or " ")

res = ss.result
if res:
    if "error" in res:
        st.error(res["error"])
    else:
        st.latex("=" + res["latex"])
        details = []
        if res["decimal"]:
            details.append(f"decimal: `{res['decimal']}`")
        if res["polar"]:
            details.append(f"polar: `{res['polar']}`")
        if details:
            st.markdown(" &nbsp;·&nbsp; ".join(details))

# ---- history ----
if ss.history:
    st.divider()
    head, clear = st.columns([4, 1], vertical_alignment="center")
    head.markdown("**History**")
    clear.button("Clear", on_click=clear_history, width="stretch")
    # callbacks (not `if st.button(...)`) so a click can't be lost to an editor update
    for k, h in enumerate(ss.history[:30]):
        c1, c2, c3 = st.columns([6, 1.3, 1.1], vertical_alignment="center")
        c1.latex(f"{h['expr']} = {h['result']}")
        c2.button("Insert", key=f"ins{k}", help="Insert this result at the cursor", width="stretch",
                  on_click=push_to_editor, args=(h["result"], "insert"))
        c3.button("Edit", key=f"edit{k}", help="Load this expression into the editor",
                  width="stretch", on_click=push_to_editor, args=(h["expr"], "replace"))

with st.expander("How to use"):
    st.markdown(r"""
- **Type** with the keyboard or click the buttons. `/` makes a fraction (what's left of the cursor
  goes on top), `^` an exponent, `sqrt` a root, `pi` becomes π, `i` or `j` is the imaginary unit.
- **Navigate** with the arrow keys (↑/↓ jump between top and bottom of a fraction);
  **Tab** jumps to the next empty box. **Enter** solves, **Esc** clears.
- **Wrap**: select part of the expression, then click a function (√, sin, a/b, x², …).
- After a result, typing an operator continues from **ans**.
- Exact arithmetic wherever possible: $\sqrt{-4}=2i$, $\sqrt{3+4i}=2+i$, $e^{i\pi}=-1$;
  otherwise principal complex values ($\ln(-1)=\pi i$). ∛ of a negative real gives the real root.
- `E` means ×10ⁿ (`2E5` = 200000); lowercase `e` is Euler's number.
""")
