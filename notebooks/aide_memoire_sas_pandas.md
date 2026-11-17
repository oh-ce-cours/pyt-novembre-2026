# Aide-mémoire SAS EG → Python / pandas

```python
# charger pandas (les tableaux de données), sous le nom court pd
import pandas as pd
# charger numpy (calcul sur des colonnes entières), sous le nom court np
import numpy as np
```

Dans les tables : `df` est un DataFrame (une table), `s` une colonne (Series), `"a"`, `"b"`, `"x"`… des noms de colonnes.

## Lire / écrire

| Ce que ça fait | SAS | pandas |
|---|---|---|
| Lire un CSV exporté de SAS : séparateur `;`, virgule décimale, accents Windows | `PROC IMPORT DATAFILE="f.csv" DBMS=DLM; DELIMITER=";";` | `pd.read_csv("f.csv", sep=";", decimal=",", encoding="cp1252")` |
| Lire des dates au format jour/mois/année | dates `DDMMYY10.` | `pd.read_csv(..., parse_dates=["d"], dayfirst=True)` ou `pd.to_datetime(s, format="%d/%m/%Y")` |
| Lire une feuille d'un fichier Excel | `PROC IMPORT ... DBMS=XLSX` | `pd.read_excel("f.xlsx", sheet_name="Feuil1")` |
| Lire une table SAS (`.sas7bdat`) | `LIBNAME` + table SAS | `pd.read_sas("t.sas7bdat", encoding="latin-1")` |
| Exécuter une requête SQL sur la base et récupérer le résultat en table | `PROC SQL; CONNECT TO ...` | `pd.read_sql("SELECT ...", connexion, params=...)` / `verticapy.vDataFrame("SELECT ...").to_pandas()` |
| Écrire la table dans un CSV ou un fichier Excel (sans la colonne d'index) | `PROC EXPORT OUTFILE=...` | `df.to_csv("f.csv", sep=";", index=False)` / `df.to_excel("f.xlsx", index=False)` |

## Explorer

| Ce que ça fait | SAS | pandas |
|---|---|---|
| Décrire la table : colonnes, types, nombre de lignes et de colonnes | `PROC CONTENTS` | `df.info()`, `df.dtypes`, `df.shape` |
| Afficher les 10 premières lignes | `PROC PRINT (OBS=10)` | `df.head(10)` |
| Statistiques de base des colonnes numériques (nombre, moyenne, min, max…) | `PROC MEANS` | `df.describe()` |
| Compter chaque valeur d'une colonne, valeurs manquantes comprises | `PROC FREQ; TABLES x / MISSING;` | `df["x"].value_counts(dropna=False)` |
| Tableau croisé de deux colonnes, avec les totaux | `PROC FREQ; TABLES x*y;` | `pd.crosstab(df["x"], df["y"], margins=True)` |
| Nombre (ou taux) de valeurs manquantes par colonne | `NMISS` | `df.isna().sum()` (nombre) / `df.isna().mean()` (taux) |

## Sélectionner / filtrer / trier

| Ce que ça fait | SAS | pandas |
|---|---|---|
| Garder seulement certaines colonnes | `KEEP a b;` | `df[["a", "b"]]` |
| Supprimer une colonne | `DROP a;` | `df.drop(columns="a")` |
| Renommer une colonne | `RENAME a=b;` | `df.rename(columns={"a": "b"})` |
| Garder les lignes qui respectent plusieurs conditions | `WHERE x > 10 AND y = "A";` | `df.loc[(df["x"] > 10) & (df["y"] == "A")]` ou `df.query('x > 10 and y == "A"')` |
| Garder les lignes dont la valeur est dans une liste | `WHERE y IN ("A", "B");` | `df[df["y"].isin(["A", "B"])]` |
| Garder les lignes où la valeur est manquante | `WHERE y IS MISSING;` | `df[df["y"].isna()]` |
| Trier par `a` croissant, puis `b` décroissant | `PROC SORT; BY a DESCENDING b;` | `df.sort_values(["a", "b"], ascending=[True, False])` |
| Garder une seule ligne par valeur de `a` (la première) | `PROC SORT NODUPKEY; BY a;` | `df.drop_duplicates("a")` |
| Supprimer les lignes identiques sur toutes les colonnes | `PROC SORT NODUP;` | `df.drop_duplicates()` |

## Créer des colonnes (étape DATA)

| Ce que ça fait | SAS | pandas |
|---|---|---|
| Calculer une nouvelle colonne à partir d'autres colonnes | `c = a * b;` | `df["c"] = df["a"] * df["b"]` |
| Valeur selon une condition (si / sinon) | `IF a > 0 THEN f = 1; ELSE f = 0;` | `df["f"] = np.where(df["a"] > 0, 1, 0)` |
| Valeur selon plusieurs conditions, avec une valeur par défaut | `SELECT; WHEN ... OTHERWISE` | `np.select([cond1, cond2], [v1, v2], default=v3)` |
| Texte en majuscules / sans espaces autour / 3 premiers caractères | `UPCASE / STRIP / SUBSTR` | `s.str.upper()` / `s.str.strip()` / `s.str[0:3]` |
| Tester un format avec une expression régulière (tout le texte / une partie) | `PRXMATCH("/motif/", x)` | `s.str.fullmatch(r"motif")` / `s.str.contains(r"motif")` |
| Nombre de jours entre deux dates | `INTCK("DAY", d1, d2)` | `(df["d2"] - df["d1"]).dt.days` |
| Extraire l'année, le mois d'une date | `YEAR(d)`, `MONTH(d)` | `df["d"].dt.year`, `df["d"].dt.month` |
| Ramener une date au 1er jour de son mois | `INTNX("MONTH", d, 0, "B")` | `df["d"].dt.to_period("M").dt.start_time` |
| Remplacer des codes par des libellés / regrouper des valeurs en tranches | `PUT(x, format.)` | `s.map({...})` / `pd.cut(s, bins=[...], labels=[...])` |
| Cumul ligne après ligne / valeur de la ligne précédente | `RETAIN` / `LAG` | `s.cumsum()` / `s.shift(1)` (par groupe : `df.groupby("g")["x"].shift(1)`) |

## Agréger

| Ce que ça fait | SAS | pandas |
|---|---|---|
| Nombre et moyenne de `v` pour chaque groupe `g`, résultat en table | `PROC MEANS; CLASS g; VAR v; OUTPUT OUT=r N=nb MEAN=moy;` | `df.groupby("g").agg(nb=("v", "count"), moy=("v", "mean")).reset_index()` |
| Somme par groupe, en ne gardant que les groupes au-dessus de 100 | `PROC SQL; SELECT g, SUM(v) ... GROUP BY g HAVING SUM(v) > 100` | `r = df.groupby("g")["v"].sum(); r[r > 100]` |
| Tableau croisé avec une somme dans chaque case / passer des colonnes en lignes | `PROC TABULATE` / `PROC TRANSPOSE` | `df.pivot_table(index="a", columns="b", values="v", aggfunc="sum", fill_value=0)` / `df.melt(...)` |
| Première / dernière ligne de chaque groupe (après tri par date) | `FIRST.g` / `LAST.g` | `df.sort_values(["g", "d"]).groupby("g").head(1)` / `.tail(1)` |

## Joindre / empiler

| Ce que ça fait | SAS | pandas |
|---|---|---|
| Ajouter les colonnes de `b` à `a` sur la clé `k` ; `validate` vérifie qu'il y a au plus une ligne de `b` par clé | `PROC SQL; ... A LEFT JOIN B ON A.k = B.k` | `a.merge(b, on="k", how="left", validate="m:1")` |
| Trouver les lignes de `a` sans correspondance dans `b` (les orphelins) | `MERGE a(IN=x) b(IN=y); BY k; IF x AND NOT y;` | `m = a.merge(b, on="k", how="left", indicator=True); m[m["_merge"] == "left_only"]` |
| Mettre deux tables l'une sous l'autre | `SET a b;` | `pd.concat([a, b], ignore_index=True)` |

Toujours vérifier le nombre de lignes avant / après une jointure.

## Macros → fonctions

```sas
/* définir la macro freq, avec deux paramètres */
%MACRO freq(table, var);
  /* tableau de fréquences de la variable, manquants compris */
  PROC FREQ DATA=&table; TABLES &var / MISSING; RUN;
/* fin de la macro */
%MEND;
/* appeler la macro sur la table contrats, variable produit */
%freq(contrats, produit);
```

```python
# définir la fonction freq, avec deux paramètres
def freq(table, var):
    # sa documentation (affichée par help(freq) ou Maj+Tab)
    """Fréquences de `var`, valeurs manquantes comprises."""
    # compter chaque valeur, manquants compris, et renvoyer le résultat
    return table[var].value_counts(dropna=False)

# appeler la fonction sur la table contrats, colonne produit
freq(contrats, "produit")
```

## Modifier une table : vues, copies, `inplace`

Extraire une partie d'une table donne, en pandas 3, toujours l'équivalent d'une **copie** : la modifier ne change pas la table d'origine. En pandas 2, c'était parfois une vue, parfois une copie (d'où le `SettingWithCopyWarning`). Ces règles marchent dans les deux versions.

