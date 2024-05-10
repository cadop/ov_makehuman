# Build the recalculated blendshapes from targets to exclude transformations due to skeletal deformation
# Write skeletal transformations to a separate .skeltargets file
# This script 

import os
from pxr import Usd, Sdf, UsdSkel, Tf, UsdGeom, Gf,Vt
import numpy as np
import warnings
from dataclasses import dataclass
from typing import List
import json


def blendshape_to_skeltarget(prim, blendshape_name, output_path):
    '''Creates a .skeltarget file for a given blendshape. The file contains the transformations applied to the skeleton
    joints when referencing the joint helper geometry after the blendshape has been applied.'''

    # Apply the blendshape to the mesh at 100% weight
    body = prim.GetChild("body")
    points = compute_blendshape_points(body, blendshape_name, 1.0)
    # Move the skeleton to the points defined by the helper geometry
    skel = UsdSkel.BindingAPI(prim).GetSkeletonRel().GetTargets()[0]
    xforms = joints_from_points(skel, points, 0)

    # Save the skeletal transformations to a .skeltarget file. A .skeltarget file is named after the blendshape it
    # corresponds to and takes the form of a JSON file with the following structure:
    # {
    #   "blendshape": "blendshape_name",
    #    "skeleton": {
    #         "joint_path": {
    #             "translation": [x, y, z],
    #             "rotation": [x, y, z, w],
    #             "scale": [x, y, z]
    #         }
    #     }
    # }
    joints = skel.GetJointsAttr()
    data = {"blendshape": blendshape_name, "skeleton": {}}
    for joint, xform in zip(joints, xforms):
        translation = list(xform.ExtractTranslation())
        rotation = list(xform.ExtractRotation().GetQuaternion())
        scale = list(xform.ExtractScale())
        data["skeleton"][joint.GetPath().PathString] = {
            "translation": translation,
            "rotation": rotation,
            "scale": scale
        }

    with open("{output_path}.json", 'w') as f:
        json.dump(data, f, indent=4)

    # Skeltargets are effectively just skeletal animations, so we can also save the skeletal transformations to a .usda
    stage = Usd.Stage.CreateInMemory()
    skelroot = UsdSkel.Root.Define(stage, prim.GetPath().AppendChild("skeltargets"))
    stage.setDefaultPrim(skelroot.GetPrim())
    skel = UsdSkel.Skeleton.Define(stage, skelroot.GetPath().AppendChild("skeleton_{blendshape_name}"))
    topo = UsdSkel.Topology(joints)
    skel.CreateJointsAttr(topo.GetJointOrder())
    stage.GetRootLayer().Export("{output_path}.usda")


def calculate_skeltarget_verts(prim, skeltarget_path) -> np.array: 
    '''Applies the skeletal transformations defined in a .skeltarget file to the skeleton joints. There should be a mesh
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

    '''

    # Get the skeleton through the binding API. We assume the first target is the skeleton we want to use
    skel = UsdSkel.BindingAPI(prim).GetSkeletonRel().GetTargets()[0]
    # Get the mesh points
    body = prim.GetChild("body")
    current_points = body.GetAttribute("points").Get()
    points = np.array(current_points)
    points = Vt.Vec3fArray().FromNumpy(np.copy(points))

    # Load the .skeltarget file
    with open(skeltarget_path, 'r') as f:
        skeltarget = json.load(f)
    # Apply the skeletal transformations to the skeleton joints
    xforms = Vt.Matrix4dArray()
    for _, xform in skeltarget["skeleton"].items():
        translation = Gf.Vec3d(xform["translation"])
        rotation = Gf.Quatd(xform["rotation"])
        scale = Gf.Vec3d(xform["scale"])
        xform = Gf.Matrix4d()
        xform.SetTranslate(translation)
        xform.SetRotate(rotation)
        xform.SetScale(scale)
        xforms.append(xform)
    # Calculate the new vertices of the mesh
    skelCache = UsdSkel.Cache()
    skelQuery = skelCache.GetSkelQuery(skel)
    success = skelQuery.ComputeSkinnedPoints(xforms, points, time=0)
    if not success:
        raise ValueError("Failed to compute skinned points")
    return points


def compose_xforms(source_xforms: Vt.Matrix4dArray, target_skeleton: UsdSkel.Skeleton, time: int = 0) -> Vt.Matrix4dArray:
    source_xforms = np.array(source_xforms)
    skel_cache = UsdSkel.Cache()
    skel_query = skel_cache.GetSkelQuery(target_skeleton)
    xforms = skel_query.ComputeJointLocalTransforms(time)
    xforms = np.array(xforms)
    inv_xforms = np.linalg.inv(xforms)
    new_xforms = np.matmul(source_xforms, inv_xforms)
    new_xforms = np.matmul(new_xforms, xforms)
    return Vt.Matrix4dArray().FromNumpy(new_xforms)

