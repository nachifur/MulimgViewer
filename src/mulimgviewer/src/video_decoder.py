"""Incremental, ordinal-accurate decoding with bounded resident codec state."""
import threading
from collections import OrderedDict
from contextlib import contextmanager
from PIL import Image
from concurrent.futures import CancelledError
if __package__:
    from .video_seek_index import PacketKeyframeIndex
else:
    from video_seek_index import PacketKeyframeIndex

try:
    import av
except (ImportError, OSError):
    av = None


class DecoderSession:
    def __init__(self, path, fps, fast_seek, pixels, threads=1):
        self.path, self.fps, self.fast_seek = str(path), fps, fast_seek
        self.threads = max(1,int(threads))
        self.bytes_hint = max(8 * 1024**2, int(pixels) * (24+8*self.threads))
        self.container = self.iterator = self.stream = None
        self.next_index = 0
        self.lock = threading.Lock()
        self.users = 0
        self.anchors = OrderedDict()
        self.opens = self.decoded = self.seeks = 0
        self.packet_index = None
        self.packet_index_failed = False

    def close(self):
        if self.packet_index is not None:self.packet_index.close()
        if self.container is not None:
            self.iterator = None
            self.container.close()
        self.container = self.stream = None
        self.next_index = 0

    def _open(self):
        # Old RealMedia/AVI metadata may use a legacy code page. A malformed
        # title must not disable incremental decoding of valid video pixels.
        self.container = av.open(self.path, metadata_errors='replace')
        self.stream = self.container.streams.video[0]
        self.stream.codec_context.thread_count = self.threads
        if self.threads>1:
            self.stream.codec_context.thread_type = "AUTO"
        self.iterator = iter(self.container.decode(self.stream))
        self.next_index = 0
        self.opens += 1

    def _seek(self, target, cancelled=lambda:False):
        # Known keyframe ordinals work for VFR and nonzero stream start times.
        anchors = [(index, pts) for index, pts in self.anchors.items() if index <= target]
        distance = target-max((index for index,_ in anchors), default=0)
        if (not self.fast_seek and not self.packet_index_failed and distance>128
                and self.stream.codec_context.name in ('rv30','rv40')):
            try:
                if self.packet_index is None:
                    self.packet_index = PacketKeyframeIndex(self.path, av.open,
                                                           probe_time_base=self.stream.time_base)
                anchors = self.packet_index.ensure(target, cancelled)
                for index,pts in anchors:self.anchors[index] = pts
                while len(self.anchors)>4096:self.anchors.popitem(last=False)
            except (OSError,ValueError):
                self.packet_index_failed = True
                self.packet_index.close()
        if not anchors and not self.fast_seek and self.next_index == 0:
            return  # Already at the exact start; do not reopen a fresh codec.
        if self.fast_seek and anchors and target-max(anchors)[0] > self.fps*2:
            anchors = []
        if anchors:
            index, pts = max(anchors)
            self.container.seek(int(pts), stream=self.stream, backward=True, any_frame=False)
            self.iterator = self._seek_frames()
            for frame in self.iterator:
                if cancelled():raise CancelledError()
                if frame.pts == pts:
                    self.next_index = index
                    self.iterator = self._prepend(frame, self.iterator)
                    self.seeks += 1
                    return
                if frame.pts is not None and frame.pts > pts:
                    break
        elif self.fast_seek and target > 0:
            timestamp = int(target / self.fps / self.stream.time_base)
            self.container.seek(timestamp, stream=self.stream, backward=True, any_frame=False)
            self.iterator = iter(self.container.decode(self.stream))
            try:
                frame = next(self.iterator)
                position = float(frame.pts * frame.time_base) * self.fps
                index = round(position)
                if 0 <= index <= target and abs(index-position) < .01:
                    self.next_index = index
                    self.iterator = self._prepend(frame, self.iterator)
                    self.seeks += 1
                    return
            except (StopIteration, TypeError, ValueError):
                pass
        # Never assign approximate VFR timestamps to exact ordinal frame IDs.
        if cancelled():raise CancelledError()
        self.close()
        self._open()

    def _seek_frames(self):
        """Discard invalid pre-roll packets before the first reference picture.

        Some RM indexes seek to an I picture followed by older B packets whose
        previous reference is unavailable. Preserve errors after the anchor.
        """
        established = False
        invalid = 0
        for packet in self.container.demux(self.stream):
            try:frames = packet.decode()
            except av.error.InvalidDataError:
                invalid += 1
                if established or invalid>64:raise
                continue
            for frame in frames:
                established = established or frame.key_frame
                yield frame

    @staticmethod
    def _prepend(frame, iterator):
        yield frame
        yield from iterator

    @staticmethod
    def _buffered_image(frame):
        # Let Pillow's native raw decoder read the strided RGB plane directly.
        # This removes PyAV.to_image's Python row loop, bytearray and bytes
        # copies. The resulting RGB image OWNS its pixels; it never aliases a
        # codec buffer or depends on decoder/container lifetime.
        try:
            rgb = frame.reformat(format='rgb24')
            plane = rgb.planes[0]
            if plane.line_size < rgb.width * 3 or plane.buffer_size < plane.line_size * rgb.height:
                raise ValueError('Unsupported video buffer stride')
            return Image.frombytes('RGB', (rgb.width, rgb.height), plane,
                                   'raw', 'RGB', plane.line_size, 1)
        except (AttributeError, TypeError, ValueError, NotImplementedError):
            # Keep the established conversion for older buffer APIs/formats.
            # Do not catch MemoryError and allocate another full-size image.
            return frame.to_image()

    def frames(self, first, last, step, cancelled, buffer_images=False):
        if cancelled():return
        opened = self.container is None
        if opened:
            self._open()
        distant = (first-self.next_index>max(128,int(self.fps*2))
                   and (self.fast_seek or self.stream.codec_context.name in ('rv30','rv40')))
        if first < self.next_index or (opened and first > 0) or distant:
            try:self._seek(first, cancelled)
            except CancelledError:
                self.close()
                return
        for frame in self.iterator:
            if cancelled():
                # The generator has consumed this frame. Advance even when a
                # window change discards it, preserving subsequent ordinals.
                self.next_index += 1
                return
            index = self.next_index
            self.next_index += 1
            self.decoded += 1
            if frame.key_frame and frame.pts is not None:
                self.anchors[index] = int(frame.pts)
                if len(self.anchors) > 4096:
                    self.anchors.popitem(last=False)
            if index >= first and (index-first) % step == 0:
                rotation = getattr(frame, 'rotation', 0)
                # Arbitrary/mirrored display matrices retain FFmpeg's exact
                # autorotation path rather than silently changing the image.
                matrix = frame.side_data.get('DISPLAYMATRIX')
                if matrix is not None:
                    import struct
                    values = struct.unpack('=9i',bytes(matrix))
                    if not hasattr(frame,'rotation'):
                        raise ValueError('Display-matrix API unavailable; use FFmpeg autorotation')
                    if values[0]*values[4]-values[1]*values[3] < 0 or rotation % 90:
                        raise ValueError('Unsupported display transform; use FFmpeg autorotation')
                image = self._buffered_image(frame) if buffer_images else frame.to_image()
                transform = {90:Image.ROTATE_90,180:Image.ROTATE_180,270:Image.ROTATE_270}.get(int(rotation)%360)
                if transform is not None:
                    image = image.transpose(transform)
                yield index, image
            if index >= last:
                return


