"""
Web version of the complex calculator.

Run locally:   streamlit run streamlit_app.py
Deploy:        push this folder to GitHub, then create an app on share.streamlit.io
               with streamlit_app.py as the main file.
"""

import itertools
import math
from pathlib import Path

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from calc import CalcError, Evaluator, Q, format_value, mat_mul
from latex_io import latex_to_expr, value_latex

st.set_page_config(page_title="Complex Calculator", page_icon="🧮", layout="centered")

math_input = components.declare_component(
    "math_input", path=str(Path(__file__).parent / "math_input"))

MAX_SIZE = 5

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

tab_calc, tab_mat = st.tabs(["Calculator", "Matrices"])


# ==========================================================================
# Calculator tab
# ==========================================================================

with tab_calc:
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
            c2.button("Insert", key=f"ins{k}", help="Insert this result at the cursor",
                      width="stretch", on_click=push_to_editor, args=(h["result"], "insert"))
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


# ==========================================================================
# Matrices tab
# ==========================================================================

def _grid(name):
    """The cell texts of matrix `name`, kept at full 5x5 so shrinking a matrix loses nothing."""
    return ss.setdefault(f"{name}_grid", [[""] * MAX_SIZE for _ in range(MAX_SIZE)])


def matrix_editor(name, rows, cols):
    grid = _grid(name)
    # the editor's base table is only rebuilt when the size changes (or a button refills it);
    # otherwise the widget keeps its own edits
    if ss.get(f"{name}_shape") != (rows, cols):
        ss[f"{name}_shape"] = (rows, cols)
        ss[f"{name}_ver"] = ss.get(f"{name}_ver", 0) + 1
        ss[f"{name}_base"] = pd.DataFrame(
            [grid[i][:cols] for i in range(rows)],
            index=[str(i + 1) for i in range(rows)], columns=[str(j + 1) for j in range(cols)])
    base = ss[f"{name}_base"]
    edited = st.data_editor(
        base, key=f"{name}_editor{ss[f'{name}_ver']}", width="stretch",
        column_config={c: st.column_config.TextColumn(c) for c in base.columns})
    for i in range(rows):
        for j in range(cols):
            v = edited.iat[i, j]
            empty = v is None or (isinstance(v, float) and math.isnan(v))
            grid[i][j] = "" if empty else str(v)
    return [row[:cols] for row in grid[:rows]]


def parse_matrix(name, cells):
    ev = Evaluator()
    ev.deg, ev.ans = deg, ss.ans
    out = []
    for i, row in enumerate(cells):
        out_row = []
        for j, text in enumerate(row):
            try:
                out_row.append(ev.evaluate(text.strip() or "0"))     # empty cell = 0
            except CalcError as err:
                raise CalcError(f"{name}[{i + 1},{j + 1}] = '{text}': {err}")
        out.append(out_row)
    return out


def bmatrix(m, decimals=False):
    def cell(v):
        if decimals:
            main, dec, _ = format_value(v, deg)
            return dec or main
        return value_latex(v)
    rows = r" \\ ".join(" & ".join(cell(v) for v in row) for row in m)
    return rf"\begin{{bmatrix}} {rows} \end{{bmatrix}}"


def refill(name, texts):
    """Callback: replace a matrix's cells and make its editor reload."""
    grid = _grid(name)
    for i in range(MAX_SIZE):
        for j in range(MAX_SIZE):
            grid[i][j] = texts[i][j] if i < len(texts) and j < len(texts[0]) else ""
    ss[f"{name}_shape"] = None


def use_result_as_a(texts):
    refill("A", texts)
    ss.m_inner = len(texts[0])


def clear_matrices():
    refill("A", [[]])
    refill("B", [[]])


with tab_mat:
    st.markdown("**Matrix multiplication**  A · B")
    sizes = list(range(1, MAX_SIZE + 1))
    s1, s2, s3 = st.columns(3)
    a_rows = s1.selectbox("Rows of A", sizes, index=1, key="m_a_rows")
    inner = s2.selectbox("Columns of A = rows of B", sizes, index=1, key="m_inner")
    b_cols = s3.selectbox("Columns of B", sizes, index=1, key="m_b_cols")

    ca, cb = st.columns(2)
    with ca:
        st.markdown(f"**A** ({a_rows}×{inner})")
        a_cells = matrix_editor("A", a_rows, inner)
    with cb:
        st.markdown(f"**B** ({inner}×{b_cols})")
        b_cells = matrix_editor("B", inner, b_cols)
    st.caption("Each cell takes any calculator expression: `3+4i`, `1/2`, `sqrt(2)`, `2pi`, "
               "`e^(i*pi/3)`, `ans` … Empty cells count as 0.")

    try:
        A = parse_matrix("A", a_cells)
        B = parse_matrix("B", b_cells)
        C = mat_mul(A, B)
    except CalcError as err:
        st.error(str(err))
    else:
        decimals = st.toggle("Show decimals", key="m_decimals")
        st.latex(rf"A \cdot B = {bmatrix(C, decimals)}")
        with st.expander("Full product"):
            st.latex(rf"{bmatrix(A, decimals)} \cdot {bmatrix(B, decimals)} = {bmatrix(C, decimals)}")
        c_texts = [[format_value(v, deg)[0] for v in row] for row in C]
        b1, b2, _ = st.columns([1.3, 1, 2])
        b1.button("Use result as A", on_click=use_result_as_a, args=(c_texts,), width="stretch",
                  help="Put A·B into A, e.g. to multiply by B again")
        b2.button("Clear", on_click=clear_matrices, width="stretch")
