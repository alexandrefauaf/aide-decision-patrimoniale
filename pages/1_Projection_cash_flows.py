import plotly.graph_objects as go
import streamlit as st

from src import cashflow as cf
from src import utils
from src.utils import format_eur, format_pct

INVESTED_ENVELOPES = ["assurance_vie", "pea", "compte_titres"]
INITIAL_SAVINGS = {"livret_a": 10_000, "assurance_vie": 15_000, "pea": 8_000, "compte_titres": 2_000}

defaults = {
    "cf_age": 30,
    "cf_income": 42_000,
    "cf_expenses": 30_000,
    "cf_retirement_age": 64,
    "cf_pension": 24_000,
    "cf_horizon": 35,
    "cf_inflation": 2.0,
    "cf_av_seniority": 0,
    "cf_pea_seniority": 0,
    "cf_unit": "Euros courants",
    "cf_events": [],
}
for env in cf.ENVELOPES:
    defaults[f"cf_init_{env}"] = INITIAL_SAVINGS[env]
    defaults[f"cf_ret_{env}"] = round(cf.DEFAULT_RETURNS[env] * 100, 2)
    defaults[f"cf_vol_{env}"] = round(cf.DEFAULT_VOLATILITIES[env] * 100, 2)
    defaults[f"cf_split_{env}"] = round(cf.DEFAULT_SPLIT[env] * 100)
utils.init_state(defaults)

# Hypothèses transmises par le module « Profil de risque ».
transfer = st.session_state.pop("pending_transfer", None)
if transfer:
    for env in INVESTED_ENVELOPES:
        st.session_state[f"cf_ret_{env}"] = round(transfer["expected_return"] * 100, 2)
        st.session_state[f"cf_vol_{env}"] = round(transfer["volatility"] * 100, 2)
    st.session_state["cf_profile_applied"] = transfer["profile"]


@st.cache_data(show_spinner="Simulation Monte Carlo en cours...")
def run_monte_carlo(params, events):
    return cf.monte_carlo(params, events)


def describe_event(event):
    if isinstance(event, cf.RealEstatePurchase):
        return (
            f"Année {event.year} : achat immobilier, apport {format_eur(event.down_payment)}, "
            f"emprunt {format_eur(event.loan_amount)} à {format_pct(event.loan_rate, 2)} "
            f"sur {event.loan_years} ans, mensualité {format_eur(event.monthly_payment)}"
        )
    return f"Année {event.year} : {event.label.lower()}, {format_eur(abs(event.amount))}"


st.title("Projection de cash-flows")
st.caption(
    "Projection annuelle du patrimoine à partir des revenus, des charges et de l'épargne par enveloppe. "
    "Fiscalité simplifiée, détaillée dans l'onglet « Hypothèses »."
)

tab_situation, tab_envelopes, tab_events, tab_assumptions = st.tabs(
    ["Situation", "Enveloppes", "Événements", "Hypothèses"]
)

with tab_situation:
    col1, col2, col3 = st.columns(3)
    col1.number_input("Âge", 18, 90, key="cf_age")
    col1.number_input("Âge de départ à la retraite", 50, 75, key="cf_retirement_age")
    col2.number_input("Revenus nets annuels (€)", 0, step=1_000, key="cf_income")
    col2.number_input("Pension annuelle estimée (€ d'aujourd'hui)", 0, step=1_000, key="cf_pension")
    col3.number_input("Charges annuelles (€)", 0, step=1_000, key="cf_expenses")
    col3.number_input("Inflation annuelle (%)", 0.0, 10.0, step=0.1, format="%.1f", key="cf_inflation")
    st.slider("Horizon de projection (années)", 5, 60, key="cf_horizon")

