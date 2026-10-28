"""voxstage — a voicebot engine whose pipeline is observable from the first line.

Every stage emits structured events (JSONL, time.monotonic()), so latency,
cost and errors are measured by the engine itself rather than bolted on later.
"""

__version__ = "0.0.1"

# The normalize package lives beside this one (normalize/, decision R11-4). A checkout that has not installed it still
# imports it: the folder is put on the path when `voxstage_normalize` cannot be found.
import importlib.util as _util
import os as _os
import sys as _sys

if _util.find_spec("voxstage_normalize") is None:
    _sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "normalize"))
