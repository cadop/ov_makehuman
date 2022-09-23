import omni.ui as ui
from . import mhcaller
from .human_ui import ParamPanel, ButtonPanel, HumanPanel
from .browser import AssetBrowserFrame
from .ui_widgets import *
from .styles import window_style

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
    

    def __init__(self, *args, **kwargs):
        """Constructs an instance of MHWindow"""

        super().__init__(*args, **kwargs)

        # Reference to UI panel for destructor
        self.panel = None
        # Reference to asset browser for destructor
        self.browser = None

        # Dock UI wherever the "Content" tab is found (bottom panel by default)
        self.deferred_dock_in(
            "Content", ui.DockPolicy.CURRENT_WINDOW_IS_ACTIVE)

        self.frame.set_build_fn(self._build_ui)

    def _build_ui(self):

        # Create instance of manager class
        mh_call = mhcaller.MHCaller()

        mh_call.filepath = "D:/human.obj"

        # Right-most panel includes panels for modifiers, listing/removing
        # applied proxies, and executing Human creation and updates
        self.panel = HumanPanel(mh_call)
        # Left-most panel is a browser for MakeHuman assets. It includes
        # a reference to the list of applied proxies so that an update
        # can be triggered when new assets are added
        self.browser = AssetBrowserFrame(mh_call, self.panel.toggle)

        
        with self.frame:

            # Widgets are built starting on the right
            with ui.HStack(style = window_style):
                with ui.ZStack(width=0):
                    # Draggable splitter
                    with ui.Placer(offset_x=600,draggable=True, drag_axis=ui.Axis.X):
                        ui.Rectangle(width=5, name="splitter")
                    with ui.VStack():
                        with ui.HStack():
                            self.browser.build_widget()
                            ui.Spacer(width=10)
                self.panel.build_widget()



    # Properly destroying UI elements and references prevents 'Zombie UI'
    # (abandoned objects that interfere with Kit)
    def destroy(self):
        """Destroys the instance of MHWindow
        """
        super().destroy()
        self.panel.destroy()