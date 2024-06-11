from pxr import Sdf, Usd, UsdGeom, UsdSkel, Tf, Vt
import carb
import omni
import omni.usd
import numpy as np
import os
import warnings
from dataclasses import dataclass
from pxr import Gf, Sdf
import omni.kit.commands
from collections import OrderedDict
import json
from typing import Dict, List
import omni.timeline
@dataclass
class MeshData:
    vertices: list
    uvs: list
    normals: list
    faces: list
    vert_indices: list
    uv_indices: list
    normal_indices: list
    nface_verts: list


def make_human():


    # Get the extension path
    manager = omni.kit.app.get_app().get_extension_manager()
    ext_id = manager.get_enabled_extension_id("siborg.create.human")
    ext_path = manager.get_extension_path(ext_id)

    # Get USD context and stage
    usd_context = omni.usd.get_context()
    stage = usd_context.get_stage()

    # Stage must have a valid start time code for animation to work
    stage.SetStartTimeCode(1)

    # Get the default root prim
    root = stage.GetDefaultPrim()

    # Define a SkelRoot.
    rootPath = Sdf.Path(f"{root.GetPath()}/skel_root")
    skel_root = UsdSkel.Root.Define(stage, rootPath)
    # Add custom data to the prim by key, designating the prim is a human
    skel_root.GetPrim().SetCustomDataByKey("human", True)
    # Define a Skeleton, and associate with root.
    skeleton = UsdSkel.Skeleton.Define(stage, rootPath.AppendChild("skeleton"))
    rootBinding = UsdSkel.BindingAPI.Apply(skel_root.GetPrim())
    rootBinding.CreateSkeletonRel().AddTarget(skeleton.GetPrim().GetPath())

    # Load the base mesh
    prim = omni_load_obj(usd_context, os.path.join(ext_path, "data", "3dobjs", "base.obj"), rootPath.AppendChild("mesh"))
    # mesh = get_first_child_mesh_df(prim)

    target_names = []

    # Traverse the MakeHuman targets directory
    targets_dir = os.path.join(ext_path, "data", "targets")
    for dirpath, _, filenames in os.walk(targets_dir):
        for filename in filenames:
            # Skip non-target files
            if not filename.endswith(".target"):
                continue
            print(f"Importing {filename}")
            target = mhtarget_to_blendshapes(stage, prim, os.path.join(dirpath, filename))
            target_names.append(target)


    # Define an Animation (with blend shape weight time-samples).
    animation = UsdSkel.Animation.Define(stage, skeleton.GetPrim().GetPath().AppendChild("animation"))
    animation.CreateBlendShapesAttr().Set(target_names)
    weightsAttr = animation.CreateBlendShapeWeightsAttr(np.zeros(len(target_names)))
    weightsAttr.Set(np.zeros(len(target_names)), 0)
    weightsAttr.Set(np.ones(len(target_names)), 10)

    # Bind Skeleton to animation.
    skeletonBinding = UsdSkel.BindingAPI.Apply(skeleton.GetPrim())
    anim_path=animation.GetPrim().GetPath()
    skeletonBinding.CreateAnimationSourceRel().AddTarget(anim_path)
    

def get_first_child_mesh_df(parent_prim: Usd.Prim) -> Usd.Prim:
    # Depth-first search for the first mesh prim
    for child_prim in parent_prim.GetChildren():
        if UsdGeom.Mesh(child_prim):
            return child_prim
        else:
            return get_first_child_mesh_df(child_prim)

