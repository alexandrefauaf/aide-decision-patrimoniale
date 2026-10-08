import pytest

from src import cashflow as cf


def make_params(**overrides):
    values = {
        "age": 30,
        "net_income": 40_000,
        "expenses": 30_000,
        "retirement_age": 64,
        "pension": 20_000,
        "horizon": 10,
        "inflation": 0.02,
        "initial_savings": {"livret_a": 5_000, "assurance_vie": 0, "pea": 0, "compte_titres": 0},
        "expected_returns": dict.fromkeys(cf.ENVELOPES, 0.0),
        "volatilities": dict.fromkeys(cf.ENVELOPES, 0.0),
        "savings_split": {"livret_a": 0, "assurance_vie": 1, "pea": 0, "compte_titres": 0},
    }
    values.update(overrides)
    return cf.Params(**values)


def test_monthly_payment_reference_value():
    # 200 000 € sur 20 ans à 3 % : 1 109,20 € par mois (valeur des simulateurs bancaires).
    assert cf.monthly_payment(200_000, 0.03, 20) == pytest.approx(1109.20, abs=0.01)


def test_monthly_payment_zero_rate():
    assert cf.monthly_payment(120_000, 0.0, 10) == pytest.approx(1_000)


def test_remaining_balance_boundaries():
    assert cf.remaining_balance(200_000, 0.03, 20, 0) == pytest.approx(200_000)
    assert cf.remaining_balance(200_000, 0.03, 20, 240) == pytest.approx(0, abs=0.01)
    # Au début d'un prêt, les mensualités remboursent surtout des intérêts.
    assert cf.remaining_balance(200_000, 0.03, 20, 120) > 100_000


def test_constant_euros_cancel_inflation():
    # Sans rendement, avec des flux indexés, l'épargne annuelle est constante en euros constants.
    params = make_params()
    real = cf.to_constant_euros(cf.project(params), params.inflation)
    assert real["net_cashflow"].iloc[1:].tolist() == pytest.approx([10_000] * 10)
    assert real["income"].iloc[-1] == pytest.approx(40_000)


def test_nominal_income_follows_inflation():
    projection = cf.project(make_params())
    assert projection["income"].iloc[10] == pytest.approx(40_000 * 1.02**10)


def test_pension_replaces_income_after_retirement():
    projection = cf.project(make_params(age=60, retirement_age=62, inflation=0.0, horizon=5))
    assert projection["income"].tolist() == pytest.approx([0, 40_000, 40_000, 20_000, 20_000, 20_000])


def test_livret_a_cap_redirects_to_securities_account():
    params = make_params(
        inflation=0.0,
        initial_savings={"livret_a": 20_000, "assurance_vie": 0, "pea": 0, "compte_titres": 0},
        savings_split={"livret_a": 1, "assurance_vie": 0, "pea": 0, "compte_titres": 0},
    )
    first_year = cf.project(params).iloc[1]
    assert first_year["livret_a"] == pytest.approx(cf.LIVRET_A_CAP)
    assert first_year["compte_titres"] == pytest.approx(20_000 + 10_000 - cf.LIVRET_A_CAP)


def test_securities_account_gains_are_taxed_each_year():
    params = make_params(
        net_income=0,
        expenses=0,
        inflation=0.0,
        horizon=1,
        initial_savings={"livret_a": 0, "assurance_vie": 0, "pea": 0, "compte_titres": 10_000},
        expected_returns={"livret_a": 0, "assurance_vie": 0, "pea": 0, "compte_titres": 0.10},
    )
    row = cf.project(params).iloc[1]
    assert row["taxes"] == pytest.approx(1_000 * cf.PFU_RATE)
    assert row["compte_titres"] == pytest.approx(10_000 + 1_000 * (1 - cf.PFU_RATE))


