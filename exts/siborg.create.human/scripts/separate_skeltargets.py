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


def blendshape_to_skeltarget(stage, prim, blendshape_name, output_path):
    '''Creates a .skeltarget file for a given blendshape. The file contains the transformations applied to the skeleton
    joints when referencing the joint helper geometry after the blendshape has been applied.'''

    # Apply the blendshape to the mesh at 100% weight

    # Calculate the new vertices

    # Move the skeleton to the points defined by the helper geometry

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


def calculate_skeltarget_verts(stage, prim, skeltarget_path):
    '''Applies the skeletal transformations defined in a .skeltarget file to the skeleton joints. There should be a mesh
    in the scene that is already bound and skinned to the skeleton.

    Parameters:
    ------------
    stage: Usd.Stage
        The stage containing the mesh and skeleton
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
    for joint_path, xform in skeltarget["skeleton"].items():
        translation = Gf.Vec3d(xform["translation"])
        rotation = Gf.Quatd(xform["rotation"])
        scale = Gf.Vec3d(xform["scale"])
        xform = Gf.Matrix4d(translation, rotation, scale)
        xforms.append(xform)        
    # Calculate the new vertices of the mesh
    success = UsdSkel.SkinningQuery.ComputeSkinnedPoints(xforms, points, time=0)
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

def separate_blendshape(stage, prim, blendshape, new_blendshape_path, skeltarget_path):
    '''Applies the inverse of the skeletal transformations to the blendshape to isolate the deformation caused by the
    blendshape without the corresponding skeletal transformations. The resulting blendshape is added to the prim.'''

    # Calculate the new vertices of the blendshape after the skeletal transformations have been applied
    skel_deformation = calculate_skeltarget_verts(stage, prim, skeltarget_path)

    # Apply the blendshape to the mesh at 100% weight and calculate the new vertices of the blendshape
    body = prim.GetChild("body")
    points = compute_blendshape_points(body, blendshape, 1.0)
    # Subtract the skeletal deformation from the blendshape deformation
    # Create a new blendshape with the corrected vertices
    # Create the new blendshape
    targets_prim = stage.DefinePrim(prim.GetPath().AppendChild("skelfree_targets"))
    new_blendshape = UsdSkel.BlendShape.Define(stage, targets_prim.GetPath().AppendChild(blendshape.GetName()))
    # Add custom attributes to the blendshape to store the skeletal transformations
    return new_blendshape


def bind_target(stage, prim, new_blendshape_path):
    '''Binds the new blendshape to the mesh.

    Parameters:
    ------------
    stage: Usd.Stage
        The stage containing the mesh and skeleton
    prim: Usd.Prim
        The skelroot containing and mesh
    new_blendshape_path: str
        The path to the new blendshape to be bound to the mesh (should probably be inside the skelroot already)'''


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
