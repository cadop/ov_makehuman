import os
from typing import List, Union
import carb.settings
import omni.kit.commands
from siborg.create.human.mhcaller import MHCaller
import omni.usd
from omni.kit.browser.core import DetailItem
from omni.kit.browser.folder.core import (
    FolderBrowserModel,
    FileDetailItem,
    BrowserFile,
)
from siborg.create.human.shared import data_path
from ..human import Human


class AssetDetailItem(FileDetailItem):
    """Represents Makehuman asset detail item
    """

    def __init__(self, file: BrowserFile):
        """Constructs an instance of AssetDetailItem

        Parameters
        ----------
        file : BrowserFile
            BrowserFile object from which to create detail item
        """
        dirs = file.url.split("/")
        name = dirs[-1]
        super().__init__(name, file.url, file, file.thumbnail)


class MHAssetBrowserModel(FolderBrowserModel):
    """Represents Makehuman asset browser model
    """

    def __init__(self, human: Human, *args, **kwargs):
        """Constructs an instance of MHAssetBrowserModel

        Parameters
        ----------
        human : Human
            The human to which to add assets
        """

        self.human = human

        super().__init__(
            *args,
            show_category_subfolders=True,
            hide_file_without_thumbnails=False,
            **kwargs,
        )
        # Add the data path as the root folder from which to build a collection
        super().append_root_folder(data_path(""), name="MakeHuman")

    def create_detail_item(
        self, file: BrowserFile
    ) -> Union[FileDetailItem, List[FileDetailItem]]:
        """Create detail item(s) from a file.
        A file may include multiple detail items.
        Overwrite parent function to add thumbnails.
        Parameters
        ----------
        file : BrowserFile
            File object to create detail item(s)

        Returns
        -------
        Union[FileDetailItem, List[FileDetailItem]]
            FileDetailItem or list of items created from file
        """

        dirs = file.url.split("/")
        name = dirs[-1]

        # Get the file name without the extension
        filename_noext = os.path.splitext(file.url)[0]

        thumb = filename_noext + ".thumb"
        thumb_png = filename_noext + ".png"

        # If there is already a PNG, get it. If not, rename the thumb file to a PNG
        # (They are the same format just with different extensions). This lets us
        # use Makehuman's asset thumbnails
        if os.path.exists(thumb_png):
            thumb = thumb_png
        elif os.path.exists(thumb):
            os.rename(thumb, thumb_png)
            thumb = thumb_png
        else:
            thumb = None

        return FileDetailItem(name, file.url, file, thumb)
