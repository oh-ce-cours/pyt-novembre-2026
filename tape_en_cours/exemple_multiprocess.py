from multiprocessing import Pool
import time


def traitement(x):
    time.sleep(10)  # Simulate some work
    return x * x


if __name__ == "__main__":
    with Pool(5) as p:
        print(p.map(traitement, range(20)))
