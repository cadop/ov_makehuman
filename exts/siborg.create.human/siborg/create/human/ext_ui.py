import omni.ui as ui
import omni.kit.commands
import json
from typing import List, TypeVar, Union, Callable
from dataclasses import dataclass, field
from . import styles
from pxr import Usd, Tf, UsdSkel
import os
import inspect
from siborg.create.human.shared import data_path
from collections import defaultdict
from . import modifiers
from .modifiers import Modifier
from . import mhusd

class SliderEntry:

    def __init__(
        self,
        label: str,
        model: ui.SimpleFloatModel,
        fn: object,
        image: str = None,
        step: float = 0.01,
        min: float = None,
        max: float = None,
        default: float = 0,
    ):
        """Constructs an instance of SliderEntry

        Parameters
        ----------
        label : str
            Label to display for slider/field
        model : ui.SimpleFloatModel
            Model to publish changes to
        fn : object
            Function to run when changes are made
        image: str, optional
            Path on disk to an image to display. By default None
        step : float, optional
            Division between values for the slider, by default 0.01
        min : float, optional
            Minimum value, by default None
        max : float, optional
            Maximum value, by default None
        default : float, optional
            Default parameter value, by default 0
        """
        self.label = label
        self.model = model
        self.fn = fn
        self.step = step
        self.min = min
        self.max = max
        self.default = default
        self.image = image
        self._build_widget()

    def _build_widget(self):
        """Construct the UI elements"""
        with ui.HStack(height=0, style=styles.sliderentry_style):
            # If an image is available, display it
            if self.image:
                ui.Image(self.image, height=75, style={"border_radius": 5})
            # Stack the label and slider on top of each other
            with ui.VStack(spacing = 5):
                ui.Label(
                    self.label,
                    height=15,
                    alignment=ui.Alignment.CENTER,
                    name="label_param",
                )
                # create a floatdrag (can be used as a slider or an entry field) to
                # input parameter values
                self.drag = ui.FloatSlider(model=self.model, step=self.step)
                # Limit drag values to within min and max if provided
                if self.min is not None:
                    self.drag.min = self.min
                if self.max is not None:
                    self.drag.max = self.max

class SliderGroup:
    """A UI widget providing a labeled group of slider entries

    Attributes
    ----------
    label : str
        Display title for the group. Can be none if no title is desired.
    params : list of Param
        List of parameters to display in the group
    """

    def __init__(self, label: str = None, modifiers: List[Modifier] = None):
        self.label = label
        self.modifiers = modifiers or []
        self._build_widget()

    def _build_widget(self):
        """Construct the UI elements"""
        with ui.CollapsableFrame(self.label, style=styles.panel_style, collapsed=True, height=0):
            with ui.VStack(name="contents", spacing = 8):
                # Create a slider entry for each parameter
                for m in self.modifiers:
                    SliderEntry(
                        m.label,
                        m.value_model,
                        m.fn,
                        image=m.image,
                        min=m.min_val,
                        max=m.max_val,
                        default=m.default_val,
                    )

    def destroy(self):
        """Destroys the instance of SliderEntryPanel. Executes the destructor of
        the SliderEntryPanel's SliderEntryPanelModel instance.
        """
        self.params = None

