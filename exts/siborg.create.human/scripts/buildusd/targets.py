import numpy as np
import os
import json
import warnings
from collections import defaultdict
from pxr import UsdGeom, UsdSkel, Sdf, Tf
from typing import List


class TargetModifier:
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
        if "target" in modifier_data:
            tlabel = modifier_data["target"].split("-")
            if "|" in tlabel[len(tlabel) - 1]:
                tlabel = tlabel[:-1]
            if len(tlabel) > 1 and tlabel[0] == group:
                label = tlabel[1:]
            else:
                label = tlabel
            self.label = " ".join([word.capitalize() for word in label])
            # Guess a suitable image path from modifier name
            tlabel = modifier_data["target"].replace("|", "-").split("-")
            # image = modifier_image(("%s.png" % "-".join(tlabel)).lower())
            self.image = None
        else:
            print(f"No target for modifier {self.full_name}. Is this a macrovar modifier?")
            return
        # Blendshapes are named based on the modifier name
        self.blend = Tf.MakeValidIdentifier(modifier_data["target"])
        self.min_blend = None
        self.max_blend = None
        if "min" in modifier_data and "max" in modifier_data:
            # Some modifiers adress two blendshapes in either direction
            self.min_blend = Tf.MakeValidIdentifier(f"{self.blend}_{modifier_data['min']}")
            self.max_blend = Tf.MakeValidIdentifier(f"{self.blend}_{modifier_data['max']}")
            self.blend = None
            self.min_val = -1
        else:
            # Some modifiers only adress one blendshape
            self.min_val = 0
        # Modifiers either in the range [0,1] or [-1,1]
        self.max_val = 1


def import_modifiers(prim, modifiers_path):
    """Import modifiers from a JSON file. Write customdata to the prim to store the modifiers."""
    groups = defaultdict(list)
    modifiers = []
    with open(modifiers_path, "r") as f:
        data = json.load(f)
        for group in data:
            groupname = group["group"].capitalize()
            for modifier_data in group["modifiers"]:
                if "target" in modifier_data:
                    modifier = TargetModifier(groupname, modifier_data)
                elif "macrovar" in modifier_data:
                    print("Macrovar modifiers not yet implemented")
                    break
                    # raise NotImplementedError("Macrovar modifiers not yet implemented")
                    # modifier = MacroModifier(groupname, modifier_data)
                # Add the modifier to the group
                groups[groupname].append(modifier)
                # Add the modifier to the list of all modifiers (for tracking changes)
                modifiers.append(modifier)
    # Write the modifiers to the prim
    groups_custom_data = {}
    for group, modifier_list in groups.items():
        for modifier in modifier_list:
            modifier_custom_data = {
                # "label": modifier.label,
                "min_val": modifier.min_val,
                "max_val": modifier.max_val,
                "blend": modifier.blend,
                "min_blend": modifier.min_blend,
                "max_blend": modifier.max_blend,
            }
            # Remove None values
            modifier_custom_data = {k: v for k, v in modifier_custom_data.items() if v is not None}
            groups_custom_data[group] = modifier_custom_data
            prim.SetCustomDataByKey("modifiers", groups_custom_data)


