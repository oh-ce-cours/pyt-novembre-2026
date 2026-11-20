# Jour 2 — Passer une variable dans une requête, sans injection SQL

**Règle :** jamais de f-string ni de `+` pour mettre une valeur dans du SQL. On laisse le pilote
(ou VerticaPy) l'insérer : il la traite comme du texte, jamais comme du SQL.

Équivalent SAS : `%sysfunc(quote(&var))` plutôt que `'&var'`.

## Le problème

```python
valeur = "AUTO' OR '1'='1"      # une saisie piège

pd.read_sql(f"SELECT * FROM mon_schema.contrats WHERE produit = '{valeur}'", cnx)
# -> WHERE produit = 'AUTO' OR '1'='1'  : la condition est toujours vraie, TOUTES les lignes sortent
```

## pandas et vertica_python : paramètres

```python
sql = "SELECT * FROM mon_schema.contrats WHERE produit = :p AND prime_annuelle > :mini"

df = pd.read_sql(sql, cnx, params={"p": valeur, "mini": 500})

cur = cnx.cursor()              # après read_sql, qui ferme le curseur ouvert avant lui
cur.execute(sql, {"p": valeur, "mini": 500})

# variante : requête préparée par le serveur (? à la place de :nom)
cur.execute("SELECT * FROM mon_schema.contrats WHERE produit = ?", [valeur],
            use_prepared_statements=True)
```

## VerticaPy : écrire la condition en Python

```python
v = vp.vDataFrame("mon_schema.contrats")
v.filter(v["produit"] == valeur)               # VerticaPy double les apostrophes
v.isin({"produit": ["AUTO", "SANTE"]})         # une liste de valeurs

v.filter(f"produit = '{valeur}'")              # DANGER : même problème qu'avec une f-string
```

## Noms de tables et de colonnes

Un nom de table ou de colonne **ne peut pas** passer en paramètre : on le vérifie contre une liste autorisée.

```python
assert colonne in {"produit", "statut", "agence"}
sql = f"SELECT {colonne}, COUNT(*) FROM mon_schema.contrats GROUP BY {colonne}"
```

## Vérifié

Sur une table de 3 200 contrats, avec `valeur = "AUTO' OR '1'='1"` :

| méthode | lignes renvoyées |
|---|---|
| f-string | **3 200** (toute la table) |
| `params={"p": ...}`, `cur.execute(sql, {...})`, `?` préparé | 0 |
| `v.filter(v["produit"] == valeur)` | 0 |
