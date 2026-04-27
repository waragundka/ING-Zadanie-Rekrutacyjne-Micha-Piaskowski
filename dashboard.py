"""Streamlit dashboard for the NBP currency-basket simulator.

Run with:  streamlit run dashboard.py
"""
from __future__ import annotations

import logging
from dataclasses import asdict
from datetime import date, timedelta
from io import BytesIO
from pathlib import Path

import pandas as pd
import streamlit as st

from portfolio_sim import (
    Allocation,
    NBPAPIError,
    NBPClient,
    PortfolioSimulator,
    compute_metrics,
    record_run,
)
from portfolio_sim.report import build_one_pager
from portfolio_sim.visualizer import (
    allocation_pie_chart,
    daily_change_chart,
    drawdown_chart,
    return_attribution_chart,
    returns_distribution_chart,
    total_value_chart,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)-7s %(name)s | %(message)s")

DEFAULT_START = date.today() - timedelta(days=45)
ALLOCATION_KEYS = ("alloc_USD", "alloc_EUR", "alloc_HUF")

try:
    import kaleido  # noqa: F401  -- detection only, used implicitly by plotly
    _PDF_EXPORT_AVAILABLE = True
except ImportError:
    _PDF_EXPORT_AVAILABLE = False

PAGE_STYLE = """
    <style>
        #MainMenu, footer, header, .stDeployButton { visibility: hidden; display: none; }
        .block-container { padding-top: 2rem; padding-bottom: 3rem; max-width: 1400px; }
        [data-testid="stMetricValue"] { font-size: 1.4rem; font-weight: 600; color: #E5E5E5; }
        [data-testid="stMetricLabel"] { font-size: 0.78rem; color: #8A8A8A; text-transform: uppercase; letter-spacing: 0.04em; }
        [data-testid="stMetricDelta"] { font-size: 0.85rem; }
        h1 { font-size: 1.8rem !important; font-weight: 600; color: #E5E5E5; margin-bottom: 0.2rem; }
        h2 { font-size: 1.15rem !important; font-weight: 600; color: #E5E5E5; margin-top: 1.5rem; }
        h3 { font-size: 1rem !important; font-weight: 600; color: #E5E5E5; }
        hr { margin: 1.5rem 0 1rem 0; border-color: #2A2A2A; }
        .stButton button[kind="primary"] {
            background-color: #FF6200; border-color: #FF6200; color: white; font-weight: 600;
        }
        .stButton button[kind="primary"]:hover {
            background-color: #E55700; border-color: #E55700;
        }
        .alloc-residual {
            padding: 0.55rem 0.75rem;
            background: linear-gradient(90deg, #1F1F1F, #161616);
            border-left: 3px solid #2ECC71;
            border-radius: 4px;
            margin: 0.5rem 0 0.25rem 0;
            color: #E5E5E5;
            font-size: 0.85rem;
        }
        .alloc-residual strong { color: #2ECC71; font-weight: 600; }
        .alloc-residual--warn { border-left-color: #E74C3C; }
        .alloc-residual--warn strong { color: #E74C3C; }

        /* Custom KPI tile — same visual weight as st.metric, but value
           coloring is explicit (gain green, loss red, risk orange). */
        .kpi-tile { padding: 0.15rem 0 0.55rem 0; }
        .kpi-label { font-size: 0.78rem; color: #8A8A8A; text-transform: uppercase;
                     letter-spacing: 0.04em; line-height: 1.4; }
        .kpi-value { font-size: 1.4rem; font-weight: 600; color: #E5E5E5;
                     line-height: 1.3; margin-top: 0.15rem; font-variant-numeric: tabular-nums; }
        .kpi-value--pos { color: #2ECC71; }
        .kpi-value--neg { color: #E74C3C; }
        .kpi-value--risk { color: #FF6200; }
        .kpi-sub { font-size: 0.85rem; color: #8A8A8A; line-height: 1.3;
                   font-variant-numeric: tabular-nums; }
    </style>
"""

PLOTLY_CONFIG = {
    "displaylogo": False,
    # All chart titles, axis labels and threshold lines are baked in by the
    # builders — there's nothing for the user to edit, and leaving editable on
    # surfaces "Click to enter..." placeholders that overlap real labels.
    "editable": False,
    "modeBarButtonsToRemove": ["lasso2d", "select2d", "autoScale2d"],
    "scrollZoom": False,
    "toImageButtonOptions": {"format": "png", "scale": 2, "filename": "portfolio_chart"},
}


