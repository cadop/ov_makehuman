from dataclasses import dataclass
from pxr import UsdGeom, Gf, Tf


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
    with open(filename, "r") as infile:
        lines = infile.readlines()

    # Remove comments
    newdata = [x.rstrip("\n").split() for x in lines if "#" not in x]

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
        if ln[0] == "v":
            vertices.append(tuple(ln[1:]))
        elif ln[0] == "vt":
            uvs.append(ln[1:])
        elif ln[0] == "f":
            if nPerFace:
                if nPerFace > len(ln[1:]):
                    raise ValueError(f"Face has less than {nPerFace} vertices")
                faces.append(ln[1 : nPerFace + 1])  # Only consider the first nPerFace vertices
                nface_verts.append(nPerFace)
            else:
                faces.append(ln[1:])  # Consider all vertices
                nface_verts.append(len(ln[1:]))
        elif ln[0] == "g":
            # Record the accumulated data and start a new group
            # Flat lists of face vertex indices
            if group:
                for face in faces:
                    for i in range(len(face)):
                        vert_indices.append(int(face[i].split("/")[0]) - 1)
                        uv_indices.append(int(face[i].split("/")[1]) - 1)

                mesh_data.append(
                    MeshData(group, None, None, None, vert_indices, uv_indices, normal_indices, nface_verts)
                )
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
