"""Validation des numéros de contrat."""
from datetime import date

PREFIXES = {"AUT", "HAB", "SAN", "PRV"}


def est_num_contrat_valide(num):
    """Indique si `num` est un numéro de contrat valide.

    Format attendu : PPP-AAAA-NNNNNN
    - PPP : préfixe produit parmi AUT, HAB, SAN, PRV (en majuscules) ;
    - AAAA : année de souscription, entre 2000 et l'année en cours ;
    - NNNNNN : exactement 6 chiffres.

    Lève TypeError si `num` n'est pas une chaîne.

    >>> est_num_contrat_valide("AUT-2023-000123")
    True
    """
    if not isinstance(num, str):
        raise TypeError(f"numéro de contrat attendu (str), reçu {type(num).__name__}")
    morceaux = num.split("-")
    if len(morceaux) != 3:
        return False
    prefixe, annee, numero = morceaux
    return (
        prefixe in PREFIXES
        and annee.isdigit()
        and 2000 <= int(annee) <= date.today().year
        and numero.isdigit()
    )
