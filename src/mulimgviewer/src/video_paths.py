"""Frame path naming shared by extraction and future/virtual index entries."""

def frame_filename(index, fps, step=1):
    physical = int(index)*max(1,int(step))
    fps = float(fps or 0)
    rounded = max(1,int(round(fps))) if fps > 0 else 1
    seconds = f'{physical/(fps if fps > 0 else rounded):.2f}'.rstrip('0').rstrip('.') or '0'
    return f'{seconds}s_frame_{physical%rounded+1}.jpeg'
