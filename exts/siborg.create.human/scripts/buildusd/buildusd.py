# Build the human USD file outside of Omniverse

import os

from animation import build_anim
from meshes import load_basemesh
from pxr import Sdf, Usd, UsdGeom, UsdSkel
from skeletons import build_skeleton
from targets import import_targets
from modifiers import import_modifiers


def make_human():
    # Create a stage
    stage = Usd.Stage.CreateInMemory()

    # Stage must have a valid start time code for animation to work
    stage.SetStartTimeCode(1)

    # Set the units/scale
    UsdGeom.SetStageMetersPerUnit(stage, 1.0)

    # Create a root prim
    root = stage.DefinePrim("/Human", "Xform")
    stage.SetDefaultPrim(root)

    # Define a SkelRoot.
    rootPath = Sdf.Path(f"{root.GetPath()}/skel_root")
    skel_root = UsdSkel.Root.Define(stage, rootPath)
    # Add custom data to the prim by key, designating the prim is a human
    skel_root.GetPrim().SetCustomDataByKey("human", True)

    # Get the extension path
    ext_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    # Load the base mesh from a file
    base_mesh_file = os.path.join(ext_path, "data", "3dobjs", "base.obj")
    load_basemesh(stage, rootPath, base_mesh_file)

    # Create the skeleton
    skeleton = build_skeleton(stage, skel_root, ext_path)

    prim = skel_root.GetPrim()
    # Import the modifiers
    modifiers_path = os.path.join(ext_path, "data", "modifiers", "modeling_modifiers.json")
    import_modifiers(prim, modifiers_path)

    # Import the targets
    targets_path = os.path.join(ext_path, "data", "targets", "armslegs")
    import_targets(stage, prim, targets_path)

    # Create and bind animation for blendshapes
    build_anim(stage, skeleton, ext_path, blendshapes=True)

    # Create a resizing skeleton for scaling. When blendshapes are applied, we will update the resizing skeleton
    # joints in the rest pose, and then transfer the bone lengths to the original skeleton.
    resize_skel = build_skeleton(stage, skel_root, ext_path, "resize_skeleton")
    # Move the original skeleton to the resizing skeleton's rest pose
    skelcache = UsdSkel.Cache()
    resizeSkelQuery = skelcache.GetSkelQuery(resize_skel)
    resize_skel_restxforms = resizeSkelQuery.ComputeJointLocalTransforms(0)
    skeleton.GetRestTransformsAttr().Set(resize_skel_restxforms)

    # Create and bind animation for scaling
    build_anim(stage, resize_skel, ext_path, "resize_anim")

    # Save the stage to a file
    save_path = os.path.join(ext_path, "data", "human_base.usd")
    print(f"Saving to {save_path}")
    stage.Export(save_path)


if __name__ == "__main__":
    make_human()
