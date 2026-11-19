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

## CSV ou Parquet ?

| | CSV | Parquet |
|---|---|---|
| s'ouvre dans Excel | oui | non |
| types à la relecture | tout redevient texte (dates à reconvertir) | conservés (dates, nombres) |
| taille | grosse | 5 à 10 fois plus petite (compressé, par colonnes) |
| relecture de 3,2 M lignes | plusieurs secondes | 0,05 à 2 s |
| lire seulement quelques colonnes | non, tout le fichier est lu | oui (`columns=`, `filters=`) |

En résumé : **CSV pour échanger** (Excel, autre outil), **Parquet pour retravailler en Python**.
C'est l'équivalent d'une table copiée dans une bibliothèque SAS permanente : on interroge la base
une fois, puis on travaille sur le fichier.
