# Build the recalculated blendshapes from targets to exclude transformations due to skeletal deformation
# Write skeletal transformations to a separate .skeltargets file

import os
from pxr import Usd, UsdSkel, UsdGeom, Gf, Vt
import numpy as np
import json


def blendshape_to_skeltarget(prim: Usd.Prim, blendshape_name: str, output_path: str):
    """Creates a .skeltarget file for a given blendshape. The file contains the transformations applied to the skeleton
    joints when referencing the joint helper geometry after the blendshape has been applied."""

    # Apply the blendshape to the mesh at 100% weight
    points = compute_blendshape_points(prim, blendshape_name, 0.5)

    # Move the skeleton to the points defined by the helper geometry
    skel_path = UsdSkel.BindingAPI(prim).GetSkeletonRel().GetTargets()[0]
    skel = UsdSkel.Skeleton.Get(prim.GetStage(), skel_path)
    xforms = joints_from_points(skel, points, 0)

    # Save the skeletal transformations to a .skeltarget file. A .skeltarget file is named after the blendshape it
    # corresponds to and takes the form of a JSON file with the following structure:
    # {
    #   "blendshape": "blendshape_name",
    #    "skeleton": {
    #         "joint_path": {
    #             "translation": [x, y, z],
    #             "rotation": {
    #                 "axis": [x, y, z],
    #                 "angle": angle
    #             },
    #             "scale": [x, y, z]
    #         }
    #     }
    # }
    joints = skel.GetJointsAttr().Get()
    data = {"blendshape": blendshape_name, "skeleton": {}}
    for joint, xform in zip(joints, xforms):
        xform.Orthonormalize()
        translation = list(xform.ExtractTranslation())

        rotation = xform.ExtractRotation()
        rotation = {"axis": list(rotation.GetAxis()), "angle": rotation.GetAngle()}

        scale = list(Gf.Vec3d(*(v.GetLength() for v in xform.ExtractRotationMatrix())))
        data["skeleton"][joint] = {"translation": translation, "rotation": rotation, "scale": scale}

    with open(output_path, "w") as f:
        json.dump(data, f, indent=4)

    # Skeltargets are effectively just skeletal animations, so we can also save the skeletal transformations to a .usda
    # stage = Usd.Stage.CreateInMemory()
    # skelroot = UsdSkel.Root.Define(stage, prim.GetPath().AppendChild("skeltargets"))
    # stage.SetDefaultPrim(skelroot.GetPrim())
    # skel = UsdSkel.Skeleton.Define(stage, skelroot.GetPath().AppendChild(f"skeleton_{blendshape_name}"))
    # skelCache = UsdSkel.Cache()
    # skelQuery = skelCache.GetSkelQuery(skel)
    # skel.CreateJointsAttr(skelQuery.GetJointOrder())
    # stage.GetRootLayer().Export(f"{output_path}.usda")


def calculate_skeltarget_verts(prim: Usd.Prim, skeltarget_path: str) -> np.array:
    """Applies the skeletal transformations defined in a .skeltarget file to the skeleton joints. There should be a mesh
    in the scene that is already bound and skinned to the skeleton.

    Parameters:
    ------------
    prim: Usd.Prim
        The skelroot containing the skeleton and mesh
    skeltarget_path: str
        The path to the .skeltarget file containing the skeletal transformations

    Returns:
    ------------
    np.array
        The new vertices of the mesh after the skeletal transformations have been applied

    """

    # Get the skeleton through the binding API. We assume the first target is the skeleton we want to use
    skel_path = UsdSkel.BindingAPI(prim).GetSkeletonRel().GetTargets()[0]
    skel = UsdSkel.Skeleton.Get(prim.GetStage(), skel_path)
    # Get the mesh points
    body = prim.GetChild("body")
    current_points = body.GetAttribute("points").Get()
    points = Vt.Vec3fArray(current_points)

    # Load the .skeltarget file
    with open(skeltarget_path, "r") as f:
        skeltarget = json.load(f)

    # Apply the skeletal transformations to the skeleton joints
    num_joints = len(skel.GetJointsAttr().Get())
    translations = Vt.Vec3fArray(num_joints)
    rotations = Vt.QuatfArray(num_joints)
    scales = Vt.Vec3hArray(num_joints)

    for i, (joint, data) in enumerate(skeltarget["skeleton"].items()):
        translations[i] = Gf.Vec3f(*data["translation"])

        rotation = data["rotation"]
        quatd = Gf.Rotation(rotation["axis"], rotation["angle"]).GetQuat()
        rotations[i] = Gf.Quatf(quatd)

        scales[i] = Gf.Vec3h(*data["scale"])
    
    xforms = UsdSkel.MakeTransforms(translations, rotations, scales)
    # Get the animation of the skeleton
    anim_path = UsdSkel.BindingAPI(skel).GetAnimationSourceRel().GetTargets()[0]
    anim = UsdSkel.Animation.Get(prim.GetStage(), anim_path)
    anim.SetTransforms(xforms, 0)

    # Query the skeleton and geometry, and compute the new vertices of the mesh
    skelRoot = UsdSkel.Root(prim)
    skelCache = UsdSkel.Cache()
    skelCache.Populate(skelRoot, Usd.PrimDefaultPredicate)
    skinningQuery = skelCache.GetSkinningQuery(body)
    skelQuery = skelCache.GetSkelQuery(skel)
    xformCache = UsdGeom.XformCache(0)
    world_xforms = skelQuery.ComputeJointWorldTransforms(xformCache)

    # Calculate the new vertices of the mesh
    success = skinningQuery.ComputeSkinnedPoints(world_xforms, points, time=0)
    if not success:
        raise ValueError("Failed to compute skinned points")
    # # Reset the joint positions to rest pose so they don't stack
    xforms = skelQuery.ComputeJointLocalTransforms(0, True)
    anim.SetTransforms(xforms, 0)

    return np.array(points)


