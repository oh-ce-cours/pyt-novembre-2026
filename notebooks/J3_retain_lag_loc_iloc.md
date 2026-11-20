# Jour 3 — RETAIN, LAG, FIRST./LAST. en pandas ; loc et iloc

## 1. RETAIN et LAG : les équivalents

En pandas, pas de boucle ligne à ligne : chaque usage de RETAIN / LAG a sa fonction.
On trie d'abord (comme `PROC SORT` avant `BY`) :

```python
df = df.sort_values(["client", "date"])
g = df.groupby("client")                     # = BY client
```

| SAS | pandas |
|---|---|
| `prec = lag(montant);` | `df["prec"] = df["montant"].shift(1)` |
| idem par client (`if first.client then prec = .;`) | `df["prec"] = g["montant"].shift(1)` |
| `ecart = date - lag(date);` par client | `df["ecart_jours"] = g["date"].diff().dt.days` |
| `retain cumul; cumul + montant;` (remis à 0 à `first.`) | `df["cumul"] = g["montant"].cumsum()` |
| `retain dernier; if montant ne . then dernier = montant;` | `df["dernier"] = g["montant"].ffill()` |
| `retain rang; if first.client then rang = 0; rang + 1;` | `df["rang"] = g.cumcount() + 1` |
| `first.client` | `df["first"] = ~df.duplicated("client")` |
| `last.client` | `df["last"] = ~df.duplicated("client", keep="last")` |

- le `groupby` fait le `if first. then ... = .;` tout seul : le calcul repart à zéro à chaque client ;
- pas de piège du `LAG` conditionnel (en SAS, `if x then y = lag(z);` ne fait avancer la file que si `x`
  est vrai) : `shift` calcule sur toutes les lignes, on filtre après ;
- un RETAIN vraiment conditionnel sans fonction toute faite : une boucle `for` reste acceptable.

## 2. Exemple : l'écart maximum entre deux dates successives, par branche

**Énoncé.** À partir d'une table de contrats (filtrée sur `date_saisie` non vide), une ligne par `branche` avec :
`libelle_branche`, `first_date` (date la plus ancienne), `last_date` (la plus récente), `nb_ctr` (nombre de
contrats), `ecart_jour_max` (écart maximum en jours entre deux dates **successives**), `date_inf_ecart` et
`date_sup_ecart` (les deux dates qui donnent cet écart).

### Le SAS de départ… et ses deux bugs

```sas
if first.branche then do;
   date_comp = date_saisie; first_date = date_saisie; nb_ctr = 1; ecart_jour_max = 0;
end;
else do;
   nb_ctr + 1;
   if date_saisie - date_comp > ecart_jour_max then do;
      ecart_jour_max = date_saisie - date_comp;
      date_inf_ecart = date_comp; date_sup_ecart = date_saisie;
      date_comp = date_saisie;                       /* BUG 1 : dans le if */
   end;
end;
```

1. `date_comp` n'avance que quand un record est battu : l'écart n'est pas mesuré entre deux dates
   **successives**. Dates 01/01, 11/01, 19/01, 27/01, 04/02 : le SAS trouve 16 jours (11/01 → 27/01),
   la bonne réponse est 10 jours (01/01 → 11/01).
2. `date_inf_ecart` / `date_sup_ecart` ne sont pas remises à vide au `first.` (RETAIN) : une branche sans
   écart hérite des dates de la branche précédente.

Correction SAS : `date_comp = date_saisie;` **après** le `if`, à chaque ligne, et
`date_inf_ecart = .; date_sup_ecart = .;` dans le `first.`.

### En pandas, avec une boucle (proche de l'étape DATA)

```python
res = []
for branche, groupe in contrats.groupby("branche"):
    dates = groupe["date_saisie"].sort_values().reset_index(drop=True)
    ecarts = dates.diff()                     # date - date précédente
    ligne = {"branche": branche,
             "libelle_branche": groupe["libelle_branche"].iloc[0],
             "first_date": dates.iloc[0], "last_date": dates.iloc[-1],
             "date_inf_ecart": pd.NaT, "date_sup_ecart": pd.NaT,
             "ecart_jour_max": 0, "nb_ctr": len(dates)}
    if len(dates) > 1:                        # un seul contrat : pas d'écart
        i = ecarts.idxmax()                   # 1re ligne du plus grand écart
        ligne.update(date_inf_ecart=dates[i - 1], date_sup_ecart=dates[i],
                     ecart_jour_max=ecarts[i].days)
    res.append(ligne)
branches = pd.DataFrame(res)
```

