import json
import os
from typing import List

import numpy as np
from pxr import Gf, Tf, Usd, UsdGeom, UsdSkel


def build_skeleton(stage: Usd.Stage, skel_root: UsdSkel.Root, ext_path: str, name: str = "skeleton"):
    # Get all meshes that are not joints
    non_joint_meshes = [
        m for m in skel_root.GetPrim().GetChildren() if m.IsA(UsdGeom.Mesh) and not m.GetName().startswith("joint")
    ]
    rig = load_skel_json(os.path.join(ext_path, "data", "rigs", "cmu_mb.mhskel"))
    verts = np.array(non_joint_meshes[0].GetPrim().GetAttribute("points").Get())
    skeleton = create_skeleton(stage, skel_root, rig, verts, name)

    weights_json = os.path.join(ext_path, "data", "rigs", "weights.cmu_mb.json")
    joint_indices, weights = vertices_to_weights(
        skeleton.GetJointNamesAttr().Get(),
        weights_json,
        skel_root.GetPrim().GetChildren()[0],
    )
    elements = joint_indices.shape[1]

    # bind the skeleton to each non-joint mesh
    for mesh in non_joint_meshes:
        meshBinding = UsdSkel.BindingAPI.Apply(mesh.GetPrim())
        meshBinding.CreateSkeletonRel().AddTarget(skeleton.GetPrim().GetPath())
        meshBinding.CreateJointIndicesPrimvar(constant=False, elementSize=elements).Set(joint_indices)
        meshBinding.CreateJointWeightsPrimvar(constant=False, elementSize=elements).Set(weights)

    return skeleton


def create_skeleton(stage, skel_root, rig, mesh_verts, name="skeleton") -> UsdSkel.Skeleton:
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
                child_path = path + "/" + Tf.MakeValidIdentifier(neighbor[0])
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


def vertices_to_weights(joint_names: List[str], weights_json: str, mesh: UsdGeom.Mesh):
    """Returns, in vertex order, a list of joints and their weights for each vertex"""
    vertices = mesh.GetAttribute("points").Get()
    joint_names = list(joint_names)
    with open(weights_json, "r") as f:
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
    joint_indices = np.array([x + [0] * (max_len - len(x)) for x in joint_indices])
    joint_weights = np.array([x + [0] * (max_len - len(x)) for x in joint_weights])
    # Normalize the weights
    joint_weights = joint_weights / np.sum(joint_weights, axis=1)[:, None]
    return joint_indices, joint_weights


def load_skel_json(rig_json: str) -> dict:
    """Load a skeleton from JSON files"""

    dirname = os.path.dirname(rig_json)

    with open(rig_json, "r") as f:
        skel_data = json.load(f)
    weights_json = os.path.join(dirname, skel_data["weights_file"])
    with open(weights_json, "r") as f:
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
        subtree[child_name]["vertex_weights"] = weight_data.get(
            child_name, []
        )  # Get vertex weights if available, else an empty list
    return subtree