def separate_blendshape(stage, prim, blendshape, skeltarget_path):
    '''Subtracts the mesh deformation due to skeletal transformations from deformation caused by the blendshape  to
    create a new blendshape without the corresponding skeletal transformation deformation. The resulting blendshape is
    added to the prim.'''
    # Get the mesh
    body = prim.GetChild("body")
    # Get the mesh points before any transformation is applied
    default_points = body.GetAttribute("points").Get()

    # Calculate the new vertices of the blendshape after the skeletal transformations have been applied
    skel_deformation = calculate_skeltarget_verts(prim, skeltarget_path)
    # Calculate the offset between the original mesh and the mesh after skeletal deformation
    skeletal_deformation_offset = default_points - skel_deformation

    # Get the blendshape offsets
    blendshape_offsets = np.array(blendshape.GetOffsetsAttr().Get())
    blendshape_indices = np.array(blendshape.GetPointIndicesAttr().Get())

    # Subtract the skeletal deformation from the blendshape offsets at any 
    corrected_offsets = blendshape_offsets - skeletal_deformation_offset[blendshape_indices]

    # Create a new blendshape with the corrected vertices
    # Create the new blendshape
    targets_prim = stage.DefinePrim(prim.GetPath().AppendChild("skelfree_targets"))
    new_blendshape = UsdSkel.BlendShape.Define(stage, targets_prim.GetPath().AppendChild(blendshape.GetPrim().GetName()))
    new_blendshape.CreateOffsetsAttr().Set(Vt.Vec3fArray().FromNumpy(corrected_offsets))
    new_blendshape.CreatePointIndicesAttr().Set(Vt.IntArray().FromNumpy(blendshape_indices))

    # Add custom attributes to the blendshape to store the skeletal transformations
    return new_blendshape


def bind_target(prim, blendshape):
    '''Binds the new blendshape to the mesh.

    Parameters:
    ------------
    prim: Usd.Prim
        The skelroot containing and mesh
    blendshape: BlendShape
        The blendshape to be bound to the mesh (should probably be inside the skelroot already)'''
    # Get the mesh
    body = prim.GetChild("body")
    meshBinding = UsdSkel.BindingAPI.Apply(body.GetPrim())
    meshBinding.CreateBlendShapeTargetsRel().AddTarget(blendshape.GetPath())

def compute_blendshape_points(body: Usd.Prim, blendshape, weight) -> np.array:
    '''Compute the new points of a mesh after a blendshape has been applied.'''
    mesh_binding = UsdSkel.BindingAPI(body)
    blend_query = UsdSkel.BlendShapeQuery(mesh_binding)
    # Use updated blendshape weights to compute subShapeWeights, blendShapeIndices, and subShapeIndices
    # Get just the blendshapes that apply to this mesh
    blendshapes_on_body = body.GetAttribute("skel:blendShapes").Get()
    blendshapes_on_body = np.array(blendshapes_on_body)
    # Zero out the weights for all blendshapes applied to the body
    weights_on_body = np.zeros(len(blendshapes_on_body))
    # Set the weight for the blendshape we're interested in
    weights_on_body[np.isin(blendshape, blendshapes_on_body)] = weight
    # Compute the new points
    subShapeWeights, blendShapeIndices, subShapeIndices = blend_query.ComputeSubShapeWeights(weights_on_body)
    blendShapePointIndices = blend_query.ComputeBlendShapePointIndices()
    subShapePointOffset = blend_query.ComputeSubShapePointOffsets()
    current_points = body.GetAttribute("points").Get()
    points = np.array(current_points)
    points = Vt.Vec3fArray().FromNumpy(np.copy(points))
    success = blend_query.ComputeDeformedPoints(subShapeWeights,
                                                blendShapeIndices,
                                                subShapeIndices,
                                                blendShapePointIndices,
                                                subShapePointOffset,
                                                points)
    if success:
        # Compare old points to new points
        old_points = np.array(current_points)
        new_points = np.array(points)
        # See what changed
        changed = np.where(old_points != new_points)[0]
        # print(f"Changed: {changed}")
    else:
        raise ValueError("Failed to compute deformed points")

    return new_points


def joints_from_points(resize_skel: UsdSkel.Skeleton, points: Vt.Vec3fArray, time: int):
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

    xforms = Vt.Matrix4dArray().FromNumpy(np.array(xforms))
    topo = UsdSkel.Topology(joints)
    return UsdSkel.ComputeJointLocalTransforms(topo, xforms, Gf.Matrix4d(np.eye(4)))


def compute_transform(head_vertices):
    """Compute the rest and bind transforms for a joint"""
    head_position = np.mean(head_vertices, axis=0)
    # Bind transform is in world space
    transform = np.eye(4)
    transform[:3, 3] = head_position

    return Gf.Matrix4d(transform.T)
