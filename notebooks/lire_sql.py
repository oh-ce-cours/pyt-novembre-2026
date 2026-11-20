"""Lire une requête SQL dans pandas en sachant à l'avance ce qu'elle va coûter.

    from lire_sql import lire_sql, estimer_sql
    estimer_sql("SELECT * FROM mon_schema.contrats", conn)          # compte + estime, ne lit rien
    df = lire_sql("SELECT * FROM mon_schema.contrats", conn)        # avertit / refuse si trop gros

Fonctionne avec toute connexion DB-API (vertica_python, sqlite3, psycopg…).
"""
import time
import warnings

import pandas as pd
from pandas.api.types import union_categoricals

try:
    import pyarrow  # noqa: F401  (présent au datalab)
    TEXTE = "string[pyarrow]"
except ImportError:
    TEXTE = None


class RequeteTropGrosse(Exception):
    """La requête dépasse les seuils : agréger dans la base, filtrer, ou passer force=True."""


def _sans_point_virgule(sql):
    return sql.strip().rstrip(";")


def _lire(sql, conn, **kwargs):
    with warnings.catch_warnings():
        # pandas avertit quand la connexion n'est pas SQLAlchemy : sans importance ici
        warnings.filterwarnings("ignore", message=".*SQLAlchemy.*")
        return pd.read_sql(sql, conn, **kwargs)


def estimer_sql(sql, conn, echantillon=20_000, afficher=True):
    """Nombre de lignes, RAM et durée estimées, sans ramener toute la requête.

    - nombre de lignes : SELECT COUNT(*) sur la requête (exact ; la base exécute la requête
      sans transférer les lignes : rapide sur une table, plus long sur une jointure lourde) ;
    - RAM et durée : mesurées sur les `echantillon` premières lignes, puis extrapolées.
    """
    sql = _sans_point_virgule(sql)
    t0 = time.perf_counter()
    nb_lignes = int(_lire(f"SELECT COUNT(*) AS n FROM ({sql}) AS t", conn).iloc[0, 0])
    duree_comptage = time.perf_counter() - t0

    t0 = time.perf_counter()
    ech = _lire(f"SELECT * FROM ({sql}) AS t LIMIT {echantillon}", conn)
    duree_ech = time.perf_counter() - t0

    n_ech = max(len(ech), 1)
    octets_par_ligne = ech.memory_usage(deep=True, index=False).sum() / n_ech
    estimation = {
        "lignes": nb_lignes,
        "colonnes": ech.shape[1],
        "ram_mo": round(octets_par_ligne * nb_lignes / 1e6, 1),
        # le pic pendant la lecture vaut environ 2x le DataFrame final (lignes Python + DataFrame)
        "pic_ram_mo": round(2 * octets_par_ligne * nb_lignes / 1e6, 1),
        "duree_s": round(duree_ech / n_ech * nb_lignes, 1),
        "duree_comptage_s": round(duree_comptage, 2),
        "echantillon": ech,
    }
    if afficher:
        print(f"{nb_lignes:,} lignes × {ech.shape[1]} colonnes".replace(",", " ")
              + f" | DataFrame ≈ {estimation['ram_mo']:,.0f} Mo".replace(",", " ")
              + f" (pic pendant la lecture ≈ {estimation['pic_ram_mo']:,.0f} Mo)".replace(",", " ")
              + f" | lecture ≈ {estimation['duree_s']:.0f} s")
    return estimation


def _colonnes_category(ech, ratio_max=0.5):
    """Colonnes texte où les valeurs se répètent beaucoup (produit, statut, agence…)."""
    return [c for c in ech.columns
            if ech[c].dtype == object and len(ech) > 0
            and ech[c].dropna().map(type).eq(str).all()
            and ech[c].nunique() / len(ech) <= ratio_max]


def _lire_morceaux(sql, conn, cat, textes, dates, taille_morceau):
    """Lit la requête par morceaux et convertit chaque morceau dès son arrivée."""
    morceaux = []
    for m in _lire(sql, conn, chunksize=taille_morceau):
        for c in cat:
            m[c] = m[c].astype("category")
        for c in textes:
            m[c] = m[c].astype(TEXTE)
        for c in dates:
            m[c] = pd.to_datetime(m[c])
        morceaux.append(m)
    return morceaux


def _lire_partie(parametres, sql, cat, textes, dates, taille_morceau):
    """Exécuté dans un processus à part : sa propre connexion, sa part des lignes."""
    import vertica_python
    with vertica_python.connect(**parametres) as conn:
        return _lire_morceaux(sql, conn, cat, textes, dates, taille_morceau)