with tab_envelopes:
    if st.session_state.get("cf_profile_applied"):
        st.info(
            f"Rendements et volatilités de l'assurance-vie, du PEA et du compte-titres repris de "
            f"l'allocation du profil « {st.session_state['cf_profile_applied']} ». Ils restent modifiables."
        )
    header = st.columns([1.2, 1, 1, 1, 1])
    for column, title in zip(
        header[1:],
        ["Encours initial (€)", "Rendement attendu (%)", "Volatilité (%)", "Part de l'épargne annuelle (%)"],
    ):
        column.markdown(f"**{title}**")
    for env in cf.ENVELOPES:
        row = st.columns([1.2, 1, 1, 1, 1], vertical_alignment="center")
        label = cf.ENVELOPE_LABELS[env]
        row[0].markdown(label)
        row[1].number_input(
            f"Encours initial {label}", 0, step=1_000, key=f"cf_init_{env}", label_visibility="collapsed"
        )
        row[2].number_input(
            f"Rendement {label}", -5.0, 15.0, step=0.1, format="%.2f", key=f"cf_ret_{env}",
            label_visibility="collapsed",
        )
        row[3].number_input(
            f"Volatilité {label}", 0.0, 40.0, step=0.5, format="%.2f", key=f"cf_vol_{env}",
            label_visibility="collapsed",
        )
        row[4].number_input(
            f"Part de l'épargne {label}", 0, 100, step=5, key=f"cf_split_{env}", label_visibility="collapsed"
        )
    split_total = sum(st.session_state[f"cf_split_{env}"] for env in cf.ENVELOPES)
    if split_total != 100:
        st.caption(f"Les parts de l'épargne annuelle totalisent {split_total} % : elles sont ramenées à 100 %.")
    col1, col2 = st.columns(2)
    col1.number_input("Ancienneté de l'assurance-vie (années)", 0, 40, key="cf_av_seniority")
    col2.number_input("Ancienneté du PEA (années)", 0, 40, key="cf_pea_seniority")

with tab_events:
    st.caption(
        "Les montants sont exprimés en euros de l'année de l'événement. "
        "Un événement placé au-delà de l'horizon de projection est ignoré."
    )
    col1, col2 = st.columns(2)
    kind = col1.selectbox("Type d'événement", ["Achat immobilier", "Héritage", "Dépense exceptionnelle"])
    event_year = col2.number_input("Dans combien d'années", 1, 60, 5)
    if kind == "Achat immobilier":
        col1, col2, col3, col4 = st.columns(4)
        new_event = cf.RealEstatePurchase(
            year=event_year,
            down_payment=col1.number_input("Apport (€)", 0, value=40_000, step=5_000),
            loan_amount=col2.number_input("Montant emprunté (€)", 0, value=200_000, step=10_000),
            loan_rate=col3.number_input("Taux du crédit (%)", 0.0, 15.0, 3.3, step=0.1, format="%.2f") / 100,
            loan_years=col4.number_input("Durée du crédit (années)", 1, 30, 20),
            fees_rate=col1.number_input("Frais d'acquisition (%)", 0.0, 15.0, 7.5, step=0.5) / 100,
            appreciation=col2.number_input("Revalorisation annuelle du bien (%)", -5.0, 10.0, 1.5, step=0.1) / 100,
            rent_saved=col3.number_input("Loyer annuel économisé (€ d'aujourd'hui)", 0, value=0, step=500),
        )
        st.write(
            f"Mensualité calculée : **{format_eur(new_event.monthly_payment)}** hors assurance. "
            f"Prix du bien hors frais : {format_eur(new_event.price)}."
        )
    else:
        amount = st.number_input("Montant (€)", 0, value=50_000 if kind == "Héritage" else 15_000, step=1_000)
        sign = 1 if kind == "Héritage" else -1
        new_event = cf.OneOffFlow(year=event_year, amount=sign * amount, label=kind)
    if st.button("Ajouter l'événement", key="btn_add_event"):
        st.session_state["cf_events"].append(new_event)

    events = st.session_state["cf_events"]
    if events:
        st.markdown("**Événements pris en compte**")
    for i, event in enumerate(events):
        col_text, col_button = st.columns([5, 1], vertical_alignment="center")
        col_text.write(describe_event(event))
        if col_button.button("Supprimer", key=f"btn_delete_event_{i}"):
            events.pop(i)
            st.rerun()