def mhtarget_to_blendshapes(stage, prim, path : str) -> Sdf.Path:
    """Import a blendshape from a MakeHuman target file.

    Parameters
    ----------
    stage : Usd.Stage
        The stage to import the blendshape onto.
    prim : Usd.Prim
        The prim to import the blendshape onto. Contains multiple meshes. Indices are not shared between meshes,
        so we need to create a separate blendshape for each mesh and keep track of any index offsets.
    path : str
        Path to the target file.
    """

    # Get the group directory
    group_dir = os.path.dirname(path)
    target_name = Tf.MakeValidIdentifier(os.path.splitext(os.path.basename(path))[0])
    group_name = Tf.MakeValidIdentifier(os.path.basename(group_dir))
    
    # group = stage.DefinePrim(prim.GetPath().AppendChild(group_name))
    # blendshape = UsdSkel.BlendShape.Define(stage, group.GetPath().AppendChild(target_name))

        # Load the target file
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

    # Get all the meshes. We need to determine which meshes are affected by this target
    
    meshes = prim.GetChildren()

    # The meshes' indices are not shared, so we need to keep track of the starting index for each mesh
    index_start = 0
    for mesh in meshes:
        # The next index offset is the current offset plus the number of vertices in the current mesh
        verts = len(mesh.GetAttribute("points").Get())
        index_end = index_start + verts

        if np.any(np.logical_and(changed_indices >= index_start, changed_indices < index_end)):
            print(f"{target_name} targets mesh {mesh.GetPath()}")
            # This mesh is affected by the target, so create a blendshape for it
            blendshape = UsdSkel.BlendShape.Define(stage, mesh.GetPath().AppendChild(target_name))
            indices = np.arange(verts)
            offsets = np.zeros((verts, 3), dtype=np.float32)
            mask = np.logical_and(changed_indices >= index_start, changed_indices < index_end)
            target_indices = changed_indices[mask] - index_start
            target_offsets = changed_offsets[mask]
            offsets[target_indices] = target_offsets
            # Set the indices and offsets
            blendshape.CreateOffsetsAttr().Set(offsets)
            blendshape.CreatePointIndicesAttr().Set(indices)
            # Bind mesh to blend shapes.
            meshBinding = UsdSkel.BindingAPI.Apply(mesh.GetPrim())
            meshBinding.CreateBlendShapeTargetsRel().AddTarget(blendshape.GetPath())
            # Get the existing blendshapes for this mesh
            existing_blendshapes = meshBinding.GetBlendShapesAttr().Get()
            # Add the new blendshape
            if existing_blendshapes:
                existing_blendshapes = list(existing_blendshapes)
                existing_blendshapes.append(target_name)
            else:
                existing_blendshapes = [target_name]
            # Set the updated blendshapes for this mesh.
            meshBinding.GetBlendShapesAttr().Set(existing_blendshapes)
        # Update the index offset
        index_start = index_end

    return target_name

def create_geom(stage, path:str, mesh_data: MeshData):
    """Create a UsdGeom.Mesh prim from vertices and faces.
    
    Parameters
    ----------
    stage : Usd.Stage
        The stage to create the mesh on.
    path : str
        The path at which to create the mesh prim
    vertices : np.ndarray
        An N x 3 array of vertex positions
    nPerFace : np.ndarray
        An array of length N where each element is the number of vertices in each face
    faces : np.ndarray
        An N x max(nPerFace) array of vertex indices
    """
    meshGeom = UsdGeom.Mesh.Define(stage, path)

    # Set vertices. This is a list of tuples for ALL vertices in an unassociated
    # cloud. Faces are built based on indices of this list.
    #   Example: 3 explicitly defined vertices:
    #   meshGeom.CreatePointsAttr([(-10, 0, -10), (-10, 0, 10), (10, 0, 10)]
    meshGeom.CreatePointsAttr(mesh_data.vertices)

    # Set face vertex count. This is an array where each element is the number
    # of consecutive vertex indices to include in each face definition, as
    # indices are given as a single flat list. The length of this list is the
    # same as the number of faces
    #   Example: 4 faces with 4 vertices each
    #   meshGeom.CreateFaceVertexCountsAttr([4, 4, 4, 4])
    # 
    #   Example: 4 faces with varying number of vertices
    #   meshGeom.CreateFaceVertexCountsAttr([3, 4, 5, 6])

    meshGeom.CreateFaceVertexCountsAttr(mesh_data.nface_verts)

    # Set face vertex indices.
    #   Example: one face with 4 vertices defined by 4 indices.
    #   meshGeom.CreateFaceVertexIndicesAttr([0, 1, 2, 3])
    meshGeom.CreateFaceVertexIndicesAttr(mesh_data.vert_indices)

    # Set vertex normals. Normals are represented as a list of tuples each of
    # which is a vector indicating the direction a point is facing. This is later
    # Used to calculate face normals
    #   Example: Normals for 3 vertices
    # meshGeom.CreateNormalsAttr([(0, 1, 0), (0, 1, 0), (0, 1, 0), (0, 1,
    # 0)])

    # meshGeom.CreateNormalsAttr(mesh.getNormals())
    # meshGeom.SetNormalsInterpolation("vertex")

    # Set vertex uvs. UVs are represented as a list of tuples, each of which is a 2D
    # coordinate. UV's are used to map textures to the surface of 3D geometry
    #   Example: texture coordinates for 3 vertices
    #   texCoords.Set([(0, 1), (0, 0), (1, 0)])

    texCoords = meshGeom.CreatePrimvar(
        "st", Sdf.ValueTypeNames.TexCoord2fArray, UsdGeom.Tokens.faceVarying
    )
    texCoords.Set(mesh_data.uvs)

    # # Subdivision is set to catmullClark for smooth surfaces
    meshGeom.CreateSubdivisionSchemeAttr().Set("catmullClark")

    return meshGeom.GetPrim()