### En pandas, sans boucle

```python
d = contrats.sort_values(["branche", "date_saisie"]).copy()
d["ecart"] = d.groupby("branche")["date_saisie"].diff().dt.days

res = d.groupby("branche").agg(libelle_branche=("libelle_branche", "first"),
                               first_date=("date_saisie", "min"), last_date=("date_saisie", "max"),
                               ecart_jour_max=("ecart", "max"), nb_ctr=("date_saisie", "size"))
plus_grand = d.loc[d.dropna(subset=["ecart"]).groupby("branche")["ecart"].idxmax()]
res["date_sup_ecart"] = plus_grand.set_index("branche")["date_saisie"]
res["date_inf_ecart"] = res["date_sup_ecart"] - pd.to_timedelta(res["ecart_jour_max"], unit="D")
res["ecart_jour_max"] = res["ecart_jour_max"].fillna(0).astype(int)
branches = res.reset_index()
```

Les deux donnent le même résultat.

### Erreurs fréquentes vues en formation

| code | problème |
|---|---|
| `"nb_ctr": df.shape[0]` | nombre de lignes de **toute** la table : `len(groupe)` |
| `index.start` | n'existe que sur un `RangeIndex` : plante après un filtre (pandas 2) |
| `groupe["libelle"].unique()` | un tableau dans la case : `.iloc[0]` |
| `reset_index()` | ajoute une colonne `index` : `reset_index(drop=True)` |
| `x.shift(1)` puis `x - decale` | c'est `x.diff()` |
| branche à un seul contrat | aucun écart : prévoir le cas (`if len(dates) > 1`) |

## 3. Pourquoi `reset_index(drop=True)` ?

`idxmax()` renvoie une **étiquette** d'index, et `dates[i - 1]` cherche l'étiquette « i moins 1 ».
Après un tri, les étiquettes sont dans le désordre :

```
après sort_values :            après reset_index(drop=True) :
12   2020-01-01                0   2020-01-01
25   2020-01-10                1   2020-01-10
 7   2020-03-01                2   2020-03-01
```

- sans `reset_index` : `idxmax()` → 7, `dates[6]` → `KeyError` (et même s'il existait, ce ne serait pas la date d'avant) ;
- avec : `idxmax()` → 2, `dates[1]` = la date précédente ;
- `drop=True` : jeter l'ancien index au lieu d'en faire une colonne.

## 4. `loc` et `iloc`

Chaque ligne a **deux** repères : son **étiquette** (le nombre affiché à gauche) et sa **position** (0, 1, 2…).

| | se repère par | exemple ci-dessus (trié) |
|---|---|---|
| `.loc[...]` | l'**étiquette** | `.loc[12]` → 2020-01-01 |
| `.iloc[...]` | la **position** (*i* = *integer*) | `.iloc[0]` → 2020-01-01 (la 1re) |
| `[...]` sur une Series | l'étiquette, comme `.loc` | `[7]` → 2020-03-01 |

SAS : `.iloc[n]` ≈ `set table point=n;` ; `.loc[...]` ≈ chercher par la clé.

- 1re / dernière ligne : `.iloc[0]` / `.iloc[-1]`, toujours juste ;
- après un tri ou un filtre, les étiquettes ne sont plus 0, 1, 2… : `iloc`, ou `reset_index(drop=True)`.

## 5. Filtrer : avec ou sans `.loc` ?

**Pour lire**, les deux donnent la même chose :

```python
df[df["montant"] > 0][["client", "montant"]]          # deux crochets à la suite
df.loc[df["montant"] > 0, ["client", "montant"]]      # un seul crochet
```

**Pour modifier**, `.loc` est obligatoire :

```python
df[df["montant"] < 0]["montant"] = 0         # SettingWithCopyWarning : df N'EST PAS modifié
df.loc[df["montant"] < 0, "montant"] = 0     # df est modifié
```

Sans `.loc`, le premier crochet crée une copie : le `= 0` modifie la copie, qui est jetée
(en pandas 3, ça ne modifie jamais `df`).

En résumé :

1. lire : `df[condition]`, `df[["col1", "col2"]]` ;
2. lignes **et** colonnes : `.loc[lignes, colonnes]` (`df[condition, colonnes]` sans `.loc` : erreur) ;
3. modifier : toujours `.loc[condition, "colonne"] = valeur` (≈ `if montant < 0 then montant = 0;`).
