"""Questionnaire de profil de risque inspiré de la logique MiFID II.

Chaque réponse rapporte de 0 à 3 points. Le score d'un axe est la somme de ses
points ramenée sur 100. Le score global est la moyenne des quatre axes pondérée
par AXIS_WEIGHTS, puis il est converti en profil par PROFILE_THRESHOLDS.
"""

from dataclasses import dataclass

import numpy as np

AXES = {
    "knowledge": "Connaissances et expérience",
    "financial": "Situation financière",
    "horizon": "Horizon et objectifs",
    "tolerance": "Tolérance aux pertes",
}

# La tolérance pèse le plus lourd car elle mesure directement le rapport au risque.
# Les connaissances pèsent le moins : bien connaître les marchés ne dit pas
# qu'on peut ou qu'on veut prendre du risque.
AXIS_WEIGHTS = {"knowledge": 0.20, "financial": 0.25, "horizon": 0.25, "tolerance": 0.30}

PROFILES = ["Prudent", "Équilibré", "Dynamique", "Offensif"]
# Score global < 35 : prudent ; < 55 : équilibré ; < 75 : dynamique ; sinon offensif.
PROFILE_THRESHOLDS = [35, 55, 75]

# Plafonnement par la capacité à subir des pertes (score de l'axe « situation financière »).
CAPACITY_CAP_PRUDENT = 30
CAPACITY_CAP_BALANCED = 50

# Indicateur de risque (SRI, de 1 à 7) maximal des supports compatibles avec chaque profil.
SRI_MAX = {"Prudent": 2, "Équilibré": 3, "Dynamique": 5, "Offensif": 7}

ASSET_CLASSES = ["Monétaire", "Obligations", "Actions", "Immobilier"]
ALLOCATIONS = {
    "Prudent": {"Monétaire": 0.30, "Obligations": 0.45, "Actions": 0.15, "Immobilier": 0.10},
    "Équilibré": {"Monétaire": 0.15, "Obligations": 0.35, "Actions": 0.35, "Immobilier": 0.15},
    "Dynamique": {"Monétaire": 0.05, "Obligations": 0.20, "Actions": 0.60, "Immobilier": 0.15},
    "Offensif": {"Monétaire": 0.00, "Obligations": 0.10, "Actions": 0.80, "Immobilier": 0.10},
}

# Hypothèses de long terme par classe d'actifs (rendement annuel, volatilité).
ASSET_CLASS_RETURNS = {"Monétaire": 0.020, "Obligations": 0.030, "Actions": 0.065, "Immobilier": 0.045}
ASSET_CLASS_VOLATILITIES = {"Monétaire": 0.005, "Obligations": 0.05, "Actions": 0.16, "Immobilier": 0.09}
ASSET_CLASS_CORRELATIONS = np.array(
    [
        [1.0, 0.1, 0.0, 0.0],
        [0.1, 1.0, 0.2, 0.2],
        [0.0, 0.2, 1.0, 0.5],
        [0.0, 0.2, 0.5, 1.0],
    ]
)

# (identifiant, axe, intitulé, [(réponse, points), ...])
QUESTIONS = [
    (
        "products",
        "knowledge",
        "Quels produits financiers connaissez-vous suffisamment pour en expliquer le fonctionnement ?",
        [
            ("Aucun en particulier", 0),
            ("Les livrets et les fonds en euros", 1),
            ("Les actions, les obligations et les fonds (OPCVM, ETF)", 2),
            ("Également les produits structurés ou les produits dérivés", 3),
        ],
    ),
    (
        "experience",
        "knowledge",
        "Depuis combien de temps investissez-vous sur les marchés financiers ?",
        [
            ("Je n'ai jamais investi", 0),
            ("Moins de 2 ans", 1),
            ("Entre 2 et 5 ans", 2),
            ("Plus de 5 ans", 3),
        ],
    ),
    (
        "bond_rates",
        "knowledge",
        "Lorsque les taux d'intérêt montent, le prix d'une obligation à taux fixe déjà émise :",
        [
            ("Je ne sais pas", 0),
            ("Monte", 0),
            ("Ne change pas", 0),
            ("Baisse", 3),
        ],
    ),
    (
        "income_stability",
        "financial",
        "Comment décririez-vous vos revenus ?",
        [
            ("Irréguliers ou incertains", 0),
            ("Stables, mais ils couvrent tout juste mes dépenses", 1),
            ("Stables, avec une capacité d'épargne régulière", 2),
            ("Élevés et issus de plusieurs sources", 3),
        ],
    ),
    (
        "emergency_fund",
        "financial",
        "Votre épargne de précaution, disponible immédiatement, représente :",
        [
            ("Moins de 3 mois de dépenses", 0),
            ("Entre 3 et 6 mois", 1),
            ("Entre 6 et 12 mois", 2),
            ("Plus de 12 mois", 3),
        ],
    ),
    (
        "wealth_share",
        "financial",
        "Quelle part de votre patrimoine financier ce placement représente-t-il ?",
        [
            ("Plus de 75 %", 0),
            ("Entre 50 et 75 %", 1),
            ("Entre 25 et 50 %", 2),
            ("Moins de 25 %", 3),
        ],
    ),
    (
        "duration",
        "horizon",
        "Pendant combien de temps comptez-vous laisser cet argent investi ?",
        [
            ("Moins de 2 ans", 0),
            ("Entre 2 et 5 ans", 1),
            ("Entre 5 et 10 ans", 2),
            ("Plus de 10 ans", 3),
        ],
    ),
    (
        "objective",
        "horizon",
        "Quel est votre objectif principal ?",
        [
            ("Préserver mon capital", 0),
            ("Obtenir des revenus complémentaires réguliers", 1),
            ("Faire croître mon capital sur le long terme", 2),
            ("Rechercher la performance la plus élevée possible", 3),
        ],
    ),
    (
        "liquidity_need",
        "horizon",
        "Pourriez-vous avoir besoin d'une part importante de cette somme dans les trois ans ?",
        [
            ("Oui, c'est très probable", 0),
            ("C'est possible", 1),
            ("C'est peu probable", 2),
            ("Non, c'est exclu", 3),
        ],
    ),
    (
        "drawdown_reaction",
        "tolerance",
        "Votre portefeuille perd 20 % en six mois. Que faites-vous ?",
        [
            ("Je vends tout pour ne pas perdre davantage", 0),
            ("Je vends une partie pour limiter le risque", 1),
            ("Je ne change rien et j'attends", 2),
            ("J'en profite pour investir davantage", 3),
        ],
    ),
    (
        "risk_return",
        "tolerance",
        "Sur un an, quel placement choisiriez-vous ?",
        [
            ("Gain possible de 3 %, aucune perte possible", 0),
            ("Gain possible de 8 %, perte possible de 5 %", 1),
            ("Gain possible de 15 %, perte possible de 12 %", 2),
            ("Gain possible de 30 %, perte possible de 25 %", 3),
        ],
    ),
    (
        "max_loss",
        "tolerance",
        "Quelle baisse de votre placement sur un an pourriez-vous accepter sans remettre en cause votre stratégie ?",
        [
            ("Aucune", 0),
            ("Jusqu'à 5 %", 1),
            ("Jusqu'à 15 %", 2),
            ("Plus de 25 %", 3),
        ],
    ),
]