@st.cache_data(show_spinner=False, ttl=3600)
def _run_cached(
    amount: float,
    weights_items: tuple[tuple[str, float], ...],
    start: date,
    days: int,
) -> tuple[pd.DataFrame, dict, str, bytes, bytes | None]:
    """NBP history is immutable past today, so identical inputs reuse results."""
    allocation = Allocation(weights=dict(weights_items))
    simulator = PortfolioSimulator(NBPClient())
    result = simulator.run(amount=amount, allocation=allocation, start=start, holding_days=days)
    metrics = compute_metrics(result.valuations, result.initial_amount)
    audit_path = record_run(result, metrics)

    fig = build_one_pager(result, metrics)
    one_pager_html = fig.to_html(include_plotlyjs="cdn").encode("utf-8")
    one_pager_pdf: bytes | None = None
    if _PDF_EXPORT_AVAILABLE:
        try:
            one_pager_pdf = fig.to_image(format="pdf")
        except Exception as exc:  # kaleido import OK but rendering failed
            logging.getLogger(__name__).warning("PDF export failed: %s", exc)
    return result.valuations, asdict(metrics), str(audit_path), one_pager_html, one_pager_pdf


def _signed_color(value: float | None) -> str:
    """Map a signed quantity to a tile color class — gain green, loss red."""
    if value is None or value == 0:
        return ""
    return "kpi-value--pos" if value > 0 else "kpi-value--neg"


def _kpi_tile(
    col,
    label: str,
    value: str,
    *,
    color_class: str = "",
    sub: str | None = None,
) -> None:
    """Render a KPI cell with optional gain/loss coloring on the main value."""
    sub_html = f"<div class='kpi-sub'>{sub}</div>" if sub else ""
    col.markdown(
        f"<div class='kpi-tile'>"
        f"<div class='kpi-label'>{label}</div>"
        f"<div class='kpi-value {color_class}'>{value}</div>"
        f"{sub_html}"
        f"</div>",
        unsafe_allow_html=True,
    )


def _render_kpis(initial: float, metrics: dict) -> None:
    row1 = st.columns(4)
    _kpi_tile(row1[0], "Initial capital", f"{initial:,.2f} PLN")

    pnl = metrics["total_return_pln"]
    _kpi_tile(
        row1[1],
        "Final value",
        f"{metrics['final_value']:,.2f} PLN",
        color_class=_signed_color(pnl),
        sub=f"{pnl:+,.2f} PLN",
    )

    pct = metrics["total_return_pct"]
    _kpi_tile(row1[2], "Total return", f"{pct:+.2f}%", color_class=_signed_color(pct))
    _kpi_tile(row1[3], "Holding days", f"{metrics['holding_days']}")

    row2 = st.columns(4)
    best_value = metrics["best_day_value"]
    best_date = metrics["best_day"].strftime("%Y-%m-%d") if metrics["best_day"] is not None else None
    _kpi_tile(
        row2[0],
        "Best day",
        f"{best_value:+,.2f} PLN" if metrics["best_day"] is not None else "—",
        color_class=_signed_color(best_value),
        sub=best_date,
    )

    worst_value = metrics["worst_day_value"]
    worst_date = metrics["worst_day"].strftime("%Y-%m-%d") if metrics["worst_day"] is not None else None
    _kpi_tile(
        row2[1],
        "Worst day",
        f"{worst_value:+,.2f} PLN" if metrics["worst_day"] is not None else "—",
        color_class=_signed_color(worst_value),
        sub=worst_date,
    )

    dd = metrics["max_drawdown_pct"]
    _kpi_tile(row2[2], "Max drawdown", f"{dd:.2f}%", color_class=_signed_color(dd))
    _kpi_tile(row2[3], "Realized volatility", f"{metrics['realized_volatility_pct']:.2f}%")

    row3 = st.columns(4)
    sharpe = metrics.get("sharpe_ratio")
    sortino = metrics.get("sortino_ratio")
    _kpi_tile(
        row3[0],
        "Sharpe (raw, daily)",
        f"{sharpe:.3f}" if sharpe is not None else "—",
        color_class=_signed_color(sharpe),
    )
    _kpi_tile(
        row3[1],
        "Sortino (raw, daily)",
        f"{sortino:.3f}" if sortino is not None else "—",
        color_class=_signed_color(sortino),
    )
    # VaR/CVaR carry an inherent risk meaning regardless of sign — orange (ING)
    # rather than red, to distinguish regulatory tail-risk capital from realized loss.
    _kpi_tile(
        row3[2],
        "VaR 95% (1d)",
        f"{metrics['var_95_pln']:,.2f} PLN",
        color_class="kpi-value--risk" if metrics["var_95_pln"] > 0 else "",
    )
    _kpi_tile(
        row3[3],
        "CVaR 95% (1d)",
        f"{metrics['cvar_95_pln']:,.2f} PLN",
        color_class="kpi-value--risk" if metrics["cvar_95_pln"] > 0 else "",
    )


