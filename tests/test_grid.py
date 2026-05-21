from grid_search.grid import generate_combinations, combo_name


def test_generate_combinations_count():
    params = {"beame": [0.05, 0.1], "mat": ["GALLIUM", "TUNGSTEN"]}
    combos = generate_combinations(params)
    assert len(combos) == 4


def test_generate_combinations_single_param():
    params = {"beame": [0.05, 0.1, 0.5]}
    combos = generate_combinations(params)
    assert len(combos) == 3
    assert all("beame" in c for c in combos)


def test_generate_combinations_values():
    params = {"beame": [0.05], "mat": ["GALLIUM"]}
    combos = generate_combinations(params)
    assert combos == [{"beame": 0.05, "mat": "GALLIUM"}]


def test_combo_name_basic():
    assert combo_name({"beame": 0.05, "mat": "GALLIUM"}) == "beame0.05_matGALLIUM"


def test_combo_name_integer_value():
    assert combo_name({"beame": 1}) == "beame1"


def test_combo_name_preserves_order():
    name = combo_name({"z": 1, "a": 2})
    assert name == "z1_a2"
