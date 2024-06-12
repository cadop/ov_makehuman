import omni.ui as ui
from . import styles
from .modifiers import Modifier
from typing import List


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
                        step=self.step,
                        min_value=self.min,
                        max_value=self.max,
                    )
                    return
                self.drag = ui.FloatSlider(model=self.model, step=self.step)


class SliderGroup:
    """A UI widget providing a labeled group of slider entries

    Attributes
    ----------
    label : str
        Display title for the group. Can be none if no title is desired.
    """

    def __init__(self, label: str = None, modifiers: List[Modifier] = None):
        self.label = label
        self.modifiers = modifiers or []
        self.slider_entries = []
        self._build_widget()

    def _build_widget(self):
        """Construct the UI elements"""
        with ui.CollapsableFrame(self.label, style=styles.panel_style, collapsed=True, height=0):
            with ui.VStack(name="contents", spacing=8):
                # Create a slider entry for each parameter
                for m in self.modifiers:
                    self.slider_entries.append(
                        SliderEntry(
                            m.label,
                            m.value_model,
                            m.fn,
                            image=m.image,
                            min=m.min_val,
                            max=m.max_val,
                            default=m.default_val,
                        )
                    )

    def destroy(self):
        """Destroys the instance of SliderEntryPanel. Executes the destructor of
        the SliderEntryPanel's SliderEntryPanelModel instance.
        """
        for entry in self.slider_entries:
            entry.model.destroy()
