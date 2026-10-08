"""Projection annuelle de cash-flows et simulation Monte Carlo."""

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

ENVELOPES = ["livret_a", "assurance_vie", "pea", "compte_titres"]
ENVELOPE_LABELS = {
    "livret_a": "Livret A",
    "assurance_vie": "Assurance-vie",
    "pea": "PEA",
    "compte_titres": "Compte-titres",
}

# Fiscalité simplifiée, taux en vigueur en 2026.
PFU_RATE = 0.314  # 12,8 % d'impôt + 18,6 % de prélèvements sociaux
PEA_RATE_AFTER_5Y = 0.186  # prélèvements sociaux seuls après 5 ans
AV_RATE_BEFORE_8Y = 0.30  # 12,8 % + 17,2 % : l'assurance-vie est restée à 17,2 %
AV_RATE_AFTER_8Y = 0.247  # 7,5 % + 17,2 %
AV_ALLOWANCE = 4_600  # abattement annuel sur les gains après 8 ans, personne seule
LIVRET_A_CAP = 22_950
PEA_CAP = 150_000

# En cas de besoin, on puise d'abord dans l'épargne liquide et non fiscalisée,
# et en dernier dans le PEA (un retrait avant 5 ans entraîne sa clôture).
WITHDRAWAL_ORDER = ["livret_a", "compte_titres", "assurance_vie", "pea"]

DEFAULT_RETURNS = {"livret_a": 0.017, "assurance_vie": 0.030, "pea": 0.065, "compte_titres": 0.065}
DEFAULT_VOLATILITIES = {"livret_a": 0.0, "assurance_vie": 0.04, "pea": 0.16, "compte_titres": 0.16}
DEFAULT_SPLIT = {"livret_a": 0.10, "assurance_vie": 0.40, "pea": 0.40, "compte_titres": 0.10}

# Corrélations entre enveloppes pour le Monte Carlo (ordre de ENVELOPES).
# PEA et compte-titres portent tous deux des actions, d'où 0,9 entre eux.
CORRELATIONS = np.array(
    [
        [1.0, 0.0, 0.0, 0.0],
        [0.0, 1.0, 0.6, 0.6],
        [0.0, 0.6, 1.0, 0.9],
        [0.0, 0.6, 0.9, 1.0],
    ]
)


def monthly_payment(principal, annual_rate, years):
    """Mensualité constante d'un prêt amortissable, hors assurance."""
    n = int(years * 12)
    if principal <= 0 or n <= 0:
        return 0.0
    i = annual_rate / 12
    if i == 0:
        return principal / n
    return principal * i / (1 - (1 + i) ** -n)


def remaining_balance(principal, annual_rate, years, months_paid):
    """Capital restant dû après `months_paid` mensualités."""
    n = int(years * 12)
    k = min(max(months_paid, 0), n)
    if principal <= 0 or n <= 0:
        return 0.0
    i = annual_rate / 12
    if i == 0:
        return principal * (1 - k / n)
    growth = (1 + i) ** k
    payment = monthly_payment(principal, annual_rate, years)
    return max(0.0, principal * growth - payment * (growth - 1) / i)


def to_constant_euros(df, inflation):
    """Convertit toutes les colonnes monétaires en euros d'aujourd'hui."""
    out = df.copy()
    money_columns = [c for c in df.columns if c not in ("year", "age")]
    deflator = (1 + inflation) ** df["year"]
    out[money_columns] = df[money_columns].div(deflator, axis=0)
    return out


@dataclass
class RealEstatePurchase:
    year: int
    down_payment: float
    loan_amount: float
    loan_rate: float
    loan_years: int
    fees_rate: float = 0.075
    appreciation: float = 0.015
    rent_saved: float = 0.0  # loyer annuel qui disparaît, en euros d'aujourd'hui

    @property
    def price(self):
        # L'apport et le prêt financent le bien et les frais d'acquisition.
        return (self.down_payment + self.loan_amount) / (1 + self.fees_rate)

    @property
    def monthly_payment(self):
        return monthly_payment(self.loan_amount, self.loan_rate, self.loan_years)


@dataclass
class OneOffFlow:
    year: int
    amount: float  # positif pour un encaissement (héritage), négatif pour une dépense
    label: str = ""


