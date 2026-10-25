# Rapport de conception Data Warehouse Mubawab

## 1. Objectif

Ce rapport décrit une architecture de données permettant de transformer les
annonces immobilières récupérées par le scraper Mubawab en données fiables
pour l'analyse et la visualisation.

Les objectifs principaux sont :

- conserver les données originales récupérées ;
- nettoyer et normaliser les champs métiers ;
- historiser les prix et la disponibilité des annonces ;
- automatiser le traitement avec Apache Airflow ;
- préparer les données pour Power BI, Metabase, Superset ou Tableau.

## 2. Architecture proposée

```text
Mubawab
   |
   v
Extraction par le scraper
   |
   v
Bronze : données brutes
raw_listings
raw_listing_details
   |
   v
Silver : données nettoyées
stg_listings
stg_listing_details
   |
   v
Gold : Data Warehouse
dim_property
dim_location
dim_date
fact_listing_snapshot
fact_listing_price
   |
   v
BI et analyses
```

Le scraper utilise actuellement SQLite pour stocker les annonces et les
détails. SQLite convient au développement local. Pour un environnement
partagé, PostgreSQL est recommandé comme entrepôt de données.

## 3. Couches de données

### 3.1 Bronze : données brutes

La couche Bronze conserve les valeurs telles qu'elles ont été extraites du
site, sans transformation destructive.

Tables principales :

- `raw_listings`
- `raw_listing_details`

Champs importants :

```text
ad_id
url
title_raw
price_raw
city_raw
area_raw
description_raw
features_full
images_json
scraped_at
detail_scraped
```

Cette couche permet de rejouer les transformations, de diagnostiquer les
erreurs et de conserver une trace de la source.

### 3.2 Silver : données nettoyées

La couche Silver contient les données typées et normalisées.

Tables principales :

- `stg_listings`
- `stg_listing_details`

Exemples de transformations :

```text
"900 000 DH"       -> 900000
"120 m²"           -> 120
"Appartement"      -> apartment
"Casablanca "      -> Casablanca
"3 chambres"       -> 3
```

Exemple de structure :

```sql
CREATE TABLE stg_listings (
    listing_id       VARCHAR(100) NOT NULL,
    listing_url      TEXT NOT NULL,
    title            TEXT,
    transaction_type VARCHAR(30),
    property_type    VARCHAR(50),
    city             VARCHAR(100),
    neighborhood     VARCHAR(150),
    price_amount     NUMERIC(14, 2),
    currency         VARCHAR(10),
    area_m2          NUMERIC(12, 2),
    bedrooms         INTEGER,
    bathrooms        INTEGER,
    description      TEXT,
    first_seen_at    TIMESTAMP,
    last_seen_at     TIMESTAMP,
    scraped_at       TIMESTAMP NOT NULL,
    source           VARCHAR(30) NOT NULL,
    record_hash      VARCHAR(64) NOT NULL,
    PRIMARY KEY (listing_id, scraped_at)
);
```

Les chargements Silver doivent être idempotents. Une même exécution relancée
ne doit pas créer de doublons.

### 3.3 Gold : données analytiques

La couche Gold utilise un modèle en étoile composé de dimensions et de tables
de faits.

Dimensions :

- `dim_property`
- `dim_location`
- `dim_date`

Tables de faits :

- `fact_listing_snapshot`
- `fact_listing_price`
- `fact_listing_availability`

## 4. Modèle du Data Warehouse

### 4.1 Dimension propriété

`dim_property` contient une ligne de référence par annonce ou propriété.

```sql
CREATE TABLE dim_property (
    property_key     BIGSERIAL PRIMARY KEY,
    listing_id       VARCHAR(100) UNIQUE NOT NULL,
    listing_url      TEXT NOT NULL,
    title            TEXT,
    property_type    VARCHAR(50),
    bedrooms         INTEGER,
    bathrooms        INTEGER,
    area_m2          NUMERIC(12, 2),
    description      TEXT,
    first_seen_at    TIMESTAMP NOT NULL,
    last_seen_at     TIMESTAMP NOT NULL,
    is_current       BOOLEAN NOT NULL DEFAULT TRUE
);
```

### 4.2 Dimension localisation

