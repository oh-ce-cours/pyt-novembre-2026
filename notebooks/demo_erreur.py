primes = {"AUT-2021-000001": 1210.5, "HAB-2022-000002": 320.0}


def prime_mensuelle(num) -> float:
    return primes[num] / 12


print("Prime mensuelle : " + str(prime_mensuelle("AUT-2021-000001")))
print(prime_mensuelle("HAB-2022-00002"))
total = sum(primes.values) / len(primes)