with tab_assumptions:
    st.markdown(
        f"""
**Projection**
- Les revenus, les charges et la pension sont saisis en euros d'aujourd'hui et indexés sur l'inflation.
- Chaque année, les encours sont d'abord rémunérés, puis le cash-flow net est investi (s'il est positif)
  selon la répartition choisie, ou prélevé (s'il est négatif) dans l'ordre livret A, compte-titres,
  assurance-vie, PEA.
- Plafonds de versement : {format_eur(cf.LIVRET_A_CAP)} sur le livret A et {format_eur(cf.PEA_CAP)} sur le PEA.
  L'excédent est versé sur le compte-titres.
- Les euros constants sont obtenus en divisant les montants de l'année *t* par (1 + inflation)^*t*.

**Fiscalité simplifiée (taux 2026)**
- Compte-titres : prélèvement forfaitaire unique de {format_pct(cf.PFU_RATE)} appliqué chaque année aux gains,
  comme s'ils étaient intégralement réalisés.
- Assurance-vie : imposition au moment des retraits, sur la seule part de gains. {format_pct(cf.AV_RATE_BEFORE_8Y, 0)}
  avant 8 ans ; après 8 ans, abattement annuel de {format_eur(cf.AV_ALLOWANCE)} puis {format_pct(cf.AV_RATE_AFTER_8Y)}.
- PEA : imposition au moment des retraits, sur la part de gains. {format_pct(cf.PFU_RATE)} avant 5 ans,
  {format_pct(cf.PEA_RATE_AFTER_5Y)} (prélèvements sociaux seuls) après.
- Livret A : exonéré.
- Non pris en compte : impôt sur le revenu (les revenus sont saisis nets), droits de succession,
  imposition des plus-values immobilières, frais des enveloppes, assurance emprunteur.

**Immobilier**
- L'apport et le prêt financent le prix du bien et les frais d'acquisition. La valeur du bien est revalorisée
  chaque année au taux saisi. Le patrimoine net est égal à l'épargne financière plus la valeur du bien moins
  le capital restant dû.

**Monte Carlo**
- 1 000 trajectoires. Chaque année, les rendements des enveloppes sont tirés dans une loi normale dont la
  moyenne est le rendement attendu et l'écart-type la volatilité saisie, avec une corrélation fixe entre
  enveloppes. Les tirages sont indépendants d'une année sur l'autre.
"""
    )

inflation = st.session_state["cf_inflation"] / 100
params = cf.Params(
    age=st.session_state["cf_age"],
    net_income=st.session_state["cf_income"],
    expenses=st.session_state["cf_expenses"],
    retirement_age=st.session_state["cf_retirement_age"],
    pension=st.session_state["cf_pension"],
    horizon=st.session_state["cf_horizon"],
    inflation=inflation,
    initial_savings={env: st.session_state[f"cf_init_{env}"] for env in cf.ENVELOPES},
    expected_returns={env: st.session_state[f"cf_ret_{env}"] / 100 for env in cf.ENVELOPES},
    volatilities={env: st.session_state[f"cf_vol_{env}"] / 100 for env in cf.ENVELOPES},
    savings_split={env: st.session_state[f"cf_split_{env}"] / 100 for env in cf.ENVELOPES},
    av_seniority=st.session_state["cf_av_seniority"],
    pea_seniority=st.session_state["cf_pea_seniority"],
)
events = st.session_state["cf_events"]

projection = cf.project(params, events)
quantiles, shortfall_probability = run_monte_carlo(params, events)

st.divider()
st.radio("Unité d'affichage", ["Euros courants", "Euros constants"], horizontal=True, key="cf_unit")
constant = st.session_state["cf_unit"] == "Euros constants"
view = cf.to_constant_euros(projection, inflation) if constant else projection
view_quantiles = cf.to_constant_euros(quantiles, inflation) if constant else quantiles
unit = st.session_state["cf_unit"].lower()

final, final_quantiles = view.iloc[-1], view_quantiles.iloc[-1]
final_age = int(final["age"])
col1, col2, col3, col4 = st.columns(4)
col1.metric(f"Patrimoine net à {final_age} ans", format_eur(final["net_wealth"]))
col2.metric("Médiane Monte Carlo", format_eur(final_quantiles["median"]))
col3.metric(
    "Intervalle 10 % - 90 %",
    f"{utils.format_number(final_quantiles['p10'] / 1000)} - {utils.format_number(final_quantiles['p90'] / 1000)} k€",
)
col4.metric("Trajectoires où l'épargne ne suffit pas", format_pct(shortfall_probability, 0))

unfunded_years = projection.loc[projection["unfunded"] > 0, "age"]
if not unfunded_years.empty:
    st.warning(
        f"Dans la projection, l'épargne financière ne couvre plus les besoins à partir de "
        f"{int(unfunded_years.iloc[0])} ans. Les montants non financés ne sont pas reportés en dette."
    )

