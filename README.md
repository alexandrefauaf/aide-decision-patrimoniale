# Plateforme d'aide à la décision patrimoniale

Application Streamlit en trois modules : un simulateur de projection de cash-flows, un questionnaire de profil de risque investisseur et un module d'estimation de la valeur d'actifs corporels (immobilier, montres et voitures de collection).

C'est un projet personnel, réalisé en parallèle de mes études d'ingénieur à l'ESILV. Ce n'est pas un outil de conseil : les hypothèses sont simplifiées et les données du troisième module sont simulées.

## Pourquoi ce projet

Je m'intéresse à la gestion de patrimoine et je voulais comprendre concrètement ce qu'il y a derrière les outils qu'utilise un conseiller : comment on projette un patrimoine dans le temps, comment on passe d'un questionnaire à un profil de risque, et ce qu'un modèle statistique peut dire, ou ne pas dire, de la valeur d'un actif. Le plus simple pour comprendre était de les construire moi-même, en restant à une échelle que je peux expliquer ligne par ligne.

## Les trois modules

### 1. Projection de cash-flows

À partir de l'âge, des revenus, des charges, de l'épargne répartie entre livret A, assurance-vie, PEA et compte-titres, et de l'âge de départ à la retraite, le module projette le patrimoine année par année.
ù
- Événements ponctuels : achat immobilier financé à crédit (la mensualité est calculée), héritage, dépense exceptionnelle.
- Résultats en euros courants et en euros constants.
- Simulation Monte Carlo de 1 000 trajectoires, avec la médiane et les quantiles 10 % et 90 %.
- Graphiques du patrimoine net, de sa décomposition par enveloppe et du cash-flow annuel, et tableau exportable en CSV.

### 2. Profil de risque

Un questionnaire de douze questions, inspiré de la logique MiFID II, réparties sur quatre axes : connaissances et expérience, situation financière, horizon et objectifs, tolérance aux pertes.

- Chaque axe reçoit un score sur 100. Le score global est une moyenne pondérée qui donne un profil : prudent, équilibré, dynamique ou offensif.
- Une règle de cohérence plafonne le profil quand la capacité financière à subir des pertes est faible, même si l'appétence au risque déclarée est élevée. Un avertissement l'indique.
- Le résultat affiche un radar des quatre axes, le niveau d'indicateur de risque (SRI, de 1 à 7) compatible et une allocation indicative entre monétaire, obligations, actions et immobilier.
- Un bouton reporte le rendement et la volatilité de cette allocation dans le module de projection.

### 3. Valeur d'actifs corporels

Pour trois catégories (immobilier résidentiel, montres de collection, voitures de collection), le module compare une régression linéaire et un gradient boosting, puis estime la valeur d'un actif décrit par l'utilisateur et la projette sur dix ans.

**Les données sont simulées.** Je n'avais pas de source de prix fiable et libre pour les montres et les voitures, j'ai donc écrit un générateur (`data/generate_data.py`) : un prix de base par ville ou par modèle, des coefficients pour l'état, l'âge, le kilométrage, la présence de la boîte et des papiers, quelques interactions, puis un bruit aléatoire. La graine est fixe. Les estimations illustrent la méthode, elles ne disent rien du marché réel.

Résultats en validation croisée à 5 blocs :

| Catégorie | Modèle | MAE | R² |
|---|---|---|---|
| Immobilier | Régression linéaire | 31 214 € | 0,954 |
| Immobilier | Gradient boosting | 28 964 € | 0,959 |
| Montres | Régression linéaire | 2 583 € | 0,943 |
| Montres | Gradient boosting | 2 052 € | 0,964 |
| Voitures | Régression linéaire | 6 417 € | 0,922 |
| Voitures | Gradient boosting | 6 686 € | 0,915 |

Le gradient boosting n'est pas toujours le meilleur : sur les voitures, la régression linéaire fait légèrement mieux. Les deux modèles prédisent le logarithme du prix, et mes règles de génération sont en grande partie multiplicatives, ce qu'un modèle linéaire en logarithme capte déjà très bien. L'écart en faveur du gradient boosting n'apparaît que là où j'ai mis des effets non linéaires (la décote puis la prime de collection selon l'âge des montres, par exemple). Ces scores sont par ailleurs optimistes par construction, puisque les données suivent des règles régulières.

