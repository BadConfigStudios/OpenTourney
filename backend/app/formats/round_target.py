import math


def recommended_rounds(active_entry_count: int) -> int:
    """ceil(log2(active_entry_count)) — the standard Swiss round-count
    recommendation for a given active (non-dropped) entry count. Returns
    0 for 0 or 1 active entries, where no meaningful round target exists."""
    if active_entry_count <= 1:
        return 0
    return math.ceil(math.log2(active_entry_count))
