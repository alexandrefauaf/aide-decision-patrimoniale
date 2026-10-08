import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from data import generate_data as gd
from src import asset_models as am
from src import utils
from src.utils import format_eur, format_pct

MODEL_COLORS = {am.LINEAR: utils.SERIES_COLORS[0], am.BOOSTING: utils.SERIES_COLORS[1]}


@st.cache_resource(show_spinner="Entraînement des modèles (premier lancement uniquement)...")
def load_models(category):
    return am.train_category(category)


def real_estate_form():
    col1, col2 = st.columns(2)
    return {
        "city": col1.selectbox("Ville", list(gd.CITIES)),
        "surface": col2.number_input("Surface (m²)", 12, 220, 60),
        "year_built": col1.number_input("Année de construction", 1870, gd.REFERENCE_YEAR - 1, 1975),
        "condition": col2.selectbox("État", list(gd.REAL_ESTATE_CONDITIONS), index=2),
    }


def watch_form():
    col1, col2 = st.columns(2)
    brands = sorted({spec[0] for spec in gd.WATCHES.values()})
    brand = col1.selectbox("Marque", brands, index=brands.index("Rolex"))
    reference = col2.selectbox("Référence", [r for r, spec in gd.WATCHES.items() if spec[0] == brand])
    first_year = gd.WATCHES[reference][2]
    year = col1.number_input("Année", first_year, gd.REFERENCE_YEAR - 1, max(first_year, 2015))
    condition = col2.selectbox("État", list(gd.WATCH_CONDITIONS), index=2)
    box = col1.checkbox("Boîte d'origine", value=True)
    papers = col2.checkbox("Papiers d'origine", value=True)
    return {
        "brand": brand,
        "reference": reference,
        "year": year,
        "condition": condition,
        "box": int(box),
        "papers": int(papers),
    }


def car_form():
    col1, col2 = st.columns(2)
    brands = sorted({spec[0] for spec in gd.CARS.values()})
    brand = col1.selectbox("Marque", brands, index=brands.index("Porsche"))
    model = col2.selectbox("Modèle", [m for m, spec in gd.CARS.items() if spec[0] == brand])
    _, _, start, end = gd.CARS[model]
    return {
        "brand": brand,
        "model": model,
        "year": col1.number_input("Année", start, end, (start + end) // 2),
        "mileage": col2.number_input("Kilométrage", 4_000, 320_000, 90_000, step=5_000),
        "condition": st.selectbox("État", list(gd.CAR_CONDITIONS), index=1),
    }


FORMS = {"immobilier": real_estate_form, "montres": watch_form, "voitures": car_form}

st.title("Valeur d'actifs corporels")
st.info(
    "Les données de ce module sont simulées : les prix sont générés par des règles simples puis bruités "
    "(script data/generate_data.py). Les estimations illustrent la méthode et ne reflètent pas le marché réel."
)

utils.init_state({"am_category": "immobilier"})
category = st.radio(
    "Catégorie",
    list(am.CATEGORIES),
    format_func=lambda c: am.CATEGORIES[c]["label"],
    horizontal=True,
    key="am_category",
)
cfg = am.CATEGORIES[category]
result = load_models(category)
metrics = result["metrics"].set_index("model")

tab_estimate, tab_models, tab_data = st.tabs(["Estimation", "Comparaison des modèles", "Données"])

with tab_estimate:
    col_form, col_result = st.columns([1, 1.3], gap="large")
    with col_form:
        st.subheader("Description de l'actif")
        asset = FORMS[category]()
        models = list(result["models"])
        model_name = st.selectbox(
            "Modèle utilisé",
            models,
            index=models.index(result["best"]),
            help="Par défaut, le modèle dont l'erreur absolue moyenne en validation croisée est la plus faible.",
        )
        with st.expander("Hypothèses de projection"):
            low_default, central_default, high_default = (round(r * 100, 1) for r in cfg["rates"])
            st.caption("Taux annuels d'évolution de la valeur. Ce sont des hypothèses, pas des résultats du modèle.")
            # La clé dépend de la catégorie pour retrouver les valeurs par défaut en en changeant.
            low_rate = st.number_input("Scénario bas (%)", -10.0, 15.0, low_default, step=0.5, key=f"low_{category}")
            central_rate = st.number_input(
                "Scénario central (%)", -10.0, 15.0, central_default, step=0.5, key=f"central_{category}"
            )
            high_rate = st.number_input("Scénario haut (%)", -10.0, 15.0, high_default, step=0.5, key=f"high_{category}")

    value, low, high = am.estimate(result, model_name, asset)
    rates = (low_rate / 100, central_rate / 100, high_rate / 100)
    projection = am.project_value(value, low, high, rates)

    with col_result:
        st.subheader("Estimation")
        st.metric("Valeur estimée", format_eur(round(value, -2)))
        st.write(f"Fourchette 10 % - 90 % : **{format_eur(round(low, -2))} à {format_eur(round(high, -2))}**")
        st.caption(
            "La fourchette vient des erreurs du modèle en validation croisée : 80 % des prix simulés "
            "se situent dans cet intervalle autour de la prédiction."
        )

        st.subheader("Projection à 10 ans")
        years = gd.REFERENCE_YEAR + projection["year"]
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=years, y=projection["high"], mode="lines", line={"width": 0}, hoverinfo="skip", showlegend=False))
        fig.add_trace(
            go.Scatter(
                x=years, y=projection["low"], mode="lines", line={"width": 0}, fill="tonexty", fillcolor=utils.BAND,
                hoverinfo="skip", name="Fourchette (scénarios bas et haut)",
            )
        )
        fig.add_trace(
            go.Scatter(
                x=years, y=projection["central"], mode="lines", name="Scénario central",
                line={"color": utils.NAVY, "width": 2}, hovertemplate="%{y:,.0f} €",
            )
        )
        utils.show_figure(utils.style_figure(fig, height=340))
        final = projection.iloc[-1]
        st.write(
            f"Dans 10 ans : **{format_eur(round(final['central'], -2))}** dans le scénario central "
            f"({format_pct(rates[1])} par an), entre {format_eur(round(final['low'], -2))} et "
            f"{format_eur(round(final['high'], -2))} selon les scénarios. "
            "Les frais de détention (entretien, assurance, taxe foncière) ne sont pas déduits."
        )