def separate_blendshape(prim: Usd.Prim, blendshape: UsdSkel.BlendShape, skeltarget_path: str) -> UsdSkel.BlendShape:
    """Subtracts the mesh deformation due to skeletal transformations from deformation caused by the blendshape  to
    create a new blendshape without the corresponding skeletal transformation deformation. The resulting blendshape is
    added to the prim."""
    # Get the mesh
    body = prim.GetChild("body")
    # Get the mesh points before any transformation is applied
    default_points = body.GetAttribute("points").Get()

    # Calculate the new vertices of the blendshape after the skeletal transformations have been applied
    skel_deformation = calculate_skeltarget_verts(prim, skeltarget_path)

    # Create a new mesh with the skeletal deformation for visualization purposes
    mesh = UsdGeom.Mesh(body)
    skel_mesh = UsdGeom.Mesh.Define(prim.GetStage(), prim.GetPath().AppendChild("skel_mesh"))
    skel_mesh.GetPointsAttr().Set(Vt.Vec3fArray().FromNumpy(skel_deformation))
    skel_mesh.GetFaceVertexCountsAttr().Set(mesh.GetFaceVertexCountsAttr().Get())
    skel_mesh.GetFaceVertexIndicesAttr().Set(mesh.GetFaceVertexIndicesAttr().Get())

    # Calculate the offset between the original mesh and the mesh after skeletal deformation
    skeletal_deformation_offset = default_points - skel_deformation

    # Get the blendshape offsets
    blendshape_offsets = np.array(blendshape.GetOffsetsAttr().Get())
    blendshape_indices = np.array(blendshape.GetPointIndicesAttr().Get())

    # Subtract the skeletal deformation from the blendshape offsets at any
    corrected_offsets = blendshape_offsets - skeletal_deformation_offset[blendshape_indices]

    # Overwrite the blendshape with the corrected offsets
    blendshape.GetOffsetsAttr().Set(Vt.Vec3fArray().FromNumpy(corrected_offsets))
    blendshape.GetPointIndicesAttr().Set(Vt.IntArray().FromNumpy(blendshape_indices))

    # TODO Add custom attributes to the blendshape to store the skeletal transformations
    return blendshape


def skel_from_skeltarget(prim: Usd.Prim, skeltarget_path: str):
    '''Create a new skeleton from a .skeltarget file'''
    with open(skeltarget_path, "r") as f:
        skeltarget = json.load(f)
    
    skelroot = UsdSkel.Root.Define(prim.GetStage(), prim.GetPath().AppendChild("skeltargets"))
    skel = UsdSkel.Skeleton.Define(prim.GetStage(), skelroot.GetPath().AppendChild(f"skeleton_{skeltarget['blendshape']}"))
    skel.CreateJointsAttr(Vt.TokenArray(skeltarget["skeleton"].keys()))

    # Apply the skeletal transformations to the skeleton joints
    num_joints = len(skel.GetJointsAttr().Get())
    translations = Vt.Vec3fArray(num_joints)
    rotations = Vt.QuatfArray(num_joints)
    scales = Vt.Vec3hArray(num_joints)

    for i, (joint, data) in enumerate(skeltarget["skeleton"].items()):
        translations[i] = Gf.Vec3f(*data["translation"])

        rotation = data["rotation"]
        quatd = Gf.Rotation(rotation["axis"], rotation["angle"]).GetQuat()
        rotations[i] = Gf.Quatf(quatd)

        scales[i] = Gf.Vec3h(*data["scale"])

    xforms = UsdSkel.MakeTransforms(translations, rotations, scales)
    skel.CreateRestTransformsAttr().Set(xforms, Usd.TimeCode.Default())


