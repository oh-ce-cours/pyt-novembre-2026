def est_divisible_par(dessus: int, dessous: int) -> bool:
    """Regarde si un nombre est divisible par un autre.

    Detail : on utilise l'opérateur modulo pour savoir si le reste de la division est nul.

    Args:
        dessus (int): le nombre du dessus
        dessous (int): le nombre du dessous

    Returns:
        bool: si le nombre est divisible ou pas.
    """
    return dessus % dessous == 0


for nombre in range(1, 16):
    resultat = ""
    if est_divisible_par(nombre, 3):
        resultat += "fizz"
    if est_divisible_par(nombre, 5):
        resultat += "buzz"
    if not resultat:
        resultat = str(nombre)
    print(resultat)