PRESETS: dict[str, tuple[float, float, float]] = {
    "Equal": (33.33, 33.34, 33.33),
    "USD-heavy": (60.0, 25.0, 15.0),
    "EUR-heavy": (15.0, 60.0, 25.0),
    "HUF-heavy": (15.0, 25.0, 60.0),
}


def _apply_preset(values: tuple[float, float, float]) -> None:
    for key, value in zip(ALLOCATION_KEYS, values):
        st.session_state[key] = float(value)


def _normalize_to_100() -> None:
    """Scale weights proportionally and patch drift onto the largest weight."""
    ss = st.session_state
    total = sum(ss[k] for k in ALLOCATION_KEYS)
    if total == 0:
        return
    for key in ALLOCATION_KEYS:
        ss[key] = round(ss[key] * 100 / total, 2)
    drift = round(100 - sum(ss[k] for k in ALLOCATION_KEYS), 2)
    if drift:
        ss[max(ALLOCATION_KEYS, key=lambda k: ss[k])] += drift


def _render_allocation_inputs() -> dict[str, float]:
    """Number inputs + presets — the pattern used by Bloomberg AIM and Aladdin."""
    st.sidebar.subheader("Currency split (%)")
    st.sidebar.caption("Type a weight per currency (decimals allowed). Total must equal 100%.")

    ss = st.session_state
    ss.setdefault("alloc_USD", 30.0)
    ss.setdefault("alloc_EUR", 40.0)
    ss.setdefault("alloc_HUF", 30.0)

    preset_top = st.sidebar.columns(2)
    preset_bottom = st.sidebar.columns(2)
    preset_slots = [*preset_top, *preset_bottom]
    for slot, (label, weights) in zip(preset_slots, PRESETS.items()):
        slot.button(
            label,
            use_container_width=True,
            on_click=_apply_preset,
            args=(weights,),
            key=f"preset_{label}",
        )

    values: dict[str, float] = {}
    for key in ALLOCATION_KEYS:
        code = key.removeprefix("alloc_")
        values[code] = st.sidebar.number_input(
            code,
            min_value=0.0,
            max_value=100.0,
            step=0.1,
            format="%.2f",
            key=key,
        )

    total = round(sum(values.values()), 2)
    st.sidebar.button(
        "Normalize to 100%",
        use_container_width=True,
        disabled=(abs(total - 100) < 1e-9 or total == 0),
        on_click=_normalize_to_100,
    )

    if abs(total - 100) < 1e-9:
        st.sidebar.markdown(
            "<div class='alloc-residual'>Total <strong>100.00%</strong> — fully allocated.</div>",
            unsafe_allow_html=True,
        )
    else:
        st.sidebar.markdown(
            f"<div class='alloc-residual alloc-residual--warn'>"
            f"Total <strong>{total:.2f}%</strong> — must be 100%.</div>",
            unsafe_allow_html=True,
        )

    return values


def _render_sidebar() -> tuple[float, date, dict[str, float], int, bool]:
    st.sidebar.header("Simulation parameters")
    amount = st.sidebar.number_input(
        "Investment amount (PLN)", min_value=1.0, value=1000.0, step=100.0, format="%.2f"
    )
    start = st.sidebar.date_input("Start date", value=DEFAULT_START, max_value=date.today())
    days = st.sidebar.number_input("Holding period (days)", min_value=1, max_value=365, value=30)

    percentages = _render_allocation_inputs()
    alloc_total = round(sum(percentages.values()), 2)
    alloc_valid = abs(alloc_total - 100.0) < 1e-9

    # Hardlock: don't let the user run a misweighted basket. This mirrors the
    # commit-disabled-until-balanced pattern from Aladdin / Bloomberg AIM.
    st.sidebar.markdown("")
    submitted = st.sidebar.button(
        "Run simulation",
        use_container_width=True,
        type="primary",
        disabled=not alloc_valid,
        help=(
            None
            if alloc_valid
            else f"Allocation must sum to 100% (currently {alloc_total:.2f}%)."
        ),
    )
    return amount, start, percentages, int(days), submitted


def _build_excel_bytes(valuations: pd.DataFrame, metrics: dict) -> bytes:
    metrics_view = {key: ("" if value is None else value) for key, value in metrics.items()}
    metrics_frame = pd.DataFrame([metrics_view])
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        valuations.to_excel(writer, sheet_name="Valuations")
        metrics_frame.to_excel(writer, sheet_name="KPIs", index=False)
    return buffer.getvalue()


