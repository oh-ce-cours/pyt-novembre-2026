def est_divisible_par(dessus: int, dessous: int) -> bool:
    """ """
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
