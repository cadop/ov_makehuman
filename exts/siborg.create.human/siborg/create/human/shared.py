from pathlib import Path
import os
import Usd
import omni.timeline

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

def current_timecode() -> Usd.TimeCode:
    """Get the current timecode from the timeline"""
    timeline_interface = omni.timeline.get_timeline_interface()
    timecodes_per_second = timeline_interface.get_time_codes_per_seconds()
    time = timeline_interface.get_current_time()
    return Usd.TimeCode(time * timecodes_per_second)
