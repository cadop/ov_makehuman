import numpy as np
from pxr import Usd, UsdSkel, Tf


def build_anim(stage: Usd.Stage, skeleton: UsdSkel.Skeleton, name: str = "target_anim", blendshapes: bool = False):
    # Create an Animation
    name = Tf.MakeValidIdentifier(name)
    animation = UsdSkel.Animation.Define(stage, skeleton.GetPrim().GetPath().AppendChild(name))

    if blendshapes:
        # Create a blend shape animation
        skelRoot = UsdSkel.Root.Find(skeleton.GetPrim())
        skelRoot_prim = skelRoot.GetPrim()

        # Traverse the "targets" group
        target_names = []
        targets = skelRoot_prim.GetChild("targets")
        for group in targets.GetChildren():
            target_names.extend(target.GetName() for target in group.GetChildren())
        # Define an Animation (with blend shape weight time-samples).
        animation.CreateBlendShapesAttr().Set(target_names)
        weightsAttr = animation.CreateBlendShapeWeightsAttr()
        weightsAttr.Set(np.zeros(len(target_names)), 0)

    skelcache = UsdSkel.Cache()
    skelQuery = skelcache.GetSkelQuery(skeleton)
    # Add a joints attribute to the animation
    joints = skelQuery.GetJointOrder()
    animation.CreateJointsAttr(joints)

    bind_animation(skeleton, animation)
    return animation


def bind_animation(skeleton: UsdSkel.Skeleton, animation: UsdSkel.Animation):
    # Bind Skeleton to animation.
    skeletonBinding = UsdSkel.BindingAPI.Apply(skeleton.GetPrim())
    blend_anim_path = animation.GetPrim().GetPath()
    skeletonBinding.CreateAnimationSourceRel().AddTarget(blend_anim_path)
