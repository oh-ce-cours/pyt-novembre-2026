from fizz_buzz_qualite import est_divisible_par


def test_est_divisible_par():
    assert est_divisible_par(3, 3) is True


def test_est_divisible_par_false():
    assert est_divisible_par(5, 5) is True
    assert est_divisible_par(15, 3) is True
    assert est_divisible_par(15, 5) is True
    assert est_divisible_par(15, 4) is False
