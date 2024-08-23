from omni.kit.browser.folder.core import FolderBrowserWidget
from .delegate import AssetDetailDelegate
from .model import MHAssetBrowserModel
from .options_menu import FolderOptionsMenu
import omni.ui as ui


class AssetBrowserFrame:
    """A widget to browse and select Makehuman assets
    Attributes
    ----------
    mhcaller : MHCaller
        Wrapper object for Makehuman functions
    """

    def __init__(self, model: MHAssetBrowserModel, **kwargs):
        """Constructs an instance of AssetBrowserFrame. This is a browser that
        displays available Makehuman assets (skeletons/rigs, proxies) and allows
        a user to apply them to the human.

        Parameters
        ----------
        model : MHAssetBrowserModel
            A model to hold browser data
        """
        self.model = model
        self.build_widget()

    def build_widget(self):
        """Build UI widget"""
        # The delegate to execute browser actions
        self._delegate = AssetDetailDelegate(self.model)
        # Drop down menu to hold options
        self._options_menu = FolderOptionsMenu()

        with ui.VStack():
            self._widget = FolderBrowserWidget(
                self.model, detail_delegate=self._delegate, options_menu=self._options_menu)
            ui.Separator(height=2)
            # Progress bar to show download progress (initially hidden)
            self._progress_bar = ui.ProgressBar(height=20, visible=False)
            self._options_menu.bind_progress_bar(self._progress_bar)