@dataclass
class RiskResult:
    axis_scores: dict
    global_score: float
    uncapped_profile: str
    profile: str
    warnings: list
    sri_max: int
    allocation: dict

    @property
    def capped(self):
        return self.profile != self.uncapped_profile


def axis_scores(answers):
    """Score sur 100 de chaque axe à partir de `answers` (identifiant de question -> indice de réponse)."""
    points = dict.fromkeys(AXES, 0)
    maximum = dict.fromkeys(AXES, 0)
    for question_id, axis, _, options in QUESTIONS:
        points[axis] += options[answers[question_id]][1]
        maximum[axis] += max(p for _, p in options)
    return {axis: 100 * points[axis] / maximum[axis] for axis in AXES}


def global_score(scores):
    return sum(AXIS_WEIGHTS[axis] * scores[axis] for axis in AXES)


def profile_index(score):
    return sum(score >= threshold for threshold in PROFILE_THRESHOLDS)


def profile_cap(scores, answers):
    """Indice du profil maximal autorisé et motifs de plafonnement.

    La capacité à subir des pertes est une donnée objective (revenus, épargne de
    précaution, poids du placement dans le patrimoine) : elle prime sur
    l'appétence au risque déclarée. Même logique pour un horizon très court.
    """
    cap = len(PROFILES) - 1
    reasons = []
    if scores["financial"] < CAPACITY_CAP_PRUDENT:
        cap = 0
        reasons.append("votre capacité financière à subir des pertes est faible")
    elif scores["financial"] < CAPACITY_CAP_BALANCED:
        cap = 1
        reasons.append("votre capacité financière à subir des pertes est limitée")
    if answers["duration"] == 0:
        cap = 0
        reasons.append("votre horizon de placement est inférieur à 2 ans")
    return cap, reasons


def evaluate(answers):
    scores = axis_scores(answers)
    score = global_score(scores)
    uncapped = profile_index(score)
    cap, reasons = profile_cap(scores, answers)
    final = min(uncapped, cap)

    warnings = []
    if final < uncapped:
        warnings.append(
            f"Vos réponses correspondent à un profil « {PROFILES[uncapped]} », mais "
            f"{' et '.join(reasons)} : le profil retenu est plafonné à « {PROFILES[final]} »."
        )
    profile = PROFILES[final]
    return RiskResult(
        axis_scores=scores,
        global_score=score,
        uncapped_profile=PROFILES[uncapped],
        profile=profile,
        warnings=warnings,
        sri_max=SRI_MAX[profile],
        allocation=dict(ALLOCATIONS[profile]),
    )


def allocation_assumptions(allocation):
    """Rendement attendu et volatilité annuels d'une allocation entre classes d'actifs."""
    weights = np.array([allocation[c] for c in ASSET_CLASSES])
    returns = np.array([ASSET_CLASS_RETURNS[c] for c in ASSET_CLASSES])
    vols = np.array([ASSET_CLASS_VOLATILITIES[c] for c in ASSET_CLASSES])
    cov = ASSET_CLASS_CORRELATIONS * np.outer(vols, vols)
    return float(weights @ returns), float(np.sqrt(weights @ cov @ weights))
