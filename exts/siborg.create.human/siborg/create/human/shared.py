from pathlib import Path
import os

# Shared methods that are useful to several modules


def data_path(path):
    """Returns the absolute path of a path given relative to "exts/<omni.ext>/data"

    Parameters
    ----------
    path : str
        Relative path

    Returns
    -------
    str
        Absolute path
    """
    # Uses an absolute path, and then works its way up the folder directory to find the data folder
    data = os.path.join(str(Path(__file__).parents[3]), "data", path)
    return data