def load_obj(filename, nPerFace=None):

    with open(filename, 'r') as infile:
        lines = infile.readlines()

    vertices = []
    uvs = []
    normals = []
    faces = []
    nface_verts = []

    for line in lines:
        parts = line.strip().split()
        if parts[0] == 'v':
            vertices.append(tuple(parts[1:]))
        elif parts[0] == 'vt':
            uvs.append(parts[1:])
        elif parts[0] == 'vn':
            normals.append(parts[1:])
        elif parts[0] == 'f':
            if nPerFace:
                if nPerFace > len(parts[1:]):
                    raise ValueError(f'Face has less than {nPerFace} vertices')
                faces.append(parts[1:nPerFace+1])  # Only consider the first nPerFace vertices
                nface_verts.append(nPerFace)
            else:
                faces.append(parts[1:]) # Consider all vertices
                nface_verts.append(len(parts[1:]))

    # Flat lists of face vertex indices
    vert_indices = []
    uv_indices = []
    normal_indices = []

    for face in faces:
        for i in range(len(face)):
            vert_indices.append(int(face[i].split('/')[0]) - 1)
            if uvs:
                uv_indices.append(int(face[i].split('/')[1]) - 1)
            if normals:
                normal_indices.append(int(face[i].split('/')[2]) - 1)

    # convert to Gf.Vec3f
    vertices = [Gf.Vec3f(*map(float, v)) for v in vertices]
    uvs = [Gf.Vec2f(*map(float, uv)) for uv in uvs]

    return MeshData(vertices, uvs, normals, faces, vert_indices, uv_indices, normal_indices, nface_verts)

def omni_load_obj(context, filepath, destination):
    omni.kit.commands.execute('CreatePayloadCommand',
        usd_context=context,
        path_to=destination,
        asset_path=filepath,
        instanceable=False)
    return context.get_stage().GetPrimAtPath(destination).GetChildren()[0]

def add_to_scene():
        """Imports the pre-assembled human USD file into the scene.
        """

        # Get the extension path
        manager = omni.kit.app.get_app().get_extension_manager()
        ext_id = manager.get_enabled_extension_id("siborg.create.human")
        ext_path = manager.get_extension_path(ext_id)
        filepath = os.path.join(ext_path, "data", "human_base.usd")

        # Get the stage
        usd_context = omni.usd.get_context()
        stage = usd_context.get_stage()
        default_prim = stage.GetDefaultPrim()
        prim_path = default_prim.GetPath().AppendChild("human")
        
        # Import the human into the scene

        omni.kit.commands.execute('CreatePayloadCommand',
            usd_context=usd_context,
            path_to=prim_path,
            asset_path=filepath,
            instanceable=False)

        return stage.GetPrimAtPath(prim_path)

def edit_blendshapes(prim: Usd.Prim, blendshapes: Dict[str, float], time = 0):
    """Edit the blendshapes of a human animation

    Parameters
    ----------
    prim : Usd.Prim
        A prim, containing meshes and 2 skeletons with blendshapes
    blendshapes : Dict[str, float]
        A dictionary of blendshape names to weights
    time : float, optional
        The time to set the blendshapes at, by default 1
    """
    # print(f"Blendshapes: {blendshapes}")

    # Get the stage
    usd_context = omni.usd.get_context()
    stage = usd_context.get_stage()
    skeleton_paths = UsdSkel.BindingAPI(prim).GetSkeletonRel().GetTargets()
    # Grab the the first skeleton that isn't the target skeleton. This skeleton deforms the meshes
    skeleton_path = next(path for path in skeleton_paths if path.elementString != "resize_skeleton")
    skeleton = UsdSkel.Skeleton.Get(stage, skeleton_path)
    animation_paths = UsdSkel.BindingAPI(skeleton).GetAnimationSourceRel().GetTargets()
    animation_path = next(path for path in animation_paths if path.elementString == "target_anim")
    animation = UsdSkel.Animation.Get(stage, animation_path)
    apply_weights(animation, blendshapes, time)


