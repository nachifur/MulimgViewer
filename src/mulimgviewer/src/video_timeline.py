"""Shared global-page to local-video mapping used by playback and the index."""


def page_count(counts, size, sequential=False):
    size = max(1, int(size))
    counts = [max(0, int(value)) for value in counts]
    frames = sum(counts) if sequential else max(counts, default=0)
    return (frames + size - 1) // size


def page_segments(counts, size, batch, sequential=False):
    """Return (video, first, stop) spans, with no padding between serial videos."""
    size = max(1, int(size))
    if batch < 0 or batch >= page_count(counts, size, sequential):
        return []
    result = []
    if sequential:
        first, stop = batch * size, (batch + 1) * size
        base = 0
        for video, count in enumerate(counts):
            count = max(0, int(count))
            start, end = max(first, base), min(stop, base + count)
            if start < end:
                result.append((video, start-base, end-base))
            base += count
    else:
        for video, count in enumerate(counts):
            count = max(0, int(count))
            if count:
                local = min(batch, (count-1)//size)
                result.append((video, local*size, min((local+1)*size, count)))
    return result


def raw_dependencies(counts, size, batch, sequential=False):
    size = max(1, int(size))
    return [(video, local) for video, start, stop in page_segments(counts, size, batch, sequential)
            for local in range(start//size, (stop-1)//size+1)]
