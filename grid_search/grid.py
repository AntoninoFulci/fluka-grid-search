from itertools import product


def generate_combinations(parameters: dict[str, list]) -> list[dict]:
    keys = list(parameters.keys())
    values = list(parameters.values())
    return [dict(zip(keys, combo)) for combo in product(*values)]


def combo_name(params: dict) -> str:
    return "_".join(f"{k}{v}" for k, v in params.items())
