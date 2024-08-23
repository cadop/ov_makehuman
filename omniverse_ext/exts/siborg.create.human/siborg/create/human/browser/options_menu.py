from omni.kit.browser.core import OptionMenuDescription, OptionsMenu
from omni.kit.browser.folder.core.models.folder_browser_item import FolderCollectionItem
import carb
import asyncio
from ..shared import data_path
from .downloader import Downloader
import omni.ui as ui


class FolderOptionsMenu(OptionsMenu):
    """
    Represent options menu used in material browser. 
    """

    def __init__(self):
        super().__init__()
        # Progress bar widget to show download progress
        self._progress_bar : ui.ProgressBar = None
        self.downloader = Downloader(self.progress_fn,)
        self._download_menu_desc = OptionMenuDescription(
            "Download Assets",
            clicked_fn=self._on_download_assets,
            get_text_fn=self._get_menu_item_text,
            enabled_fn=self.downloader.not_downloading
        )
        self.append_menu_item(self._download_menu_desc)

    def destroy(self) -> None:
        super().destroy()

    def progress_fn(self, proportion: float):
        carb.log_info(f"Download is {int(proportion * 100)}% done")
        if self._progress_bar:
            self._progress_bar.model.set_value(proportion)

    def _get_menu_item_text(self) -> str:
        # Show download state if download starts
        if self.downloader._is_downloading:
            return "Download In Progress"
        return "Download Assets"

    def bind_progress_bar(self, progress_bar):
        self._progress_bar = progress_bar

    def _on_download_assets(self):
        # Show progress bar
        if self._progress_bar:
            self._progress_bar.visible = True
        loop = asyncio.get_event_loop()
        asyncio.run_coroutine_threadsafe(self._download(), loop)

    def _is_remove_collection_enabled(self) -> None:
        '''Don't allow removing the default collection'''
        if self._browser_widget is not None:
            return self._browser_widget.collection_index >= 1
        else:
            return False

    def _on_remove_collection(self) -> None:
        if self._browser_widget is None or self._browser_widget.collection_index < 0:
            return
        else:
            browser_model = self._browser_widget.model
            collection_items = browser_model.get_collection_items()
            if browser_model.remove_collection(collection_items[self._browser_widget.collection_index]):
                # Update collection combobox and default none selected
                browser_model._item_changed(None)
                self._browser_widget.collection_index -= 1

    def _hide_progress_bar(self):
        if self._progress_bar:
            self._progress_bar.visible = False

    async def _download(self):
        # Makehuman system assets
        url = "http://files.makehumancommunity.org/asset_packs/makehuman_system_assets/makehuman_system_assets_cc0.zip"
        # Smaller zip for testing
        # url = "https://download.tuxfamily.org/makehuman/asset_packs/shirts03/shirts03_ccby.zip"
        dest_url = data_path("")
        await self.downloader.download(url, dest_url)
        self._hide_progress_bar()
        self.refresh_collection()

    def refresh_collection(self):
        collection_item: FolderCollectionItem = self._browser_widget.collection_selection
        if collection_item:
            folder = collection_item.folder
            folder._timeout = 10
            asyncio.ensure_future(folder.start_traverse())
