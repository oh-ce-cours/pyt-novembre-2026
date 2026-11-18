"""
Fonctions utilitaires pour le jeu Fizz Buzz.
"""


def est_divisible_par(dessus: int, dessous: int) -> bool:
    """Regarde si un nombre est divisible par un autre.

    Detail : on utilise l'opérateur modulo pour savoir si le reste de la division est nul.

    Args:
        dessus (int): le nombre du dessus
        dessous (int): le nombre du dessous

    Returns:
        bool: si le nombre est divisible ou pas.
    """
    return not dessus % dessous


def fizz_buzz(nombre) -> str:
    """Renvoie le résultat du jeu Fizz Buzz pour un élément donné."""
    resultat = ""
    nombre = 2
    if est_divisible_par(nombre, 3):
        resultat += "fizz"
    if est_divisible_par(nombre, 5):
        resultat += "buzz"
    if not resultat:
        resultat = str(nombre)

    return resultat


for nombre in range(1, 16):
    print(fizz_buzz(nombre))
