"""
A basic example of authoring blend shape animation applied to a
triangular mesh with UsdSkel.
From https://github.com/moddyz/USDSandbox/blob/1d9a4d809e25e45478c1993b8370818c702a675c/src/usdSnippets/authorBlendShapes.py
"""

from pxr import Sdf, Usd, UsdGeom, UsdSkel


if __name__ == "__main__":
    # Create a new stage.
    stage = Usd.Stage.CreateInMemory()
    stage.SetStartTimeCode(1)
    stage.SetEndTimeCode(10)

    # Define a SkelRoot.
    rootPath = Sdf.Path("/root")
    root = UsdSkel.Root.Define(stage, rootPath)
    stage.SetDefaultPrim(root.GetPrim())

    # Define a Skeleton, and associate with root.
    skeleton = UsdSkel.Skeleton.Define(stage, rootPath.AppendChild("skeleton"))
    rootBinding = UsdSkel.BindingAPI.Apply(root.GetPrim())
    rootBinding.CreateSkeletonRel().AddTarget(skeleton.GetPrim().GetPath())

    # Define a Mesh (a right triangle).
    mesh = UsdGeom.Mesh.Define(stage, rootPath.AppendChild("mesh"))
    mesh.CreateExtentAttr().Set([(-2, -2, -2), (2, 2, 2)])
    mesh.CreateFaceVertexCountsAttr().Set([3])
    mesh.CreateFaceVertexIndicesAttr().Set([0, 1, 2])
    mesh.CreatePointsAttr().Set([
        (0, 0, 0),
        (1, 0, 0),
        (0, 1, 0)
    ])

    # Define blend shape target A.
    # This offsets the first point of the triangle pipmesh.
    targetA = UsdSkel.BlendShape.Define(stage, mesh.GetPrim().GetPath().AppendChild("targetA"))
    targetA.CreateOffsetsAttr().Set([
        (1, 1, 1),
    ])
    targetA.CreatePointIndicesAttr().Set([0,])

    # Define blend shape target B.
    # This offsets the second and third points of the triangle mesh.
    # This blendshape also has an in-between
    targetB = UsdSkel.BlendShape.Define(stage, mesh.GetPrim().GetPath().AppendChild("targetB"))
    targetB.CreateOffsetsAttr().Set([
        (5, 0, 0),
        (-5, -5, -5),
    ])
    targetB.CreatePointIndicesAttr().Set([1, 2])
    inbetween0 = targetB.CreateInbetween("inbetween0")
    inbetween0.SetWeight(0.5)
    inbetween0.SetOffsets([
        (0, 0, 0),
        (0, -3, 0),
    ])

    # Apply BindingAPI onto Mesh, then associate the blend shape targets with the mesh.
    meshBinding = UsdSkel.BindingAPI.Apply(mesh.GetPrim())
    meshBinding.CreateBlendShapesAttr().Set(["targetA", "targetB"])
    meshBinding.CreateBlendShapeTargetsRel().SetTargets([
        targetA.GetPrim().GetPath(),
        targetB.GetPrim().GetPath(),
    ])

    # Define an Animation (with blend shape weight time-samples).
    animation = UsdSkel.Animation.Define(stage, skeleton.GetPrim().GetPath().AppendChild("animation"))
    animation.CreateBlendShapesAttr().Set(["targetA", "targetB"])
    weightsAttr = animation.CreateBlendShapeWeightsAttr()
    weightsAttr.Set([0, 0], 1)
    weightsAttr.Set([0, 1], 5)
    weightsAttr.Set([1, 1], 10)

    # Bind Skeleton to animation.
    skeletonBinding = UsdSkel.BindingAPI.Apply(skeleton.GetPrim())
    skeletonBinding.CreateAnimationSourceRel().AddTarget(animation.GetPrim().GetPath())

    print(stage.GetRootLayer().ExportToString())