```sql
CREATE TABLE dim_location (
    location_key BIGSERIAL PRIMARY KEY,
    city         VARCHAR(100) NOT NULL,
    neighborhood VARCHAR(150),
    region       VARCHAR(100),
    country      VARCHAR(100) NOT NULL DEFAULT 'Morocco',
    UNIQUE (city, neighborhood)
);
```

### 4.3 Dimension date

```sql
CREATE TABLE dim_date (
    date_key     INTEGER PRIMARY KEY,
    full_date    DATE UNIQUE NOT NULL,
    year         INTEGER NOT NULL,
    quarter      INTEGER NOT NULL,
    month        INTEGER NOT NULL,
    week         INTEGER NOT NULL,
    day_of_month INTEGER NOT NULL
);
```

### 4.4 Faits des snapshots

Chaque ligne représente l'état d'une annonce lors d'une extraction.

```sql
CREATE TABLE fact_listing_snapshot (
    snapshot_key     BIGSERIAL PRIMARY KEY,
    property_key     BIGINT NOT NULL REFERENCES dim_property(property_key),
    location_key     BIGINT REFERENCES dim_location(location_key),
    date_key         INTEGER NOT NULL REFERENCES dim_date(date_key),
    scraped_at       TIMESTAMP NOT NULL,
    price_amount     NUMERIC(14, 2),
    currency         VARCHAR(10),
    area_m2          NUMERIC(12, 2),
    is_available     BOOLEAN,
    source           VARCHAR(30) NOT NULL,
    UNIQUE (property_key, scraped_at)
);
```

Ce modèle permet de suivre :

- l'évolution du prix d'un bien ;
- le prix moyen par ville et par type de propriété ;
- le prix au mètre carré ;
- le nombre d'annonces disponibles par période ;
- les annonces nouvelles, modifiées ou disparues.

## 5. Orchestration Airflow

Le DAG devrait suivre l'enchaînement suivant :

```text
start
  |
  v
extract_listings
  |
  v
extract_listing_details
  |
  v
validate_raw_data
  |
  v
load_staging
  |
  v
transform_dimensions
  |
  v
load_fact_snapshot
  |
  v
data_quality_checks
  |
  v
finish
```

### 5.1 Extraction des annonces

Commande indicative :

```text
mubawab-scraper-cli scrape \
  --orchestrator brut \
  --city all \
  --action all \
  --max-pages 0 \
  --workers 2
```

### 5.2 Extraction des détails

Commande actuellement utilisée par le DAG :

```text
mubawab-scraper-cli details \
  --transaction all \
  --city all \
  --limit 500 \
  --workers 1
```

Cette tâche traite les annonces non enrichies et marque les détails réussis
pour permettre la reprise après interruption.

### 5.3 Chargement Silver

La tâche de staging doit :

1. lire `raw_listings` et `raw_listing_details` ;
2. convertir les prix, surfaces et nombres ;
3. normaliser les villes et types de biens ;
4. calculer un `record_hash` ;
5. insérer ou mettre à jour les lignes Silver ;
6. rejeter les enregistrements invalides dans une table d'erreurs.

### 5.4 Chargement Gold

Le chargement Gold doit :

1. créer les villes et quartiers absents de `dim_location` ;
2. insérer ou mettre à jour les propriétés ;
3. générer les dates nécessaires dans `dim_date` ;
4. insérer un snapshot dans `fact_listing_snapshot` ;
5. éviter les doublons avec une contrainte unique.

## 6. Fréquence d'exécution

Le DAG actuel est planifié toutes les 20 minutes :

```text
*/20 * * * *
```

Une organisation adaptée est :

- extraction et staging toutes les 20 minutes ;
- snapshot analytique une fois par heure ou une fois par jour ;
- contrôles qualité après chaque chargement ;
- archivage périodique des données anciennes.

La fréquence du snapshot dépend du besoin d'analyse. Un snapshot à chaque
exécution fournit un historique détaillé, mais augmente le volume de données.

## 7. Contrôles qualité

Les contrôles suivants doivent être exécutés avant de publier les données Gold :

```sql
SELECT COUNT(*)
FROM stg_listings
WHERE listing_id IS NULL;
```

