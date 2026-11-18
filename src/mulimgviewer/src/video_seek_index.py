"""Bounded, lazy ordinal indexes for supported frame-aligned video packets."""
from collections import OrderedDict
from concurrent.futures import CancelledError
from heapq import heappop, heappush
from threading import BoundedSemaphore
from threading import Event, Thread
from queue import Queue, Empty, Full
import subprocess

if __package__:
    from .video_tools import resolve_video_tools
    from .resource_monitor import tracked_video_process
    from .video_index_store import VideoIndexStore
    from .video_mp4_index import mp4_keyframes
else:
    from video_tools import resolve_video_tools
    from resource_monitor import tracked_video_process
    from video_index_store import VideoIndexStore
    from video_mp4_index import mp4_keyframes


# Packet scans share disk bandwidth and Python demux/reorder work. Starting
# one scan per CPU slot caused severe contention with 24 large inputs. This
# limits only index I/O; normal video decoding keeps its full worker budget.
_SCAN_READERS = BoundedSemaphore(2)
# Native demuxing avoids per-packet Python/GIL transitions. The independent
# I/O cap still sits inside the executor's admitted decoder worker budget.
_PROBE_READERS = BoundedSemaphore(4)


class PacketKeyframeIndex:
    """Count presentation ordinals without decoding or assuming a frame rate.

    RM demuxing merges slices into complete video-frame packets. A small
    reorder heap handles B pictures arriving after their reference pictures.
    Only keyframes are retained, never a filename or pixel buffer per frame.
    """
    def __init__(self, path, opener, probe_time_base=None, index_cache_dir=None):
        self.path, self.opener = path, opener
        self.anchors = OrderedDict()
        self.container = self.iterator = None
        self.count = 0
        self.heap = []
        self.last_pts = None
        self.exhausted = False
        self.probe_time_base = probe_time_base
        self._probe_through = -1
        self._store=None
        self._cache_checked=False
        self._index_cache_dir=index_cache_dir

    def close(self):
        if self.container is not None:self.container.close()
        self.container = self.iterator = None
        self.heap.clear()
        self.count = 0
        self.last_pts = None
        self.exhausted = False
        if self.probe_time_base is None:self._probe_through = -1

    def _commit(self):
        pts, keyframe = heappop(self.heap)
        if self.last_pts is not None and pts <= self.last_pts:
            raise ValueError('Packet timestamps cannot establish unique presentation ordinals')
        if keyframe:
            self.anchors[self.count] = pts
            if len(self.anchors)>4096:self.anchors.popitem(last=False)
        self.count += 1
        self.last_pts = pts

    def ensure(self, target, cancelled):
        readers = _PROBE_READERS if self.probe_time_base is not None else _SCAN_READERS
        while not readers.acquire(timeout=.05):
            if cancelled():raise CancelledError()
        try:
            if cancelled():raise CancelledError()
            return self._scan(target, cancelled)
        finally:readers.release()

    def _scan(self, target, cancelled):
        if self.probe_time_base is not None:
            try:return self._scan_probe(target, cancelled)
            except (OSError, ValueError, subprocess.SubprocessError):
                # Missing/incompatible probes retain the established PyAV
                # path, without disabling exact incremental video decoding.
                self.probe_time_base = None
                self.close()
                self.anchors.clear()
        if self.anchors and target<min(self.anchors):
            self.close()
            self.anchors.clear()
        if self.container is None:
            # This reader only scans forward; it never seeks. Loading RM's
            # potentially huge audio/native indexes makes each packet costly
            # and is unnecessary for our own sparse presentation-order index.
            # The actual decoder retains its normal native seek indexes.
            self.container = self.opener(self.path, metadata_errors='replace',
                                         options={'fflags': '+ignidx'})
            self.iterator = iter(self.container.demux(self.container.streams.video[0]))
        while self.count <= target and not self.exhausted:
            if cancelled():raise CancelledError()
            try:packet = next(self.iterator)
            except StopIteration:
                while self.heap:self._commit()
                self.exhausted = True
                break
            if not packet.size or getattr(packet,'is_discard',False):continue
            if packet.pts is None:raise ValueError('Packet has no presentation timestamp')
            heappush(self.heap, (int(packet.pts), bool(packet.is_keyframe)))
            if len(self.heap)>64:self._commit()
        return [(index,pts) for index,pts in self.anchors.items() if index<=target]

    def _scan_probe(self, target, cancelled):
        """Demux in native code rather than crossing the Python GIL per packet.

        Stop and reap the probe at the requested ordinal. Later scans restart
        at an EXACT known keyframe, not at a frame-rate-derived timestamp.
        """
        if not self._cache_checked:
            self._cache_checked=True
            try:
                self._store=VideoIndexStore(self.path,self.probe_time_base,self._index_cache_dir)
                saved=self._store.load()
                if saved is not None:
                    self._probe_through,anchors=saved
                    self.anchors.update(anchors)
                    self.count=self._probe_through+1
            except OSError:self._store=None
        if self.anchors and target < min(self.anchors):
            self.anchors.clear()
            self._probe_through = -1
        if target <= self._probe_through:
            return [(i,p) for i,p in self.anchors.items() if i<=target]
        tables=mp4_keyframes(self.path,self.opener,self.probe_time_base,target)
        if cancelled():raise CancelledError()
        if tables is not None:
            self._probe_through,anchors=tables
            self.anchors=OrderedDict(anchors)
            self.count=self._probe_through+1
            if self._store is not None:self._store.save(self._probe_through,anchors)
            return anchors
        known = [(i,p) for i,p in self.anchors.items() if i<=target]
        start = max(known) if known else None
        self.count = start[0] if start else 0
        self.heap.clear()
        self.last_pts = None
        packets = self._probe_packets(start, cancelled)
        try:
            for pts, keyframe in packets:
                if cancelled():raise CancelledError()
                if start is not None and pts < start[1]:continue
                if start is not None and not self.heap and self.last_pts is None and pts != start[1]:
                    raise ValueError('Probe did not return the exact indexed anchor')
                heappush(self.heap,(pts,keyframe))
                if len(self.heap)>64:self._commit()
                if self.count>target:break
            else:
                while self.heap:self._commit()
                self.exhausted = True
            self._probe_through = self.count-1
            if self._store is not None:
                self._store.save(self._probe_through,self.anchors.items())
        finally:
            packets.close()
            self.heap.clear()
        return [(i,p) for i,p in self.anchors.items() if i<=target]

    def _probe_packets(self, start, cancelled):
        commands, env = resolve_video_tools()
        args = [commands['ffprobe'],'-v','error','-fflags','+ignidx',
                '-select_streams','v:0','-show_entries','packet=pts,flags:packet_side_data=',
                '-of','csv=p=0']
        if start is not None:
            seconds = float((start[1]-1)*self.probe_time_base)
            if start[1]>=0:seconds=max(0.,seconds)
            args.extend(['-read_intervals',f'{seconds:.9f}%'])
        args.append(str(self.path))
        options = dict(stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,
                       env=env,bufsize=0)
        if hasattr(subprocess,'CREATE_NO_WINDOW'):options['creationflags']=subprocess.CREATE_NO_WINDOW
        # A fixed queue bounds read-ahead. Its reader lets cancellation remain
        # responsive even if a filesystem or a damaged probe stops producing.
        blocks, stop = Queue(maxsize=4), Event()
        with tracked_video_process(args,**options) as process:
            def read():
                while not stop.is_set():
                    try:block=process.stdout.read(65536)
                    except (OSError,ValueError):block=b''
                    while not stop.is_set():
                        try:blocks.put(block,timeout=.05);break
                        except Full:continue
                    if not block:return
            reader=Thread(target=read,name='video-index-pipe',daemon=True)
            reader.start()
            tail=b''
            try:
                while True:
                    if cancelled():raise CancelledError()
                    try:block=blocks.get(timeout=.05)
                    except Empty:continue
                    if not block:
                        while process.poll() is None:
                            if cancelled():raise CancelledError()
                            try:process.wait(timeout=.05)
                            except subprocess.TimeoutExpired:continue
                        if process.returncode!=0:raise OSError('Packet probe failed')
                        if tail.strip():raise ValueError('Incomplete packet probe record')
                        return
                    lines=(tail+block).split(b'\n')
                    tail=lines.pop()
                    if len(tail)>65536:raise ValueError('Oversized packet probe record')
                    for line in lines:
                        if not line.strip():continue
                        pts,separator,flags=line.strip().partition(b',')
                        if not separator:raise ValueError('Invalid packet probe record')
                        if b'D' not in flags:yield int(pts),b'K' in flags
            finally:
                stop.set()
                if process.poll() is None:process.kill()
                process.wait()
                reader.join(timeout=1)
