"""Génération des jeux de données synthétiques du module « actifs corporels ».

Les prix ne viennent d'aucune source de marché : ils sont construits à partir de
règles simples (prix de base, coefficients d'état, d'âge, de kilométrage...) puis
bruités. La graine est fixe pour que les résultats soient reproductibles.

Lancé directement, le script écrit les trois jeux de données en CSV dans data/ :
    python data/generate_data.py
"""

from pathlib import Path

import numpy as np
import pandas as pd

SEED = 42
REFERENCE_YEAR = 2025

# Prix de base au m² par ville (ordres de grandeur).
CITIES = {
    "Paris": 9600,
    "Nice": 5100,
    "Lyon": 4900,
    "Bordeaux": 4600,
    "Rennes": 4000,
    "Nantes": 3800,
    "Toulouse": 3700,
    "Strasbourg": 3700,
    "Marseille": 3700,
    "Lille": 3600,
}
CITY_WEIGHTS = [0.22, 0.07, 0.12, 0.09, 0.07, 0.09, 0.10, 0.07, 0.10, 0.07]
REAL_ESTATE_CONDITIONS = {"À rénover": 0.82, "Correct": 0.94, "Bon": 1.00, "Refait à neuf": 1.10}

# référence : (marque, prix de base, première année, modèle « icône »)
WATCHES = {
    "Submariner": ("Rolex", 11_000, 1960, True),
    "Daytona": ("Rolex", 26_000, 1963, True),
    "Datejust": ("Rolex", 7_000, 1960, False),
    "GMT-Master II": ("Rolex", 14_000, 1982, True),
    "Speedmaster": ("Omega", 5_500, 1960, True),
    "Seamaster": ("Omega", 4_200, 1960, False),
    "Nautilus": ("Patek Philippe", 85_000, 1976, True),
    "Calatrava": ("Patek Philippe", 22_000, 1960, False),
    "Royal Oak": ("Audemars Piguet", 42_000, 1972, True),
    "Tank": ("Cartier", 5_000, 1960, False),
    "Santos": ("Cartier", 6_500, 1978, False),
    "Reverso": ("Jaeger-LeCoultre", 7_500, 1960, False),
}
WATCH_CONDITIONS = {"Usé": 0.70, "Bon": 0.85, "Très bon": 1.00, "Neuf ou comme neuf": 1.12}

# modèle : (marque, prix de base, début de production, fin de production)
CARS = {
    "911": ("Porsche", 85_000, 1965, 1989),
    "944": ("Porsche", 18_000, 1982, 1991),
    "308": ("Ferrari", 95_000, 1975, 1985),
    "280 SL": ("Mercedes-Benz", 110_000, 1963, 1971),
    "Type E": ("Jaguar", 95_000, 1961, 1974),
    "A110": ("Alpine", 90_000, 1963, 1977),
    "DS": ("Citroën", 30_000, 1955, 1975),
    "2CV": ("Citroën", 11_000, 1955, 1990),
    "205 GTI": ("Peugeot", 22_000, 1984, 1994),
    "504 Cabriolet": ("Peugeot", 35_000, 1969, 1983),
    "M3 E30": ("BMW", 75_000, 1986, 1991),
    "Spider": ("Alfa Romeo", 22_000, 1966, 1993),
    "Coccinelle": ("Volkswagen", 14_000, 1950, 1978),
}
CAR_CONDITIONS = {"À restaurer": 0.50, "Bon": 0.85, "Très bon": 1.10, "Concours": 1.40}


def generate_real_estate(n=2500, seed=SEED):
    rng = np.random.default_rng(seed)
    city = rng.choice(list(CITIES), n, p=CITY_WEIGHTS)
    surface = np.clip(rng.lognormal(np.log(55), 0.5, n), 12, 220).round()
    year_built = rng.integers(1870, REFERENCE_YEAR, n)
    condition = rng.choice(list(REAL_ESTATE_CONDITIONS), n, p=[0.15, 0.30, 0.35, 0.20])
    # Un logement récent n'est pas « à rénover ».
    condition = np.where((year_built >= 2010) & (condition == "À rénover"), "Bon", condition)

    base = pd.Series(city).map(CITIES).to_numpy()
    condition_factor = pd.Series(condition).map(REAL_ESTATE_CONDITIONS).to_numpy()
    # Effet de l'époque de construction : prime pour l'ancien de caractère et le neuf,
    # décote pour les immeubles des années 1950-1980.
    era_factor = np.select(
        [year_built < 1915, year_built < 1948, year_built < 1981, year_built < 2006],
        [1.05, 1.00, 0.92, 0.98],
        default=1.07,
    )
    # Les petites surfaces se vendent plus cher au m².
    size_factor = (surface / 60) ** -0.12
    price_m2 = base * condition_factor * era_factor * size_factor
    # Deux interactions : l'ancien est davantage valorisé à Paris, et un bien ancien
    # à rénover subit une décote supplémentaire (travaux plus lourds).
    price_m2 *= np.where((city == "Paris") & (year_built < 1915), 1.06, 1.0)
    price_m2 *= np.where((condition == "À rénover") & (year_built < 1948), 0.95, 1.0)

    price = price_m2 * surface * rng.lognormal(0, 0.10, n)
    return pd.DataFrame(
        {
            "city": city,
            "surface": surface.astype(int),
            "year_built": year_built,
            "condition": condition,
            "price": (price / 100).round() * 100,
        }
    )