st.subheader("Évolution du patrimoine net")
fig = go.Figure()
fig.add_trace(
    go.Scatter(x=view_quantiles["age"], y=view_quantiles["p90"], mode="lines", line={"width": 0}, hoverinfo="skip", showlegend=False)
)
fig.add_trace(
    go.Scatter(
        x=view_quantiles["age"], y=view_quantiles["p10"], mode="lines", line={"width": 0}, fill="tonexty",
        fillcolor=utils.BAND, hoverinfo="skip", name="Intervalle 10 % - 90 %",
    )
)
fig.add_trace(
    go.Scatter(
        x=view_quantiles["age"], y=view_quantiles["median"], mode="lines", name="Médiane Monte Carlo",
        line={"color": utils.GREY, "width": 2, "dash": "dash"}, hovertemplate="%{y:,.0f} €",
    )
)
fig.add_trace(
    go.Scatter(
        x=view["age"], y=view["net_wealth"], mode="lines", name="Projection à rendements constants",
        line={"color": utils.NAVY, "width": 2}, hovertemplate="%{y:,.0f} €",
    )
)
fig.update_xaxes(title_text="Âge")
utils.show_figure(utils.style_figure(fig))
st.caption(
    f"Montants en {unit}. La médiane Monte Carlo se situe en général sous la projection à rendements "
    "constants : la volatilité réduit le rendement composé."
)

st.subheader("Décomposition par enveloppe")
has_property = (projection["property_value"] > 0).any()
fig = go.Figure()
stacked = [(env, cf.ENVELOPE_LABELS[env]) for env in cf.ENVELOPES]
if has_property:
    stacked.append(("property_value", "Immobilier (valeur du bien)"))
for (column, label), color in zip(stacked, utils.SERIES_COLORS):
    fig.add_trace(
        go.Scatter(
            x=view["age"], y=view[column], mode="lines", name=label, stackgroup="wealth",
            line={"width": 1, "color": "white"}, fillcolor=color, hovertemplate="%{y:,.0f} €",
        )
    )
if has_property:
    fig.add_trace(
        go.Scatter(
            x=view["age"], y=view["net_wealth"], mode="lines", name="Patrimoine net (après dette)",
            line={"color": utils.NAVY, "width": 2}, hovertemplate="%{y:,.0f} €",
        )
    )
fig.update_xaxes(title_text="Âge")
utils.show_figure(utils.style_figure(fig))
if has_property:
    st.caption("L'écart entre le haut des aires et la courbe correspond au capital restant dû.")

st.subheader("Cash-flow annuel")
flows = view.iloc[1:]
fig = go.Figure(
    go.Bar(x=flows["age"], y=flows["net_cashflow"], marker_color=utils.NAVY, hovertemplate="%{y:,.0f} €<extra></extra>")
)
fig.update_xaxes(title_text="Âge")
utils.show_figure(utils.style_figure(fig, height=320))
st.caption(
    "Revenus moins charges et mensualités de crédit, plus ou moins les événements ponctuels. "
    "Un cash-flow positif est épargné, un cash-flow négatif est prélevé sur l'épargne."
)

st.subheader("Tableau récapitulatif")
columns = {
    "year": "Année",
    "age": "Âge",
    "income": "Revenus",
    "expenses": "Charges",
    "loan_payments": "Mensualités de crédit",
    "one_off": "Événements ponctuels",
    "net_cashflow": "Cash-flow net",
    "taxes": "Fiscalité des placements",
    **cf.ENVELOPE_LABELS,
    "property_value": "Valeur immobilière",
    "debt": "Capital restant dû",
    "net_wealth": "Patrimoine net",
}
table = projection[list(columns)].rename(columns=columns)
table["Patrimoine net (euros constants)"] = cf.to_constant_euros(projection, inflation)["net_wealth"]
money_columns = [c for c in table.columns if c not in ("Année", "Âge")]
table[money_columns] = table[money_columns].round(0)

st.dataframe(table.style.format(dict.fromkeys(money_columns, format_eur)), hide_index=True, height=420)
st.caption("Tableau en euros courants, avec le patrimoine net également exprimé en euros constants.")
st.download_button(
    "Exporter en CSV",
    # Séparateur point-virgule, virgule décimale et BOM pour une ouverture directe dans Excel en français.
    data=table.to_csv(index=False, sep=";", decimal=",").encode("utf-8-sig"),
    file_name="projection_cash_flows.csv",
    mime="text/csv",
    key="btn_export_csv",
)
