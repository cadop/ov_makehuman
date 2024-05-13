# Build the human USD file outside of Omniverse

import os
from pxr import Usd, Sdf, UsdSkel, Tf, UsdGeom, Gf
import numpy as np
import warnings
from dataclasses import dataclass
from typing import List
import json
from collections import defaultdict

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

    # Get all meshes that are not joints
    non_joint_meshes = [m for m in skel_root.GetPrim().GetChildren() if m.IsA(UsdGeom.Mesh) and not m.GetName().startswith("joint")]
    rig = load_skel_json(os.path.join(ext_path, "data","rigs","default.mhskel"))
    verts = np.array(non_joint_meshes[0].GetPrim().GetAttribute("points").Get())
    skeleton = create_skeleton(stage, skel_root, rig, verts)

    weights_json = os.path.join(ext_path, "data","rigs","default_weights.mhw")
    joint_indices, weights = vertices_to_weights(skeleton.GetJointNamesAttr().Get(), weights_json, skel_root.GetPrim().GetChildren()[0])
    elements = joint_indices.shape[1]

    # bind the skeleton to each non-joint mesh
    for mesh in non_joint_meshes:
        meshBinding = UsdSkel.BindingAPI.Apply(mesh.GetPrim())
        meshBinding.CreateSkeletonRel().AddTarget(skeleton.GetPrim().GetPath())
        meshBinding.CreateJointIndicesPrimvar(constant=False, elementSize=elements).Set(joint_indices)
        meshBinding.CreateJointWeightsPrimvar(constant=False, elementSize=elements).Set(weights)

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

    # Traverse the "targets" group
    target_names = []
    targets = prim.GetChild("targets")
    for group in targets.GetChildren():
        target_names.extend(target.GetName() for target in group.GetChildren())
    # Define an Animation (with blend shape weight time-samples).
    blend_animation = UsdSkel.Animation.Define(stage, skeleton.GetPrim().GetPath().AppendChild("blendshape_animation"))
    blend_animation.CreateBlendShapesAttr().Set(target_names)
    weightsAttr = blend_animation.CreateBlendShapeWeightsAttr()
    weightsAttr.Set(np.zeros(len(target_names)), 0)
    skelcache = UsdSkel.Cache()
    SkelQuery = skelcache.GetSkelQuery(skeleton)
    # Add a joints attribute to the animation
    joints = SkelQuery.GetJointOrder()
    blend_animation.CreateJointsAttr(joints)

    # Bind Skeleton to animation.
    skeletonBinding = UsdSkel.BindingAPI.Apply(skeleton.GetPrim())
    blend_anim_path = blend_animation.GetPrim().GetPath()
    skeletonBinding.CreateAnimationSourceRel().AddTarget(blend_anim_path)

    import_modifiers(prim, modifiers_path)

    # Create a resizing skeleton for scaling. When blendshapes are applied, we will update the resizing skeleton
    # joints in the rest pose, and then transfer the bone lengths to the original skeleton.
    resize_skel = create_skeleton(stage, skel_root, rig, verts, "resize_skeleton")
    # Move the original skeleton to the resizing skeleton's rest pose
    resizeSkelQuery = skelcache.GetSkelQuery(resize_skel)
    resize_skel_restxforms = resizeSkelQuery.ComputeJointLocalTransforms(0)
    skeleton.GetRestTransformsAttr().Set(resize_skel_restxforms)
    # Create animation just for scaling the resizing skeleton
    scale_animation = UsdSkel.Animation.Define(stage, resize_skel.GetPrim().GetPath().AppendChild("scale_animation"))
    # Add a joints attribute to the scaling animation
    joints = resizeSkelQuery.GetJointOrder()
    scale_animation.CreateJointsAttr(joints)
    # Bind resizing skeleton to animation (so we can transform bones)
    resize_skelbinding = UsdSkel.BindingAPI.Apply(resize_skel.GetPrim())
    resize_skelbinding.CreateAnimationSourceRel().AddTarget(scale_animation.GetPrim().GetPath())
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


