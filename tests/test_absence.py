from betsuggester.features import absence_numbers, rotation_snapshot


def test_only_rotation_players_count_as_missing():
    history = [("Star", 34.0, 25.0), ("Bench", 6.0, 2.0), ("Starter", 28.0, 12.0)]
    rot = rotation_snapshot(history)
    assert set(rot) == {"Star", "Starter"}
    assert absence_numbers(rot, {"Star", "Bench"}) == {"out_min": 34.0, "out_stat": 25.0, "n_out": 1}


def test_nobody_missing():
    assert absence_numbers({"A": (30.0, 10.0)}, set()) == {"out_min": 0, "out_stat": 0, "n_out": 0}