| Ce que ça fait | À éviter | À faire |
|---|---|---|
| Garder le résultat d'une opération (dédoublonner, trier…) | `df.drop_duplicates(inplace=True)` (renvoie `None`, obsolète en pandas 3.1) | `df = df.drop_duplicates()` |
| Modifier une colonne entière | `df["c"].replace("a", "b", inplace=True)` (ne fait rien en pandas 3) | `df["c"] = df["c"].replace("a", "b")` |
| Modifier certaines lignes d'une colonne | `df[df["x"] < 0]["x"] = 0` (ne fait rien) | `df.loc[df["x"] < 0, "x"] = 0` |
| Travailler sur une sous-table qu'on va modifier | `neg = df[df["x"] < 0]` puis `neg["x"] = 0` (avertissement en pandas 2) | `neg = df[df["x"] < 0].copy()` |

## Pièges courants

- Codes (postaux, INSEE, SIREN) : les lire en texte, `dtype={"code_postal": "string"}`.
- `NaN != NaN` : tester les manquants avec `.isna()`, jamais avec `== None`.
- Conditions combinées : `&`, `|`, `~` et **des parenthèses** autour de chaque comparaison.
- Une boucle `for` sur les lignes (ou `apply`) est 10 à 100 fois plus lente que l'opération sur la colonne.

## Trouver de l'aide

| Ce que ça fait | Où |
|---|---|
| Afficher l'aide d'une fonction dans le notebook | `objet?` · `help(objet)` · `Maj+Tab` |
| Lister tout ce qu'on peut faire avec un objet | `dir(objet)` |
| Documentation officielle de Python, en français | https://docs.python.org/fr/3/ |
| Documentation officielle de pandas (explications et chaque fonction) | https://pandas.pydata.org/docs/ |
| Correspondance SAS → pandas, par l'équipe pandas | https://pandas.pydata.org/docs/getting_started/comparison/comparison_with_sas.html |
| Questions / réponses : chercher le message d'erreur exact ; vérifier la date et les votes des réponses | https://stackoverflow.com |
| Tutoriels détaillés et progressifs, en anglais | https://realpython.com |