@dataclass
class Params:
    age: int = 30
    net_income: float = 42_000
    expenses: float = 30_000
    retirement_age: int = 64
    pension: float = 24_000
    horizon: int = 35
    inflation: float = 0.02
    initial_savings: dict = field(default_factory=lambda: dict.fromkeys(ENVELOPES, 0.0))
    expected_returns: dict = field(default_factory=lambda: dict(DEFAULT_RETURNS))
    volatilities: dict = field(default_factory=lambda: dict(DEFAULT_VOLATILITIES))
    savings_split: dict = field(default_factory=lambda: dict(DEFAULT_SPLIT))
    av_seniority: int = 0
    pea_seniority: int = 0


def _normalized_split(split):
    total = sum(max(split.get(env, 0.0), 0.0) for env in ENVELOPES)
    if total <= 0:
        return {env: float(env == "livret_a") for env in ENVELOPES}
    return {env: max(split.get(env, 0.0), 0.0) / total for env in ENVELOPES}


def _withdrawal_tax(env, params, t):
    """Taux appliqué à la part de gains d'un retrait, et abattement annuel sur ces gains."""
    if env == "assurance_vie":
        if params.av_seniority + t >= 8:
            return AV_RATE_AFTER_8Y, AV_ALLOWANCE
        return AV_RATE_BEFORE_8Y, 0.0
    if env == "pea":
        if params.pea_seniority + t >= 5:
            return PEA_RATE_AFTER_5Y, 0.0
        return PFU_RATE, 0.0
    # Livret A exonéré ; compte-titres déjà imposé chaque année sur ses gains.
    return 0.0, 0.0


def _invest(balances, basis, amount, split):
    overflow = 0.0
    for env in ENVELOPES:
        deposit = amount * split[env]
        if env == "livret_a":
            room = max(0.0, LIVRET_A_CAP - balances[env])
        elif env == "pea":
            # Le plafond du PEA porte sur les versements, pas sur la valeur du plan.
            room = max(0.0, PEA_CAP - basis[env])
        else:
            room = deposit
        accepted = min(deposit, room)
        balances[env] += accepted
        basis[env] += accepted
        overflow += deposit - accepted
    balances["compte_titres"] += overflow
    basis["compte_titres"] += overflow


def _withdraw(balances, basis, need, params, t):
    """Prélève `need` euros nets d'impôt. Retourne (impôt payé, besoin non couvert)."""
    tax_paid = 0.0
    for env in WITHDRAWAL_ORDER:
        if need < 0.01:
            break
        balance = balances[env]
        if balance <= 0:
            continue
        rate, allowance = _withdrawal_tax(env, params, t)
        # Seule la part de gains du retrait est imposable, au prorata de la plus-value latente.
        gain_share = max(0.0, 1 - basis[env] / balance)
        if gain_share * need <= allowance:
            gross = need
        else:
            # Retrait brut W tel que W - rate * (gain_share * W - allowance) = need.
            gross = (need - rate * allowance) / (1 - rate * gain_share)
        gross = min(gross, balance)
        tax = rate * max(0.0, gain_share * gross - allowance)
        basis[env] -= basis[env] * gross / balance
        balances[env] -= gross
        tax_paid += tax
        need -= gross - tax
    # En dessous du centime, l'écart n'est qu'un résidu d'arrondi.
    return tax_paid, need if need >= 0.01 else 0.0


