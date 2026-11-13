"""Presentation rules based on loaded sources, independent of GUI choice order."""
INPUT_NAMES = ('Sequential', 'Parallel auto', 'Parallel manual', 'Image File List')


def loaded_input_mode(manager, config, painted=False):
    fallback = {2: 0, 0: 1, 1: 2, 3: 3}.get(manager.type, -1)
    choice = getattr(config, 'status_input_mode', fallback) if config.video_mode else fallback
    if config.video_mode and painted:
        choice = getattr(manager, '_status_input_mode', choice)
    return INPUT_NAMES[choice] if 0 <= choice < len(INPUT_NAMES) else 'Input'


def auto_title_fields(kind, video, sources, serial, parallel_sequential):
    """Return down/up, parent, prefix, name, suffix switches for Title Auto."""
    if video:
        # List, folder and manual inputs describe the same video collection.
        if sources > 1:
            return [False, True, True, bool(serial or parallel_sequential), False]
        return [False, False, True, True, False]
    if kind in (0, 1):
        return [False, True, True, bool(serial or parallel_sequential), False]
    return [False, kind == 3, True, True, False]
