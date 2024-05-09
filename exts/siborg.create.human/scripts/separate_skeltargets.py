# Build the recalculated blendshapes from targets to exclude transformations due to skeletal deformation
# Write skeletal transformations to a separate .skeltargets file
# This script 

import os
from pxr import Usd, Sdf, UsdSkel, Tf, UsdGeom, Gf
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

    # Load the .skeltarget file
    # Apply the skeletal transformations to the skeleton joints
    # Calculate the new vertices of the mesh


def separate_blendshape(stage, prim, blendshape, new_blendshape_path, skeltarget_path):
    '''Applies the inverse of the skeletal transformations to the blendshape to isolate the deformation caused by the
    blendshape without the corresponding skeletal transformations. The resulting blendshape is added to the prim.'''

    # Calculate the new vertices of the blendshape after the skeletal transformations have been applied
    skel_deformation = calculate_skeltarget_verts(stage, prim, skeltarget_path)

    # Apply the blendshape to the mesh at 100% weight
    # Calculate the new vertices of the blendshape
    # Subtract the skeletal deformation from the blendshape deformation
    # Create a new blendshape with the corrected vertices
    # Create the new blendshape
    targets_prim = stage.DefinePrim(prim.GetPath().AppendChild("skelfree_targets"))
    new_blendshape = UsdSkel.BlendShape.Define(stage, targets_prim.GetPath().AppendChild(blendshape.GetName()))
    # Add custom attributes to the blendshape to store the skeletal transformations
    return new_blendshape


def apply_target(stage, prim, new_blendshape_path):
    '''Binds the new blendshape to the mesh.
    
    Parameters:
    ------------
    stage: Usd.Stage
        The stage containing the mesh and skeleton
    prim: Usd.Prim
        The skelroot containing and mesh
    new_blendshape_path: str
        The path to the new blendshape to be applied to the mesh (should probably be inside the skelroot already)'''