def _lire_en_parallele(sql, conn, n, colonnes, cat, textes, dates, taille_morceau):
    """Découpe la requête en n parts disjointes (MOD(HASH(toutes les colonnes), n) = i)
    et les lit dans n processus : le décodage par le pilote, qui est le goulot, se fait
    sur n cœurs au lieu d'un. Des threads ne servent à rien ici (GIL).

    Vertica uniquement (fonction HASH) ; reprend les paramètres de la connexion `conn`.
    """
    from concurrent.futures import ProcessPoolExecutor

    parametres = getattr(conn, "options", None)
    if parametres is None:
        raise ValueError("parallele > 1 : connexion vertica_python attendue "
                         "(au datalab avec VerticaPy : vp.current_cursor().connection)")
    parametres = dict(parametres)
    cle = ", ".join(f't."{c}"' for c in colonnes)
    parts = [f"SELECT * FROM ({sql}) AS t WHERE MOD(HASH({cle}), {n}) = {i}" for i in range(n)]
    with ProcessPoolExecutor(n) as pool:
        resultats = pool.map(_lire_partie, [parametres] * n, parts, [cat] * n, [textes] * n,
                             [dates] * n, [taille_morceau] * n)
        return [m for morceaux in resultats for m in morceaux]


def lire_sql(sql, conn, max_lignes=5_000_000, max_ram_mo=2_000, force=False,
             optimiser=True, taille_morceau=200_000, parallele=1, afficher=True):
    """Comme pd.read_sql, mais :

    1. estime d'abord lignes / RAM / durée (voir estimer_sql) ;
    2. avertit au-delà de la moitié des seuils, refuse au-delà (sauf force=True) ;
    3. lit par morceaux de `taille_morceau` lignes : le pic de RAM reste proche du DataFrame final ;
    4. si optimiser=True : colonnes texte répétitives -> category, autres textes -> string[pyarrow]
       (un objet Python par valeur coûte cher et fragmente la mémoire), dates -> datetime64 ;
    5. parallele=N (Vertica) : lit en N processus et N connexions simultanées ; à régler selon
       le nombre de cœurs disponibles et avec l'accord des administrateurs de la base.
       L'ordre des lignes n'est pas conservé (ORDER BY sans effet) ;
    6. affiche ce que la lecture a réellement coûté.
    """
    sql = _sans_point_virgule(sql)
    est = estimer_sql(sql, conn, afficher=afficher)

    trop = []
    if est["lignes"] > max_lignes:
        trop.append(f"{est['lignes']:,} lignes > max_lignes={max_lignes:,}")
    if est["pic_ram_mo"] > max_ram_mo:
        trop.append(f"pic RAM estimé {est['pic_ram_mo']:,.0f} Mo > max_ram_mo={max_ram_mo:,}")
    if trop and not force:
        raise RequeteTropGrosse(" ; ".join(trop) + ". Agréger ou filtrer dans la requête "
                                "(GROUP BY, WHERE, colonnes utiles), ou relancer avec force=True.")
    if est["lignes"] > max_lignes / 2 or est["pic_ram_mo"] > max_ram_mo / 2:
        warnings.warn(f"Grosse requête : {est['lignes']:,} lignes, ~{est['ram_mo']:,.0f} Mo, "
                      f"~{est['duree_s']:.0f} s.", stacklevel=2)

    cat = _colonnes_category(est["echantillon"]) if optimiser else []
    dates = ([c for c in est["echantillon"].columns
              if est["echantillon"][c].dropna().map(type).astype(str).str.contains("date").all()
              and est["echantillon"][c].notna().any()] if optimiser else [])

    ech = est["echantillon"]
    textes = ([c for c in ech.columns if c not in cat and ech[c].dtype == object
               and ech[c].notna().any() and ech[c].dropna().map(type).eq(str).all()]
              if optimiser and TEXTE else [])

    t0 = time.perf_counter()
    if parallele > 1:
        morceaux = _lire_en_parallele(sql, conn, parallele, list(ech.columns), cat, textes, dates,
                                      taille_morceau)
    else:
        morceaux = _lire_morceaux(sql, conn, cat, textes, dates, taille_morceau)
    if not morceaux:
        df = est["echantillon"].iloc[0:0]
    else:
        # recoller les category de chaque morceau sans repasser en texte
        cols_cat = {c: union_categoricals([m[c] for m in morceaux]) for c in cat}
        for m in morceaux:
            for c in cat:
                m[c] = pd.Categorical(m[c], categories=cols_cat[c].categories)
        df = pd.concat(morceaux, ignore_index=True)
    duree = time.perf_counter() - t0

    if afficher:
        mo = df.memory_usage(deep=True).sum() / 1e6
        debit = len(df) / duree if duree else float("nan")
        print(f"Lu : {len(df):,} lignes en {duree:.1f} s ({debit:,.0f} lignes/s)".replace(",", " ")
              + (f" | {parallele} processus" if parallele > 1 else "")
              + f" | DataFrame {mo:,.0f} Mo".replace(",", " ")
              + (f" | category : {', '.join(cat)}" if cat else "")
              + (f" | string[pyarrow] : {', '.join(textes)}" if textes else "")
              + (f" | dates : {', '.join(dates)}" if dates else ""))
    return df
