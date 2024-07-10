from pxr import Sdf, UsdShade, Usd

def create_preview_surface_material(stage):
    default_prim = stage.GetDefaultPrim()
    mtl_path = default_prim.GetPath().AppendChild("Looks").AppendChild("PreviewSurface")
    mtl = UsdShade.Material.Define(stage, mtl_path)
    shader = UsdShade.Shader.Define(stage, mtl_path.AppendPath("Shader"))
    shader.CreateIdAttr("UsdPreviewSurface")
    shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set((1.0, 0.0, 0.0))
    shader.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(0.5)
    shader.CreateInput("metallic", Sdf.ValueTypeNames.Float).Set(0.0)
    mtl.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(), "surface")
    return mtl


def bind_material(prim: Usd.Prim, material: UsdShade.Material):
    bindingApi = UsdShade.MaterialBindingAPI(prim)
    bindingApi.Bind(material)