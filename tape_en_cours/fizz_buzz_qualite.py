def est_divisible_par(dessus: int, dessous: int) -> bool:
    """Regarde si un nombre est divisible par un autre.

    Args:
        dessus (int): _description_
        dessous (int): _description_

    Returns:
        bool: _description_
    """
    return dessus % dessous == 0


for nombre in range(1, 16):
    resultat = ""
    if est_divible_par(nombre, 3):
        resultat += "fizz"
    if est_divible_par(nombre, 5):
        resultat += "buzz"
    if not resultat:
        resultat = str(nombre)
    print(resultat)