def generate_watches(n=2000, seed=SEED):
    rng = np.random.default_rng(seed + 1)
    reference = rng.choice(list(WATCHES), n)
    specs = pd.DataFrame([WATCHES[r] for r in reference], columns=["brand", "base", "first_year", "iconic"])
    first_year = specs["first_year"].to_numpy()
    iconic = specs["iconic"].to_numpy()

    # Plus de montres récentes que de montres anciennes sur le marché.
    year = REFERENCE_YEAR - 1 - (rng.beta(1.2, 2.0, n) * (REFERENCE_YEAR - 1 - first_year)).astype(int)
    age = REFERENCE_YEAR - year

    condition = rng.choice(list(WATCH_CONDITIONS), n, p=[0.12, 0.33, 0.37, 0.18])
    condition = np.where((age > 30) & (condition == "Neuf ou comme neuf"), "Très bon", condition)
    # Les papiers et la boîte se perdent avec le temps, et vont souvent ensemble.
    papers = rng.random(n) < np.clip(0.85 - 0.012 * age, 0.15, 0.90)
    box = rng.random(n) < np.where(papers, 0.90, 0.40)

    condition_factor = pd.Series(condition).map(WATCH_CONDITIONS).to_numpy()
    # Décote pendant les vingt premières années, puis prime de collection au-delà
    # de 25 ans, plus forte pour les modèles icônes.
    age_factor = 1 - 0.012 * np.minimum(age, 20) + np.maximum(age - 25, 0) * np.where(iconic, 0.022, 0.012)
    # Un « full set » (boîte et papiers) vaut plus que la somme des deux.
    set_factor = 1 + 0.05 * box + 0.09 * papers + 0.04 * (box & papers)

    price = specs["base"].to_numpy() * condition_factor * age_factor * set_factor * rng.lognormal(0, 0.14, n)
    return pd.DataFrame(
        {
            "brand": specs["brand"],
            "reference": reference,
            "year": year,
            "condition": condition,
            "box": box.astype(int),
            "papers": papers.astype(int),
            "price": (price / 10).round() * 10,
        }
    )


def generate_cars(n=2000, seed=SEED):
    rng = np.random.default_rng(seed + 2)
    model = rng.choice(list(CARS), n)
    specs = pd.DataFrame([CARS[m] for m in model], columns=["brand", "base", "start", "end"])
    start, end = specs["start"].to_numpy(), specs["end"].to_numpy()

    year = rng.integers(start, end + 1)
    mileage = np.clip(rng.lognormal(np.log(95_000), 0.55, n), 4_000, 320_000)
    mileage = (mileage / 1000).round() * 1000
    condition = rng.choice(list(CAR_CONDITIONS), n, p=[0.12, 0.40, 0.36, 0.12])

    condition_factor = pd.Series(condition).map(CAR_CONDITIONS).to_numpy()
    mileage_factor = np.exp(-0.22 * mileage / 100_000)
    # Les premiers millésimes d'un modèle sont les plus recherchés.
    year_factor = 1 + 0.012 * (end - year)
    # Un faible kilométrage ne se paie vraiment que sur une voiture en très bel état.
    low_mileage_premium = np.where((mileage < 50_000) & np.isin(condition, ["Très bon", "Concours"]), 1.08, 1.0)

    price = (
        specs["base"].to_numpy()
        * condition_factor
        * mileage_factor
        * year_factor
        * low_mileage_premium
        * rng.lognormal(0, 0.17, n)
    )
    return pd.DataFrame(
        {
            "brand": specs["brand"],
            "model": model,
            "year": year,
            "mileage": mileage.astype(int),
            "condition": condition,
            "price": (price / 100).round() * 100,
        }
    )


if __name__ == "__main__":
    folder = Path(__file__).parent
    datasets = {
        "immobilier.csv": generate_real_estate(),
        "montres.csv": generate_watches(),
        "voitures.csv": generate_cars(),
    }
    for filename, df in datasets.items():
        df.to_csv(folder / filename, index=False)
        print(f"{filename} : {len(df)} lignes")
