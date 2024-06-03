import json


def calculate_weight_for_part(part, value):
    lower_bound = part["lowest"]
    upper_bound = part["highest"]
    if lower_bound <= value <= upper_bound:
        range_span = upper_bound - lower_bound
        if range_span == 0:
            return None  # Avoid division by zero
        weight_high = (value - lower_bound) / range_span
        return {"low": part["low"], "high": part["high"], "weight_low": 1 - weight_high, "weight_high": weight_high}
    return None


def calculate_weights_for_target(macrotargets, values):
    weights = {}
    for target, value in values.items():
        parts = macrotargets[target]["parts"]
        for part in parts:
            weight = calculate_weight_for_part(part, value)
            if weight:
                weights[target] = weight
                break
    return weights


def compose_filenames(combinations, weights):
    filenames = {}
    for combo_name, combo_parts in combinations.items():
        parts = []
        combo_weights = 1
        for part in combo_parts:
            if part in weights:
                weight_info = weights[part]
                low_label = weight_info["low"]
                high_label = weight_info["high"]
                # Choose label based on higher weight
                chosen_label = low_label if weight_info["weight_low"] > weight_info["weight_high"] else high_label
                parts.append(chosen_label)
                combo_weights *= max(weight_info["weight_low"], weight_info["weight_high"])
            else:
                parts.append("unknown")  # Placeholder if no weight data is available

        filename = "-".join(parts) + ".target"
        filenames[filename] = combo_weights
    return filenames


def normalize_weights(filenames):
    total_weight = sum(filenames.values())
    if total_weight == 0:
        return filenames  # Avoid division by zero
    # Normalize each weight by dividing by the total weight
    for key in filenames:
        filenames[key] /= total_weight
    return filenames


def load_json_data(filepath):
    with open(filepath, "r") as file:
        data = json.load(file)
    return data