## Hypothèses et simplifications

Projection :

- Les revenus, les charges et la pension sont indexés sur l'inflation. Les revenus sont saisis nets d'impôt sur le revenu.
- Chaque année, les encours sont rémunérés, puis le cash-flow net est investi selon une répartition fixe ou, s'il est négatif, prélevé dans l'ordre livret A, compte-titres, assurance-vie, PEA.
- Les plafonds de versement du livret A (22 950 €) et du PEA (150 000 €) sont appliqués, l'excédent va sur le compte-titres.
- Pour un achat immobilier, l'apport et le prêt financent le bien et les frais d'acquisition. Le bien est revalorisé à un taux constant. L'assurance emprunteur n'est pas comptée.

Fiscalité, volontairement simplifiée (taux 2026) :

- Compte-titres : prélèvement forfaitaire unique de 31,4 % appliqué chaque année aux gains, comme s'ils étaient tous réalisés.
- Assurance-vie : imposition de la part de gains des retraits, à 30 % avant 8 ans ; après 8 ans, abattement annuel de 4 600 € puis 24,7 %.
- PEA : imposition de la part de gains des retraits, à 31,4 % avant 5 ans et 18,6 % (prélèvements sociaux seuls) après.
- Ne sont pas modélisés : le barème de l'impôt sur le revenu, les droits de succession, les plus-values immobilières, les frais des contrats.

Monte Carlo :

- Les rendements annuels de chaque enveloppe suivent une loi normale (moyenne et volatilité saisies), avec une matrice de corrélation fixe entre enveloppes. Les années sont indépendantes entre elles : pas de crise qui dure, pas de queues épaisses.

Profil de risque :

- Les pondérations, les seuils et la correspondance entre profil et SRI sont mes choix, documentés dans `src/risk_profile.py`. Un vrai questionnaire réglementaire est plus long et propre à chaque établissement.

Actifs corporels :

- Données simulées (voir plus haut). Les taux d'évolution utilisés pour la projection à dix ans sont des hypothèses que l'utilisateur peut modifier, pas des résultats du modèle. Les frais de détention ne sont pas déduits.

## Lancer le projet

Python 3.11.

```bash
python -m venv .venv
source .venv/bin/activate        # sous Windows : .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

L'application s'ouvre sur `http://localhost:8501`. Elle ne demande ni clé d'API ni connexion à un service externe. Les modèles du module 3 sont entraînés au premier affichage de chaque catégorie (une à deux secondes) puis gardés en cache.

Pour lancer les tests :

```bash
pytest
```

Pour écrire les jeux de données simulés en CSV et les regarder :

```bash
python data/generate_data.py
```

## Organisation du code

```
app.py                          navigation, page d'accueil, bandeau de bas de page
pages/
    1_Projection_cash_flows.py
    2_Profil_de_risque.py
    3_Actifs_corporels.py
src/
    cashflow.py                 projection annuelle, fiscalité simplifiée, Monte Carlo
    risk_profile.py             questionnaire, scoring, plafonnement, allocations
    asset_models.py             entraînement, validation croisée, estimation, projection
    utils.py                    formats français, palette, utilitaires d'affichage
data/
    generate_data.py            génération des données simulées
tests/
    test_cashflow.py
    test_risk_profile.py
```

Les calculs sont dans `src/` et ne dépendent pas de Streamlit (sauf `utils.py`), ce qui permet de les tester directement. Les pages ne font que la saisie et l'affichage.

## Ce que je voudrais améliorer

- Remplacer les données simulées de l'immobilier par les données DVF (Demandes de valeurs foncières, en open data), ce qui obligerait à traiter de vraies questions : nettoyage, géolocalisation, évolution des prix dans le temps.
- Rendre la fiscalité plus fidèle : imposer le compte-titres à la cession plutôt que chaque année, traiter l'assurance-vie au-delà de 150 000 € de versements, et afficher un patrimoine net de fiscalité latente.
- Améliorer le Monte Carlo avec des rendements log-normaux et un tirage par classe d'actifs plutôt que par enveloppe, pour que l'allocation issue du profil de risque se retrouve directement dans la simulation.