def create_skeleton(stage, skel_root, rig, mesh_verts, name = "skeleton") -> UsdSkel.Skeleton:
    # Define a Skeleton, and associate with root.
    rootPath = skel_root.GetPath()
    skeleton = UsdSkel.Skeleton.Define(stage, rootPath.AppendChild(name))
    rootBinding = UsdSkel.BindingAPI.Apply(skel_root.GetPrim())
    rootBinding.CreateSkeletonRel().AddTarget(skeleton.GetPrim().GetPath())

    # Determine the root, which has no parent. If there are multiple roots, use the last one.
    root = [name for name, item in rig.items() if item["parent"] == None][-1]

    visited = []  # List to keep track of visited bones.
    queue = [[root, rig[root]]]  # Initialize a queue
    path_queue = [root]  # Keep track of paths in a parallel queue
    joint_paths = [root]  # Keep track of joint paths
    joint_names = [root]  # Keep track of joint names
    helper_vertices = {}  # Keep track of helper geometry (vertices)

    # Compute the root transforms
    root_vert_idxs = rig[root]["head_vertices"]
    root_vertices = mesh_verts[root_vert_idxs]
    root_rest_xform, root_bind_xform = compute_transforms(mesh_verts, root_vertices)

    bind_xforms = [Gf.Matrix4d(root_bind_xform)]  # Bind xforms are in world space
    rest_xforms = [Gf.Matrix4d(root_rest_xform)]  # Rest xforms are in local space

    helper_vertices[root] = root_vert_idxs
    # Traverse skeleton (breadth-first) and store joint data
    while queue:
        v = queue.pop(0)
        path = path_queue.pop(0)
        for neighbor in v[1]["children"].items():
            if neighbor[0] not in visited:
                visited.append(neighbor[0])
                queue.append(neighbor)
                child_path = path+"/"+Tf.MakeValidIdentifier(neighbor[0])
                path_queue.append(child_path)
                joint_paths.append(child_path)
                joint_names.append(neighbor[0])
                vert_idxs = neighbor[1]["head_vertices"]
                helper_vertices[child_path] = vert_idxs
                parent_vert_idxs = v[1]["head_vertices"]
                vertices = mesh_verts[np.array(vert_idxs)]
                parent_vertices = mesh_verts[np.array(parent_vert_idxs)]
                rest_xform, bind_xform = compute_transforms(vertices, parent_vertices)
                rest_xforms.append(Gf.Matrix4d(rest_xform))
                bind_xforms.append(Gf.Matrix4d(bind_xform))


    skeleton.CreateJointNamesAttr(joint_names)
    skeleton.CreateJointsAttr(joint_paths)
    skeleton.CreateBindTransformsAttr(bind_xforms)
    skeleton.CreateRestTransformsAttr(rest_xforms)
    skeleton.GetPrim().SetCustomData(helper_vertices)
    return skeleton



def compute_transforms(head_vertices, parent_vertices=None):
    """Compute the rest and bind transforms for a joint"""
    head_position = np.mean(head_vertices, axis=0)
    # Bind transform is in world space
    bind_transform = np.eye(4)
    bind_transform[:3, 3] = head_position

    # If a parent head is provided, adjust the head to be in local space.
    if parent_vertices is not None:
        local_head = head_position - np.mean(parent_vertices, axis=0)
    else:
        local_head = head_position
    rest_transform = np.eye(4)
    rest_transform[:3, 3] = local_head

    return rest_transform.T, bind_transform.T


class TargetModifier():
    """ A class holding the data and methods for a modifier that targets specific blendshapes.
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
                "max_blend": modifier.max_blend
            }
            # Remove None values
            modifier_custom_data = {k: v for k, v in modifier_custom_data.items() if v is not None}
            groups_custom_data[group] = modifier_custom_data
            prim.SetCustomDataByKey("modifiers", groups_custom_data)


def mhtarget_to_blendshapes(stage, prim, path : str) -> [Sdf.Path]:
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
    path_components = path.split(os.path.sep)[path.split(os.path.sep).index("targets")+1:-1]
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

@dataclass
class MeshData:
    name: str
    vertices: list
    uvs: list
    normals: list
    vert_indices: list
    uv_indices: list
    normal_indices: list
    nface_verts: list


def create_geom(stage, path: str, mesh_data: MeshData):
    """Create a UsdGeom.Mesh prim from vertices and faces.

    Parameters
    ----------
    stage : Usd.Stage
        The stage to create the mesh on.
    path : str
        The path at which to create the mesh prim
    mesh_data : MeshData
        The mesh data to use to create the mesh prim. Contains vertices, faces, and normals.
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

    # texCoords = meshGeom.CreatePrimvar(
    #     "st", Sdf.ValueTypeNames.TexCoord2fArray, UsdGeom.Tokens.faceVarying
    # )
    # texCoords.Set(mesh_data.uvs)

    # # Subdivision is set to catmullClark for smooth surfaces
    meshGeom.CreateSubdivisionSchemeAttr().Set("catmullClark")

    return meshGeom.GetPrim()

