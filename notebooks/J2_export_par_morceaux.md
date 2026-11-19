# Jour 2 — Lire une grosse requête et l'écrire en CSV ou Parquet, morceau par morceau

## Pourquoi par morceaux ?

`pd.read_sql(sql, conn)` ramène **toutes** les lignes d'un coup : le pilote fabrique d'abord un objet
Python par valeur, puis pandas construit le DataFrame. Pendant un instant, les deux existent en mémoire.

Avec `chunksize=`, pandas renvoie les lignes **par paquets** (des DataFrames de `chunksize` lignes au plus) :
un seul paquet est en mémoire à la fois. On l'écrit dans un fichier, on passe au suivant.

Mesuré sur 3,2 millions de lignes × 8 colonnes :

| | durée | pic de RAM |
|---|---|---|
| `pd.read_sql` d'un coup | 18 s | + 2 800 Mo |
| par morceaux de 200 000 lignes, écrits en CSV | 22 s | + 320 Mo |
| par morceaux de 200 000 lignes, écrits en Parquet | 18 s | + 450 Mo |

Le réflexe reste de **filtrer et agréger dans la requête** (`WHERE`, `GROUP BY`, colonnes utiles) :
on n'exporte par morceaux que ce qui doit vraiment sortir de la base.

## La requête

```python
import pandas as pd

sql = "SELECT * FROM mon_schema.contrats"
# conn : la connexion à la base (vertica_python, sqlite3…)
```