with tab_models:
    st.caption(
        f"Validation croisée à {am.N_FOLDS} blocs sur {utils.format_number(len(result['data']))} observations simulées. "
        "Les deux modèles prédisent le logarithme du prix ; les métriques sont calculées sur les prix en euros."
    )
    comparison = pd.DataFrame(
        {
            "Modèle": metrics.index,
            "MAE": [f"{format_eur(m)} (± {format_eur(s)})" for m, s in zip(metrics["mae"], metrics["mae_std"])],
            "R²": [
                f"{utils.format_number(m, 3)} (± {utils.format_number(s, 3)})"
                for m, s in zip(metrics["r2"], metrics["r2_std"])
            ],
            "Erreur relative médiane": [format_pct(e) for e in metrics["median_relative_error"]],
        }
    )
    st.dataframe(comparison, hide_index=True)
    st.caption("MAE et R² : moyenne et écart-type sur les blocs de validation.")

    col_importance, col_scatter = st.columns(2, gap="large")
    with col_importance:
        st.subheader("Importance des variables")
        importances = result["importances"]
        order = (
            importances.groupby("feature")["importance"].max().sort_values().index
        )
        fig = go.Figure()
        for name in result["models"]:
            subset = importances[importances["model"] == name].set_index("feature").loc[order]
            fig.add_trace(
                go.Bar(
                    x=subset["importance"],
                    y=[am.FEATURE_LABELS[f] for f in order],
                    orientation="h",
                    name=name,
                    marker_color=MODEL_COLORS[name],
                    hovertemplate="%{x:.3f}",
                )
            )
        fig.update_layout(barmode="group", bargap=0.35)
        utils.style_figure(fig, height=380, euros=False)
        fig.update_layout(hovermode="y unified")
        fig.update_xaxes(title_text="Baisse du R² quand la variable est permutée", showgrid=True, gridcolor=utils.LIGHT_GREY)
        fig.update_yaxes(showgrid=False, ticksuffix="  ")
        utils.show_figure(fig)
        note = "Importance par permutation, mesurée sur 20 % des données mises de côté."
        if "brand" in result["features"]:
            note += " La marque se déduit de la référence ou du modèle : ces deux variables se partagent l'importance."
        st.caption(note)

    with col_scatter:
        st.subheader("Prix prédits et prix simulés")
        shown_model = st.radio("Modèle affiché", list(result["models"]), horizontal=True, key=f"scatter_{category}")
        sample = result["data"].sample(500, random_state=am.SEED).index
        actual = result["data"].loc[sample, "price"]
        predicted = result["out_of_fold"][shown_model][sample]
        bounds = [min(actual.min(), predicted.min()), max(actual.max(), predicted.max())]
        fig = go.Figure()
        fig.add_trace(
            go.Scatter(
                x=bounds, y=bounds, mode="lines", line={"color": utils.GREY, "width": 1},
                name="Prédiction parfaite", hoverinfo="skip",
            )
        )
        fig.add_trace(
            go.Scatter(
                x=actual, y=predicted, mode="markers", name="Prédictions hors échantillon",
                marker={"color": MODEL_COLORS[shown_model], "size": 6, "opacity": 0.55},
                hovertemplate="Simulé : %{x:,.0f} €<br>Prédit : %{y:,.0f} €<extra></extra>",
            )
        )
        utils.style_figure(fig, height=380, euros=False)
        fig.update_layout(hovermode="closest")
        # dtick "D2" : graduations en 1, 2 et 5 par décade, pour des axes logarithmiques lisibles.
        fig.update_xaxes(type="log", dtick="D2", tickformat=",.0f", title_text="Prix simulé (€, échelle logarithmique)")
        fig.update_yaxes(type="log", dtick="D2", tickformat=",.0f", title_text="Prix prédit (€)")
        utils.show_figure(fig)
        st.caption("500 observations tirées au hasard, chacune prédite par un modèle qui ne l'a pas vue.")

with tab_data:
    st.caption(
        f"{utils.format_number(len(result['data']))} observations simulées avec une graine fixe. "
        "Extrait des 200 premières lignes."
    )
    preview = result["data"].head(200).rename(columns=am.FEATURE_LABELS)
    st.dataframe(preview.style.format({"Prix": format_eur}), hide_index=True, height=420)
