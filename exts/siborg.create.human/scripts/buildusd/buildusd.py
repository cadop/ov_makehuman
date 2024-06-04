# Build the human USD file outside of Omniverse

import os

from animation import build_blend_anim, build_scale_anim
from mesh import MeshData, create_geom, load_obj
from pxr import Sdf, Usd, UsdGeom, UsdSkel
from skeleton import build_skeleton
from targets import import_modifiers, mhtarget_to_blendshapes


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

    # Load the base mesh from a file
    ext_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    base_mesh_file = os.path.join(ext_path, "data", "3dobjs", "base.obj")
    meshes = load_obj(base_mesh_file)
    meshes = combine_joint_meshes(meshes)
    for m in meshes:
        create_geom(stage, rootPath.AppendChild(m.name), m)

    # Create the skeleton
    skeleton = build_skeleton(stage, skel_root, ext_path)

    prim = skel_root.GetPrim()
    # Import the modifiers
    modifiers_path = os.path.join(ext_path, "data", "modifiers", "modeling_modifiers.json")
    # Traverse the MakeHuman targets directory
    targets_dir = os.path.join(ext_path, "data", "targets", "armslegs")
    for dirpath, _, filenames in os.walk(targets_dir):
        for filename in filenames:
            # Skip non-target files
            if not filename.endswith(".target"):
                continue
            print(f"Importing {filename}")
            mhtarget_to_blendshapes(stage, prim, os.path.join(dirpath, filename))

    import_modifiers(prim, modifiers_path)

    # Create and bind animation for blendshapes
    build_blend_anim(stage, skeleton, ext_path)

    # Create a resizing skeleton for scaling. When blendshapes are applied, we will update the resizing skeleton
    # joints in the rest pose, and then transfer the bone lengths to the original skeleton.
    resize_skel = build_skeleton(stage, skel_root, ext_path, "resize_skeleton")
    # Move the original skeleton to the resizing skeleton's rest pose
    skelcache = UsdSkel.Cache()
    resizeSkelQuery = skelcache.GetSkelQuery(resize_skel)
    resize_skel_restxforms = resizeSkelQuery.ComputeJointLocalTransforms(0)
    skeleton.GetRestTransformsAttr().Set(resize_skel_restxforms)

    # Create and bind animation for scaling
    build_scale_anim(stage, resize_skel, ext_path)

    # Save the stage to a file
    save_path = os.path.join(ext_path, "data", "human_base.usd")
    print(f"Saving to {save_path}")
    stage.Export(save_path)


def combine_joint_meshes(meshes):
    joints, non_joints = [], []
    for m in meshes:
        if m.name.startswith("joint"):
            joints.append(m)
        else:
            non_joints.append(m)
    meshes = non_joints
    # Combine the joint meshes into a single mesh
    vertices = joints[0].vertices
    uvs = joints[0].uvs
    normals = joints[0].normals
    face_verts = []
    vertex_idxs = []
    uv_idxs = []
    normal_idxs = []
    for m in joints:
        face_verts.extend(m.nface_verts)
        vertex_idxs.extend(m.vert_indices)
        uv_idxs.extend(m.uv_indices)
        normal_idxs.extend(m.normal_indices)
    # Create a new mesh
    joint_mesh = MeshData("joints", vertices, uvs, normals, vertex_idxs, uv_idxs, normal_idxs, face_verts)
    meshes.append(joint_mesh)
    return meshes


if __name__ == "__main__":
    make_human()