def load_obj(filename, nPerFace=None):

    with open(filename, 'r') as infile:
        lines = infile.readlines()

    # Remove comments
    newdata = [x.rstrip('\n').split() for x in lines if '#' not in x]

    vertices = []
    uvs = []
    mesh_data = []
    group = ""
    faces = []
    vert_indices = []
    uv_indices = []
    normal_indices = []
    nface_verts = []

    for i, ln in enumerate(newdata):
        if ln[0] == 'v':
            vertices.append(tuple(ln[1:]))
        elif ln[0] == 'vt':
            uvs.append(ln[1:])
        elif ln[0] == 'f':
            if nPerFace:
                if nPerFace > len(ln[1:]):
                    raise ValueError(f'Face has less than {nPerFace} vertices')
                faces.append(ln[1:nPerFace+1])  # Only consider the first nPerFace vertices
                nface_verts.append(nPerFace)
            else:
                faces.append(ln[1:]) # Consider all vertices
                nface_verts.append(len(ln[1:]))
        elif ln[0] == 'g':
            # Record the accumulated data and start a new group
                # Flat lists of face vertex indices
            if group:
                for face in faces:
                    for i in range(len(face)):
                        vert_indices.append(int(face[i].split('/')[0]) - 1)
                        uv_indices.append(int(face[i].split('/')[1]) - 1)

                mesh_data.append(MeshData(group, None, None, None, vert_indices, uv_indices, normal_indices, nface_verts))
            faces = []
            vert_indices = []
            uv_indices = []
            normal_indices = []
            nface_verts = []
            group = Tf.MakeValidIdentifier(ln[1])
            print(f"Group {group}")

    # convert to Gf.Vec3f
    vertices = [Gf.Vec3f(*map(float, v)) for v in vertices]
    uvs = [Gf.Vec2f(*map(float, uv)) for uv in uvs]

    # Add all vertices and UVs to each mesh
    for mesh in mesh_data:
        mesh.vertices = vertices
        mesh.uvs = uvs

    return mesh_data

def load_skel_json(rig_json: str) -> dict:
    """Load a skeleton from JSON files"""

    dirname = os.path.dirname(rig_json)

    with open(rig_json, 'r') as f:
        skel_data = json.load(f)
    weights_json = os.path.join(dirname, skel_data["weights_file"])
    with open(weights_json, 'r') as f:
        weights_data = json.load(f)
        weights_data = weights_data["weights"]
    # Root bone has no parent
    return build_tree(None, skel_data, weights_data)

def build_tree(node_name, skel_data, weight_data):
    """Recursively build the tree structure and integrate vertex weights."""
    children = {}
    for name, item in skel_data["bones"].items():
        if item["parent"] == node_name:
            children[name] = item
            child = children[name]
            child["head_vertices"] = skel_data["joints"][child["head"]]
            child["tail_vertices"] = skel_data["joints"][child["tail"]]

    subtree = {}
    for child_name in children:
        subtree[child_name] = children[child_name]
        subtree[child_name]["children"] = build_tree(child_name, skel_data, weight_data)
        subtree[child_name]["vertex_weights"] = weight_data.get(child_name, [])  # Get vertex weights if available, else an empty list
    return subtree


def vertices_to_weights(joint_names: List[str], weights_json: str, mesh: UsdGeom.Mesh):
    """Returns, in vertex order, a list of joints and their weights for each vertex"""
    vertices = mesh.GetAttribute("points").Get()
    joint_names = list(joint_names)
    with open(weights_json, 'r') as f:
        weights_data = json.load(f)
        weights_data = weights_data["weights"]
    joint_indices = [[] for _ in range(len(vertices))]
    joint_weights = [[] for _ in range(len(vertices))]
    for joint in joint_names:
        if joint not in weights_data:
            continue
        for vertex_data in weights_data[joint]:
            idx = vertex_data[0]
            weight = vertex_data[1]
            joint_indices[idx].append(joint_names.index(joint))
            joint_weights[idx].append(weight)
    # Make the array rectangular
    max_len = max(len(x) for x in joint_indices)
    joint_indices = np.array([x + [0]*(max_len-len(x)) for x in joint_indices])
    joint_weights = np.array([x + [0]*(max_len-len(x)) for x in joint_weights])
    # Normalize the weights
    joint_weights = joint_weights / np.sum(joint_weights, axis=1)[:, None]
    return joint_indices, joint_weights


if __name__ == "__main__":
    make_human()