class DecoderBank:
    def __init__(self, limit=0):
        self.lock = threading.RLock()
        self.limit = max(0, int(limit))
        self.sessions = OrderedDict()
        self.disabled = set()
        self.closed = False
        self.idle_policy = None
        self.idle_bytes = 0

    @property
    def available(self):
        return av is not None

    def configure(self, limit):
        # A GUI policy update must not wait while a background trim closes a
        # codec. Only publish the new immutable integer here; workers trim.
        self.limit = max(0, int(limit))

    @contextmanager
    def lease(self, path, fps, fast_seek, pixels, threads=1):
        key = str(path)
        with self.lock:
            if self.closed:
                raise RuntimeError('Decoder bank is closed')
            self._trim()
            session = self.sessions.get(key)
            if session is None:
                session = self.sessions[key] = DecoderSession(path, fps, fast_seek, pixels, threads)
            self.sessions.move_to_end(key)
            was_resident = session.container is not None
            session.users += 1
            if was_resident and session.users == 1:
                self.idle_bytes = max(0, self.idle_bytes-session.bytes_hint)
        try:
            with session.lock:
                if session.threads != threads:
                    session.close()
                    session.threads = threads
                    session.bytes_hint = max(8*1024**2, int(pixels)*(24+8*threads))
                yield session
        finally:
            with self.lock:
                session.users -= 1
                self._trim(prefer=session if not was_resident else None)

    def _trim(self, prefer=None):
        # Active codec state is charged to the executor's weighted working
        # set. This reservation covers IDLE retained contexts only; counting
        # both would artificially evict useful state during every scan.
        limit, covered = self.limit, set()
        if not self.closed and self.idle_policy is not None:
            limit, covered = self.idle_policy()
        def idle(key, session):
            return session.container is not None and session.users == 0 and key not in covered
        resident = sum(s.bytes_hint for key, s in self.sessions.items() if idle(key, s))
        # A cyclic scan larger than the cache must not evict every resident
        # decoder. Keep a useful stable subset; newly opened transient codecs
        # are the first eviction candidates when the idle reservation is full.
        if resident > limit and prefer is not None and idle(str(prefer.path), prefer):
            prefer.close()
            resident -= prefer.bytes_hint
        for key, session in self.sessions.items():
            if resident <= limit:
                break
            if idle(key, session):
                session.close()
                resident -= session.bytes_hint
        # Publish a scalar snapshot so GUI-side budget calculation never
        # waits for a codec close under this bank's lock.
        self.idle_bytes = sum(s.bytes_hint for s in self.sessions.values()
                              if s.container is not None and s.users == 0)

    def trim(self, paths=None):
        with self.lock:
            if paths is not None:
                for key, session in list(self.sessions.items()):
                    if key not in paths and session.users == 0:
                        session.close()
                        del self.sessions[key]
            self._trim()

    def close(self):
        with self.lock:
            self.closed = True
            self.limit = 0
            self._trim()  # Leased contexts close when their current task exits.