class ModifierUI(ui.Frame):
    """UI Widget for displaying and modifying human parameters

    Attributes
    ----------
    model : ParamPanelModel
        Stores data for the panel
    toggle : ui.SimpleBoolModel
        Model to track whether changes should be instant
    models : list of SliderEntryPanelModel
        Models for each group of parameter sliders
    """

    def __init__(self, **kwargs):
        """Constructs an instance of ParamPanel. Panel contains a scrollable list of collapseable groups. These include
        a group of macros (which affect multiple modifiers simultaneously), as well as groups of modifiers for
        different body parts. Each modifier can be adjusted using a slider or doubleclicking to enter values directly.
        Values are restricted based on the limits of a particular modifier.
        """

        # Subclassing ui.Frame allows us to use styling on the whole widget
        super().__init__(**kwargs)
        # If no instant update function is passed, use a dummy function and do nothing
        self.groups, self.mods = self._init_groups_and_mods()
        self.group_widgets = []
        self.set_build_fn(self._build_widget)
        self.human_prim = None
        self.macrovars = []

    def _init_groups_and_mods(self):
        """Initialize the groups and modifiers"""
        return modifiers.parse_modifiers()
        
    def _build_widget(self):
        with self:
            with ui.ScrollingFrame():
                with ui.VStack(spacing=10):
                    for g, m in self.groups.items():
                        self.group_widgets.append(SliderGroup(g, m))
        for m in self.mods:
            callback = self.create_callback(m)
            m.value_model.add_value_changed_fn(callback)

    def create_callback(self, m: Modifier):
        """Callback for when a modifier value is changed.
        
        Parameters
        m : Modifier
            Modifier whose value was changed. Used to determine which blendshape(s) to edit"""
        def callback(v):
            # If the modifier has a macrovar, we need to edit the macrovar
            if m.macrovar:
                mhusd.edit_blendshapes(self.human_prim, m.fn(v, self.macrovars))
            else:
                mhusd.edit_blendshapes(self.human_prim, m.fn(v))

        return callback

    def reset(self):
        """Reset every SliderEntryPanel to set UI values to defaults
        """
        for model in self.models:
            model.reset()

    def load_values(self, human_prim: Usd.Prim):
        """Load values from the human prim into the UI. Specifically, this function
        loads the values of the modifiers from the prim and updates any which
        have changed.

        Parameters
        ----------
        HumanPrim : Usd.Prim
            The USD prim representing the human
        """

        # Make the prim exists
        if not human_prim.IsValid():
            self.human_prim = None
            self.macrovars = []
            return
        self.human_prim = human_prim
        self.macrovars = mhusd.read_macrovars(human_prim)
        
        # # Reset the UI to defaults
        # self.reset()

        # # Get the data from the prim
        # humandata = human_prim.GetCustomData()

        # modifiers = humandata.get("Modifiers")

        modifiers = mhusd.read_modifiers(human_prim)

        # Set any changed values in the models
        for SliderEntryPanelModel in self.models:
            for param in SliderEntryPanelModel.params:
                if param.full_name in modifiers:
                    param.value.set_value(modifiers[param.full_name])

    def update_models(self):
        """Update all models"""
        for model in self.models:
            model.apply_changes()

    def destroy(self):
        """Destroys the ParamPanel instance as well as the models attached to each group of parameters
        """
        super().destroy()
        for model in self.models:
            model.destroy()

class DemoUI(ModifierUI):
    """UI widget for modifying one blendshape on a demo mesh. Demonstrates helper-driving-skeleton functionality."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def _init_groups_and_mods(self):
        """For the demo, we have one group with one modifier that we define explicitly"""
        # Define the group and modifier
        group = "Demo"
        modifier = Modifier(group, {})
        modifier.blend = Tf.MakeValidIdentifier("length")
        modifier.label = "Length"
        modifier.fn = lambda model: {modifier.blend: model.get_value_as_float()}
        mods = [modifier]
        return {group: mods}, mods
class NoSelectionNotification:
    """
    When no human selected, show notification.
    """
    def __init__(self):
        self._container = ui.ZStack()
        with self._container:
            ui.Rectangle()
            with ui.VStack(spacing=10):
                ui.Spacer(height=10)
                with ui.HStack(height=0):
                    ui.Spacer()
                    ui.ImageWithProvider(
                        data_path('human_icon.png'),
                        width=192,
                        height=192,
                        fill_policy=ui.IwpFillPolicy.IWP_PRESERVE_ASPECT_FIT
                    )
                    ui.Spacer()
                self._message_label = ui.Label(
                    "No human is current selected.",
                    height=0,
                    alignment=ui.Alignment.CENTER
                )
                self._suggestion_label = ui.Label(
                    "Select a human prim to see its properties here.",
                    height=0,
                    alignment=ui.Alignment.CENTER
                )

    @property
    def visible(self) -> bool:
        return self._container.visible

    @visible.setter
    def visible(self, value) -> None:
        self._container.visible = value

    def set_message(self, message: str) -> None:
        messages = message.split("\n")
        self._message_label.text = messages[0]
        self._suggestion_label.text = messages[1]


def modifier_image(name : str):
    """Guess the path to a modifier's corresponding image on disk based on the name
    of the modifier. Useful for building UI for list of modifiers.

    Parameters
    ----------
    name : str
        Name of the modifier

    Returns
    -------
    str
        The path to the image on disk
    """
    if name is None:
        # If no modifier name is provided, we can't guess the file name
        return None
    name = name.lower()
    # Return the modifier path based on the modifier name
    # TODO determine if images can be loaded from the Makehuman module stored in
    # site-packages so we don't have to include the data twice
    return os.path.join(os.path.dirname(inspect.getfile(makehuman)),targets.getTargets().images.get(name, name))