def _simulate(params, events, returns):
    """Déroule la projection année par année.

    `returns[t - 1][j]` est le rendement de l'enveloppe j pendant l'année t.
    Convention : les encours du début d'année sont rémunérés, puis les flux de
    l'année sont investis ou prélevés en fin d'année.
    """
    balances = {env: float(params.initial_savings.get(env, 0.0)) for env in ENVELOPES}
    # Versements nets par enveloppe : on suppose qu'il n'y a pas de plus-value latente au départ.
    basis = dict(balances)
    split = _normalized_split(params.savings_split)
    purchases = [e for e in events if isinstance(e, RealEstatePurchase)]
    flows = [e for e in events if isinstance(e, OneOffFlow)]

    financial = sum(balances.values())
    rows = [
        {
            "year": 0,
            "age": params.age,
            "income": 0.0,
            "expenses": 0.0,
            "loan_payments": 0.0,
            "one_off": 0.0,
            "net_cashflow": 0.0,
            "taxes": 0.0,
            **balances,
            "property_value": 0.0,
            "debt": 0.0,
            "financial_wealth": financial,
            "net_wealth": financial,
            "unfunded": 0.0,
        }
    ]

    for t in range(1, params.horizon + 1):
        index = (1 + params.inflation) ** t
        taxes = 0.0

        for j, env in enumerate(ENVELOPES):
            gain = balances[env] * returns[t - 1][j]
            if env == "compte_titres" and gain > 0:
                # Simplification : les gains du compte-titres sont imposés au PFU chaque année,
                # comme s'ils étaient intégralement réalisés ou distribués.
                taxes += gain * PFU_RATE
                gain *= 1 - PFU_RATE
            balances[env] += gain
        basis["compte_titres"] = balances["compte_titres"]

        working = params.age + t <= params.retirement_age
        income = (params.net_income if working else params.pension) * index
        expenses = params.expenses * index

        loan_payments = property_value = debt = one_off = 0.0
        for purchase in purchases:
            elapsed = t - purchase.year
            if elapsed < 0:
                continue
            if elapsed == 0:
                one_off -= purchase.down_payment
            if elapsed < purchase.loan_years:
                loan_payments += 12 * purchase.monthly_payment
            expenses -= purchase.rent_saved * index
            property_value += purchase.price * (1 + purchase.appreciation) ** elapsed
            debt += remaining_balance(
                purchase.loan_amount, purchase.loan_rate, purchase.loan_years, 12 * (elapsed + 1)
            )
        expenses = max(expenses, 0.0)
        one_off += sum(flow.amount for flow in flows if flow.year == t)

        net_cashflow = income - expenses - loan_payments + one_off
        unfunded = 0.0
        if net_cashflow >= 0:
            _invest(balances, basis, net_cashflow, split)
        else:
            withdrawal_tax, unfunded = _withdraw(balances, basis, -net_cashflow, params, t)
            taxes += withdrawal_tax

        financial = sum(balances.values())
        rows.append(
            {
                "year": t,
                "age": params.age + t,
                "income": income,
                "expenses": expenses,
                "loan_payments": loan_payments,
                "one_off": one_off,
                "net_cashflow": net_cashflow,
                "taxes": taxes,
                **balances,
                "property_value": property_value,
                "debt": debt,
                "financial_wealth": financial,
                "net_wealth": financial + property_value - debt,
                "unfunded": unfunded,
            }
        )
    return rows


def project(params, events=()):
    """Projection déterministe en euros courants, une ligne par année (année 0 = situation initiale)."""
    returns = [[params.expected_returns[env] for env in ENVELOPES]] * params.horizon
    return pd.DataFrame(_simulate(params, events, returns))


def monte_carlo(params, events=(), n_sims=1000, seed=42):
    """Simule `n_sims` trajectoires de patrimoine net avec des rendements annuels aléatoires.

    Retourne le tableau des quantiles par année (euros courants) et la part des
    trajectoires dans lesquelles l'épargne financière ne suffit pas au moins une année.
    """
    rng = np.random.default_rng(seed)
    mean = np.array([params.expected_returns[env] for env in ENVELOPES])
    vol = np.array([params.volatilities[env] for env in ENVELOPES])
    cov = CORRELATIONS * np.outer(vol, vol)
    draws = rng.multivariate_normal(mean, cov, size=(n_sims, params.horizon))
    # Une loi normale peut théoriquement donner moins de -100 %.
    draws = np.maximum(draws, -1.0)

    wealth = np.empty((n_sims, params.horizon + 1))
    shortfall = np.zeros(n_sims, dtype=bool)
    for s in range(n_sims):
        rows = _simulate(params, events, draws[s].tolist())
        wealth[s] = [row["net_wealth"] for row in rows]
        shortfall[s] = any(row["unfunded"] > 0 for row in rows)

    p10, median, p90 = np.percentile(wealth, [10, 50, 90], axis=0)
    years = np.arange(params.horizon + 1)
    quantiles = pd.DataFrame(
        {"year": years, "age": params.age + years, "p10": p10, "median": median, "p90": p90}
    )
    return quantiles, float(shortfall.mean())