**Ou, avec VerticaPy** (à la place du bloc précédent), on construit la requête avec le vDataFrame,
puis on la lit avec pandas sur la même connexion (`to_pandas()` ramène tout d'un coup, sans morceaux) :

```python
v = vp.vDataFrame("mon_schema.contrats")
v.filter("statut = 'ACTIF'")                      # écrit en SQL, exécuté par Vertica

sql = f"SELECT * FROM {v.current_relation()}"     # le SQL construit par VerticaPy
conn = vp.current_cursor().connection             # la connexion ouverte par VerticaPy
```

## Écrire en CSV

Deux fonctions : une pour **créer** le fichier (avec l'en-tête), une pour **ajouter** à la fin (sans en-tête).

```python
def creer_csv(morceau, fichier):
    """Crée le fichier avec l'en-tête."""
    morceau.to_csv(fichier, mode="w", header=True, index=False,
                   sep=";", decimal=",", encoding="utf-8-sig")


def ajouter_csv(morceau, fichier):
    """Ajoute des lignes à la fin, sans en-tête."""
    morceau.to_csv(fichier, mode="a", header=False, index=False,
                   sep=";", decimal=",", encoding="utf-8")


morceaux = pd.read_sql(sql, conn, chunksize=200_000)
creer_csv(next(morceaux), "contrats.csv")      # next = prendre le premier morceau
for morceau in morceaux:                       # la boucle continue avec les suivants
    ajouter_csv(morceau, "contrats.csv")
```

- `mode="w"` crée (ou écrase) le fichier, `mode="a"` ajoute à la fin.
- `sep=";"` et `decimal=","` : le format attendu par un Excel français.
- `utf-8-sig` ajoute au début du fichier une marque invisible qui permet à Excel de lire les accents :
  seulement à la création, sinon elle se retrouve au milieu du fichier.

Relire : `pd.read_csv("contrats.csv", sep=";", decimal=",", encoding="utf-8-sig")`.

## Écrire en Parquet

```python
import pyarrow as pa
import pyarrow.parquet as pq


def creer_parquet(morceau, fichier):
    """Crée le fichier, y écrit le premier morceau, renvoie l'écrivain resté ouvert."""
    table = pa.Table.from_pandas(morceau, preserve_index=False)
    ecrivain = pq.ParquetWriter(fichier, table.schema)
    ecrivain.write_table(table)
    return ecrivain


def ajouter_parquet(morceau, ecrivain):
    """Ajoute un morceau, avec les types du premier."""
    table = pa.Table.from_pandas(morceau, schema=ecrivain.schema, preserve_index=False)
    ecrivain.write_table(table)


def typer(morceau):
    """Mêmes types dans tous les morceaux.
    À adapter : une ligne par colonne de date ou de nombre présente dans la requête."""
    morceau["date_effet"] = pd.to_datetime(morceau["date_effet"])
    morceau["date_resiliation"] = pd.to_datetime(morceau["date_resiliation"])
    morceau["prime_annuelle"] = morceau["prime_annuelle"].astype("float64")
    return morceau


morceaux = pd.read_sql(sql, conn, chunksize=200_000)
ecrivain = creer_parquet(typer(next(morceaux)), "contrats.parquet")
for morceau in morceaux:
    ajouter_parquet(typer(morceau), ecrivain)
ecrivain.close()                               # obligatoire : sans close, le fichier est illisible
```

Pourquoi c'est un peu plus long qu'en CSV :

- un fichier Parquet se termine par une description de tout son contenu : on garde l'**écrivain ouvert**
  pendant la boucle, et `close()` écrit cette fin ;
- le fichier a **un seul jeu de types** pour toutes ses colonnes : si une colonne est entièrement vide
  dans un morceau (ex. `date_resiliation`), pandas ne devine pas que c'est une date. `typer()` impose
  les mêmes types partout.

Relire (pandas utilise pyarrow) :

```python
df = pd.read_parquet("contrats.parquet")                                   # tout
df = pd.read_parquet("contrats.parquet", columns=["produit", "prime_annuelle"],
                     filters=[("statut", "==", "ACTIF")])                  # seulement l'utile
```

## Pourquoi le Parquet est plus petit

Mesuré sur 1 million de contrats (données générées, valeurs toutes différentes : pas de lignes copiées
qui gonfleraient artificiellement la compression) :

| fichier | taille |
|---|---|
| DataFrame en mémoire | 352 Mo |
| CSV | 69,8 Mo |
| Parquet (compression par défaut, `snappy`) | 20,6 Mo, **3,4 fois plus petit** |
| Parquet `compression="zstd"` | 14,3 Mo, **4,9 fois plus petit** |

Taille de chaque colonne dans les deux formats :

| colonne | exemple de valeur | CSV | Parquet | pourquoi |
|---|---|---|---|---|
| `produit` | `HABITATION` | 8,0 Mo | 0,25 Mo | 4 valeurs possibles : stockées une fois, puis un petit numéro par ligne (dictionnaire) |
| `statut` | `ACTIF` | 6,7 Mo | 0,26 Mo | idem, 3 valeurs |
| `agence` | `AG-10042` | 9,0 Mo | 1,0 Mo | idem, 250 valeurs |
| `date_effet` | `2015-04-04` | 11,0 Mo | 1,7 Mo | en CSV, 10 caractères ; en Parquet, un nombre (jours depuis 1970) |
| `date_resiliation` | vide à 70 % | 4,0 Mo | 0,8 Mo | les valeurs vides ne coûtent presque rien |
| `prime_annuelle` | `841,76` | 7,1 Mo | 4,4 Mo | un nombre binaire de 8 octets, compressé ; gain modeste, les valeurs sont toutes différentes |
| `id_client` | `C012345` | 8,0 Mo | 6,0 Mo | presque toutes différentes : peu de gain |
| `num_contrat` | `AUT-2015-000007` | 16,0 Mo | 6,2 Mo | toutes différentes, mais début répétitif (`AUT-2015-`) : la compression le repère |

Les trois raisons :

1. **CSV = du texte, ligne par ligne.** Chaque valeur est réécrite en caractères à chaque ligne :
   « HABITATION » est écrit des centaines de milliers de fois, une date prend 10 caractères.
2. **Parquet = colonne par colonne, en binaire.** Les valeurs d'une même colonne sont rangées ensemble
   et dans leur vrai type (date, nombre) : les valeurs répétées sont remplacées par un numéro
   (dictionnaire), les suites identiques sont résumées (« 500 fois ACTIF »).
3. **Puis chaque colonne est compressée** (`snappy` par défaut, `zstd` plus fort et aussi rapide ici).

Règle pratique : le gain est **énorme sur les colonnes à peu de valeurs** (produit, statut, agence,
codes) et sur les dates, **faible sur les identifiants et les montants**, qui sont tous différents.
Une table « métier » typique gagne 3 à 5 fois. (Sur une table où des lignes se répètent, le gain
peut dépasser 10 fois.)

## Stats d'usage : écrire et relire

Même million de lignes, Python 3.11, pandas 2.3, pyarrow :

| opération | CSV | Parquet |
|---|---|---|
| écrire le fichier (`to_csv` / `to_parquet`) | 1,7 s | **0,3 s** |
| relire tout (`read_csv` / `read_parquet`) | 0,75 s | **0,25 s** |
| pic de mémoire pendant la relecture complète | + 460 Mo | + 420 Mo |
| relire 2 colonnes (`usecols=` / `columns=`) | 0,18 s | **0,04 s** |
| pic de mémoire pour 2 colonnes | + 64 Mo | + 56 Mo |
| dates relues comme dates | seulement avec `parse_dates=[...]` | **oui, automatiquement** |
| nombres à virgule française | seulement avec `decimal=","` | **rien à préciser** |

À retenir :

- la mémoire après relecture est **la même** dans les deux cas : c'est la taille du DataFrame,
  pas celle du fichier, qui compte ;
- pour économiser la mémoire, on lit **moins de colonnes** (`usecols=` en CSV, `columns=` en Parquet) :
  ici 7 fois moins de mémoire ;
- Parquet est 3 à 5 fois plus rapide à écrire et à relire, et **n'a besoin d'aucun paramètre**
  (séparateur, décimale, encodage, dates) : le fichier connaît ses types ;
- le temps le plus long reste celui de la base vers Python (18 s pour 3,2 M lignes, voir plus haut) :
  c'est pour ça qu'on extrait **une fois** et qu'on relit le fichier ensuite.

## CSV ou Parquet ?

| | CSV | Parquet |
|---|---|---|
| s'ouvre dans Excel | oui | non |
| types à la relecture | tout redevient texte (dates à reconvertir) | conservés (dates, nombres) |
| taille | grosse | 3 à 5 fois plus petite (voir plus haut) |
| vitesse d'écriture et de relecture | correcte | 3 à 5 fois plus rapide |
| lire seulement quelques colonnes | oui (`usecols=`), mais tout le fichier est parcouru | oui (`columns=`, `filters=`), seules ces colonnes sont lues sur le disque |

En résumé : **CSV pour échanger** (Excel, autre outil), **Parquet pour retravailler en Python**.
C'est l'équivalent d'une table copiée dans une bibliothèque SAS permanente : on interroge la base
une fois, puis on travaille sur le fichier.