def mhtarget_to_blendshapes(stage, prim, path: str) -> List[Sdf.Path]:
    """Import a blendshape from a MakeHuman target file.

    Parameters
    ----------
    stage : Usd.Stage
        The stage to import the blendshape onto.
    prim : Usd.Prim
        The prim to import the blendshape onto. Contains multiple meshes.
    path : str
        Path to the target file.
    """

    # The original ranges for the indices of the mesh vertices
    # See http://www.makehumancommunity.org/wiki/Documentation:Basemesh
    # index_ranges = {
    #     'body': (0, 13379),
    #     'helper_tongue': (13380, 13605),
    #     'joints': (13606, 14597),
    #     'helper_x_eye': (14598, 14741),
    #     'helper_x_eyelashes-y': (14742, 14991),
    #     'helper_lower_teeth': (14992, 15059),
    #     'helper_upper_teeth': (15060, 15127),
    #     'helper_genital': (15128, 15327),
    #     'helper_tights': (15328, 18001),
    #     'helper_skirt': (18002, 18721),
    #     'helper_hair': (18722, 19149),
    #     'ground': (19150, 19157)
    # }

    # Create a prim to hold the blendshapes. It's just a container for the blendshapes so it doesn't need a type.
    targets_prim = stage.DefinePrim(prim.GetPath().AppendChild("targets"))
    path_components = path.split(os.path.sep)[path.split(os.path.sep).index("targets") + 1 : -1]
    group_name = Tf.MakeValidIdentifier(path_components[0])
    target_basename = os.path.splitext(os.path.basename(path))[0]
    prefix = "_".join(path_components[1:]) or ""
    target_name = f"{prefix}_{target_basename}" if prefix else target_basename
    target_name = Tf.MakeValidIdentifier(target_name)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            raw = np.loadtxt(path, dtype=np.float32)
            # The first column is the vertex index, the rest are the offsets.
    except Warning as e:
        print(f"Warning: {e}")
        # Some of the files are empty, so just skip them
        return

    # The first column is the vertex index, the rest are the offsets.
    changed_indices = raw[:, 0].astype(np.int32)
    changed_offsets = raw[:, 1:]
    group = stage.DefinePrim(targets_prim.GetPath().AppendChild(group_name))
    blendshape = UsdSkel.BlendShape.Define(stage, group.GetPath().AppendChild(target_name))
    indices = np.array(changed_indices)
    offsets = changed_offsets[np.isin(changed_indices, indices)]
    blendshape.CreateOffsetsAttr().Set(offsets)
    blendshape.CreatePointIndicesAttr().Set(indices)

    # Get all the meshes. We need to determine which meshes are affected by this target

    meshes = [child for child in prim.GetChildren() if child.IsA(UsdGeom.Mesh)]

    for mesh in meshes:
        vert_idxs = mesh.GetAttribute("faceVertexIndices").Get()
        index_start = np.min(vert_idxs)
        index_end = np.max(vert_idxs) + 1
        if np.any(np.logical_and(changed_indices >= index_start, changed_indices < index_end)):
            print(f"{target_name} targets mesh {mesh.GetPath()}")
            # This mesh is affected by the target, so bind it to the blendshape
            meshBinding = UsdSkel.BindingAPI.Apply(mesh.GetPrim())
            meshBinding.CreateBlendShapeTargetsRel().AddTarget(blendshape.GetPath())
            # Get the existing blendshapes for this mesh
            existing_blendshapes = meshBinding.GetBlendShapesAttr().Get()
            bound_blendshapes = [b.name for b in meshBinding.GetBlendShapeTargetsRel().GetTargets()]
            # Add the new blendshape
            if existing_blendshapes:
                if target_name in existing_blendshapes:
                    print(f"Blendshape {target_name} already exists on {mesh.GetPath()}")
                    continue
                existing_blendshapes = list(existing_blendshapes)
                existing_blendshapes.append(target_name)
            else:
                existing_blendshapes = [target_name]
            if len(existing_blendshapes) != len(bound_blendshapes):
                bound_set = set(bound_blendshapes)
                existing_set = set(existing_blendshapes)
                unbound = existing_set.difference(bound_set)
                mismatched = bound_set.difference(existing_set)
                print(f"Blendshapes {unbound} exist but are not bound")
                print(f"Blendshapes {mismatched} are bound but do not exist")
            # Set the updated blendshapes for this mesh.
            meshBinding.GetBlendShapesAttr().Set(existing_blendshapes)


def import_targets(stage, prim, targets_dir: str):
    # Traverse the MakeHuman targets directory
    for dirpath, _, filenames in os.walk(targets_dir):
        for filename in filenames:
            # Skip non-target files
            if not filename.endswith(".target"):
                continue
            print(f"Importing {filename}")
            mhtarget_to_blendshapes(stage, prim, os.path.join(dirpath, filename))
