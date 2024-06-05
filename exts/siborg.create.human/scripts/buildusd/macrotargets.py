import json
from pxr import Usd
from targets import Modifier


class MacroModifier(Modifier):
    """A class holding the data and methods for a modifier that targets multiple blendshapes by modifying interdependent variables."""

    def __init__(self, group: str, modifier_data: dict):
        super().__init__()
        if not macrodata:
            raise ValueError("Macrodata must be loaded before creating a MacroModifier instance.")
        if "macrovar" not in modifier_data:
            print(f"No macrovar for modifier {str(modifier_data)}. Is this a target modifier?")
            return

        # If the group name is hyphenated, the first part is the group name and the second part is the prefix
        # for targets affected by this macrovar
        if "-" in group:
            self.data["group"] = group.split("-")[0]
            self.data["targetsprefix"] = group.split("-")[1]
        else:
            self.data["group"] = group
            self.data["targetsprefix"] = ""

        # Macrovars are always in the range [0,1]
        self.data["min_val"] = 0
        self.data["max_val"] = 1

        self.isEthnicModifier = modifier_data.get("modifierType") == "EthnicModifier"
        if self.isEthnicModifier:
            # TODO Uppercase the label
            self.data["label"] = modifier_data["macrovar"]
            self.data["parts"] = None
            self.data["center"] = None
            return

        # Get the macrodata based on the modifier macrovar
        self.data["macrovar"] = modifier_data["macrovar"].lower()
        macrovar_data = macrodata["macrotargets"][self.data["macrovar"]]
        self.data["label"] = macrovar_data["label"]
        self.data["parts"] = macrovar_data["parts"]
        self.data["center"] = calculate_center_of_range(self.data["parts"])


macrodata: dict = {}
"""The macrodata dictionary containing all macrovars and their parts, for mapping from modifiers to specific targets"""


def import_macrodata_mappings(filepath):
    global macrodata
    macrodata = load_json_data(filepath)


# NOTE: The stuff below needs to run in real time, so really it should be a part of the extension or exposed
# as a part of an API. This is just a proof of concept for now.


def calculate_center_of_range(parts):
    min_value = min(part["lowest"] for part in parts)
    max_value = max(part["highest"] for part in parts)
    return (min_value + max_value) / 2


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


def load_json_data(filepath):
    with open(filepath, "r") as file:
        data = json.load(file)
    return data
