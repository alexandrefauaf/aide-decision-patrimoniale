import pytest

from src import risk_profile as rp

FINANCIAL_QUESTIONS = ["income_stability", "emergency_fund", "wealth_share"]


def answers_with(default, **overrides):
    answers = {question[0]: default for question in rp.QUESTIONS}
    answers.update(overrides)
    return answers


def test_questionnaire_structure():
    assert len(rp.QUESTIONS) == 12
    for axis in rp.AXES:
        assert sum(question[1] == axis for question in rp.QUESTIONS) == 3
    assert sum(rp.AXIS_WEIGHTS.values()) == pytest.approx(1)
    for allocation in rp.ALLOCATIONS.values():
        assert sum(allocation.values()) == pytest.approx(1)


def test_extreme_answers():
    lowest = rp.evaluate(answers_with(0))
    highest = rp.evaluate(answers_with(3))
    assert (lowest.profile, lowest.global_score) == ("Prudent", 0)
    assert (highest.profile, highest.global_score) == ("Offensif", 100)
    assert not highest.capped and highest.warnings == []


def test_weighted_score():
    # Seul l'axe « tolérance » est au maximum : le score global vaut son poids.
    answers = answers_with(0, drawdown_reaction=3, risk_return=3, max_loss=3)
    result = rp.evaluate(answers)
    assert result.axis_scores["tolerance"] == 100
    assert result.global_score == pytest.approx(100 * rp.AXIS_WEIGHTS["tolerance"])


def test_profile_thresholds():
    assert [rp.PROFILES[rp.profile_index(s)] for s in (0, 34.9, 35, 54.9, 55, 74.9, 75, 100)] == [
        "Prudent", "Prudent", "Équilibré", "Équilibré", "Dynamique", "Dynamique", "Offensif", "Offensif",
    ]


def test_low_loss_capacity_caps_profile_to_prudent():
    # Appétence maximale partout, mais aucune capacité financière à subir des pertes.
    answers = answers_with(3, **dict.fromkeys(FINANCIAL_QUESTIONS, 0))
    result = rp.evaluate(answers)
    assert result.uncapped_profile == "Offensif"
    assert result.profile == "Prudent"
    assert result.capped
    assert len(result.warnings) == 1 and "plafonné" in result.warnings[0]
    assert result.sri_max == rp.SRI_MAX["Prudent"]
    assert result.allocation == rp.ALLOCATIONS["Prudent"]


def test_limited_loss_capacity_caps_profile_to_balanced():
    # 4 points sur 9 sur l'axe financier : score de 44, sous le seuil de 50.
    answers = answers_with(3, income_stability=2, emergency_fund=1, wealth_share=1)
    result = rp.evaluate(answers)
    assert result.axis_scores["financial"] == pytest.approx(100 * 4 / 9)
    assert result.profile == "Équilibré"
    assert result.capped


def test_cap_does_not_raise_or_warn_when_not_binding():
    # Capacité limitée mais réponses prudentes par ailleurs : pas de plafonnement à signaler.
    result = rp.evaluate(answers_with(0, income_stability=1))
    assert result.profile == "Prudent"
    assert not result.capped and result.warnings == []


def test_short_horizon_caps_profile():
    result = rp.evaluate(answers_with(3, duration=0))
    assert result.uncapped_profile == "Offensif"
    assert result.profile == "Prudent"
    assert "horizon" in result.warnings[0]


def test_allocation_assumptions():
    expected_return, volatility = rp.allocation_assumptions(
        {"Monétaire": 0, "Obligations": 0, "Actions": 1, "Immobilier": 0}
    )
    assert expected_return == pytest.approx(rp.ASSET_CLASS_RETURNS["Actions"])
    assert volatility == pytest.approx(rp.ASSET_CLASS_VOLATILITIES["Actions"])

    # La diversification ramène la volatilité sous la moyenne pondérée des volatilités.
    allocation = rp.ALLOCATIONS["Équilibré"]
    _, volatility = rp.allocation_assumptions(allocation)
    weighted_average = sum(allocation[c] * rp.ASSET_CLASS_VOLATILITIES[c] for c in rp.ASSET_CLASSES)
    assert volatility < weighted_average
