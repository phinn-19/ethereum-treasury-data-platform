from pathlib import Path
from html import escape

import duckdb
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st


# =============================================================================
# APP CONFIG
# =============================================================================

DB = Path("data", "silver", "ethereum_treasury.duckdb")

COLORS = {
    "navy": "#2B5277",
    "navy_2": "#466F98",
    "blue": "#7F9BB6",
    "blue_light": "#AFC2D2",
    "gold": "#F1DB82",
    "gold_dark": "#D6B64C",
    "teal": "#466F98",
    "orange": "#D6B64C",
    "slate": "#AAB4BE",
    "ink": "#1C2C3D",
    "muted": "#6D7B8B",
    "grid": "#E8EDF1",
    "border": "#DCE3E9",
    "background": "#F6F8FA",
    "surface": "#FFFFFF",
}

DIRECTION_COLORS = {
    "IN": COLORS["navy_2"],
    "OUT": COLORS["gold_dark"],
    "INTERNAL": COLORS["slate"],
}

st.set_page_config(
    page_title="Ethereum Treasury Monitoring Data Platform",
    page_icon="Ξ",
    layout="wide",
    initial_sidebar_state="expanded",
)


# =============================================================================
# STYLE
# =============================================================================

def apply_styles():
    st.markdown(
        f"""
        <style>
        .stApp {{
            background:
                radial-gradient(
                    circle at 88% 7%,
                    rgba(241, 219, 130, 0.16) 0,
                    rgba(241, 219, 130, 0.00) 27rem
                ),
                radial-gradient(
                    circle at 22% 14%,
                    rgba(127, 155, 182, 0.13) 0,
                    rgba(127, 155, 182, 0.00) 32rem
                ),
                linear-gradient(
                    135deg,
                    #FBFCFD 0%,
                    #F3F7FA 54%,
                    #FCFAF3 100%
                );
            color: {COLORS["ink"]};
        }}

        .block-container {{
            max-width: 1480px;
            padding-top: 1.1rem;
            padding-bottom: 3rem;
        }}

        [data-testid="stSidebar"] {{
            background:
                radial-gradient(
                    circle at 15% 10%,
                    rgba(127, 155, 182, 0.18) 0,
                    rgba(127, 155, 182, 0.00) 16rem
                ),
                linear-gradient(
                    165deg,
                    #355F86 0%,
                    #2E557B 46%,
                    #294C70 100%
                );
            border-right: 1px solid rgba(255, 255, 255, 0.10);
        }}

        [data-testid="stSidebar"] h1,
        [data-testid="stSidebar"] h2,
        [data-testid="stSidebar"] h3,
        [data-testid="stSidebar"] p,
        [data-testid="stSidebar"] label {{
            color: #FFFFFF !important;
        }}

        [data-testid="stSidebar"] [data-testid="stCaptionContainer"] p {{
            color: #D7E0E8 !important;
        }}

        [data-testid="stSidebar"] .stButton > button {{
            background:
                linear-gradient(
                    135deg,
                    #F1D464 0%,
                    #E8C547 55%,
                    #DDBA39 100%
                ) !important;
            color: #203B55 !important;
            border: 1px solid rgba(255, 255, 255, 0.24) !important;
            border-radius: 8px !important;
            font-weight: 750 !important;
            box-shadow: 0 4px 12px rgba(17, 41, 63, 0.16);
            transition:
                transform 160ms ease,
                box-shadow 160ms ease,
                filter 160ms ease;
        }}

        [data-testid="stSidebar"] .stButton > button * {{
            color: #203B55 !important;
        }}

        [data-testid="stSidebar"] .stButton > button:hover {{
            transform: translateY(-1px);
            box-shadow: 0 7px 16px rgba(17, 41, 63, 0.20);
            filter: brightness(1.035);
        }}

        [data-testid="stSidebar"] .stButton > button:active {{
            transform: translateY(0);
            filter: brightness(0.98);
        }}

        [data-testid="stSidebar"] input,
        [data-testid="stSidebar"] [data-baseweb="select"] > div {{
            border-radius: 8px !important;
        }}

        [data-baseweb="tag"] {{
            background: {COLORS["gold"]} !important;
            color: #203B55 !important;
        }}

        [data-baseweb="tag"] * {{
            color: #203B55 !important;
        }}

        [data-testid="stHeader"] {{
            background: transparent !important;
            height: 2.75rem !important;
            pointer-events: none;
        }}

        [data-testid="stToolbar"] {{
            visibility: visible !important;
            opacity: 1 !important;
            pointer-events: auto !important;
        }}

        [data-testid="stDeployButton"] {{
            display: none !important;
        }}

        #MainMenu {{
            visibility: hidden;
        }}

        /*
        Streamlit has used different test IDs for the collapsed sidebar
        control across versions. Support all common variants.
        */
        [data-testid="collapsedControl"],
        [data-testid="stSidebarCollapsedControl"],
        [data-testid="stSidebarCollapseButton"] {{
            visibility: visible !important;
            display: flex !important;
            opacity: 1 !important;
            pointer-events: auto !important;
            z-index: 999999 !important;
        }}

        [data-testid="collapsedControl"],
        [data-testid="stSidebarCollapsedControl"] {{
            position: fixed !important;
            top: 0.55rem !important;
            left: 0.55rem !important;
        }}

        [data-testid="collapsedControl"] button,
        [data-testid="stSidebarCollapsedControl"] button,
        [data-testid="stSidebarCollapseButton"] button {{
            visibility: visible !important;
            opacity: 1 !important;
            pointer-events: auto !important;
            background: rgba(255, 255, 255, 0.96) !important;
            color: {COLORS["navy"]} !important;
            border: 1px solid rgba(43, 82, 119, 0.22) !important;
            border-radius: 8px !important;
            box-shadow: 0 4px 14px rgba(31, 55, 79, 0.14) !important;
        }}

        [data-testid="collapsedControl"] button:hover,
        [data-testid="stSidebarCollapsedControl"] button:hover,
        [data-testid="stSidebarCollapseButton"] button:hover {{
            background: #FFFFFF !important;
            border-color: rgba(43, 82, 119, 0.36) !important;
        }}

        [data-testid="collapsedControl"] svg,
        [data-testid="stSidebarCollapsedControl"] svg,
        [data-testid="stSidebarCollapseButton"] svg {{
            color: {COLORS["navy"]} !important;
            fill: currentColor !important;
        }}

        h1, h2, h3 {{
            color: {COLORS["ink"]};
            letter-spacing: -0.025em;
        }}

        .dashboard-header {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 1rem;
            position: relative;
            overflow: hidden;
            background:
                radial-gradient(
                    circle at 92% 18%,
                    rgba(241, 219, 130, 0.28) 0,
                    rgba(241, 219, 130, 0.00) 17rem
                ),
                linear-gradient(
                    108deg,
                    #315A80 0%,
                    #4E7597 50%,
                    #8FA5B6 100%
                );
            background-size: 125% 125%;
            border-radius: 10px;
            padding: 0.9rem 1.05rem;
            margin-bottom: 0.78rem;
            border-bottom: 3px solid {COLORS["gold"]};
            box-shadow:
                0 10px 28px rgba(43, 82, 119, 0.13);
            animation:
                panelIn 420ms ease both,
                headerGradient 10s ease-in-out 450ms infinite alternate;
        }}

        .dashboard-header > * {{
            position: relative;
            z-index: 1;
        }}

        .dashboard-header::after {{
            content: "";
            position: absolute;
            inset: 0;
            pointer-events: none;
            background:
                linear-gradient(
                    112deg,
                    transparent 18%,
                    rgba(255, 255, 255, 0.00) 36%,
                    rgba(255, 255, 255, 0.10) 50%,
                    rgba(255, 255, 255, 0.00) 64%,
                    transparent 82%
                );
            transform: translateX(-120%);
            animation:
                headerSheen 7.5s ease-in-out 1.4s infinite;
        }}

        .dashboard-eyebrow {{
            color: {COLORS["gold"]};
            font-size: 0.7rem;
            font-weight: 800;
            letter-spacing: 0.12em;
            text-transform: uppercase;
            margin-bottom: 0.16rem;
        }}

        .dashboard-title {{
            color: #FFFFFF;
            font-size: 1.72rem;
            line-height: 1.05;
            font-weight: 780;
            letter-spacing: -0.035em;
        }}

        .dashboard-subtitle {{
            color: #D7E4EE;
            font-size: 0.78rem;
            margin-top: 0.24rem;
        }}

        .status-wrap {{
            display: flex;
            gap: 0.45rem;
            flex-wrap: wrap;
            justify-content: flex-end;
        }}

        .status-pill {{
            display: inline-flex;
            align-items: center;
            gap: 0.35rem;
            background:
                linear-gradient(
                    135deg,
                    rgba(255, 255, 255, 0.16),
                    rgba(255, 255, 255, 0.08)
                );
            border: 1px solid rgba(255, 255, 255, 0.24);
            color: #FFFFFF;
            padding: 0.4rem 0.62rem;
            border-radius: 999px;
            font-size: 0.72rem;
            font-weight: 650;
            white-space: nowrap;
        }}

        .status-pill-gold {{
            background: {COLORS["gold"]};
            border-color: {COLORS["gold"]};
            color: {COLORS["navy"]};
        }}

        .status-pill-warm {{
            background:
                linear-gradient(
                    135deg,
                    rgba(255, 246, 205, 0.25),
                    rgba(241, 219, 130, 0.12)
                );
            border-color: rgba(255, 242, 186, 0.34);
        }}

        .status-dot {{
            width: 7px;
            height: 7px;
            border-radius: 999px;
            background: #71D3B8;
            box-shadow: 0 0 0 3px rgba(113, 211, 184, 0.15);
        }}

        .read-guide {{
            display: flex;
            align-items: center;
            gap: 0.7rem;
            flex-wrap: wrap;
            background:
                linear-gradient(
                    135deg,
                    rgba(255, 255, 255, 0.86),
                    rgba(247, 250, 252, 0.92)
                );
            border: 1px solid {COLORS["border"]};
            border-radius: 8px;
            padding: 0.52rem 0.66rem;
            margin: 0.1rem 0 0.72rem 0;
            color: {COLORS["muted"]};
            font-size: 0.71rem;
            box-shadow: 0 2px 7px rgba(22, 32, 43, 0.025);
        }}

        .read-chip {{
            display: inline-flex;
            align-items: center;
            gap: 0.32rem;
            white-space: nowrap;
        }}

        .read-dot {{
            width: 7px;
            height: 7px;
            border-radius: 999px;
            display: inline-block;
        }}

        .section-title {{
            color: {COLORS["ink"]};
            font-size: 1.15rem;
            font-weight: 730;
            letter-spacing: -0.015em;
            margin-top: 0.10rem;
            margin-bottom: 0.1rem;
        }}

        .section-note {{
            color: {COLORS["muted"]};
            font-size: 0.8rem;
            margin-bottom: 0.45rem;
        }}

        .kpi-card {{
            height: 96px;
            display: grid;
            grid-template-columns: minmax(0, 1fr) 43%;
            align-items: center;
            gap: 0.35rem;
            background:
                radial-gradient(
                    circle at 90% 16%,
                    color-mix(
                        in srgb,
                        var(--accent) 10%,
                        transparent
                    ) 0,
                    transparent 9rem
                ),
                linear-gradient(
                    145deg,
                    #FFFFFF 0%,
                    color-mix(
                        in srgb,
                        var(--accent) 5%,
                        #FFFFFF
                    ) 100%
                );
            border: 1px solid {COLORS["border"]};
            border-radius: 8px;
            padding: 0.56rem 0.58rem 0.48rem 0.62rem;
            box-shadow: 0 2px 7px rgba(22, 32, 43, 0.035);
            position: relative;
            overflow: hidden;
            transition:
                transform 180ms ease,
                box-shadow 180ms ease,
                border-color 180ms ease;
            animation: cardIn 420ms ease both;
        }}

        .kpi-card::before {{
            content: "";
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            height: 3px;
            background: var(--accent);
        }}

        .kpi-card:hover {{
            transform: translateY(-3px);
            border-color: #C9D2DC;
            box-shadow: 0 10px 25px rgba(22, 32, 43, 0.075);
        }}

        .kpi-content {{
            min-width: 0;
            align-self: center;
        }}

        .kpi-label {{
            color: {COLORS["muted"]};
            font-size: 0.62rem;
            font-weight: 760;
            letter-spacing: 0.045em;
            text-transform: uppercase;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }}

        .kpi-value {{
            color: {COLORS["ink"]};
            font-size: 1.28rem;
            line-height: 1.12;
            font-weight: 780;
            margin-top: 0.18rem;
            white-space: nowrap;
        }}

        .kpi-note {{
            color: {COLORS["muted"]};
            font-size: 0.58rem;
            margin-top: 0.10rem;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }}

        .kpi-spark {{
            width: 100%;
            align-self: center;
            opacity: 0.98;
        }}

        .spark-path {{
            stroke-dasharray: 500;
            stroke-dashoffset: 500;
            animation: drawSpark 900ms ease forwards 120ms;
        }}

        .spark-area {{
            opacity: 0;
            animation:
                sparkAreaIn 620ms ease forwards 260ms;
        }}

        .spark-dot {{
            opacity: 0;
            transform-box: fill-box;
            transform-origin: center;
            animation:
                sparkDotIn 360ms ease forwards 760ms;
        }}

        div[data-testid="stPlotlyChart"] {{
            background:
                radial-gradient(
                    circle at 92% 8%,
                    rgba(232, 197, 71, 0.07) 0,
                    rgba(232, 197, 71, 0.00) 12rem
                ),
                linear-gradient(
                    145deg,
                    #FFFFFF 0%,
                    #FBFCFE 72%,
                    #F8FAFC 100%
                );
            border: 1px solid {COLORS["border"]};
            border-radius: 8px;
            padding: 0.05rem;
            box-shadow: 0 2px 7px rgba(22, 32, 43, 0.025);
            transition:
                transform 180ms ease,
                box-shadow 180ms ease;
            animation: panelIn 460ms ease both;
        }}

        div[data-testid="stPlotlyChart"]:hover {{
            transform: translateY(-1px);
            box-shadow: 0 8px 20px rgba(22, 32, 43, 0.055);
        }}

        div[data-testid="stDataFrame"] {{
            background: #FFFFFF;
            border: 1px solid {COLORS["border"]};
            border-radius: 8px;
            overflow: hidden;
        }}

        .alert-card {{
            background: #FFFFFF;
            border: 1px solid {COLORS["border"]};
            border-left: 4px solid {COLORS["gold"]};
            border-radius: 8px;
            padding: 0.7rem 0.75rem;
            min-height: 112px;
            box-shadow: 0 2px 7px rgba(22, 32, 43, 0.03);
            transition: transform 180ms ease, box-shadow 180ms ease;
            animation: cardIn 420ms ease both;
        }}

        .alert-card:hover {{
            transform: translateY(-2px);
            box-shadow: 0 8px 20px rgba(22, 32, 43, 0.06);
        }}

        .alert-top {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 0.55rem;
        }}

        .alert-value {{
            color: {COLORS["ink"]};
            font-size: 1.05rem;
            font-weight: 780;
        }}

        .alert-badge {{
            display: inline-block;
            padding: 0.18rem 0.42rem;
            border-radius: 999px;
            color: #FFFFFF;
            font-size: 0.62rem;
            font-weight: 800;
            letter-spacing: 0.03em;
        }}

        .alert-title {{
            color: {COLORS["ink"]};
            font-size: 0.78rem;
            font-weight: 720;
            margin-top: 0.38rem;
        }}

        .alert-meta {{
            color: {COLORS["muted"]};
            font-size: 0.67rem;
            line-height: 1.35;
            margin-top: 0.18rem;
        }}

        @keyframes headerGradient {{
            0% {{
                background-position: 0% 50%;
            }}
            100% {{
                background-position: 100% 50%;
            }}
        }}

        @keyframes headerSheen {{
            0%, 66% {{
                transform: translateX(-120%);
            }}
            82%, 100% {{
                transform: translateX(120%);
            }}
        }}

        @keyframes sparkAreaIn {{
            from {{
                opacity: 0;
            }}
            to {{
                opacity: 1;
            }}
        }}

        @keyframes sparkDotIn {{
            from {{
                opacity: 0;
                transform: scale(0.45);
            }}
            to {{
                opacity: 1;
                transform: scale(1);
            }}
        }}

        @keyframes cardIn {{
            from {{
                opacity: 0;
                transform: translateY(7px);
            }}
            to {{
                opacity: 1;
                transform: translateY(0);
            }}
        }}

        @keyframes panelIn {{
            from {{
                opacity: 0;
                transform: translateY(5px);
            }}
            to {{
                opacity: 1;
                transform: translateY(0);
            }}
        }}

        @keyframes drawSpark {{
            to {{
                stroke-dashoffset: 0;
            }}
        }}

        @media (max-width: 1000px) {{
            .dashboard-header {{
                flex-direction: column;
            }}

            .status-wrap {{
                justify-content: flex-start;
            }}

            .kpi-card {{
                height: 96px;
            }}
        }}

        @media (prefers-reduced-motion: reduce) {{
            .kpi-card,
            div[data-testid="stPlotlyChart"],
            .spark-path {{
                animation: none;
                transition: none;
            }}
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


apply_styles()


# =============================================================================
# DATA LOADING
# =============================================================================

@st.cache_data(show_spinner="Loading treasury data...")
def load_data():
    if not DB.exists():
        raise FileNotFoundError(f"DuckDB not found: {DB}")

    con = duckdb.connect(
        str(DB),
        read_only=True,
    )

    try:
        con.execute(
            "SET TimeZone='UTC'"
        )

        return {
            "wallets":
                con.execute(
                    """
                    SELECT *
                    FROM gold.wallets
                    """
                ).df(),

            "org_erc20":
                con.execute(
                    """
                    SELECT *
                    FROM gold.organization_daily_erc20_flows
                    """
                ).df(),

            "org_native":
                con.execute(
                    """
                    SELECT *
                    FROM gold.organization_daily_native_eth_usd_flows
                    """
                ).df(),

            "wallet_erc20":
                con.execute(
                    """
                    SELECT *
                    FROM gold.wallet_daily_erc20_flows
                    """
                ).df(),

            "wallet_native":
                con.execute(
                    """
                    SELECT *
                    FROM gold.wallet_daily_native_eth_usd_flows
                    """
                ).df(),

            "erc20_values":
                con.execute(
                    """
                    SELECT *
                    FROM gold.wallet_erc20_transfer_valuations
                    """
                ).df(),

            "native_values":
                con.execute(
                    """
                    SELECT *
                    FROM gold.organization_native_eth_valuations
                    """
                ).df(),

            "large_erc20":
                con.execute(
                    """
                    SELECT *
                    FROM gold.organization_large_erc20_transfers
                    """
                ).df(),

            "large_native":
                con.execute(
                    """
                    SELECT *
                    FROM gold.organization_large_native_eth_transfers
                    """
                ).df(),
        }

    finally:
        con.close()


# =============================================================================
# HELPERS
# =============================================================================

def numeric_columns(dataframe, columns):
    out = dataframe.copy()

    for column in columns:
        if column in out.columns:
            out[column] = pd.to_numeric(
                out[column],
                errors="coerce",
            )

    return out


def safe_sum(series):
    if series.empty:
        return 0.0

    value = series.sum(
        min_count=1
    )

    if pd.isna(value):
        return 0.0

    return float(value)


def format_usd(value):
    value = float(value)
    absolute = abs(value)

    if absolute >= 1_000_000_000:
        return (
            f"${value / 1_000_000_000:,.2f}B"
        )

    if absolute >= 1_000_000:
        return (
            f"${value / 1_000_000:,.2f}M"
        )

    if absolute >= 1_000:
        return (
            f"${value / 1_000:,.2f}K"
        )

    return (
        f"${value:,.2f}"
    )


def format_percentage(
    numerator,
    denominator,
):
    if denominator == 0:
        return "N/A"

    return (
        f"{numerator / denominator * 100:.1f}%"
    )


def short_address(value):
    if (
        value is None
        or pd.isna(value)
    ):
        return "—"

    value = str(value)

    if len(value) <= 18:
        return value

    return (
        f"{value[:8]}"
        f"…"
        f"{value[-6:]}"
    )


def section_header(
    title,
    note=None,
):
    title_html = (
        '<div class="section-title">'
        + escape(title)
        + "</div>"
    )

    st.markdown(
        title_html,
        unsafe_allow_html=True,
    )

    if note:
        note_html = (
            '<div class="section-note">'
            + escape(note)
            + "</div>"
        )

        st.markdown(
            note_html,
            unsafe_allow_html=True,
        )


def sparkline_svg(
    values,
    color,
):
    clean_values = (
        pd.Series(values)
        .dropna()
        .astype(float)
        .tail(18)
        .tolist()
    )

    if not clean_values:
        clean_values = [0.0, 0.0]

    if len(clean_values) == 1:
        clean_values = [
            clean_values[0],
            clean_values[0],
        ]

    width = 118
    height = 48
    pad = 3

    minimum = min(clean_values)
    maximum = max(clean_values)

    if maximum == minimum:
        y_values = [
            height / 2
            for _ in clean_values
        ]
    else:
        y_values = [
            height
            -
            pad
            -
            (
                (value - minimum)
                /
                (maximum - minimum)
            )
            *
            (
                height
                -
                2 * pad
            )
            for value
            in clean_values
        ]

    step = (
        (width - 2 * pad)
        /
        max(
            len(clean_values) - 1,
            1,
        )
    )

    line_points = [
        (
            pad + index * step,
            y_values[index],
        )
        for index
        in range(
            len(clean_values)
        )
    ]

    points = " ".join(
        f"{x:.1f},{y:.1f}"
        for x, y
        in line_points
    )

    baseline = (
        height
        -
        pad
    )

    area_points = (
        f"{line_points[0][0]:.1f},{baseline:.1f} "
        +
        points
        +
        f" {line_points[-1][0]:.1f},{baseline:.1f}"
    )

    last_x, last_y = (
        line_points[-1]
    )

    spark_key = (
        abs(
            hash(
                (
                    tuple(
                        round(
                            value,
                            6,
                        )
                        for value
                        in clean_values
                    ),
                    color,
                )
            )
        )
        %
        1_000_000_000
    )

    gradient_id = (
        f"spark_fill_{spark_key}"
    )

    shadow_id = (
        f"spark_shadow_{spark_key}"
    )

    return (
        f'<svg viewBox="0 0 {width} {height}" '
        f'width="100%" height="{height}" '
        f'preserveAspectRatio="none">'
        f'<defs>'
        f'<linearGradient id="{gradient_id}" '
        f'x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0%" '
        f'stop-color="{color}" '
        f'stop-opacity="0.30" />'
        f'<stop offset="58%" '
        f'stop-color="{color}" '
        f'stop-opacity="0.11" />'
        f'<stop offset="100%" '
        f'stop-color="{color}" '
        f'stop-opacity="0.015" />'
        f'</linearGradient>'
        f'<filter id="{shadow_id}" '
        f'x="-20%" y="-70%" '
        f'width="140%" height="240%">'
        f'<feDropShadow '
        f'dx="0" dy="1.0" '
        f'stdDeviation="1.15" '
        f'flood-color="{color}" '
        f'flood-opacity="0.30" />'
        f'</filter>'
        f'</defs>'
        f'<polygon class="spark-area" '
        f'points="{area_points}" '
        f'fill="url(#{gradient_id})" />'
        f'<polyline class="spark-path" '
        f'fill="none" '
        f'stroke="{color}" '
        f'stroke-width="2.45" '
        f'stroke-linecap="round" '
        f'stroke-linejoin="round" '
        f'filter="url(#{shadow_id})" '
        f'points="{points}" />'
        f'<circle class="spark-dot" '
        f'cx="{last_x:.1f}" '
        f'cy="{last_y:.1f}" '
        f'r="2.35" '
        f'fill="{color}" '
        f'stroke="#FFFFFF" '
        f'stroke-width="0.7" />'
        f'</svg>'
    )


def kpi_card(
    label,
    value,
    series,
    color,
    note,
):
    html = (
        f'<div class="kpi-card" '
        f'style="--accent:{color};">'
        f'<div class="kpi-content">'
        f'<div class="kpi-label">{escape(label)}</div>'
        f'<div class="kpi-value">{escape(value)}</div>'
        f'<div class="kpi-note">{escape(note)}</div>'
        f'</div>'
        f'<div class="kpi-spark">'
        f'{sparkline_svg(series, color)}'
        f'</div>'
        f'</div>'
    )

    st.markdown(
        html,
        unsafe_allow_html=True,
    )


def alert_card(row):
    direction = str(
        row["direction"]
    )

    badge_color = {
        "IN":
            COLORS["navy_2"],
        "OUT":
            COLORS["orange"],
        "INTERNAL":
            COLORS["slate"],
    }.get(
        direction,
        COLORS["navy_2"],
    )

    counterparty = (
        row[
            "counterparty_display"
        ]
        if pd.notna(
            row[
                "counterparty_display"
            ]
        )
        else "Internal ENS transfer"
    )

    html = (
        '<div class="alert-card">'
        '<div class="alert-top">'
        f'<div class="alert-value">{escape(format_usd(row["value_usd"]))}</div>'
        f'<div class="alert-badge" style="background:{badge_color};">'
        f'{escape(direction)}'
        '</div>'
        '</div>'
        f'<div class="alert-title">{escape(str(row["asset_symbol"]))}'
        f' · {escape(str(row["wallet_context"]))}</div>'
        '<div class="alert-meta">'
        f'{escape(row["timestamp"].strftime("%Y-%m-%d %H:%M UTC"))}'
        '<br>'
        f'{escape(counterparty)}'
        '</div>'
        '</div>'
    )

    st.markdown(
        html,
        unsafe_allow_html=True,
    )


def style_figure(
    figure,
    height=360,
):
    figure.update_layout(
        template="plotly_white",
        paper_bgcolor="#FFFFFF",
        plot_bgcolor="#FFFFFF",

        font={
            "color":
                COLORS["ink"],
            "size":
                12,
        },

        title={
            "font": {
                "size":
                    16,
                "color":
                    COLORS["ink"],
            }
        },

        legend_title_text="",

        margin={
            "l":
                28,
            "r":
                18,
            "t":
                54,
            "b":
                30,
        },

        height=height,

        hoverlabel={
            "bgcolor":
                "#FFFFFF",
            "font_color":
                COLORS["ink"],
        },
    )

    figure.update_xaxes(
        gridcolor=(
            COLORS["grid"]
        ),
        zerolinecolor=(
            "#CBD5E1"
        ),
        linecolor=(
            "#D8DFE7"
        ),
    )

    figure.update_yaxes(
        gridcolor=(
            COLORS["grid"]
        ),
        zerolinecolor=(
            "#CBD5E1"
        ),
        linecolor=(
            "#D8DFE7"
        ),
    )

    return figure


def date_filter(
    dataframe,
    column,
    start_date,
    end_date,
):
    out = dataframe.copy()

    out[column] = pd.to_datetime(
        out[column],
        errors="coerce",
        utc=True,
    ).dt.date

    return out[
        (
            out[column]
            >= start_date
        )
        &
        (
            out[column]
            <= end_date
        )
    ].copy()


# =============================================================================
# PREPARE SOURCES
# =============================================================================

data = load_data()

gold_wallets = data[
    "wallets"
].copy()

org_erc20 = numeric_columns(
    data["org_erc20"],
    [
        "external_inflow_usd",
        "external_outflow_usd",
        "net_external_flow_usd",
        "internal_transfer_usd",
        "total_event_count",
        "valued_event_count",
    ],
)

org_native = numeric_columns(
    data["org_native"],
    [
        "inflow_usd",
        "outflow_usd",
        "internal_usd",
        "net_flow_usd",
        "event_count",
        "valued_event_count",
        "unvalued_event_count",
    ],
)

wallet_erc20 = numeric_columns(
    data["wallet_erc20"],
    [
        "inflow_usd",
        "outflow_usd",
        "net_flow_usd",
        "total_event_count",
        "valued_event_count",
    ],
)

wallet_native = numeric_columns(
    data["wallet_native"],
    [
        "inflow_usd",
        "outflow_usd",
        "net_flow_usd",
        "event_count",
        "valued_event_count",
        "unvalued_event_count",
    ],
)

erc20_values = numeric_columns(
    data["erc20_values"],
    [
        "amount_decimal",
        "daily_price_usd",
        "value_usd",
    ],
)

native_values = numeric_columns(
    data["native_values"],
    [
        "value_eth_decimal",
        "daily_price_usd",
        "value_usd",
    ],
)

large_erc20 = numeric_columns(
    data["large_erc20"],
    [
        "value_usd",
        "threshold_usd",
    ],
)

large_native = numeric_columns(
    data["large_native"],
    [
        "value_usd",
        "threshold_usd",
    ],
)


# =============================================================================
# METADATA / COUNTERPARTY LABELS
# =============================================================================

wallet_meta = (
    gold_wallets[
        gold_wallets[
            "monitoring_enabled"
        ]
        == True
    ][
        [
            "organization_id",
            "wallet_id",
            "wallet_name",
            "wallet_role",
            "address",
        ]
    ]
    .rename(
        columns={
            "address":
                "treasury_address",
        }
    )
    .drop_duplicates(
        subset=[
            "organization_id",
            "wallet_id",
        ]
    )
    .sort_values(
        "wallet_name"
    )
    .reset_index(
        drop=True
    )
)

if wallet_meta.empty:
    raise RuntimeError(
        "gold.wallets contains no "
        "monitoring-enabled wallets"
    )

wallet_id_to_name = dict(
    zip(
        wallet_meta["wallet_id"],
        wallet_meta["wallet_name"],
    )
)

address_to_wallet_id = dict(
    zip(
        wallet_meta[
            "treasury_address"
        ].str.lower(),
        wallet_meta["wallet_id"],
    )
)

address_to_wallet_name = dict(
    zip(
        wallet_meta[
            "treasury_address"
        ].str.lower(),
        wallet_meta["wallet_name"],
    )
)

token_label_source = (
    erc20_values[
        [
            "token_contract",
            "token_symbol",
        ]
    ]
    .dropna(
        subset=[
            "token_contract"
        ]
    )
    .drop_duplicates()
    .copy()
)

token_label_source[
    "token_contract"
] = (
    token_label_source[
        "token_contract"
    ].str.lower()
)

contract_label_map = {}

for contract, group in (
    token_label_source.groupby(
        "token_contract"
    )
):
    symbols = (
        group["token_symbol"]
        .dropna()
        .astype(str)
        .unique()
        .tolist()
    )

    if len(symbols) == 1:
        contract_label_map[
            contract
        ] = (
            f"{symbols[0]} contract"
        )


def counterparty_label(
    address,
):
    if (
        address is None
        or pd.isna(address)
    ):
        return "—"

    key = str(address).lower()

    if key in address_to_wallet_name:
        return (
            address_to_wallet_name[
                key
            ]
        )

    if key in contract_label_map:
        return (
            contract_label_map[
                key
            ]
        )

    return "External address"


def counterparty_display(
    address,
):
    if (
        address is None
        or pd.isna(address)
    ):
        return "—"

    return (
        f"{counterparty_label(address)}"
        f" · "
        f"{short_address(address)}"
    )


# =============================================================================
# THRESHOLD
# =============================================================================

thresholds = sorted(
    {
        float(value)
        for frame in [
            large_erc20,
            large_native,
        ]
        for value in (
            frame[
                "threshold_usd"
            ]
            .dropna()
            .tolist()
        )
    }
)

if len(thresholds) != 1:
    raise RuntimeError(
        "Expected exactly one "
        "large-movement threshold, "
        f"found: {thresholds}"
    )

LARGE_THRESHOLD = thresholds[0]


# =============================================================================
# ORGANIZATION EVENT VIEW
# =============================================================================

def organization_direction(
    from_wallet_id,
    to_wallet_id,
):
    if (
        pd.notna(
            from_wallet_id
        )
        and
        pd.notna(
            to_wallet_id
        )
    ):
        return "INTERNAL"

    if pd.notna(
        from_wallet_id
    ):
        return "OUT"

    if pd.notna(
        to_wallet_id
    ):
        return "IN"

    return "OTHER"


def wallet_context(
    direction,
    from_wallet_id,
    to_wallet_id,
):
    from_name = (
        wallet_id_to_name.get(
            from_wallet_id
        )
    )

    to_name = (
        wallet_id_to_name.get(
            to_wallet_id
        )
    )

    if direction == "IN":
        return (
            to_name
            or "Monitored wallet"
        )

    if direction == "OUT":
        return (
            from_name
            or "Monitored wallet"
        )

    if direction == "INTERNAL":
        return (
            f"{from_name or 'Wallet'}"
            " → "
            f"{to_name or 'Wallet'}"
        )

    return "—"


def build_event_view():
    erc = erc20_values.copy()

    erc[
        "block_timestamp"
    ] = pd.to_datetime(
        erc[
            "block_timestamp"
        ],
        utc=True,
    )

    erc[
        "from_wallet_id"
    ] = (
        erc[
            "from_address"
        ]
        .str.lower()
        .map(
            address_to_wallet_id
        )
    )

    erc[
        "to_wallet_id"
    ] = (
        erc[
            "to_address"
        ]
        .str.lower()
        .map(
            address_to_wallet_id
        )
    )

    erc = (
        erc
        .sort_values(
            [
                "block_timestamp",
                "blockchain_event_id",
                "activity_id",
            ]
        )
        .drop_duplicates(
            subset=[
                "blockchain_event_id"
            ],
            keep="first",
        )
        .copy()
    )

    erc[
        "direction"
    ] = (
        erc.apply(
            lambda row:
                organization_direction(
                    row[
                        "from_wallet_id"
                    ],
                    row[
                        "to_wallet_id"
                    ],
                ),
            axis=1,
        )
    )

    erc[
        "counterparty_address"
    ] = (
        erc.apply(
            lambda row:
                (
                    row[
                        "from_address"
                    ]
                    if (
                        row[
                            "direction"
                        ]
                        == "IN"
                    )
                    else (
                        row[
                            "to_address"
                        ]
                        if (
                            row[
                                "direction"
                            ]
                            == "OUT"
                        )
                        else None
                    )
                ),
            axis=1,
        )
    )

    erc[
        "wallet_context"
    ] = (
        erc.apply(
            lambda row:
                wallet_context(
                    row[
                        "direction"
                    ],
                    row[
                        "from_wallet_id"
                    ],
                    row[
                        "to_wallet_id"
                    ],
                ),
            axis=1,
        )
    )

    erc[
        "asset"
    ] = (
        erc[
            "token_symbol"
        ].fillna(
            "UNKNOWN"
        )
        + " · "
        + erc[
            "token_contract"
        ].str.slice(
            0,
            8,
        )
        + "…"
    )

    erc_events = (
        pd.DataFrame(
            {
                "event_id":
                    erc[
                        "blockchain_event_id"
                    ],

                "timestamp":
                    erc[
                        "block_timestamp"
                    ],

                "asset_type":
                    "ERC-20",

                "asset":
                    erc[
                        "asset"
                    ],

                "asset_symbol":
                    erc[
                        "token_symbol"
                    ].fillna(
                        "UNKNOWN"
                    ),

                "direction":
                    erc[
                        "direction"
                    ],

                "from_wallet_id":
                    erc[
                        "from_wallet_id"
                    ],

                "to_wallet_id":
                    erc[
                        "to_wallet_id"
                    ],

                "wallet_context":
                    erc[
                        "wallet_context"
                    ],

                "amount":
                    erc[
                        "amount_decimal"
                    ],

                "value_usd":
                    erc[
                        "value_usd"
                    ],

                "valuation_status":
                    erc[
                        "valuation_status"
                    ],

                "counterparty_address":
                    erc[
                        "counterparty_address"
                    ],

                "transaction_hash":
                    erc[
                        "transaction_hash"
                    ],
            }
        )
    )

    nat = native_values.copy()

    nat[
        "block_timestamp"
    ] = pd.to_datetime(
        nat[
            "block_timestamp"
        ],
        utc=True,
    )

    nat[
        "wallet_context"
    ] = (
        nat.apply(
            lambda row:
                wallet_context(
                    row[
                        "organization_direction"
                    ],
                    row[
                        "from_wallet_id"
                    ],
                    row[
                        "to_wallet_id"
                    ],
                ),
            axis=1,
        )
    )

    nat_events = (
        pd.DataFrame(
            {
                "event_id":
                    nat[
                        "native_event_id"
                    ],

                "timestamp":
                    nat[
                        "block_timestamp"
                    ],

                "asset_type":
                    "Native ETH",

                "asset":
                    "ETH (native)",

                "asset_symbol":
                    "ETH",

                "direction":
                    nat[
                        "organization_direction"
                    ],

                "from_wallet_id":
                    nat[
                        "from_wallet_id"
                    ],

                "to_wallet_id":
                    nat[
                        "to_wallet_id"
                    ],

                "wallet_context":
                    nat[
                        "wallet_context"
                    ],

                "amount":
                    nat[
                        "value_eth_decimal"
                    ],

                "value_usd":
                    nat[
                        "value_usd"
                    ],

                "valuation_status":
                    nat[
                        "valuation_status"
                    ],

                "counterparty_address":
                    nat[
                        "counterparty_address"
                    ],

                "transaction_hash":
                    nat[
                        "transaction_hash"
                    ],
            }
        )
    )

    events = pd.concat(
        [
            erc_events,
            nat_events,
        ],
        ignore_index=True,
    )

    events[
        "event_date"
    ] = (
        events[
            "timestamp"
        ].dt.date
    )

    events[
        "month"
    ] = (
        events[
            "timestamp"
        ]
        .dt.to_period(
            "M"
        )
        .astype(
            str
        )
    )

    events[
        "counterparty_label"
    ] = (
        events[
            "counterparty_address"
        ].apply(
            counterparty_label
        )
    )

    events[
        "counterparty_display"
    ] = (
        events[
            "counterparty_address"
        ].apply(
            counterparty_display
        )
    )

    events[
        "is_large"
    ] = (
        (
            events[
                "valuation_status"
            ]
            == "VALUED"
        )
        &
        (
            events[
                "value_usd"
            ]
            >= LARGE_THRESHOLD
        )
    )

    events[
        "etherscan"
    ] = (
        "https://etherscan.io/tx/"
        +
        events[
            "transaction_hash"
        ].astype(
            str
        )
    )

    return events


events = build_event_view()


# =============================================================================
# DAILY / MONTHLY HEALTH
# =============================================================================

def build_daily_health():
    erc = org_erc20.copy()

    erc[
        "activity_date"
    ] = (
        pd.to_datetime(
            erc[
                "flow_date"
            ]
        ).dt.date
    )

    erc_daily = (
        erc
        .groupby(
            "activity_date",
            as_index=False,
        )
        .agg(
            inflow_usd=(
                "external_inflow_usd",
                "sum",
            ),
            outflow_usd=(
                "external_outflow_usd",
                "sum",
            ),
            total_events=(
                "total_event_count",
                "sum",
            ),
            valued_events=(
                "valued_event_count",
                "sum",
            ),
        )
    )

    nat = org_native.copy()

    nat[
        "activity_date"
    ] = (
        pd.to_datetime(
            nat[
                "activity_date"
            ]
        ).dt.date
    )

    nat_daily = (
        nat
        .groupby(
            "activity_date",
            as_index=False,
        )
        .agg(
            inflow_usd=(
                "inflow_usd",
                "sum",
            ),
            outflow_usd=(
                "outflow_usd",
                "sum",
            ),
            total_events=(
                "event_count",
                "sum",
            ),
            valued_events=(
                "valued_event_count",
                "sum",
            ),
        )
    )

    out = (
        pd.concat(
            [
                erc_daily,
                nat_daily,
            ],
            ignore_index=True,
        )
        .groupby(
            "activity_date",
            as_index=False,
        )
        .agg(
            inflow_usd=(
                "inflow_usd",
                "sum",
            ),
            outflow_usd=(
                "outflow_usd",
                "sum",
            ),
            total_events=(
                "total_events",
                "sum",
            ),
            valued_events=(
                "valued_events",
                "sum",
            ),
        )
        .sort_values(
            "activity_date"
        )
    )

    out[
        "net_flow_usd"
    ] = (
        out[
            "inflow_usd"
        ]
        -
        out[
            "outflow_usd"
        ]
    )

    return out


daily_health = (
    build_daily_health()
)


def build_monthly_health(
    filtered_daily,
    filtered_events,
):
    daily = filtered_daily.copy()

    daily[
        "month"
    ] = (
        pd.to_datetime(
            daily[
                "activity_date"
            ]
        )
        .dt.to_period(
            "M"
        )
        .astype(
            str
        )
    )

    monthly = (
        daily
        .groupby(
            "month",
            as_index=False,
        )
        .agg(
            inflow_usd=(
                "inflow_usd",
                "sum",
            ),
            outflow_usd=(
                "outflow_usd",
                "sum",
            ),
            net_flow_usd=(
                "net_flow_usd",
                "sum",
            ),
            total_events=(
                "total_events",
                "sum",
            ),
            valued_events=(
                "valued_events",
                "sum",
            ),
        )
    )

    large_monthly = (
        filtered_events[
            filtered_events[
                "is_large"
            ]
        ]
        .groupby(
            "month",
            as_index=False,
        )
        .agg(
            large_count=(
                "event_id",
                "count",
            )
        )
    )

    monthly = (
        monthly.merge(
            large_monthly,
            on="month",
            how="left",
        )
    )

    monthly[
        "large_count"
    ] = (
        monthly[
            "large_count"
        ].fillna(
            0
        )
    )

    monthly[
        "coverage_percent"
    ] = (
        monthly[
            "valued_events"
        ]
        /
        monthly[
            "total_events"
        ]
        *
        100
    )

    return (
        monthly.sort_values(
            "month"
        )
    )


# =============================================================================
# SHARED SUMMARIES
# =============================================================================

def wallet_activity_summary(
    start_date,
    end_date,
):
    erc = date_filter(
        wallet_erc20,
        "flow_date",
        start_date,
        end_date,
    )

    nat = date_filter(
        wallet_native,
        "activity_date",
        start_date,
        end_date,
    )

    nat = nat.merge(
        wallet_meta[
            [
                "wallet_id",
                "wallet_name",
            ]
        ],
        on="wallet_id",
        how="left",
    )

    a = (
        erc
        .groupby(
            [
                "wallet_id",
                "wallet_name",
            ],
            as_index=False,
        )
        .agg(
            inflow_usd=(
                "inflow_usd",
                "sum",
            ),
            outflow_usd=(
                "outflow_usd",
                "sum",
            ),
        )
    )

    b = (
        nat
        .groupby(
            [
                "wallet_id",
                "wallet_name",
            ],
            as_index=False,
        )
        .agg(
            inflow_usd=(
                "inflow_usd",
                "sum",
            ),
            outflow_usd=(
                "outflow_usd",
                "sum",
            ),
        )
    )

    out = (
        pd.concat(
            [
                a,
                b,
            ],
            ignore_index=True,
        )
        .groupby(
            [
                "wallet_id",
                "wallet_name",
            ],
            as_index=False,
        )
        .agg(
            inflow_usd=(
                "inflow_usd",
                "sum",
            ),
            outflow_usd=(
                "outflow_usd",
                "sum",
            ),
        )
    )

    out[
        "total_flow_usd"
    ] = (
        out[
            "inflow_usd"
        ]
        +
        out[
            "outflow_usd"
        ]
    )

    out[
        "net_flow_usd"
    ] = (
        out[
            "inflow_usd"
        ]
        -
        out[
            "outflow_usd"
        ]
    )

    return out


def top_asset_summary(
    frame,
    limit=8,
):
    valued = (
        frame[
            frame[
                "valuation_status"
            ]
            == "VALUED"
        ]
    )

    rows = []

    for asset, group in (
        valued.groupby(
            "asset"
        )
    ):
        rows.append(
            {
                "asset":
                    asset,

                "inflow_usd":
                    safe_sum(
                        group.loc[
                            group[
                                "direction"
                            ]
                            == "IN",
                            "value_usd",
                        ]
                    ),

                "outflow_usd":
                    safe_sum(
                        group.loc[
                            group[
                                "direction"
                            ]
                            == "OUT",
                            "value_usd",
                        ]
                    ),

                "internal_usd":
                    safe_sum(
                        group.loc[
                            group[
                                "direction"
                            ]
                            == "INTERNAL",
                            "value_usd",
                        ]
                    ),
            }
        )

    result = (
        pd.DataFrame(
            rows
        )
    )

    if result.empty:
        return result

    result[
        "total_flow_usd"
    ] = (
        result[
            [
                "inflow_usd",
                "outflow_usd",
                "internal_usd",
            ]
        ].sum(
            axis=1
        )
    )

    return (
        result
        .sort_values(
            "total_flow_usd",
            ascending=False,
        )
        .head(
            limit
        )
    )


def counterparty_summary(
    frame,
    limit=10,
):
    external = (
        frame[
            frame[
                "direction"
            ].isin(
                [
                    "IN",
                    "OUT",
                ]
            )
            &
            frame[
                "counterparty_address"
            ].notna()
            &
            (
                frame[
                    "valuation_status"
                ]
                == "VALUED"
            )
        ]
    )

    return (
        external
        .groupby(
            [
                "counterparty_address",
                "counterparty_label",
                "counterparty_display",
            ],
            as_index=False,
        )
        .agg(
            value_usd=(
                "value_usd",
                "sum",
            ),
            events=(
                "event_id",
                "count",
            ),
        )
        .sort_values(
            "value_usd",
            ascending=False,
        )
        .head(
            limit
        )
    )


# =============================================================================
# HEADER / SIDEBAR
# =============================================================================

header_html = (
    '<div class="dashboard-header">'
    '<div>'
    '<div class="dashboard-eyebrow">ENS DAO · ETHEREUM MAINNET</div>'
    '<div class="dashboard-title">Treasury Monitor</div>'
    '<div class="dashboard-subtitle">'
    'Ethereum Treasury Monitoring Data Platform'
    '</div>'
    '</div>'
    '<div class="status-wrap">'
    '<div class="status-pill">'
    '<span class="status-dot"></span>'
    f'{len(wallet_meta)} monitored wallets'
    '</div>'
    '<div class="status-pill status-pill-warm">'
    f'Large movement ≥ {format_usd(LARGE_THRESHOLD)}'
    '</div>'
    '</div>'
    '</div>'
)

st.markdown(
    header_html,
    unsafe_allow_html=True,
)

st.sidebar.title(
    "Treasury Monitor"
)

st.sidebar.caption(
    "ENS DAO · Ethereum"
)

page = st.sidebar.radio(
    "Navigation",
    [
        "Overview",
        "Wallets",
        "Assets",
        "Large Movements",
    ],
)

st.sidebar.divider()

minimum_date = min(
    daily_health[
        "activity_date"
    ]
)

maximum_date = max(
    daily_health[
        "activity_date"
    ]
)

selected_dates = (
    st.sidebar.date_input(
        "Date range",
        value=(
            minimum_date,
            maximum_date,
        ),
        min_value=(
            minimum_date
        ),
        max_value=(
            maximum_date
        ),
    )
)

if isinstance(
    selected_dates,
    (
        tuple,
        list,
    ),
):
    if len(
        selected_dates
    ) == 2:
        start_date = (
            selected_dates[0]
        )
        end_date = (
            selected_dates[1]
        )
    else:
        start_date = (
            selected_dates[0]
        )
        end_date = (
            selected_dates[0]
        )
else:
    start_date = (
        selected_dates
    )
    end_date = (
        selected_dates
    )

if st.sidebar.button(
    "Refresh data",
    use_container_width=True,
):
    st.cache_data.clear()
    st.rerun()

st.sidebar.caption(
    "USD values are historical "
    "event valuations, not portfolio "
    "balances or accounting P&L."
)


# =============================================================================
# GLOBAL FILTERED DATA
# =============================================================================

filtered_daily = (
    daily_health[
        (
            daily_health[
                "activity_date"
            ]
            >= start_date
        )
        &
        (
            daily_health[
                "activity_date"
            ]
            <= end_date
        )
    ].copy()
)

filtered_events = (
    events[
        (
            events[
                "event_date"
            ]
            >= start_date
        )
        &
        (
            events[
                "event_date"
            ]
            <= end_date
        )
    ].copy()
)

monthly = (
    build_monthly_health(
        filtered_daily,
        filtered_events,
    )
)

internal_monthly = (
    filtered_events[
        (
            filtered_events[
                "valuation_status"
            ]
            == "VALUED"
        )
        &
        (
            filtered_events[
                "direction"
            ]
            == "INTERNAL"
        )
    ]
    .groupby(
        "month",
        as_index=False,
    )
    .agg(
        internal_usd=(
            "value_usd",
            "sum",
        )
    )
)

monthly = (
    monthly.merge(
        internal_monthly,
        on="month",
        how="left",
    )
)

monthly[
    "internal_usd"
] = (
    monthly[
        "internal_usd"
    ].fillna(
        0.0
    )
)

valued_events = (
    filtered_events[
        filtered_events[
            "valuation_status"
        ]
        == "VALUED"
    ]
)

large_events = (
    filtered_events[
        filtered_events[
            "is_large"
        ]
    ].copy()
)

total_inflow = (
    safe_sum(
        filtered_daily[
            "inflow_usd"
        ]
    )
)

total_outflow = (
    safe_sum(
        filtered_daily[
            "outflow_usd"
        ]
    )
)

net_external = (
    total_inflow
    -
    total_outflow
)

coverage_text = (
    format_percentage(
        safe_sum(
            filtered_daily[
                "valued_events"
            ]
        ),
        safe_sum(
            filtered_daily[
                "total_events"
            ]
        ),
    )
)

total_internal = (
    safe_sum(
        valued_events.loc[
            valued_events[
                "direction"
            ]
            == "INTERNAL",
            "value_usd",
        ]
    )
)

net_explanation = (
    "More entered than left"
    if net_external >= 0
    else "More left than entered"
)


# =============================================================================
# OVERVIEW
# =============================================================================

if page == "Overview":
    section_header(
        "Treasury health",
        (
            "Headline historical flow metrics for the monitored ENS treasury scope."
        ),
    )

    st.markdown(
        (
            '<div class="read-guide">'
            '<span class="read-chip">'
            f'<span class="read-dot" style="background:{COLORS["navy_2"]};"></span>'
            '<b>IN</b> external value entering ENS'
            '</span>'
            '<span class="read-chip">'
            f'<span class="read-dot" style="background:{COLORS["gold_dark"]};"></span>'
            '<b>OUT</b> external value leaving ENS'
            '</span>'
            '<span class="read-chip">'
            f'<span class="read-dot" style="background:{COLORS["slate"]};"></span>'
            '<b>INTERNAL</b> between monitored ENS wallets'
            '</span>'
            f'<span class="read-chip"><b>USD coverage</b> = {coverage_text}</span>'
            '</div>'
        ),
        unsafe_allow_html=True,
    )

    kpi_columns = (
        st.columns(5)
    )

    with kpi_columns[0]:
        kpi_card(
            "External inflow",
            format_usd(
                total_inflow
            ),
            monthly[
                "inflow_usd"
            ],
            COLORS["navy_2"],
            "External value entering ENS",
        )

    with kpi_columns[1]:
        kpi_card(
            "External outflow",
            format_usd(
                total_outflow
            ),
            monthly[
                "outflow_usd"
            ],
            COLORS["gold_dark"],
            "External value leaving ENS",
        )

    with kpi_columns[2]:
        kpi_card(
            "Net external flow",
            format_usd(
                net_external
            ),
            monthly[
                "net_flow_usd"
            ],
            COLORS["navy"],
            net_explanation,
        )

    with kpi_columns[3]:
        kpi_card(
            "Internal transfers",
            format_usd(
                total_internal
            ),
            monthly[
                "internal_usd"
            ],
            COLORS["slate"],
            "Movement within monitored ENS wallets",
        )

    with kpi_columns[4]:
        kpi_card(
            "Large movements",
            f"{len(large_events):,}",
            monthly[
                "large_count"
            ],
            COLORS["gold"],
            (
                f"Flagged at ≥ "
                f"{format_usd(LARGE_THRESHOLD)}"
            ),
        )

    st.write("")

    section_header(
        "Business breakdown",
        (
            "Historical movement by time, asset class, monitored wallet and asset."
        ),
    )

    left, right = (
        st.columns(
            [
                1.55,
                1,
            ]
        )
    )

    with left:
        figure = go.Figure()

        figure.add_trace(
            go.Scatter(
                x=monthly[
                    "month"
                ],
                y=monthly[
                    "inflow_usd"
                ],
                name="Inflow",
                mode="lines",
                line={
                    "color":
                        COLORS[
                            "navy_2"
                        ],
                    "width":
                        3,
                },
                hovertemplate=(
                    "%{x}<br>"
                    "Inflow $%{y:,.0f}"
                    "<extra></extra>"
                ),
            )
        )

        figure.add_trace(
            go.Scatter(
                x=monthly[
                    "month"
                ],
                y=monthly[
                    "outflow_usd"
                ],
                name="Outflow",
                mode="lines",
                line={
                    "color":
                        COLORS[
                            "gold_dark"
                        ],
                    "width":
                        3,
                },
                hovertemplate=(
                    "%{x}<br>"
                    "Outflow $%{y:,.0f}"
                    "<extra></extra>"
                ),
            )
        )

        figure.update_layout(
            title=(
                "Monthly External Flow"
            ),
            hovermode=(
                "x unified"
            ),
        )

        figure.update_yaxes(
            tickprefix="$"
        )

        st.plotly_chart(
            style_figure(
                figure,
                height=365,
            ),
            use_container_width=True,
            config={
                "displaylogo":
                    False,
            },
        )

        st.caption(
            "External IN and OUT value by month. "
            "Internal ENS-to-ENS transfers are excluded."
        )

    with right:
        class_rows = []

        for asset_type in [
            "ERC-20",
            "Native ETH",
        ]:
            subset = (
                valued_events[
                    valued_events[
                        "asset_type"
                    ]
                    == asset_type
                ]
            )

            class_rows.extend(
                [
                    {
                        "Asset class":
                            asset_type,
                        "Direction":
                            "IN",
                        "USD value":
                            safe_sum(
                                subset.loc[
                                    subset[
                                        "direction"
                                    ]
                                    == "IN",
                                    "value_usd",
                                ]
                            ),
                    },
                    {
                        "Asset class":
                            asset_type,
                        "Direction":
                            "OUT",
                        "USD value":
                            safe_sum(
                                subset.loc[
                                    subset[
                                        "direction"
                                    ]
                                    == "OUT",
                                    "value_usd",
                                ]
                            ),
                    },
                ]
            )

        class_frame = (
            pd.DataFrame(
                class_rows
            )
        )

        figure = px.bar(
            class_frame,
            x="Asset class",
            y="USD value",
            color="Direction",
            barmode="group",
            title=(
                "Flow by Asset Class"
            ),
            color_discrete_map=(
                DIRECTION_COLORS
            ),
        )

        figure.update_yaxes(
            tickprefix="$",
            rangemode="tozero",
        )

        st.plotly_chart(
            style_figure(
                figure,
                height=365,
            ),
            use_container_width=True,
            config={
                "displaylogo":
                    False,
            },
        )

        st.caption(
            "Historical external movement split between ERC-20 tokens and native ETH."
        )

    wallet_summary = (
        wallet_activity_summary(
            start_date,
            end_date,
        )
    )

    asset_summary = (
        top_asset_summary(
            filtered_events,
            limit=7,
        )
    )

    direction_summary = (
        large_events
        .groupby(
            "direction",
            as_index=False,
        )
        .agg(
            Events=(
                "event_id",
                "count",
            )
        )
    )

    c1, c2, c3 = (
        st.columns(
            [
                1,
                1.15,
                0.85,
            ]
        )
    )

    with c1:
        wallet_chart = (
            wallet_summary
            .sort_values(
                "total_flow_usd"
            )
        )

        figure = px.bar(
            wallet_chart,
            x="total_flow_usd",
            y="wallet_name",
            orientation="h",
            title=(
                "Wallet Activity Contribution"
            ),
            labels={
                "total_flow_usd":
                    "Inflow + outflow USD",
                "wallet_name":
                    "Wallet",
            },
        )

        figure.update_traces(
            marker_color=(
                COLORS[
                    "navy"
                ]
            )
        )

        figure.update_xaxes(
            tickprefix="$",
            rangemode="tozero",
        )

        st.plotly_chart(
            style_figure(
                figure,
                height=340,
            ),
            use_container_width=True,
            config={
                "displaylogo":
                    False,
            },
        )

    with c2:
        if not asset_summary.empty:
            asset_long = (
                asset_summary.melt(
                    id_vars=[
                        "asset",
                        "total_flow_usd",
                    ],
                    value_vars=[
                        "inflow_usd",
                        "outflow_usd",
                    ],
                    var_name=(
                        "direction"
                    ),
                    value_name=(
                        "value_usd"
                    ),
                )
            )

            asset_long[
                "direction"
            ] = (
                asset_long[
                    "direction"
                ].map(
                    {
                        "inflow_usd":
                            "IN",
                        "outflow_usd":
                            "OUT",
                    }
                )
            )

            order = (
                asset_summary
                .sort_values(
                    "total_flow_usd"
                )[
                    "asset"
                ]
                .tolist()
            )

            asset_long[
                "asset"
            ] = (
                pd.Categorical(
                    asset_long[
                        "asset"
                    ],
                    categories=(
                        order
                    ),
                    ordered=True,
                )
            )

            figure = px.bar(
                asset_long.sort_values(
                    "asset"
                ),
                x="value_usd",
                y="asset",
                color="direction",
                orientation="h",
                barmode="stack",
                title=(
                    "Top Assets by Movement Value"
                ),
                labels={
                    "value_usd":
                        "USD value",
                    "asset":
                        "Asset",
                    "direction":
                        "Direction",
                },
                color_discrete_map=(
                    DIRECTION_COLORS
                ),
            )

            figure.update_xaxes(
                tickprefix="$",
                rangemode="tozero",
            )

            st.plotly_chart(
                style_figure(
                    figure,
                    height=340,
                ),
                use_container_width=True,
                config={
                    "displaylogo":
                        False,
                },
            )

    with c3:
        if not direction_summary.empty:
            figure = px.pie(
                direction_summary,
                names="direction",
                values="Events",
                hole=0.60,
                title=(
                    "Large Movements by Direction"
                ),
                color="direction",
                color_discrete_map=(
                    DIRECTION_COLORS
                ),
            )

            figure.update_traces(
                textposition="inside",
                textinfo="percent",
                hovertemplate=(
                    "%{label}<br>"
                    "Events %{value}<br>"
                    "%{percent}"
                    "<extra></extra>"
                ),
            )

            figure.update_layout(
                showlegend=True,
                legend={
                    "orientation": "h",
                    "y": -0.06,
                    "x": 0.5,
                    "xanchor": "center",
                },
            )

            st.plotly_chart(
                style_figure(
                    figure,
                    height=340,
                ),
                use_container_width=True,
                config={
                    "displaylogo":
                        False,
                },
            )

    st.write("")

    section_header(
        "Recent large-movement alerts",
        (
            "Three latest threshold exceptions. "
            "Use Large Movements for the full event list and transactions."
        ),
    )

    alerts = (
        large_events
        .sort_values(
            "timestamp",
            ascending=False,
        )
        .head(3)
        .copy()
    )

    if alerts.empty:
        st.success(
            "No large movements in "
            "the selected date range."
        )

    else:
        alert_columns = (
            st.columns(3)
        )

        for column, (_, alert) in zip(
            alert_columns,
            alerts.iterrows(),
        ):
            with column:
                alert_card(
                    alert
                )

        st.caption(
            "Full history, counterparties, amounts and Etherscan links "
            "are available in the Large Movements page."
        )


# =============================================================================
# WALLETS
# =============================================================================

elif page == "Wallets":
    section_header(
        "Wallet analysis",
        (
            "Historical flows, assets and large movements for one monitored ENS wallet."
        ),
    )

    wallet_name_to_id = dict(
        zip(
            wallet_meta[
                "wallet_name"
            ],
            wallet_meta[
                "wallet_id"
            ],
        )
    )

    selected_wallet = (
        st.selectbox(
            "Wallet",
            options=sorted(
                wallet_name_to_id
            ),
        )
    )

    wallet_id = (
        wallet_name_to_id[
            selected_wallet
        ]
    )

    wallet_events = (
        filtered_events[
            (
                filtered_events[
                    "from_wallet_id"
                ]
                == wallet_id
            )
            |
            (
                filtered_events[
                    "to_wallet_id"
                ]
                == wallet_id
            )
        ].copy()
    )

    wallet_valued = (
        wallet_events[
            wallet_events[
                "valuation_status"
            ]
            == "VALUED"
        ]
    )

    wallet_in = (
        safe_sum(
            wallet_valued.loc[
                wallet_valued[
                    "direction"
                ]
                == "IN",
                "value_usd",
            ]
        )
    )

    wallet_out = (
        safe_sum(
            wallet_valued.loc[
                wallet_valued[
                    "direction"
                ]
                == "OUT",
                "value_usd",
            ]
        )
    )

    wallet_monthly = (
        wallet_valued
        .groupby(
            [
                "month",
                "direction",
            ],
            as_index=False,
        )
        .agg(
            value_usd=(
                "value_usd",
                "sum",
            )
        )
    )

    pivot = (
        wallet_monthly
        .pivot_table(
            index="month",
            columns="direction",
            values="value_usd",
            aggfunc="sum",
            fill_value=0,
        )
        .sort_index()
    )

    for column in [
        "IN",
        "OUT",
    ]:
        if column not in (
            pivot.columns
        ):
            pivot[
                column
            ] = 0.0

    pivot[
        "NET"
    ] = (
        pivot[
            "IN"
        ]
        -
        pivot[
            "OUT"
        ]
    )

    columns = st.columns(5)

    with columns[0]:
        kpi_card(
            "Inflow",
            format_usd(
                wallet_in
            ),
            pivot["IN"],
            COLORS["navy_2"],
            selected_wallet,
        )

    with columns[1]:
        kpi_card(
            "Outflow",
            format_usd(
                wallet_out
            ),
            pivot["OUT"],
            COLORS["gold_dark"],
            selected_wallet,
        )

    with columns[2]:
        kpi_card(
            "Net external flow",
            format_usd(
                wallet_in
                -
                wallet_out
            ),
            pivot["NET"],
            COLORS["navy"],
            selected_wallet,
        )

    with columns[3]:
        kpi_card(
            "Large movements",
            f"{int(wallet_events['is_large'].sum()):,}",
            (
                wallet_events[
                    wallet_events[
                        "is_large"
                    ]
                ]
                .groupby(
                    "month"
                )
                .size()
            ),
            COLORS["gold_dark"],
            (
                f"Threshold "
                f"{format_usd(LARGE_THRESHOLD)}"
            ),
        )

    with columns[4]:
        kpi_card(
            "Valuation coverage",
            format_percentage(
                len(
                    wallet_valued
                ),
                len(
                    wallet_events
                ),
            ),
            (
                wallet_events
                .assign(
                    valued=(
                        wallet_events[
                            "valuation_status"
                        ]
                        == "VALUED"
                    )
                )
                .groupby(
                    "month"
                )[
                    "valued"
                ]
                .mean()
                *
                100
            ),
            COLORS["navy_2"],
            "Wallet events valued in USD",
        )

    st.write("")

    left, right = (
        st.columns(
            [
                1.45,
                1,
            ]
        )
    )

    with left:
        if not wallet_monthly.empty:
            figure = px.line(
                wallet_monthly,
                x="month",
                y="value_usd",
                color="direction",
                title=(
                    "Monthly wallet flow"
                ),
                labels={
                    "month":
                        "Month",
                    "value_usd":
                        "USD value",
                    "direction":
                        "Direction",
                },
                color_discrete_map=(
                    DIRECTION_COLORS
                ),
            )

            figure.update_yaxes(
                tickprefix="$"
            )

            st.plotly_chart(
                style_figure(
                    figure,
                    height=370,
                ),
                use_container_width=True,
                config={
                    "displaylogo":
                        False,
                },
            )

    with right:
        wallet_assets = (
            top_asset_summary(
                wallet_events,
                limit=8,
            )
        )

        if not wallet_assets.empty:
            figure = px.bar(
                wallet_assets.sort_values(
                    "total_flow_usd"
                ),
                x="total_flow_usd",
                y="asset",
                orientation="h",
                title="Top assets",
                labels={
                    "total_flow_usd":
                        "USD value",
                    "asset":
                        "Asset",
                },
            )

            figure.update_traces(
                marker_color=(
                    COLORS[
                        "blue"
                    ]
                )
            )

            figure.update_xaxes(
                tickprefix="$",
                rangemode="tozero",
            )

            st.plotly_chart(
                style_figure(
                    figure,
                    height=370,
                ),
                use_container_width=True,
                config={
                    "displaylogo":
                        False,
                },
            )

    section_header(
        "Deep-dive highlights",
        (
            "Top underlying movements for the selected wallet. "
            "The full event-level table lives in Large Movements."
        ),
    )

    wallet_top = (
        wallet_events[
            wallet_events[
                "valuation_status"
            ]
            == "VALUED"
        ]
        .sort_values(
            "value_usd",
            ascending=False,
        )
        .head(5)
        .copy()
    )

    if not wallet_top.empty:
        wallet_top[
            "label"
        ] = (
            wallet_top[
                "asset_symbol"
            ]
            +
            " · "
            +
            wallet_top[
                "direction"
            ]
            +
            " · "
            +
            wallet_top[
                "timestamp"
            ].dt.strftime(
                "%Y-%m-%d"
            )
        )

        figure = px.bar(
            wallet_top.sort_values(
                "value_usd"
            ),
            x="value_usd",
            y="label",
            color="direction",
            orientation="h",
            title="Top 5 movements",
            labels={
                "value_usd":
                    "USD value",
                "label":
                    "Movement",
                "direction":
                    "Direction",
            },
            color_discrete_map=(
                DIRECTION_COLORS
            ),
        )

        figure.update_xaxes(
            tickprefix="$",
            rangemode="tozero",
        )

        st.plotly_chart(
            style_figure(
                figure,
                height=310,
            ),
            use_container_width=True,
            config={
                "displaylogo":
                    False,
            },
        )

    st.caption(
        "Need transaction-level detail? Open the Large Movements page."
    )


# =============================================================================
# ASSETS
# =============================================================================

elif page == "Assets":
    section_header(
        "Asset analysis",
        (
            "Historical treasury flows, counterparties and large movements for one valued asset."
        ),
    )

    valued_asset_events = (
        filtered_events[
            filtered_events[
                "valuation_status"
            ]
            == "VALUED"
        ]
    )

    valued_asset_summary = (
        valued_asset_events
        .groupby(
            "asset",
            as_index=False,
        )
        .agg(
            total_value_usd=(
                "value_usd",
                "sum",
            )
        )
        .sort_values(
            "total_value_usd",
            ascending=False,
        )
    )

    asset_options = (
        valued_asset_summary[
            "asset"
        ]
        .dropna()
        .tolist()
    )

    if not asset_options:
        st.info(
            "No valued assets are available "
            "for the selected date range."
        )
        st.stop()

    selected_asset = (
        st.selectbox(
            "Asset",
            asset_options,
            index=0,
            help=(
                "Business analysis focuses on assets "
                "with available USD valuation. "
                "Unvalued events remain represented "
                "through valuation-coverage metrics."
            ),
        )
    )

    asset_events = (
        filtered_events[
            filtered_events[
                "asset"
            ]
            == selected_asset
        ].copy()
    )

    asset_valued = (
        asset_events[
            asset_events[
                "valuation_status"
            ]
            == "VALUED"
        ]
    )

    asset_in = (
        safe_sum(
            asset_valued.loc[
                asset_valued[
                    "direction"
                ]
                == "IN",
                "value_usd",
            ]
        )
    )

    asset_out = (
        safe_sum(
            asset_valued.loc[
                asset_valued[
                    "direction"
                ]
                == "OUT",
                "value_usd",
            ]
        )
    )

    asset_internal = (
        safe_sum(
            asset_valued.loc[
                asset_valued[
                    "direction"
                ]
                == "INTERNAL",
                "value_usd",
            ]
        )
    )

    asset_monthly = (
        asset_valued
        .groupby(
            [
                "month",
                "direction",
            ],
            as_index=False,
        )
        .agg(
            value_usd=(
                "value_usd",
                "sum",
            )
        )
    )

    pivot = (
        asset_monthly
        .pivot_table(
            index="month",
            columns="direction",
            values="value_usd",
            aggfunc="sum",
            fill_value=0,
        )
        .sort_index()
    )

    for column in [
        "IN",
        "OUT",
        "INTERNAL",
    ]:
        if column not in (
            pivot.columns
        ):
            pivot[
                column
            ] = 0.0

    columns = st.columns(5)

    with columns[0]:
        kpi_card(
            "Inflow",
            format_usd(
                asset_in
            ),
            pivot["IN"],
            COLORS["navy_2"],
            selected_asset,
        )

    with columns[1]:
        kpi_card(
            "Outflow",
            format_usd(
                asset_out
            ),
            pivot["OUT"],
            COLORS["gold_dark"],
            selected_asset,
        )

    with columns[2]:
        kpi_card(
            "Internal movement",
            format_usd(
                asset_internal
            ),
            pivot["INTERNAL"],
            COLORS["slate"],
            selected_asset,
        )

    with columns[3]:
        kpi_card(
            "Large movements",
            f"{int(asset_events['is_large'].sum()):,}",
            (
                asset_events[
                    asset_events[
                        "is_large"
                    ]
                ]
                .groupby(
                    "month"
                )
                .size()
            ),
            COLORS["gold_dark"],
            (
                f"Threshold "
                f"{format_usd(LARGE_THRESHOLD)}"
            ),
        )

    with columns[4]:
        kpi_card(
            "Valuation coverage",
            format_percentage(
                len(
                    asset_valued
                ),
                len(
                    asset_events
                ),
            ),
            (
                asset_events
                .assign(
                    valued=(
                        asset_events[
                            "valuation_status"
                        ]
                        == "VALUED"
                    )
                )
                .groupby(
                    "month"
                )[
                    "valued"
                ]
                .mean()
                *
                100
            ),
            COLORS["navy_2"],
            "Asset events valued in USD",
        )

    st.write("")

    left, right = (
        st.columns(
            [
                1.4,
                1,
            ]
        )
    )

    with left:
        if not asset_monthly.empty:
            figure = px.line(
                asset_monthly,
                x="month",
                y="value_usd",
                color="direction",
                title=(
                    "Monthly asset movement"
                ),
                labels={
                    "month":
                        "Month",
                    "value_usd":
                        "USD value",
                    "direction":
                        "Direction",
                },
                color_discrete_map=(
                    DIRECTION_COLORS
                ),
            )

            figure.update_yaxes(
                tickprefix="$"
            )

            st.plotly_chart(
                style_figure(
                    figure,
                    height=370,
                ),
                use_container_width=True,
                config={
                    "displaylogo":
                        False,
                },
            )

    with right:
        counterparties = (
            counterparty_summary(
                asset_events,
                limit=8,
            )
            .sort_values(
                "value_usd"
            )
        )

        if not counterparties.empty:
            figure = px.bar(
                counterparties,
                x="value_usd",
                y="counterparty_display",
                orientation="h",
                title=(
                    "Top external counterparties"
                ),
                labels={
                    "value_usd":
                        "USD value",
                    "counterparty_display":
                        "Counterparty",
                },
            )

            figure.update_traces(
                marker_color=(
                    COLORS[
                        "blue"
                    ]
                )
            )

            figure.update_xaxes(
                tickprefix="$",
                rangemode="tozero",
            )

            st.plotly_chart(
                style_figure(
                    figure,
                    height=370,
                ),
                use_container_width=True,
                config={
                    "displaylogo":
                        False,
                },
            )

    section_header(
        "Deep-dive highlights",
        (
            "Top underlying movements for the selected asset. "
            "The full event-level table lives in Large Movements."
        ),
    )

    asset_top = (
        asset_events[
            asset_events[
                "valuation_status"
            ]
            == "VALUED"
        ]
        .sort_values(
            "value_usd",
            ascending=False,
        )
        .head(5)
        .copy()
    )

    if not asset_top.empty:
        asset_top[
            "label"
        ] = (
            asset_top[
                "wallet_context"
            ].astype(str)
            +
            " · "
            +
            asset_top[
                "direction"
            ]
            +
            " · "
            +
            asset_top[
                "timestamp"
            ].dt.strftime(
                "%Y-%m-%d"
            )
        )

        figure = px.bar(
            asset_top.sort_values(
                "value_usd"
            ),
            x="value_usd",
            y="label",
            color="direction",
            orientation="h",
            title="Top 5 movements",
            labels={
                "value_usd":
                    "USD value",
                "label":
                    "Movement",
                "direction":
                    "Direction",
            },
            color_discrete_map=(
                DIRECTION_COLORS
            ),
        )

        figure.update_xaxes(
            tickprefix="$",
            rangemode="tozero",
        )

        st.plotly_chart(
            style_figure(
                figure,
                height=310,
            ),
            use_container_width=True,
            config={
                "displaylogo":
                    False,
            },
        )

    st.caption(
        "Need transaction-level detail? Open the Large Movements page."
    )


# =============================================================================
# LARGE MOVEMENTS
# =============================================================================

elif page == "Large Movements":
    section_header(
        "Large movement monitoring",
        (
            "Organization-level movements flagged at or above the configured USD threshold."
        ),
    )

    direction_options = (
        sorted(
            large_events[
                "direction"
            ]
            .dropna()
            .unique()
            .tolist()
        )
    )

    type_options = (
        sorted(
            large_events[
                "asset_type"
            ]
            .dropna()
            .unique()
            .tolist()
        )
    )

    asset_options = (
        sorted(
            large_events[
                "asset"
            ]
            .dropna()
            .unique()
            .tolist()
        )
    )

    f1, f2, f3 = (
        st.columns(
            [
                1,
                1,
                1.3,
            ]
        )
    )

    with f1:
        selected_directions = (
            st.multiselect(
                "Direction",
                options=(
                    direction_options
                ),
                default=(
                    direction_options
                ),
            )
        )

    with f2:
        selected_types = (
            st.multiselect(
                "Asset type",
                options=(
                    type_options
                ),
                default=(
                    type_options
                ),
            )
        )

    with f3:
        selected_asset = (
            st.selectbox(
                "Asset",
                options=[
                    "All assets"
                ]
                +
                asset_options,
            )
        )

    view = (
        large_events[
            large_events[
                "direction"
            ].isin(
                selected_directions
            )
            &
            large_events[
                "asset_type"
            ].isin(
                selected_types
            )
        ].copy()
    )

    if (
        selected_asset
        != "All assets"
    ):
        view = (
            view[
                view[
                    "asset"
                ]
                == selected_asset
            ].copy()
        )

    external = (
        view[
            view[
                "direction"
            ].isin(
                [
                    "IN",
                    "OUT",
                ]
            )
        ]
    )

    internal = (
        view[
            view[
                "direction"
            ]
            == "INTERNAL"
        ]
    )

    metric_columns = (
        st.columns(4)
    )

    with metric_columns[0]:
        kpi_card(
            "Large movements",
            f"{len(view):,}",
            (
                view
                .groupby(
                    "month"
                )
                .size()
            ),
            COLORS["gold_dark"],
            "Current filters",
        )

    with metric_columns[1]:
        kpi_card(
            "Movement value",
            format_usd(
                safe_sum(
                    view[
                        "value_usd"
                    ]
                )
            ),
            (
                view
                .groupby(
                    "month"
                )[
                    "value_usd"
                ]
                .sum()
            ),
            COLORS["blue"],
            "Sum of large movements",
        )

    with metric_columns[2]:
        kpi_card(
            "External",
            f"{len(external):,}",
            (
                external
                .groupby(
                    "month"
                )
                .size()
            ),
            COLORS["navy_2"],
            "IN + OUT",
        )

    with metric_columns[3]:
        kpi_card(
            "Internal",
            f"{len(internal):,}",
            (
                internal
                .groupby(
                    "month"
                )
                .size()
            ),
            COLORS["slate"],
            "Between monitored ENS wallets",
        )

    st.write("")

    left, right = (
        st.columns(
            [
                1,
                1.45,
            ]
        )
    )

    with left:
        direction_summary = (
            view
            .groupby(
                "direction",
                as_index=False,
            )
            .agg(
                Events=(
                    "event_id",
                    "count",
                )
            )
        )

        if not direction_summary.empty:
            figure = px.bar(
                direction_summary,
                x="Events",
                y="direction",
                color="direction",
                orientation="h",
                title=(
                    "Movement count by direction"
                ),
                labels={
                    "direction":
                        "Direction"
                },
                color_discrete_map=(
                    DIRECTION_COLORS
                ),
            )

            figure.update_layout(
                showlegend=False
            )

            figure.update_xaxes(
                rangemode="tozero"
            )

            st.plotly_chart(
                style_figure(
                    figure,
                    height=370,
                ),
                use_container_width=True,
                config={
                    "displaylogo":
                        False,
                },
            )

    with right:
        counterparties = (
            counterparty_summary(
                view,
                limit=10,
            )
            .sort_values(
                "value_usd"
            )
        )

        if not counterparties.empty:
            figure = px.bar(
                counterparties,
                x="value_usd",
                y="counterparty_display",
                orientation="h",
                title=(
                    "Top external counterparties"
                ),
                labels={
                    "value_usd":
                        "USD value",
                    "counterparty_display":
                        "Counterparty",
                },
            )

            figure.update_traces(
                marker_color=(
                    COLORS[
                        "blue"
                    ]
                )
            )

            figure.update_xaxes(
                tickprefix="$",
                rangemode="tozero",
            )

            st.plotly_chart(
                style_figure(
                    figure,
                    height=370,
                ),
                use_container_width=True,
                config={
                    "displaylogo":
                        False,
                },
            )

    largest = (
        view
        .sort_values(
            "value_usd",
            ascending=False,
        )
        .head(
            12
        )
        .copy()
    )

    if not largest.empty:
        largest[
            "label"
        ] = (
            largest[
                "asset_symbol"
            ]
            +
            " · "
            +
            largest[
                "direction"
            ]
            +
            " · "
            +
            largest[
                "timestamp"
            ].dt.strftime(
                "%Y-%m-%d"
            )
        )

        figure = px.bar(
            largest.sort_values(
                "value_usd"
            ),
            x="value_usd",
            y="label",
            color="direction",
            orientation="h",
            title=(
                "Largest movements"
            ),
            labels={
                "value_usd":
                    "USD value",
                "label":
                    "Movement",
                "direction":
                    "Direction",
            },
            color_discrete_map=(
                DIRECTION_COLORS
            ),
        )

        figure.update_xaxes(
            tickprefix="$",
            rangemode="tozero",
        )

        st.plotly_chart(
            style_figure(
                figure,
                height=430,
            ),
            use_container_width=True,
            config={
                "displaylogo":
                    False,
            },
        )

    section_header(
        "Investigation detail",
        (
            "The charts above are the primary deep-dive view. "
            "Open transaction detail only when an event needs investigation."
        ),
    )

    with st.expander(
        "Show transaction-level details",
        expanded=False,
    ):
        details = (
            view[
                [
                    "timestamp",
                    "wallet_context",
                    "asset_type",
                    "asset",
                    "direction",
                    "amount",
                    "value_usd",
                    "counterparty_label",
                    "counterparty_address",
                    "etherscan",
                ]
            ]
            .sort_values(
                "value_usd",
                ascending=False,
            )
            .head(50)
            .rename(
                columns={
                    "timestamp":
                        "Timestamp",
                    "wallet_context":
                        "Wallet",
                    "asset_type":
                        "Asset Type",
                    "asset":
                        "Asset",
                    "direction":
                        "Direction",
                    "amount":
                        "Amount",
                    "value_usd":
                        "Value USD",
                    "counterparty_label":
                        "Counterparty",
                    "counterparty_address":
                        "Address",
                    "etherscan":
                        "Transaction",
                }
            )
        )

        st.dataframe(
            details,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Timestamp":
                    st.column_config.DatetimeColumn(
                        format=(
                            "YYYY-MM-DD "
                            "HH:mm:ss"
                        )
                    ),
                "Value USD":
                    st.column_config.NumberColumn(
                        format="$%.2f"
                    ),
                "Transaction":
                    st.column_config.LinkColumn(
                        display_text="Open"
                    ),
            },
        )

        st.caption(
            "Large movement = threshold-based asset movement, "
            "not automatically an accounting expense."
        )

