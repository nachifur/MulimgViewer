"""Five independent X/Y gaps, with migration of the legacy four-pair layout."""

GROUPS = ('func', 'xy', 'one', 'unit', 'magnifier')
DEFAULT_FUNC_GAP = (10, 10)


def normalize_gaps(values):
    """Keep old XY/One/Unit/magnifier values when adding the Func pair."""
    if isinstance(values, str):
        values = values.split(',')
    values = [int(value) for value in values]
    if len(values) == 8:
        values = list(DEFAULT_FUNC_GAP) + values
    if len(values) != 10:
        raise ValueError('Gap requires five X/Y pairs: Func, XY, One, Unit, magnifier')
    return values


def gap_pair(values, group):
    start = GROUPS.index(group) * 2
    return normalize_gaps(values)[start:start + 2]
