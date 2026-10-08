"""Formats français, palette et petits utilitaires d'affichage communs aux pages."""

import copy

import streamlit as st

DISCLAIMER = "Outil pédagogique, ne constitue pas un conseil en investissement."

NAVY = "#1B2A49"
GREY = "#6B7785"
LIGHT_GREY = "#E3E7EC"
BAND = "rgba(27, 42, 73, 0.12)"
# Couleurs des séries quand un graphique en compare plusieurs. Le bleu marine et le
# gris seuls ne se distinguent pas assez entre eux, d'où quatre teintes supplémentaires
# volontairement peu saturées.
SERIES_COLORS = ["#2B5C9E", "#D0762F", "#2E9E83", "#8A64B8", "#A8871C"]

NBSP = " "


def format_number(value, decimals=0):
    return f"{value:,.{decimals}f}".replace(",", NBSP).replace(".", ",")


def format_eur(value, decimals=0):
    return f"{format_number(value, decimals)}{NBSP}€"


def format_pct(value, decimals=1):
    """Formate un taux exprimé en fraction (0,045 -> « 4,5 % »)."""
    return f"{format_number(value * 100, decimals)}{NBSP}%"


def init_state(defaults):
    """Initialise les clés de session absentes (valeurs par défaut des widgets)."""
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = copy.deepcopy(value)


def keep_state(prefixes=("cf_", "rp_", "am_")):
    """Conserve les saisies d'une page à l'autre.

    Streamlit efface l'état d'un widget dès qu'il n'est plus affiché ; réaffecter
    la clé en fait une valeur de session ordinaire, qui survit au changement de page.
    """
    for key in list(st.session_state.keys()):
        if key.startswith(prefixes):
            st.session_state[key] = st.session_state[key]


def style_figure(fig, height=400, euros=True):
    fig.update_layout(
        template="plotly_white",
        paper_bgcolor="white",
        plot_bgcolor="white",
        height=height,
        separators=", ",
        font={"color": NAVY, "size": 13},
        margin={"l": 10, "r": 10, "t": 40, "b": 10},
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "x": 0, "traceorder": "normal"},
        hovermode="x unified",
        colorway=SERIES_COLORS,
    )
    fig.update_xaxes(showgrid=False, linecolor=LIGHT_GREY)
    fig.update_yaxes(gridcolor=LIGHT_GREY, zerolinecolor=GREY, zerolinewidth=1)
    if euros:
        fig.update_yaxes(tickformat=",.0f", ticksuffix=" €")
    return fig


def show_figure(fig):
    st.plotly_chart(fig, theme=None, config={"displayModeBar": False})


def footer():
    st.divider()
    st.caption(DISCLAIMER)
