"""voxstage — a voicebot engine whose pipeline is observable from the first line.

Every stage emits structured events (JSONL, time.monotonic()), so latency,
cost and errors are measured by the engine itself rather than bolted on later.
"""

__version__ = "0.0.1"