def _render_downloads(
    valuations: pd.DataFrame,
    metrics: dict,
    start: date,
    one_pager_html: bytes,
    one_pager_pdf: bytes | None,
) -> None:
    csv_bytes = valuations.to_csv().encode("utf-8")
    excel_bytes = _build_excel_bytes(valuations, metrics)

    # 4 buttons when PDF export is wired up, 3 otherwise — keep equal width.
    column_count = 5 if one_pager_pdf is not None else 4
    cols = st.columns([1] * (column_count - 1) + [2])
    cols[0].download_button(
        "Download CSV",
        data=csv_bytes,
        file_name=f"portfolio_{start.isoformat()}.csv",
        mime="text/csv",
        use_container_width=True,
    )
    cols[1].download_button(
        "Download Excel",
        data=excel_bytes,
        file_name=f"portfolio_{start.isoformat()}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )
    cols[2].download_button(
        "Download report (HTML)",
        data=one_pager_html,
        file_name=f"portfolio_report_{start.isoformat()}.html",
        mime="text/html",
        use_container_width=True,
        help="Single-page summary — opens in any browser, prints cleanly to PDF.",
    )
    if one_pager_pdf is not None:
        cols[3].download_button(
            "Download report (PDF)",
            data=one_pager_pdf,
            file_name=f"portfolio_report_{start.isoformat()}.pdf",
            mime="application/pdf",
            use_container_width=True,
            help="Static one-pager rendered with kaleido.",
        )


def _plot(fig) -> None:
    st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CONFIG)


def main() -> None:
    st.set_page_config(
        page_title="NBP Currency Basket Simulator",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    st.markdown(PAGE_STYLE, unsafe_allow_html=True)

    st.title("NBP Currency Basket Simulator")
    st.caption(
        "Buy-and-hold simulation across three currencies, priced on NBP table-A mid rates "
        "(api.nbp.pl)."
    )

    amount, start, percentages, days, submitted = _render_sidebar()

    if not submitted:
        st.info("Set the parameters in the sidebar and press **Run simulation**.")
        return

    if abs(sum(percentages.values()) - 100.0) > 1e-5:
        st.error(
            "Currency split must sum to exactly 100%. Adjust the weights in the sidebar "
            "or click **Normalize to 100%**."
        )
        return

    try:
        allocation = Allocation.from_percentages(percentages)
    except ValueError as exc:
        st.error(str(exc))
        return

    weights_items = tuple(allocation.weights.items())
    try:
        with st.spinner("Fetching NBP rates and pricing the basket..."):
            (
                valuations,
                metrics,
                audit_path,
                one_pager_html,
                one_pager_pdf,
            ) = _run_cached(amount, weights_items, start, days)
    except NBPAPIError as exc:
        st.error(f"NBP API error: {exc}")
        return
    except ValueError as exc:
        st.error(f"Simulation error: {exc}")
        return

    st.subheader("Key performance indicators")
    _render_kpis(amount, metrics)
    st.caption(f"Audit record: `{Path(audit_path).name}`")

    st.divider()
    st.subheader("Portfolio trajectory")
    _plot(total_value_chart(valuations, amount))

    left, right = st.columns(2, gap="medium")
    with left:
        _plot(daily_change_chart(valuations))
    with right:
        _plot(drawdown_chart(valuations))

    st.divider()
    st.subheader("Risk and return attribution")
    risk_col, attribution_col = st.columns(2, gap="medium")
    with risk_col:
        _plot(
            returns_distribution_chart(
                valuations, metrics["var_95_pln"], metrics["cvar_95_pln"]
            )
        )
    with attribution_col:
        _plot(return_attribution_chart(valuations, allocation))

    st.divider()
    st.subheader("Allocation snapshots")
    pie_left, pie_right = st.columns(2, gap="medium")
    codes = list(allocation.codes)
    initial_values = [amount * allocation.weights[code] for code in codes]
    final_values = [valuations[f"value_{code}"].iloc[-1] for code in codes]
    with pie_left:
        _plot(allocation_pie_chart(codes, initial_values, "Allocation · day 1"))
    with pie_right:
        _plot(allocation_pie_chart(codes, final_values, f"Allocation · day {days}"))

    st.divider()
    st.subheader("Export")
    _render_downloads(valuations, metrics, start, one_pager_html, one_pager_pdf)

    with st.expander("Raw valuation table"):
        st.dataframe(valuations.round(4), use_container_width=True)


if __name__ == "__main__":
    main()
