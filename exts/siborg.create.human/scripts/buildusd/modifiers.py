import json
from collections import defaultdict
from pxr import Tf
import os


class Modifier:
    """Generic class for a modifier. Subclasses are TargetModifier and MacroModifier. Should not be directly instantiated."""

    def __init__(self):
        self.data = {}


class TargetModifier(Modifier):
    """A class holding the data and methods for a modifier that targets specific blendshapes.
    blend: str
        The base name of the blendshape(s) to modify
    min_blend: str, optional
        Suffix (appended to `blendshape`) naming the blendshape for decreasing the value. Empty string by default.
    max_blend: str, optional
        Suffix (appended to `blendshape`) naming the blendshape for increasing the value. Empty string by default.
    min_val: float, optional
        The minimum value for the parameter. By default 0
    max_val: float, optional
        The maximum value for the parameter. By default 1
    image: str, optional
        The path to the image to use for labeling. By default None
    label: str, optional
        The label to use for the modifier. By default is target basename capitalized.
    """

    def __init__(self, group, modifier_data: dict):
        super().__init__()
        if "target" in modifier_data:
            self.data["group"] = group
            tlabel = modifier_data["target"].split("-")
            if "|" in tlabel[len(tlabel) - 1]:
                tlabel = tlabel[:-1]
            if len(tlabel) > 1 and tlabel[0] == group:
                label = tlabel[1:]
            else:
                label = tlabel
            self.data["label"] = " ".join([word.capitalize() for word in label])
            # Guess a suitable image path from modifier name
            tlabel = modifier_data["target"].replace("|", "-").split("-")
        else:
            print(f"No target for modifier {str(modifier_data)}. Is this a macrovar modifier?")
            return
        # Blendshapes are named based on the modifier name
        self.data["blend"] = Tf.MakeValidIdentifier(modifier_data["target"])
        self.data["min_blend"] = None
        self.data["max_blend"] = None
        if "min" in modifier_data and "max" in modifier_data:
            # Some modifiers adress two blendshapes in either direction
            self.data["min_blend"] = Tf.MakeValidIdentifier(f"{self.data['blend']}_{modifier_data['min']}")
            self.data["max_blend"] = Tf.MakeValidIdentifier(f"{self.data['blend']}_{modifier_data['max']}")
            self.data["blend"] = None
            self.data["min_val"] = -1
        else:
            # Some modifiers only adress one blendshape
            self.data["min_val"] = 0
        # Modifiers either in the range [0,1] or [-1,1]
        self.data["max_val"] = 1


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


def import_modifiers(prim, modifiers_path):
    """Import modifiers from a JSON file. Write customdata to the prim to store the modifiers."""
    groups = defaultdict(dict)
    import_macrodata_mappings(os.path.join(os.path.dirname(modifiers_path), "macro.json"))
    with open(modifiers_path, "r") as f:
        data = json.load(f)
        for group in data:
            groupname = group["group"].capitalize()
            for modifier_data in group["modifiers"]:
                if "target" in modifier_data:
                    modifier = TargetModifier(groupname, modifier_data)
                elif "macrovar" in modifier_data:
                    modifier = MacroModifier(groupname, modifier_data)
                # Add the modifier to the group
                groups[groupname][modifier.data["label"]] = modifier.data

    custom_data = json.dumps(groups, indent=4)
    prim.SetCustomDataByKey("modifiers", custom_data)


macrodata: dict = {}
"""The macrodata dictionary containing all macrovars and their parts, for mapping from modifiers to specific targets"""


def calculate_center_of_range(parts):
    min_value = min(part["lowest"] for part in parts)
    max_value = max(part["highest"] for part in parts)
    return (min_value + max_value) / 2


def import_macrodata_mappings(filepath):
    global macrodata
    macrodata = load_json_data(filepath)


def load_json_data(filepath):
    with open(filepath, "r") as f:
        return json.load(f)
