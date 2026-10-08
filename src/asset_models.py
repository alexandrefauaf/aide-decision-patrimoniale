"""Modèles d'estimation de la valeur d'actifs corporels, entraînés sur des données synthétiques."""

import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.compose import ColumnTransformer, TransformedTargetRegressor
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.model_selection import KFold, train_test_split
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import FunctionTransformer, OneHotEncoder, StandardScaler

from data.generate_data import generate_cars, generate_real_estate, generate_watches

SEED = 42
N_FOLDS = 5
LINEAR = "Régression linéaire"
BOOSTING = "Gradient boosting"

# `rates` : taux annuel d'évolution de la valeur (scénario bas, central, haut).
# Ce sont des hypothèses, elles ne sont pas estimées sur les données.
CATEGORIES = {
    "immobilier": {
        "label": "Immobilier résidentiel",
        "generator": generate_real_estate,
        "categorical": ["city", "condition"],
        "numeric": ["year_built"],
        "log_numeric": ["surface"],
        "rates": (0.0, 0.02, 0.035),
    },
    "montres": {
        "label": "Montres de collection",
        "generator": generate_watches,
        "categorical": ["brand", "reference", "condition"],
        "numeric": ["year", "box", "papers"],
        "log_numeric": [],
        "rates": (-0.02, 0.03, 0.07),
    },
    "voitures": {
        "label": "Voitures de collection",
        "generator": generate_cars,
        "categorical": ["brand", "model", "condition"],
        "numeric": ["year", "mileage"],
        "log_numeric": [],
        "rates": (-0.02, 0.025, 0.06),
    },
}

FEATURE_LABELS = {
    "city": "Ville",
    "surface": "Surface",
    "year_built": "Année de construction",
    "condition": "État",
    "brand": "Marque",
    "reference": "Référence",
    "model": "Modèle",
    "year": "Année",
    "box": "Boîte",
    "papers": "Papiers",
    "mileage": "Kilométrage",
    "price": "Prix",
}


def feature_names(category):
    cfg = CATEGORIES[category]
    return cfg["categorical"] + cfg["log_numeric"] + cfg["numeric"]


def _build_models(cfg):
    preprocessing = ColumnTransformer(
        [
            ("categorical", OneHotEncoder(handle_unknown="ignore"), cfg["categorical"]),
            ("log", make_pipeline(FunctionTransformer(np.log), StandardScaler()), cfg["log_numeric"]),
            ("numeric", StandardScaler(), cfg["numeric"]),
        ]
    )

    # Les deux modèles prédisent le logarithme du prix : les effets (état, ville,
    # kilométrage...) sont multiplicatifs, et l'erreur est ainsi relative plutôt
    # qu'absolue, ce qui évite que les biens les plus chers dominent l'apprentissage.
    def on_log_price(regressor):
        return TransformedTargetRegressor(
            regressor=make_pipeline(clone(preprocessing), regressor), func=np.log, inverse_func=np.exp
        )

    return {
        LINEAR: on_log_price(LinearRegression()),
        BOOSTING: on_log_price(
            GradientBoostingRegressor(
                n_estimators=300, learning_rate=0.08, max_depth=3, subsample=0.8, random_state=SEED
            )
        ),
    }


def train_category(category):
    """Entraîne et évalue les deux modèles d'une catégorie.

    Retourne un dictionnaire avec les données, les métriques de validation croisée,
    les importances par permutation, les prédictions hors échantillon et les
    modèles finaux réentraînés sur l'ensemble des données.
    """
    cfg = CATEGORIES[category]
    data = cfg["generator"]()
    features = feature_names(category)
    X, y = data[features], data["price"]

    folds = KFold(n_splits=N_FOLDS, shuffle=True, random_state=SEED)
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=SEED)

    metrics, importances, out_of_fold, intervals, fitted = [], [], {}, {}, {}
    for name, model in _build_models(cfg).items():
        predictions = np.zeros(len(y))
        mae, r2 = [], []
        for train_idx, test_idx in folds.split(X):
            fold_model = clone(model).fit(X.iloc[train_idx], y.iloc[train_idx])
            predictions[test_idx] = fold_model.predict(X.iloc[test_idx])
            mae.append(mean_absolute_error(y.iloc[test_idx], predictions[test_idx]))
            r2.append(r2_score(y.iloc[test_idx], predictions[test_idx]))

        relative_error = np.abs(predictions - y) / y
        metrics.append(
            {
                "model": name,
                "mae": np.mean(mae),
                "mae_std": np.std(mae),
                "r2": np.mean(r2),
                "r2_std": np.std(r2),
                "median_relative_error": float(np.median(relative_error)),
            }
        )
        out_of_fold[name] = predictions
        # Fourchette d'estimation : quantiles 10 % et 90 % du rapport prix réel / prix
        # prédit, mesurés sur les prédictions hors échantillon de la validation croisée.
        intervals[name] = tuple(np.quantile(y / predictions, [0.10, 0.90]))

        # Importance par permutation : baisse du R² sur un jeu de test quand on mélange
        # les valeurs d'une variable. Même méthode pour les deux modèles, donc comparable.
        holdout_model = clone(model).fit(X_train, y_train)
        permutation = permutation_importance(holdout_model, X_test, y_test, n_repeats=5, random_state=SEED)
        for feature, value in zip(features, permutation.importances_mean):
            importances.append({"model": name, "feature": feature, "importance": max(value, 0.0)})

        fitted[name] = clone(model).fit(X, y)

    metrics = pd.DataFrame(metrics)
    return {
        "category": category,
        "data": data,
        "features": features,
        "metrics": metrics,
        "importances": pd.DataFrame(importances),
        "out_of_fold": out_of_fold,
        "intervals": intervals,
        "models": fitted,
        "best": metrics.loc[metrics["mae"].idxmin(), "model"],
    }


def estimate(result, model_name, asset):
    """Valeur estimée d'un actif (dictionnaire variable -> valeur) et fourchette 10 % - 90 %."""
    X = pd.DataFrame([asset])[result["features"]]
    value = float(result["models"][model_name].predict(X)[0])
    low_ratio, high_ratio = result["intervals"][model_name]
    return value, value * low_ratio, value * high_ratio


def project_value(value, low, high, rates, years=10):
    """Projette la valeur et sa fourchette avec les taux annuels (bas, central, haut).

    La fourchette cumule l'incertitude du modèle (bornes de départ) et celle du
    taux d'évolution, elle s'élargit donc avec le temps.
    """
    low_rate, central_rate, high_rate = rates
    t = np.arange(years + 1)
    return pd.DataFrame(
        {
            "year": t,
            "low": low * (1 + low_rate) ** t,
            "central": value * (1 + central_rate) ** t,
            "high": high * (1 + high_rate) ** t,
        }
    )
