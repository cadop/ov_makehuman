import numpy as np
from pxr import Usd, UsdSkel


def build_blend_anim(stage: Usd.Stage, skelRoot: UsdSkel.Root, skeleton: UsdSkel.Skeleton, name: str = "target_anim"):
    skelRoot_prim = skelRoot.GetPrim()
    # Traverse the "targets" group
    target_names = []
    targets = skelRoot_prim.GetChild("targets")
    for group in targets.GetChildren():
        target_names.extend(target.GetName() for target in group.GetChildren())

    # Define an Animation (with blend shape weight time-samples).
    blend_animation = UsdSkel.Animation.Define(stage, skeleton.GetPrim().GetPath().AppendChild(name))
    blend_animation.CreateBlendShapesAttr().Set(target_names)
    weightsAttr = blend_animation.CreateBlendShapeWeightsAttr()
    weightsAttr.Set(np.zeros(len(target_names)), 0)
    skelcache = UsdSkel.Cache()
    SkelQuery = skelcache.GetSkelQuery(skeleton)
    # Add a joints attribute to the animation
    joints = SkelQuery.GetJointOrder()
    blend_animation.CreateJointsAttr(joints)

    bind_animation(skeleton, blend_animation)

    return blend_animation


def build_scale_anim(stage: Usd.Stage, skeleton: UsdSkel.Skeleton, name: str = "scale_anim"):
    skelcache = UsdSkel.Cache()
    skelQuery = skelcache.GetSkelQuery(skeleton)

    # Create animation just for scaling the resizing skeleton
    scale_animation = UsdSkel.Animation.Define(stage, skeleton.GetPrim().GetPath().AppendChild(name))
    # Add a joints attribute to the scaling animation
    joints = skelQuery.GetJointOrder()
    scale_animation.CreateJointsAttr(joints)
    # Bind resizing skeleton to animation (so we can transform bones)
    binding = UsdSkel.BindingAPI.Apply(skeleton.GetPrim())
    binding.CreateAnimationSourceRel().AddTarget(scale_animation.GetPrim().GetPath())


def bind_animation(skeleton: UsdSkel.Skeleton, blend_animation: UsdSkel.Animation):
    # Bind Skeleton to animation.
    skeletonBinding = UsdSkel.BindingAPI.Apply(skeleton.GetPrim())
    blend_anim_path = blend_animation.GetPrim().GetPath()
    skeletonBinding.CreateAnimationSourceRel().AddTarget(blend_anim_path)
