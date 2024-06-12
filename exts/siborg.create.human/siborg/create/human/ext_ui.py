import omni.ui as ui
from typing import List, Dict
from pxr import Usd, Tf
from siborg.create.human.shared import data_path
from .modifiers import Modifier, MacroModifier, TargetModifier
from . import mhusd
from .widgets import SliderGroup


class ModifierUI(ui.Frame):
    """UI Widget for displaying and modifying human parameters dynamically based on custom data on the human prim."""

    def __init__(self, **kwargs):
        # Subclassing ui.Frame allows us to use styling on the whole widget
        super().__init__(**kwargs)
        self.group_widgets: Dict[str, SliderGroup] = []
        self.modifiers: Dict[str, dict] = {}
        self.set_build_fn(self._build_widget)
        self.macrovars: Dict[str, float] = {}
        self.human_prim = None

    def _build_widget(self):
        """Build the widget from scratch every time a human is selected"""
        self.group_widgets = {}
        
        # Arrange modifiers into groups
        groups : Dict[str, List[Modifier]] = {}
        for name, data in self.modifiers.items():
            group = data["group"]
            if group not in groups:
                groups[group] = []
            if "target" in data:
                modifier = TargetModifier(group, data)
            elif "macrovar" in data:
                modifier = MacroModifier(group, data)
            groups[group].append(modifier)

        with self:
            with ui.ScrollingFrame():
                with ui.VStack(spacing=10):
                    for group, modifiers in groups.items():
                        self.group_widgets[group] = SliderGroup(group, modifiers)

        # Set the values of the sliders to the values of the modifiers
        for sliderGroup in self.group_widgets.items():
            for entry in sliderGroup.slider_entries:
                if entry.label in self.modifiers:
                    v = self.modifiers[entry.label]["weight"]
                    entry.model.set_value(v)

        for m in self.modifiers:
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
            self.macrovars = {}
            # Destroy the modifier models
            for m in self.group_widgets.values():
                m.destroy()
            return
        self.human_prim = human_prim
        self.macrovars = mhusd.read_macrovars(human_prim)
        self.modifiers = mhusd.read_modifiers(human_prim)
        self._build_widget()

    def destroy(self):
        """Destroys the ParamPanel instance as well as the models attached to each group of parameters"""
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
                        data_path("human_icon.png"),
                        width=192,
                        height=192,
                        fill_policy=ui.IwpFillPolicy.IWP_PRESERVE_ASPECT_FIT,
                    )
                    ui.Spacer()
                self._message_label = ui.Label("No human is current selected.", height=0, alignment=ui.Alignment.CENTER)
                self._suggestion_label = ui.Label(
                    "Select a human prim to see its properties here.", height=0, alignment=ui.Alignment.CENTER
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
