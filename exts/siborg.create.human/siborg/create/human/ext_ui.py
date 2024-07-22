import omni.ui as ui
import omni.usd
import omni.kit.app
from typing import List, Dict
from pxr import Usd, Tf, Trace
from siborg.create.human.shared import data_path
from . import mhusd
from . import styles
from . import modifiers
from omni.kit.property.usd import ADDITIONAL_CHANGED_PATH_EVENT_TYPE
from .shared import current_timecode


class ModifierUI(ui.Frame):
    """UI Widget for displaying and modifying human parameters dynamically based on custom data on the human prim."""

    def __init__(self, **kwargs):
        # Subclassing ui.Frame allows us to use styling on the whole widget
        super().__init__(**kwargs)
        self.slider_entries: List[SliderEntry] = []

        self.modifier_data: Dict[str, dict] = {}
        self.group_data: Dict[str, dict] = {}
        self.macrovars: Dict[str, float] = {}
        self.human_prim = None
        self.timecode = current_timecode()

        # self._message_bus = omni.kit.app.get_app().get_message_bus_event_stream()

        self.set_build_fn(self._build_widget)

    def _build_widget(self):
        """Build the widget from scratch every time a human is selected"""

        # Register a listener for when the USD stage changes, so we can update the UI during playback
        stage = omni.usd.get_context().get_stage()
        self._listener = Tf.Notice.Register(Usd.Notice.ObjectsChanged, self._on_usd_changed, stage)

        # self._bus_sub = self._message_bus.create_subscription_to_pop_by_type(ADDITIONAL_CHANGED_PATH_EVENT_TYPE, self._on_bus_event)

        with self:
            with ui.ScrollingFrame():
                with ui.VStack(spacing=10):
                    # If there are no modifiers, show a message. We don't want to build a UI with no parameters
                    if not self.modifier_data:
                        ui.Label("No parameters available", height=0, alignment=ui.Alignment.CENTER)
                        return
                    # Create a collapseable frame for each group in the UI
                    for group, modifiers_list in self.group_data.items():
                        with ui.CollapsableFrame(group, style=styles.panel_style, collapsed=True, height=0):
                            with ui.VStack(name="contents", spacing=8):
                                for modifier in modifiers_list:
                                    model = ui.SimpleFloatModel()
                                    m = self.modifier_data[modifier]
                                    self.slider_entries.append(
                                        SliderEntry(
                                            label=m["label"],
                                            model=model,
                                            min=m.get("min_val", 0),
                                            max=m.get("max_val", 1),
                                            default=m.get("default", 0),
                                        )
                                    )

        # Set the values of the sliders to the values of the modifiers
        for entry in self.slider_entries:
            if entry.label in self.modifier_data:
                default = self.modifier_data[entry.label].get("default", 0)
                v = self.modifier_data[entry.label].get("weight", default)
                entry.model.set_value(v)
                # Create a callback for when the value is changed
                callback = self.create_callback(self.modifier_data[entry.label])
                entry.model.add_value_changed_fn(callback)

    def create_callback(self, m: dict):
        """Callback for when a modifier value is changed.

        Parameters
        m : dict
            dictionary containing the modifier data"""

        def callback(v):
            blendshapes = modifiers.get_blendshape_vals(m, v)
            mhusd.edit_blendshapes(self.human_prim, blendshapes)

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

        # Make sure the prim exists
        if not human_prim.IsValid():
            self.human_prim = None
            self.macrovars = {}
            # Destroy the modifier models
            for m in self.group_widgets.values():
                m.destroy()
            return
        self.human_prim = human_prim
        self.macrovars = mhusd.read_macrovars(human_prim)
        self.modifier_data = mhusd.read_modifiers(human_prim)
        self.group_data = mhusd.read_groups(human_prim)
        self._build_widget()


    @Trace.TraceFunction
    def _on_usd_changed(self, notice, stage):
        """Callback for when the USD stage changes"""
        if self.human_prim.GetStage() != stage:
            return
        if self.timecode == current_timecode():
            return
        self.load_values(self.human_prim)


    def destroy(self):
        """Destroys the ParamPanel instance as well as the models attached to each group of parameters"""
        for w in self.group_widgets:
            w.destroy()
        self.group_widgets = []
        super().destroy()


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


class SliderEntry:
    def __init__(
        self,
        label: str,
        model: ui.SimpleFloatModel,
        min: float = 0,
        max: float = 1,
        default: float = 0,
    ):
        """Constructs an instance of SliderEntry

        Parameters
        ----------
        label : str
            Label to display for slider/field
        model : ui.SimpleFloatModel
            Model to publish changes to
        min : float, optional
            Minimum value, by default None
        max : float, optional
            Maximum value, by default None
        default : float, optional
            Default parameter value, by default 0
        """
        self.label = label
        self.model = model
        self.min = min
        self.max = max
        self.default = default
        self._build_widget()

    def _build_widget(self):
        """Construct the UI elements"""
        with ui.HStack(height=0, style=styles.sliderentry_style):
            # Stack the label and slider on top of each other
            with ui.VStack(spacing=5):
                ui.Label(
                    self.label,
                    height=15,
                    alignment=ui.Alignment.CENTER,
                    name="label_param",
                )
                # Limit drag values to within min and max if provided
                if self.min and self.max:
                    self.drag = ui.FloatSlider(
                        model=self.model,
                        step=0.01,
                        min=self.min,
                        max=self.max,
                    )
                    return
                self.drag = ui.FloatSlider(model=self.model, step=0.01)