def test_life_insurance_withdrawal_tax_before_and_after_8_years():
    # Contrat de 10 000 € qui double : la moitié de chaque retrait est un gain.
    def withdraw_net(seniority, need):
        params = make_params(
            net_income=0,
            expenses=need,
            inflation=0.0,
            horizon=1,
            initial_savings={"livret_a": 0, "assurance_vie": 10_000, "pea": 0, "compte_titres": 0},
            expected_returns={"livret_a": 0, "assurance_vie": 1.0, "pea": 0, "compte_titres": 0},
            av_seniority=seniority,
        )
        row = cf.project(params).iloc[1]
        return row["taxes"], 20_000 - row["assurance_vie"]

    tax, gross = withdraw_net(seniority=0, need=5_000)
    assert tax == pytest.approx(cf.AV_RATE_BEFORE_8Y * 0.5 * gross)
    assert gross - tax == pytest.approx(5_000)

    # Après 8 ans, 5 000 € de retrait ne contiennent que 2 500 € de gains : sous l'abattement.
    tax, gross = withdraw_net(seniority=10, need=5_000)
    assert tax == pytest.approx(0)
    assert gross == pytest.approx(5_000)

    tax, gross = withdraw_net(seniority=10, need=12_000)
    assert tax == pytest.approx(cf.AV_RATE_AFTER_8Y * (0.5 * gross - cf.AV_ALLOWANCE))
    assert gross - tax == pytest.approx(12_000)


def test_real_estate_purchase_balance_sheet():
    purchase = cf.RealEstatePurchase(
        year=1, down_payment=30_000, loan_amount=170_000, loan_rate=0.03, loan_years=20, fees_rate=0.0,
        appreciation=0.0,
    )
    params = make_params(
        inflation=0.0, horizon=20,
        initial_savings={"livret_a": 0, "assurance_vie": 0, "pea": 0, "compte_titres": 50_000},
    )
    projection = cf.project(params, [purchase])
    first, last = projection.iloc[1], projection.iloc[-1]
    assert first["loan_payments"] == pytest.approx(12 * purchase.monthly_payment)
    assert first["property_value"] == pytest.approx(200_000)
    assert first["debt"] == pytest.approx(cf.remaining_balance(170_000, 0.03, 20, 12))
    assert last["debt"] == pytest.approx(0, abs=0.01)
    assert last["net_wealth"] == pytest.approx(last["financial_wealth"] + 200_000)


def test_one_off_flows():
    events = [cf.OneOffFlow(2, 50_000, "Héritage"), cf.OneOffFlow(3, -8_000, "Dépense exceptionnelle")]
    projection = cf.project(make_params(inflation=0.0), events)
    assert projection["net_cashflow"].iloc[1:4].tolist() == pytest.approx([10_000, 60_000, 2_000])


def test_unfunded_need_is_reported():
    params = make_params(net_income=0, expenses=10_000, inflation=0.0, horizon=2)
    projection = cf.project(params)
    assert projection["unfunded"].tolist() == pytest.approx([0, 5_000, 10_000])
    assert projection["financial_wealth"].iloc[-1] == pytest.approx(0)


def test_monte_carlo_without_volatility_matches_projection():
    params = make_params(expected_returns=dict.fromkeys(cf.ENVELOPES, 0.03))
    quantiles, shortfall = cf.monte_carlo(params, n_sims=20)
    expected = cf.project(params)["net_wealth"]
    for column in ("p10", "median", "p90"):
        assert quantiles[column].tolist() == pytest.approx(expected.tolist())
    assert shortfall == 0


def test_monte_carlo_quantiles_are_ordered_and_reproducible():
    params = make_params(
        expected_returns=dict(cf.DEFAULT_RETURNS), volatilities=dict(cf.DEFAULT_VOLATILITIES),
        savings_split=dict(cf.DEFAULT_SPLIT),
    )
    first, _ = cf.monte_carlo(params, n_sims=200, seed=1)
    second, _ = cf.monte_carlo(params, n_sims=200, seed=1)
    assert (first["p10"] <= first["median"]).all() and (first["median"] <= first["p90"]).all()
    assert first.equals(second)