def compute_blendshape_points(prim: Usd.Prim, blendshape_name: str, weight: float) -> np.array:
    """Compute the new points of a mesh after a blendshape has been applied."""
    body = prim.GetChild("body")
    mesh_binding = UsdSkel.BindingAPI(body)
    blend_query = UsdSkel.BlendShapeQuery(mesh_binding)
    # Use updated blendshape weights to compute subShapeWeights, blendShapeIndices, and subShapeIndices
    # Get just the blendshapes that apply to this mesh
    blendshapes_on_body = body.GetAttribute("skel:blendShapes").Get()
    blendshapes_on_body = np.array(blendshapes_on_body)
    # Zero out the weights for all blendshapes applied to the body
    weights_on_body = np.zeros(len(blendshapes_on_body))
    # Set the weight for the blendshape we're interested in
    index = np.where(blendshapes_on_body == blendshape_name)
    weights_on_body[index] = weight
    # Compute the new points
    subShapeWeights, blendShapeIndices, subShapeIndices = blend_query.ComputeSubShapeWeights(weights_on_body)
    blendShapePointIndices = blend_query.ComputeBlendShapePointIndices()
    subShapePointOffset = blend_query.ComputeSubShapePointOffsets()
    original_points = body.GetAttribute("points").Get()
    points_to_calculate = Vt.Vec3fArray.FromNumpy(np.array(original_points, copy=True))
    success = blend_query.ComputeDeformedPoints(
        subShapeWeights,
        blendShapeIndices,
        subShapeIndices,
        blendShapePointIndices,
        subShapePointOffset,
        points_to_calculate,
    )
    if success:
        # Compare old points to new points
        new_points = np.array(points_to_calculate)
        # See what changed
        changed = np.where(original_points != new_points)[0]
        # print(f"Changed: {changed}")
    else:
        raise ValueError("Failed to compute deformed points")

    return new_points


def joints_from_points(resize_skel: UsdSkel.Skeleton, points: Vt.Vec3fArray, time: int) -> Vt.Matrix4dArray:
    """Compute the joint transforms for a skeleton from a set of points. Requires that the skeleton has customdata
    with a mapping from each bone to its set of vertices. Transforms are returned in local space."""
    # Get mapping from each bone to its set of vertices
    bone_vertices_idxs = resize_skel.GetPrim().GetCustomData()

    # Query the resizing skeleton
    skel_cache = UsdSkel.Cache()
    skel_query = skel_cache.GetSkelQuery(resize_skel)

    # Get the list of bones
    joints = skel_query.GetJointOrder()

    # Get the points attribute as a numpy array for multi-indexing
    points = np.array(points)
    # Get transforms for each bone
    xforms = []
    for joint in joints:
        vert_idxs = np.array(bone_vertices_idxs[joint])
        verts = points[vert_idxs]
        xforms.append(compute_transform(verts))

    # Convert to local space
    xforms = Vt.Matrix4dArray().FromNumpy(np.array(xforms))
    topo = UsdSkel.Topology(joints)
    return UsdSkel.ComputeJointLocalTransforms(topo, xforms, Gf.Matrix4d(np.eye(4)))


def compute_transform(head_vertices: np.array) -> Gf.Matrix4d:
    """Compute the rest and bind transforms for a joint"""
    head_position = np.mean(head_vertices, axis=0)
    # Bind transform is in world space
    transform = np.eye(4)
    transform[:3, 3] = head_position

    return Gf.Matrix4d(transform.T)


if __name__ == "__main__":
    ext_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    data_path = os.path.join(ext_path, "data")
    stage = Usd.Stage.Open(os.path.join(data_path, "human_base.usd"))
    prim = stage.GetDefaultPrim().GetChild("skel_root")
    prim_path = prim.GetPath()
    mesh = prim.GetChild("body")
    # Get all existing blendshapes
    # for blendshape_path in UsdSkel.BindingAPI(mesh).GetBlendShapeTargetsRel().GetTargets():
    for blendshape_path in [UsdSkel.BindingAPI(mesh).GetBlendShapeTargetsRel().GetTargets()[139]]:
        blendshape = UsdSkel.BlendShape.Get(stage, blendshape_path)
        blendshape_name = blendshape.GetPrim().GetName()
        # Store the skeletal transformations in a .skeltarget file
        skeltarget_path = os.path.join(data_path, "skeltargets", f"{blendshape_name}.skeltarget")
        blendshape_to_skeltarget(prim, blendshape_name, skeltarget_path)

        # Create a new blendshape without the skeletal transformations and bind it to the mesh and animation
        skelfree_blendshape = separate_blendshape(prim, blendshape, skeltarget_path)

        # Create a new skeleton from the .skeltarget for visualization purposes
        # skel_from_skeltarget(prim, skeltarget_path)


    # Save the new stage
    stage.GetRootLayer().Save()
    print("Done")