```sql
SELECT COUNT(*)
FROM stg_listings
WHERE listing_url IS NULL OR listing_url = '';
```

```sql
SELECT listing_id, scraped_at, COUNT(*)
FROM stg_listings
GROUP BY listing_id, scraped_at
HAVING COUNT(*) > 1;
```

Règles métier recommandées :

- `listing_id` est obligatoire ;
- `listing_url` est obligatoire ;
- `price_amount` est nul ou supérieur ou égal à zéro ;
- `area_m2` est nul ou strictement positif ;
- `city` est renseignée lorsque la source la fournit ;
- `scraped_at` est obligatoire ;
- aucune clé `listing_id + scraped_at` ne doit être dupliquée ;
- un volume anormalement faible doit déclencher une alerte.

Si un contrôle critique échoue, le DAG doit échouer avant le chargement Gold.

## 8. Configuration Airflow

Les chemins et paramètres non sensibles peuvent être définis avec des
variables d'environnement :

```env
MUBAWAB_DB_PATH=/usr/local/airflow/include/data/db/mubawab.db
WAREHOUSE_HOST=postgres
WAREHOUSE_PORT=5432
WAREHOUSE_DB=mubawab_dw
WAREHOUSE_SCHEMA=warehouse
```

Les mots de passe et tokens ne doivent pas être placés dans `.env` suivi par
Git. Ils doivent être stockés dans une connexion Airflow ou dans un mécanisme
de secrets.

Connexion recommandée :

```text
conn_id: mubawab_warehouse
conn_type: postgres
host: postgres
schema: mubawab_dw
login: airflow
port: 5432
```

Le mot de passe doit être renseigné uniquement dans l'environnement local ou
dans le gestionnaire de secrets utilisé par Airflow.

## 9. Organisation des fichiers

Pour le développement local :

```text
data/
├── raw/
│   ├── listings/
│   └── details/
├── processed/
│   ├── listings/
│   └── details/
└── db/
    └── mubawab.db
```

Pour la production :

```text
Bronze  -> S3, MinIO ou Azure Blob Storage
Silver  -> PostgreSQL ou DuckDB
Gold    -> PostgreSQL, Snowflake ou BigQuery
```

SQLite doit rester réservé au développement ou aux petits traitements
monoposte. Un PostgreSQL partagé est préférable pour Airflow et les outils BI.

## 10. Plan d'implémentation

### Phase 1 : stabiliser l'extraction

- installer le package scraper dans l'image Astro ;
- vérifier le chemin partagé de la base SQLite ;
- séparer les tâches d'extraction des détails ;
- ajouter des logs et des retries explicites.

### Phase 2 : créer le staging

- définir le schéma `stg_listings` ;
- écrire le nettoyage des prix, surfaces et localisations ;
- ajouter les contrôles de doublons ;
- conserver les erreurs de transformation.

### Phase 3 : créer le warehouse

- provisionner PostgreSQL ;
- créer les dimensions ;
- créer la table `fact_listing_snapshot` ;
- ajouter les chargements idempotents ;
- configurer la connexion Airflow.

### Phase 4 : qualité et supervision

- ajouter les contrôles de volume et de nullité ;
- publier les métriques du DAG ;
- configurer les alertes ;
- documenter les procédures de reprise.

### Phase 5 : exposition BI

- créer des vues analytiques ;
- connecter l'outil BI au schéma Gold ;
- définir les indicateurs métier ;
- contrôler les performances et les droits d'accès.

## 11. Indicateurs analytiques possibles

Les premières vues BI peuvent exposer :

- prix moyen et médian par ville ;
- prix au mètre carré ;
- nombre d'annonces par ville ;
- répartition par type de propriété ;
- évolution des prix dans le temps ;
- délai moyen entre première et dernière observation ;
- taux d'annonces disparues ;
- distribution des surfaces et du nombre de chambres.

## 12. Conclusion

La séparation Bronze/Silver/Gold permet de conserver la donnée originale tout
en fournissant une donnée analytique propre et historisée.

La priorité immédiate est de stabiliser l'installation du scraper dans
l'image Astro, puis de mettre en place le staging. Le passage de SQLite à
PostgreSQL doit intervenir avant un usage multi-utilisateur ou une connexion
BI en production.