def add_joints_attr(skel_cache, skel, anim):
    skel_query = skel_cache.GetSkelQuery(skel)
    joints = skel_query.GetJointOrder()
    anim.GetJointsAttr().Set(joints)


def compose_xforms(source_xforms: Vt.Matrix4dArray, target_skeleton: UsdSkel.Skeleton, time: int) -> Vt.Matrix4dArray:
    source_xforms = np.array(source_xforms)
    skel_cache = UsdSkel.Cache()
    skel_query = skel_cache.GetSkelQuery(target_skeleton)
    xforms = skel_query.ComputeJointLocalTransforms(time)
    xforms = np.array(xforms)
    inv_xforms = np.linalg.inv(xforms)
    new_xforms = np.matmul(source_xforms, inv_xforms)
    new_xforms = np.matmul(new_xforms, xforms)
    return Vt.Matrix4dArray().FromNumpy(new_xforms)


def apply_weights(animation: UsdSkel.Animation, blendshapes: Dict[str, float], time=0) -> None:
    # Get existing blendshapes and weights
    current_blendshapes = animation.GetBlendShapesAttr().Get(time)
    current_weights = np.array(animation.GetBlendShapeWeightsAttr().Get(time))

    # Convert to numpy arrays
    current_blendshapes = np.array(current_blendshapes)
    current_weights = np.array(current_weights)

    for bs, w in blendshapes.items():
        # print(bs)
        if bs not in current_blendshapes:
            continue
        indices = np.where(current_blendshapes==bs)[0]
        # print(indices)
        current_weights[indices] = [w] * len(indices)

    # Set the updated weights
    animation.GetBlendShapeWeightsAttr().Set(current_weights,time)

def compute_new_points(body: Usd.Prim, animation: UsdSkel.Animation, time=0) -> Vt.Vec3fArray:
    mesh_binding = UsdSkel.BindingAPI(body)
    blend_query = UsdSkel.BlendShapeQuery(mesh_binding)
    # Use updated blendshape weights to compute subShapeWeights, blendShapeIndices, and subShapeIndices
    current_blendshapes = animation.GetBlendShapesAttr().Get(time)
    current_weights = np.array(animation.GetBlendShapeWeightsAttr().Get(time))
    current_blendshapes = np.array(current_blendshapes)
    # Get just the blendshapes that apply to this mesh
    blendshapes_on_body = body.GetAttribute("skel:blendShapes").Get()
    blendshapes_on_body = np.array(blendshapes_on_body)
    weights_on_body = current_weights[np.isin(current_blendshapes, blendshapes_on_body)]
    # Noticed while working on separate_skeltargets.py that the this line is useless. We don't use
    # the blendshapes_on_body variable anywhere else in the function so we don't need to filter the blendshapes,
    # we just need to filter the weights
    # current_blendshapes = current_blendshapes[np.isin(current_blendshapes, blendshapes_on_body)]
    current_weights = Vt.FloatArray().FromNumpy(weights_on_body)
    subShapeWeights, blendShapeIndices, subShapeIndices = blend_query.ComputeSubShapeWeights(current_weights)
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
    return points


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


def lengthen_bones_xforms(source_skeleton: UsdSkel.Skeleton, target_skeleton: UsdSkel.Skeleton, time: int) -> Vt.Matrix4dArray:
    '''Calculates new bone transforms for a skeleton by lengthening each bone to match the source skeleton.
    
    Parameters
    ----------
    source_skeleton : UsdSkel.Skeleton
        The skeleton to copy bone lengths from
    target_skeleton : UsdSkel.Skeleton
        The skeleton to copy bone lengths to
    time : int
        Time to query
    Returns
    -------
    Vt.Matrix4dArray
        The new bone transforms'''
    lengths = compute_lengths(source_skeleton, time)
    skelcache = UsdSkel.Cache()
    skelquery = skelcache.GetSkelQuery(target_skeleton)
    xforms = skelquery.ComputeJointSkelTransforms(time)
    joints = skelquery.GetJointOrder()
    new_xforms = np.zeros((len(joints), 4, 4))
    for i in range(len(joints)):
        xform = np.array(xforms[i])
        parent = skelquery.GetTopology().GetParent(i)
        if parent == -1:
            # Root bone
            new_xforms[i] = xform
            continue
        parent_xform = np.array(xforms[parent])
        length = lengths[i]
        # Get the bone direction
        direction = xform[3, :3] - parent_xform[3, :3]
        # Normalize the direction
        direction = direction / np.linalg.norm(direction)
        # Scale the direction by the length
        direction = direction * length
        # Set the new tail position
        xform[3, :3] = parent_xform[3, :3] + direction
        new_xforms[i] = xform

    close = np.allclose(new_xforms, xforms)
    world_xforms = Vt.Matrix4dArray.FromNumpy(new_xforms)
    return UsdSkel.ComputeJointLocalTransforms(skelquery.GetTopology(), world_xforms, Gf.Matrix4d(np.eye(4)))


