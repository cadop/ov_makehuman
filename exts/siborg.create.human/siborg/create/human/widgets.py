import omni.ui as ui
from . import styles
from .modifiers import Modifier
from typing import List


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
                        min_value=self.min,
                        max_value=self.max,
                    )
                    return
                self.drag = ui.FloatSlider(model=self.model, step=0.01)
