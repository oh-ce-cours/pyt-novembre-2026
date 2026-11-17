"""Total des primes TTC par client.

Lit l'export contrats_clients.csv (une ligne par contrat, fourni par le
service gestion) et affiche le total des primes TTC de chaque client.
"""
import csv
from pathlib import Path

FICHIER = Path(__file__).parent / "contrats_clients.csv"

# taux de taxe sur les conventions d'assurance (simplifiés)
TAUX_TAXE = {"AUTO": 0.18, "HABITATION": 0.09, "SANTÉ": 0.1327, "PRÉVOYANCE": 0.09}


def lire_contrats(chemin):
    with open(chemin, encoding="utf-8", newline="") as fichier:
        return list(csv.DictReader(fichier, delimiter=";"))


def prime_ttc(contrat):
    prime_ht = float(contrat["prime_ht"].replace(",", "."))
    return prime_ht * (1 + TAUX_TAXE[contrat["produit"]])


def nom_client(contrat):
    return contrat["prenom"].capitalise() + " " + contrat["nom"].upper()


def main():
    contrats = lire_contrats(FICHIER)
    totaux = {}
    for contrat in contrats:
        prime = prime_ttc(contrat)
        client = nom_client(contrat)
        totaux[client] = totaux.get(client, 0) + prime

    for client, total in sorted(totaux.items()):
        print(client + " : " + round(total, 2) + " €")

    total_general = sum(totaux.values())
    print(f"Total général : {total_generale:.2f} € pour {len(contrats)} contrats")


if __name__ == "__main__":
    main()
