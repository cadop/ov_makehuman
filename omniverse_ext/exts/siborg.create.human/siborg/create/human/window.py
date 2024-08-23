from .ext_ui import NoSelectionNotification, ModifierUI
# from .browser import MHAssetBrowserModel, AssetBrowserFrame
import omni.ui as ui
import omni.kit.ui
import omni
import carb
from . import mhusd, styles
import json, os

WINDOW_TITLE = "Human Generator"
MENU_PATH = f"Window/{WINDOW_TITLE}"

class MHWindow(ui.Window):
    """
    Main UI window. Contains all UI widgets. Extends omni.ui.Window.

    Attributes
    -----------
    panel : HumanPanel
        A widget that includes panels for modifiers, listing/removing applied
        proxies, and executing human creation and updates
    browser: AssetBrowserFrame
        A browser for MakeHuman assets, including clothing, hair, and skeleton rigs.
    """

    def __init__(self, title):
        """Constructs an instance of MHWindow
        
        Parameters
        ----------
        menu_path : str
            The path to the menu item that opens the window
        """

        super().__init__(title)

        # # A model to hold browser data
        # self.browser_model = MHAssetBrowserModel(
        #     self._human,
        #     filter_file_suffixes=["mhpxy", "mhskel", "mhclo"],
        #     timeout=carb.settings.get_settings().get(
        #         "/exts/siborg.create.human.browser.asset/data/timeout"
        #     ),
        # )


        # Subscribe to selection events on the message bus
        bus = omni.kit.app.get_app().get_message_bus_event_stream()
        selection_event = carb.events.type_from_string("siborg.create.human.human_selected")
        self._selection_sub = bus.create_subscription_to_push_by_type(selection_event, self._on_selection_changed)
        self.frame.set_build_fn(self._build_ui)

    def _build_ui(self):
        spacer_width = 3
        with self.frame:
            # Widgets are built starting on the left
            with ui.HStack(style=styles.window_style):
                # Widget to show if no human is selected
                self.no_selection_notification = NoSelectionNotification()

                self.property_panel = ui.HStack(visible=False)
                with self.property_panel:
                    # with ui.ZStack(width=0):
                    #     # Draggable splitter
                    #     with ui.Placer(offset_x=self.frame.computed_content_width/1.8, draggable=True, drag_axis=ui.Axis.X):
                    #         ui.Rectangle(width=spacer_width, name="splitter")
                    #     with ui.HStack():
                    #         # Left-most panel is a browser for MakeHuman assets. It includes
                    #         # a reference to the list of applied proxies so that an update
                    #         # can be triggered when new assets are added
                    #         self.browser = AssetBrowserFrame(self.browser_model)
                    #         ui.Spacer(width=spacer_width)
                    with ui.HStack():
                        with ui.VStack():
                            self.modifier_ui = ModifierUI()
                with ui.VStack(width = 100, style=styles.button_style):
                    # Creates a new human in scene and resets modifiers and assets
                    ui.Button(
                        "New Human",
                        clicked_fn=mhusd.add_to_scene,
                    )
                    # Resets modifiers and assets on selected human
                    self.reset_button = ui.Button(
                        "Reset Human",
                        clicked_fn=self.reset_human,
                        enabled=False,
                    )
                    # Build a human from scratch
                    ui.Button(
                        "Build Human",
                        clicked_fn=mhusd.make_human,
                    )


    def _on_selection_changed(self, event):
        """Callback for human selection events

        Parameters
        ----------
        event : carb.events.Event
            The event that was pushed to the event stream. Contains payload data with
            the selected prim path, or "None" if no human is selected
        """

        # Get the stage
        stage = omni.usd.get_context().get_stage()

        prim_path = event.payload["prim_path"]

        # If a valid human prim is selected, 
        if not prim_path or not stage.GetPrimAtPath(prim_path):
            # Hide the property panel
            self.property_panel.visible = False

            # Show the no selection notification
            self.no_selection_notification.visible = True

            # Deactivate the reset button
            self.reset_button.enabled = False

        else:

            # Show the property panel
            self.property_panel.visible = True

            # Hide the no selection notification
            self.no_selection_notification.visible = False

            # Activate the reset button
            self.reset_button.enabled = True

            # Get the prim from the path in the event payload
            prim = stage.GetPrimAtPath(prim_path)
            self.modifier_ui.load_values(prim)



    def reset_human(self):
        # """Resets the current human in the scene"""
        # # Reset the human
        # self._human.reset()

        # # Delete the proxy prims
        # self._human.delete_proxies()

        # # Update the human in the scene and reset parameter widgets
        # self.update_human()
        pass

    def destroy(self):
        """Called when the window is destroyed. Unsuscribes from human selection events"""
        self._selection_sub.unsubscribe()
        self._selection_sub = None
        super().destroy()
