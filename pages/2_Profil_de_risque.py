import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src import risk_profile as rp
from src import utils
from src.utils import format_pct


def sri_scale(sri_max):
    boxes = []
    for level in range(1, 8):
        compatible = level <= sri_max
        boxes.append(
            f'<span style="display:inline-block;width:2.2rem;line-height:2.2rem;margin-right:4px;'
            f"text-align:center;border-radius:4px;font-weight:600;"
            f"background:{utils.NAVY if compatible else utils.LIGHT_GREY};"
            f'color:{"#FFFFFF" if compatible else utils.GREY};">{level}</span>'
        )
    return "".join(boxes)


st.title("Profil de risque investisseur")
st.caption(
    "Questionnaire en quatre axes inspiré de la logique MiFID II. "
    "Il ne remplace pas le recueil réglementaire réalisé par un conseiller."
)

with st.form("risk_form"):
    for axis, axis_label in rp.AXES.items():
        st.subheader(axis_label)
        for question_id, question_axis, text, options in rp.QUESTIONS:
            if question_axis != axis:
                continue
            st.radio(
                text,
                options=range(len(options)),
                format_func=lambda i, options=options: options[i][0],
                index=None,
                key=f"rp_answer_{question_id}",
            )
    submitted = st.form_submit_button("Calculer le profil", type="primary")

if submitted:
    answers = {q[0]: st.session_state[f"rp_answer_{q[0]}"] for q in rp.QUESTIONS}
    if None in answers.values():
        st.session_state.pop("rp_result", None)
        st.error("Merci de répondre à toutes les questions.")
    else:
        st.session_state["rp_result"] = rp.evaluate(answers)

result = st.session_state.get("rp_result")
if result:
    st.divider()
    st.header("Résultat")
    expected_return, volatility = rp.allocation_assumptions(result.allocation)

    col_summary, col_radar = st.columns([1, 1.2])
    with col_summary:
        st.metric("Profil", result.profile)
        st.metric("Score global", f"{utils.format_number(result.global_score)} / 100")
        for warning in result.warnings:
            st.warning(warning)
        st.markdown("**Indicateur de risque (SRI) des supports compatibles**")
        st.markdown(sri_scale(result.sri_max), unsafe_allow_html=True)
        st.caption(f"Supports dont l'indicateur de risque va de 1 à {result.sri_max} sur une échelle de 7.")

    with col_radar:
        # Retour à la ligne dans les libellés longs pour qu'ils tiennent autour du radar.
        labels = [rp.AXES[axis].replace(" et ", "<br>et ") for axis in rp.AXES]
        scores = [result.axis_scores[axis] for axis in rp.AXES]
        fig = go.Figure(
            go.Scatterpolar(
                r=scores + scores[:1],
                theta=labels + labels[:1],
                fill="toself",
                fillcolor=utils.BAND,
                line={"color": utils.NAVY, "width": 2},
                hovertemplate="%{r:.0f} / 100<extra></extra>",
            )
        )
        fig.update_layout(
            polar={
                "radialaxis": {
                    "range": [0, 100], "tickvals": [25, 50, 75, 100], "angle": 45, "tickangle": 0,
                    "gridcolor": utils.LIGHT_GREY, "tickfont": {"color": utils.GREY, "size": 11},
                },
                "angularaxis": {"gridcolor": utils.LIGHT_GREY, "rotation": 90, "direction": "clockwise"},
                "bgcolor": "white",
            },
            showlegend=False,
        )
        utils.style_figure(fig, height=380, euros=False)
        fig.update_layout(margin={"l": 110, "r": 110, "t": 50, "b": 50}, hovermode="closest")
        utils.show_figure(fig)

    st.subheader("Allocation indicative")
    fig = go.Figure()
    for asset_class, color in zip(rp.ASSET_CLASSES, utils.SERIES_COLORS):
        weight = result.allocation[asset_class]
        fig.add_trace(
            go.Bar(
                x=[weight * 100],
                y=["Allocation"],
                orientation="h",
                name=asset_class,
                marker={"color": color, "line": {"color": "white", "width": 2}},
                # L'étiquette n'est affichée que si le segment est assez large pour la contenir.
                text=format_pct(weight, 0) if weight >= 0.08 else "",
                textposition="inside",
                insidetextanchor="middle",
                textfont={"color": "white"},
                hovertemplate=f"{asset_class} : {format_pct(weight, 0)}<extra></extra>",
            )
        )
    fig.update_layout(barmode="stack")
    utils.style_figure(fig, height=170, euros=False)
    fig.update_layout(hovermode="closest")
    fig.update_xaxes(range=[0, 100], ticksuffix=" %")
    fig.update_yaxes(showticklabels=False)
    utils.show_figure(fig)

    allocation_table = pd.DataFrame(
        {
            "Classe d'actifs": rp.ASSET_CLASSES,
            "Poids": [format_pct(result.allocation[c], 0) for c in rp.ASSET_CLASSES],
            "Rendement annuel retenu": [format_pct(rp.ASSET_CLASS_RETURNS[c]) for c in rp.ASSET_CLASSES],
            "Volatilité retenue": [format_pct(rp.ASSET_CLASS_VOLATILITIES[c]) for c in rp.ASSET_CLASSES],
        }
    )
    st.dataframe(allocation_table, hide_index=True)
    st.write(
        f"Avec ces hypothèses, l'allocation a un rendement attendu de **{format_pct(expected_return)}** par an "
        f"pour une volatilité de **{format_pct(volatility)}**."
    )

    if st.button("Utiliser ces hypothèses dans la projection de cash-flows", key="btn_transfer"):
        st.session_state["pending_transfer"] = {
            "profile": result.profile,
            "expected_return": expected_return,
            "volatility": volatility,
        }
        st.success(
            "Hypothèses transmises : le rendement et la volatilité de l'allocation seront appliqués à "
            "l'assurance-vie, au PEA et au compte-titres dans le module de projection."
        )
        st.page_link("pages/1_Projection_cash_flows.py", label="Ouvrir la projection de cash-flows")
    st.caption(
        "L'allocation est raisonnée globalement, sans chercher à répartir les classes d'actifs entre les enveloppes."
    )

with st.expander("Méthode de calcul"):
    weights = ", ".join(f"{rp.AXES[axis].lower()} {format_pct(w, 0)}" for axis, w in rp.AXIS_WEIGHTS.items())
    st.markdown(
        f"""
- Chaque réponse vaut de 0 à 3 points. Le score d'un axe est la somme de ses points ramenée sur 100.
- Le score global est la moyenne pondérée des axes : {weights}.
- Profil : prudent en dessous de {rp.PROFILE_THRESHOLDS[0]}, équilibré jusqu'à {rp.PROFILE_THRESHOLDS[1]},
  dynamique jusqu'à {rp.PROFILE_THRESHOLDS[2]}, offensif au-delà.
- Règle de cohérence : si le score de situation financière (capacité à subir des pertes) est inférieur à
  {rp.CAPACITY_CAP_PRUDENT}, le profil est plafonné à prudent ; s'il est inférieur à {rp.CAPACITY_CAP_BALANCED},
  il est plafonné à équilibré. Un horizon inférieur à 2 ans plafonne aussi le profil à prudent.
- La correspondance entre profil et indicateur de risque (SRI) est une convention propre à cet outil.
"""
    )