def compute_lengths(skeleton: UsdSkel.Skeleton, time: int) -> [float]:
    '''Compute the lengths of each bone in a skeleton.
    
    Parameters
    ----------
    skeleton : UsdSkel.Skeleton
        The skeleton to compute bone lengths for
    Returns
    -------
    [float]
        Bone lengths, in joint order
    '''
    skelcache = UsdSkel.Cache()
    skelquery = skelcache.GetSkelQuery(skeleton)
    joints = skelquery.GetJointOrder()
    xforms = skelquery.ComputeJointSkelTransforms(time)
    lengths = []
    for i in range(len(joints)):
        tail_xform = np.array(xforms[i])
        parent = skelquery.GetTopology().GetParent(i)
        if parent == -1:
            # Root bone
            lengths.append(0)
            continue
        parent_xform = np.array(xforms[parent])
        length = np.linalg.norm(tail_xform[3, :3] - parent_xform[3, :3])
        lengths.append(length)
    return lengths


def compute_transform(head_vertices):
    """Compute the rest and bind transforms for a joint"""
    head_position = np.mean(head_vertices, axis=0)
    # Bind transform is in world space
    transform = np.eye(4)
    transform[:3, 3] = head_position

    return Gf.Matrix4d(transform.T)

def read_macrovars(human: Usd.Prim) -> Dict[str, float]:
    """Load the macrovars from a human prim

    Parameters
    ----------
    human : Usd.Prim
        The human prim

    Returns
    -------
    Dict[str, float]
        A dictionary of macrovar names to values
    """
    # Get the macrovars
    customdata = human.GetPrim().GetCustomData()
    macrovars = customdata.get("macrovars")
    return macrovars or {}


def write_macrovars(human: Usd.Prim, macrovars: Dict[str, float]):
    """Write the macrovars to a human prim

    Parameters
    ----------
    human : Usd.Prim
        The human prim
    macrovars : Dict[str, float]
        A dictionary of macrovar names to values
    """
    # Write the macrovars
    human.SetCustomDataByKey("macrovars", macrovars)


def read_modifiers(human: Usd.Prim) -> dict:
    """Load values for modifiers from the animation data authored on a human prim

    Parameters
    ----------
    human : Usd.Prim
        The human prim

    Returns
    -------
    Dict[str, float]
        A dictionary of modifier names to values
    """
    # Get the modifiers
    customdata = human.GetPrim().GetCustomData()
    modifiers = customdata.get("modifiers")

    # Get the animation
    skeleton_path = UsdSkel.BindingAPI(human).GetSkeletonRel().GetTargets()[0]
    skeleton = UsdSkel.Skeleton.Get(human.GetStage(), skeleton_path)
    animation_path = UsdSkel.BindingAPI(skeleton).GetAnimationSourceRel().GetTargets()[0]
    animation = UsdSkel.Animation.Get(human.GetStage(), animation_path)

    # Find any blendshapes with non-zero weights
    blendshapes = np.array(animation.GetBlendShapesAttr().Get(0))
    weights = np.array(animation.GetBlendShapeWeightsAttr().Get(0))
    blendshapes = blendshapes[weights > 0]
    # Find the modifiers that correspond to these blendshapes. Modifiers customdata is a hierarchical dictionary and
    # the blendshape names are stored in the "blend," "max_blend," or "minblend" key in the following structure:
    # group name:
    #     modifier name:
    #         blend: blendshape name XOR
    #         max_blend: blendshape name AND
    #         min_blend: blendshape name
    # 
    # Macrotarget modifiers won't have these keys but have a "macrovar" key instead, so we can ignore them
    for modifier, data in modifiers.items():

    return modifiers
