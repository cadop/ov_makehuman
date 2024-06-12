from typing import TypeVar, Union
import warnings
import io
import os
import makehuman
from pathlib import Path

# Makehuman loads most modules by manipulating the system path, so we have to
# run this before we can run the rest of our makehuman imports

makehuman.set_sys_path()

import human
import animation
import bvh
import files3d
import mh
from core import G
from mhmain import MHApplication
from shared import wavefront
import humanmodifier, skeleton
import proxy, gui3d, events3d, targets
from getpath import findFile
import numpy as np
import carb
from .shared import data_path


class classproperty:
    """Class property decorator. Allows us to define a property on a class
    method rather than an instance method."""
    def __init__(cls, fget):
        cls.fget = fget

    def __get__(cls, obj, owner):
        return cls.fget(owner)


class MHCaller:
    """A singleton wrapper around the Makehuman app. Lets us use Makehuman functions without
    launching the whole application. Also holds all data about the state of our Human
    and available modifiers/assets, and allows us to create new humans without creating a new
    instance of MHApp.

    Attributes
    ----------
    G : Globals
        Makehuman global object. Stores globals needed by Makehuman internally
    human : Human
        Makehuman Human object. Encapsulates all human data (parameters, available)
        modifiers, skeletons, meshes, assets, etc) and functions.
    """

    G = G
    human = None

    def __init__(cls):
        """Constructs an instance of MHCaller. This involves setting up the
        needed components to use makehuman modules independent of the GUI.
        This includes app globals (G) and the human object."""
        cls._config_mhapp()
        cls.init_human()

    def __new__(cls):
        """Singleton pattern. Only one instance of MHCaller can exist at a time."""
        if not hasattr(cls, 'instance'):
            cls.instance = super(MHCaller, cls).__new__(cls)
        return cls.instance

    @classmethod
    def _config_mhapp(cls):
        """Declare and initialize the makehuman app, and move along if we
        encounter any errors (omniverse sometimes fails to purge the app
        singleton on extension reload, which can throw an error. This just means
        the app already exists)
        """
        try:
            cls.G.app = MHApplication()
        except:
            return

        cls.human_mapper = {}

    @classmethod
    def reset_human(cls):
        """Resets the human object to its initial state. This involves setting the
        human's name to its default, resetting all modifications, and resetting all
        proxies. Does not reset the skeleton. Also flags the human as having been
        reset so that the new name can be created when adding to the Usd stage.
        """
        cls.human.resetMeshValues()

        # Subdivide the human mesh. This also means that any proxies added to the human are subdivided
        cls.human.setSubdivided(True)
        # Restore eyes
        # cls.add_proxy(data_path("eyes/high-poly/high-poly.mhpxy"), "eyes")
        # Reset skeleton to the game skeleton
        cls.human.setSkeleton(cls.game_skel)
        # Reset the human to tpose
        cls.set_tpose()

        # HACK Set the age to itcls to force an update of targets, otherwise humans
        # are created with the MH base mesh, see:
        # http://static.makehumancommunity.org/makehuman/docs/professional_mesh_topology.html
        cls.human.setAge(cls.human.getAge())

    @classmethod
    def init_human(cls):
        """Initialize the human and set some required files from disk. This
        includes the skeleton and any proxies (hair, clothes, accessories etc.)
        The weights from the base skeleton must be transfered to the chosen
        skeleton or else there will be unweighted verts on the meshes.
        """
        cls.human = human.Human(files3d.loadMesh(mh.getSysDataPath("3dobjs/base.obj"), maxFaces=5))
        # set the makehuman instance human so that features (eg skeletons) can
        # access it globally
        cls.G.app.selectedHuman = cls.human
        humanmodifier.loadModifiers(mh.getSysDataPath("modifiers/modeling_modifiers.json"), cls.human)
        # Add eyes
        # cls.add_proxy(data_path("eyes/high-poly/high-poly.mhpxy"), "eyes")
        cls.base_skel = skeleton.load(
            mh.getSysDataPath("rigs/default.mhskel"),
            cls.human.meshData,
        )

        # Load the game developer skeleton
        # The root of this skeleton is at the origin which is better for animation
        # retargeting
        cls.game_skel = skeleton.load(data_path("rigs/game_engine.mhskel"), cls.human.meshData)
        # Build joint weights on our chosen skeleton, derived from the base
        # skeleton
        cls.game_skel.autoBuildWeightReferences(cls.base_skel)

        # Set the base skeleton
        cls.human.setBaseSkeleton(cls.base_skel)

        # Set the game skeleton
        cls.human.setSkeleton(cls.game_skel)

    @classproperty
    def objects(cls):
        """List of objects attached to the human.

        Returns
        -------
        list of: guiCommon.Object
            All 3D objects included in the human. This includes the human
            itcls, as well as any proxies
        """
        # Make sure proxies are up-to-date
        cls.update()
        return cls.human.getObjects()

    @classproperty
    def meshes(cls):
        """All of the meshes of all of the objects attached to a human. This
        includes the mesh of the human itcls as well as the meshes of all proxies
        (clothing, hair, musculature, eyes, etc.)"""
        return [o.mesh for o in cls.objects]

    @classproperty
    def modifiers(cls):
        """List of modifers attached to the human. These are all macros as well as any
        individual modifiers which have changed.
        Returns
        -------
        list of: humanmodifier.Modifier
            The macros and changed modifiers included in the human
        """
        return [m for m in cls.human.modifiers if m.getValue() or m.isMacro()]

    @classproperty
    def default_modifiers(cls):
        """List of all the loaded modifiers, whether or not their default values have been changed.
        -------
        list of: humanmodifier.Modifier
            The macros and changed modifiers included in the human
        """
        return cls.human.modifiers

    @classproperty
    def proxies(cls):
        """List of proxies attached to the human.
        Returns
        -------
        list of: proxy.Proxy
            All proxies included in the human
        """
        return cls.human.getProxies()

    @classmethod
    def update(cls):
        """Propagate changes to meshes and proxies"""
        # For every mesh object except for the human (first object), update the
        # mesh and corresponding proxy
        # See https://github.com/makehumancommunity/makehuman/search?q=adaptproxytohuman
        for obj in cls.human.getObjects()[1:]:
            mesh = obj.getSeedMesh()
            pxy = obj.getProxy()
            # Update the proxy and fit to posed human
            # args are (mesh, fit_to_posed = false) by default
            pxy.update(mesh, True)
            # Update the mesh
            mesh.update()

    @classmethod
    def add_proxy(cls, proxypath : str, proxy_type  : str = None):
        """Load a proxy (hair, nails, clothes, etc.) and apply it to the human

        Parameters
        ----------
        proxypath : str
            Path to the proxy file on disk
        proxy_type: str, optional
            Proxy type, None by default
            Can be automatically determined using path names, but otherwise
            must be defined (this is a limitation of how makehuman handles
            proxies)
        """
        #  Derived from work by @tomtom92 at the MH-Community forums
        #  See: http://www.makehumancommunity.org/forum/viewtopic.php?f=9&t=17182&sid=7c2e6843275d8c6c6e70288bc0a27ae9
        # Get proxy type if none is given
        if proxy_type is None:
            proxy_type = cls.guess_proxy_type(proxypath)
        # Load the proxy
        pxy = proxy.loadProxy(cls.human, proxypath, type=proxy_type)
        # Get the mesh and Object3D object from the proxy applied to the human
        mesh, obj = pxy.loadMeshAndObject(cls.human)
        # TODO is this next line needed?
        mesh.setPickable(True)
        # TODO Can this next line be deleted? The app isn't running
        gui3d.app.addObject(obj)

        # Fit the proxy mesh to the human
        mesh2 = obj.getSeedMesh()
        fit_to_posed = True
        pxy.update(mesh2, fit_to_posed)
        mesh2.update()

        # Set the object to be subdivided if the human is subdivided
        obj.setSubdivided(cls.human.isSubdivided())


        # Set/add proxy based on type
        if proxy_type == "eyes":
            cls.human.setEyesProxy(pxy)
        elif proxy_type == "clothes":
            cls.human.addClothesProxy(pxy)
        elif proxy_type == "eyebrows":
            cls.human.setEyebrowsProxy(pxy)
        elif proxy_type == "eyelashes":
            cls.human.setEyelashesProxy(pxy)
        elif proxy_type == "hair":
            cls.human.setHairProxy(pxy)
        else:
            # Body proxies (musculature, etc)
            cls.human.setProxy(pxy)

        vertsMask = np.ones(cls.human.meshData.getVertexCount(), dtype=bool)
        proxyVertMask = proxy.transferVertexMaskToProxy(vertsMask, pxy)
        # Apply accumulated mask from previous layers on this proxy
        obj.changeVertexMask(proxyVertMask)

        # Delete masked vertices
        # TODO add toggle for this feature in UI
        # verts = np.argwhere(pxy.deleteVerts)[..., 0]
        # vertsMask[verts] = False
        # cls.human.changeVertexMask(vertsMask)

    Proxy = TypeVar("Proxy")

    @classmethod
    def remove_proxy(cls, proxy: Proxy):
        """Removes a proxy from the human. Executes a particular method for removal
        based on proxy type.

        Parameters
        ----------
        proxy : proxy.Proxy
            The Makehuman proxy to remove from the human
        """
        proxy_type = proxy.type.lower()
        # Use MakeHuman internal methods to remove proxy based on type
        if proxy_type == "eyes":
            cls.human.setEyesProxy(None)
        elif proxy_type == "clothes":
            cls.human.removeClothesProxy(proxy.uuid)
        elif proxy_type == "eyebrows":
            cls.human.setEyebrowsProxy(None)
        elif proxy_type == "eyelashes":
            cls.human.setEyelashesProxy(None)
        elif proxy_type == "hair":
            cls.human.setHairProxy(None)
        else:
            # Body proxies (musculature, etc)
            cls.human.setProxy(None)

    @classmethod
    def clear_proxies(cls):
        """Removes all proxies from the human"""
        for pxy in cls.proxies:
            cls.remove_proxy(pxy)

    Skeleton = TypeVar("Skeleton")

    @classmethod
    def remove_item(cls, item : Union[Skeleton, Proxy]):
        """Removes a Makehuman asset from the human. Assets include Skeletons
        as well as proxies. Determines removal method based on asset object type.

        Parameters
        ----------
        item : Union[Skeleton,Proxy]
            Makehuman skeleton or proxy to remove from the human
        """
        if isinstance(item, proxy.Proxy):
            cls.remove_proxy(item)
        else:
            return

    @classmethod
    def add_item(cls, path : str):
        """Add a Makehuman asset (skeleton or proxy) to the human.

        Parameters
        ----------
        path : str
            Path to the asset on disk
        """
        if "mhpxy" in path or "mhclo" in path:
            cls.add_proxy(path)
        elif "mhskel" in path:
            cls.set_skel(path)

    @classmethod
    def set_skel(cls, path : str):
        """Change the skeleton applied to the human. Loads a skeleton from disk.
        The skeleton position can be used to drive the human position in the scene.

        Parameters
        ----------
        path : str
            The path to the skeleton to load from disk
        """
        # Load skeleton from path
        skel = skeleton.load(path, cls.human.meshData)
        # Build skeleton weights based on base skeleton
        skel.autoBuildWeightReferences(cls.base_skel)
        # Set the skeleton and update the human
        cls.human.setSkeleton(skel)
        cls.human.applyAllTargets()

        # Return the skeleton object
        return skel

    @classmethod
    def guess_proxy_type(cls, path : str):
        """Guesses a proxy's type based on the path from which it is loaded.

        Parameters
        ----------
        path : str
            The path to the proxy on disk

        Returns
        -------
        Union[str,None]
            The proxy type, or none if the type could not be determined
        """
        proxy_types = ("eyes", "clothes", "eyebrows", "eyelashes", "hair")
        for type in proxy_types:
            if type in path:
                return type
        return None
    
    
    @classmethod
    def set_tpose(cls):
        """Sets the human to the T-Pose"""
        # Load the T-Pose BVH file
        pose_path = os.path.join("poses", "tpose.bvh")
        filepath = data_path(pose_path)
        bvh_file = bvh.load(filepath, convertFromZUp="auto")
        # Create an animation track from the BVH file
        anim = bvh_file.createAnimationTrack(cls.human.getBaseSkeleton())
        # Add the animation to the human
        cls.human.addAnimation(anim)
        # Set the active animation to the T-Pose
        cls.human.setActiveAnimation(anim.name)
        # Refresh the human pose
        cls.human.refreshPose()
        return

# Create an instance of MHCaller when imported
MHCaller()
