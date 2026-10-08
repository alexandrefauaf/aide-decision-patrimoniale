import streamlit as st

from src import utils

st.set_page_config(page_title="Aide à la décision patrimoniale", layout="wide")


def home():
    st.title("Aide à la décision patrimoniale")
    st.write(
        "Trois modules pour raisonner sur un patrimoine : projeter son évolution, "
        "situer le profil de risque d'un investisseur et estimer la valeur d'actifs corporels."
    )

    modules = [
        (
            cashflow_page,
            "Projection annuelle des revenus, des charges et de l'épargne par enveloppe, "
            "en euros courants et constants, avec une simulation Monte Carlo.",
        ),
        (
            risk_page,
            "Questionnaire en quatre axes inspiré de MiFID II, profil obtenu, "
            "indicateur de risque compatible et allocation indicative.",
        ),
        (
            assets_page,
            "Estimation de la valeur d'un bien immobilier, d'une montre ou d'une voiture "
            "de collection par deux modèles, et projection à dix ans.",
        ),
    ]
    for column, (page, description) in zip(st.columns(3), modules):
        with column.container(border=True, height="stretch"):
            st.subheader(page.title)
            st.write(description)
            st.page_link(page, label="Ouvrir le module")

    st.caption(
        "Les données du module « Actifs corporels » sont simulées. "
        "La fiscalité du module de projection est simplifiée ; les hypothèses sont détaillées dans chaque page."
    )


home_page = st.Page(home, title="Accueil", default=True)
cashflow_page = st.Page("pages/1_Projection_cash_flows.py", title="Projection de cash-flows")
risk_page = st.Page("pages/2_Profil_de_risque.py", title="Profil de risque")
assets_page = st.Page("pages/3_Actifs_corporels.py", title="Actifs corporels")

utils.keep_state()
st.navigation([home_page, cashflow_page, risk_page, assets_page]).run()
utils.footer()
