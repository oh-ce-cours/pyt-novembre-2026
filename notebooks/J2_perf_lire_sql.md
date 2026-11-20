# Jour 2 — Lire une grosse requête : où passe le temps, `lire_sql`, lecture en parallèle

Code : [`lire_sql.py`](lire_sql.py) (à copier à côté du notebook).

Toutes les mesures : 3,2 millions de lignes × 8 colonnes (`SELECT * FROM mon_schema.contrats`),
Vertica en local, Python 3.11, pandas 2.3, vertica-python 1.4, Mac 14 cœurs.

## 1. Où passe le temps ?

| étape | durée |
|---|---|
| Vertica exécute la requête (`cur.execute`) | 0,0 s |
| le **pilote** `vertica_python` transforme chaque valeur reçue en objet Python (`fetchall`) | **~16 s** |
| pandas construit le DataFrame | ~2 s |

Le goulot, c'est le pilote : il est écrit en Python pur et décode environ **200 000 lignes/s**,
une valeur à la fois, sur **un seul cœur**. Essayé sans gain : `binary_transfer=True`,
VerticaPy `to_pandas()` (qui fait un `fetchall` lui aussi).

Les vrais leviers, du plus efficace au moins efficace :

1. **ramener moins** : agréger dans la base (`GROUP BY`), filtrer (`WHERE`), choisir les colonnes ;
2. extraire **une fois** dans un fichier Parquet, puis travailler sur le fichier (voir `J2_export_par_morceaux.md`) ;
3. lire **par morceaux** et convertir les types au fil de l'eau : moins de RAM ;
4. lire **en parallèle** (plusieurs processus) : moins de temps.

## 2. Avant de lire : combien de lignes ?

```python
pd.read_sql(f"SELECT COUNT(*) AS n FROM ({sql}) AS t", conn)     # 0,03 s, exact
```

La base exécute la requête mais ne renvoie qu'un nombre : c'est rapide sur une table, plus long sur une
jointure lourde. `EXPLAIN` donne une estimation sans exécuter, mais elle n'est fiable que si les
statistiques sont à jour : ici **10 K** lignes annoncées avant `SELECT ANALYZE_STATISTICS('mon_schema.contrats')`,
**3 M** après. En pratique : `COUNT(*)`.

## 3. `lire_sql` : `read_sql` avec garde-fous

```python
from lire_sql import lire_sql, estimer_sql

estimer_sql(sql, conn)        # compte + lit 20 000 lignes pour estimer, ne lit rien d'autre
# 3 200 000 lignes × 8 colonnes | DataFrame ≈ 1 291 Mo (pic pendant la lecture ≈ 2 582 Mo) | lecture ≈ 20 s

df = lire_sql(sql, conn)                    # refuse : pic RAM estimé 2 583 Mo > max_ram_mo=2 000
df = lire_sql(sql, conn, force=True)        # lit quand même, en optimisant les types
```

Ce que fait `lire_sql` :

1. **estime** (`COUNT(*)` + échantillon de 20 000 lignes) : lignes, RAM, durée ;
2. **avertit** au-delà de la moitié des seuils (`max_lignes=5_000_000`, `max_ram_mo=2_000`), **refuse** au-delà,
   sauf `force=True` ;
3. lit **par morceaux** (`chunksize=200_000`) et convertit chaque morceau dès son arrivée :
   texte répétitif → `category`, autre texte → `string[pyarrow]`, dates → `datetime64` ;
4. recolle les morceaux (`union_categoricals` pour garder les `category`) ;
5. affiche ce que la lecture a réellement coûté.

L'estimation de RAM suppose qu'on ne convertit pas les types : avec `optimiser=True` (par défaut), elle est
pessimiste.

## 4. Mesures

| méthode | durée | pic de RAM | DataFrame final |
|---|---|---|---|
| `COUNT(*)` | 0,03 s | — | 1 ligne |
| agrégat dans la base (`GROUP BY produit`) | 0,2 s | — | 5 lignes |
| `pd.read_sql(sql, conn)` | 18,2 s | + 2 757 Mo | 1 299 Mo |
| `lire_sql(sql, conn, force=True)` | 18,4 s | + 542 Mo | **179 Mo** |
| `lire_sql(..., parallele=4)` | **5,5 s** | + 393 Mo, **+ ~580 Mo par processus lecteur** | 179 Mo |
| `lire_sql(..., parallele=8)` | **4,4 s** | idem | 179 Mo |
| 4 threads au lieu de 4 processus | 19,1 s | | |

- `lire_sql` ne lit pas plus vite (même pilote), mais le DataFrame est **7 fois plus petit** et le pic de RAM
  **5 fois plus bas** ;
- le parallèle divise le temps par 3 à 4, mais **pas** la mémoire totale : chaque processus a sa copie de
  Python, de pandas et de sa part des données ;
- résultat identique en parallèle et en séquentiel (vérifié ligne à ligne, à l'ordre près).

## 5. Comment marche la lecture en parallèle

```python
df = lire_sql(sql, conn, parallele=4, force=True)
```

1. **découper** la requête en 4 parts **disjointes**, que la base calcule elle-même :
   ```sql
   SELECT * FROM (<la requête>) AS t WHERE MOD(HASH(toutes les colonnes), 4) = 0   -- puis = 1, 2, 3
   ```
   `HASH(...)` transforme chaque ligne en un grand nombre ; `MOD(..., 4)` (reste de la division par 4) le range
   dans 0, 1, 2 ou 3. Chaque ligne tombe dans **une seule** part, et les parts ont à peu près la même taille ;
2. **4 processus** (`ProcessPoolExecutor`), chacun avec **sa propre connexion**, lisent chacun une part ;
3. on **recolle** les 4 résultats.

**Pourquoi des processus et pas des threads ?** Le décodage par le pilote est du calcul Python. Or Python
n'exécute qu'un seul thread à la fois (le *GIL*) : 4 threads = toujours 1 cœur (19 s, mesuré). 4 processus
= 4 interpréteurs Python, 4 cœurs.

Équivalent SAS : plusieurs sessions qui lisent chacune une partie de la table, ou `PROC SQL` en
*pass-through* découpé par une clé.

## 6. Précautions

- **Combien de processus ?** pas plus que le nombre de cœurs disponibles (`os.cpu_count()`), et 4 suffisent
  souvent : au-delà, le gain diminue ;
- **demander aux administrateurs de la base** : N lectures simultanées = N connexions et N fois la charge ;
- **la RAM** : chaque processus ajoute ~580 Mo ici ;
- **l'ordre des lignes** n'est pas conservé (un `ORDER BY` dans la requête ne sert à rien) : trier après ;
- **Vertica uniquement** (fonction `HASH`) ; avec VerticaPy, la connexion à passer est
  `vp.current_cursor().connection` ;
- dans un **script** `.py` (pas dans un notebook), mettre l'appel sous `if __name__ == "__main__":`,
  sinon chaque processus relance le script (Windows, macOS).

## En résumé

| besoin | solution | gain |
|---|---|---|
| un résultat agrégé | `GROUP BY` dans la requête | 18 s → 0,2 s |
| savoir avant de lire | `estimer_sql` / `COUNT(*)` | 0,1 s |
| moins de RAM | `lire_sql` (morceaux + `category`) | DataFrame ÷ 7, pic ÷ 5 |
| moins de temps | `lire_sql(..., parallele=4)` | 18 s → 5,5 s |
| relire souvent | extraire une fois en Parquet | relecture en 0,24 s |
