from typing import Callable
from . import mhusd
from pxr import Usd


def get_blendshape_vals(modifier_data: dict, v: float) -> dict:
    """Construct a modifier function from the given modifier data. Used for UI callbacks when a slider is changed."""

    def _get_blendshapes_for_target(modifier_data: dict, v) -> dict:
        min_val = modifier_data["min_val"]
        max_val = modifier_data["max_val"]

        if "max_blend" in modifier_data and "min_blend" in modifier_data:
            # Modifier has two blendshapes, with opposite values around 0
            if v > 0:
                max_blend = modifier_data["max_blend"]
                return {max_blend, v} if v < max_val else {max_blend, max_val}
            else:
                min_blend = modifier_data["min_blend"]
                # Invert the value for the min blendshape, as blendshape weights are always positive but the modifier
                # value can be negative
                return {min_blend, -v} if v > min_val else {min_blend, min_val}
        elif "blend" in modifier_data:
            blend = modifier_data["blend"]
            if v > min_val and v < max_val:
                return {blend, v}
            elif v <= min_val:
                return {blend, min_val}
            else:
                return {blend, max_val}
        else:
            raise ValueError("Target modifier data must contain either a 'max_blend' and 'min_blend' or 'blend' key.")

    def _get_blendshapes_for_macrovar(modifier_data: dict, v) -> dict:
        pass

    if "macrovar" in modifier_data:
        return _get_blendshapes_for_macrovar(modifier_data, v)
    else:
        try:
            return _get_blendshapes_for_target(modifier_data, v)
        except ValueError as e:
            raise ValueError(f"Macrovar modifiers must contain a 'Macrovar' key. {e}")


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


def calculate_center_of_range(parts):
    min_value = min(part["lowest"] for part in parts)
    max_value = max(part["highest"] for part in parts)
    return (min_value + max_value) / 2


def calculate_weights_for_target(macrotargets, values):
    weights = {}
    for target, parts in macrotargets.items():
        value = values.get(target, calculate_center_of_range(parts["parts"]))  # Use center if value not provided
        for part in parts["parts"]:
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
