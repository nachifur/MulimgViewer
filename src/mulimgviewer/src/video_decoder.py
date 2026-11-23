"""Video decoding, frame-accurate seeking and bounded decoder sessions."""
import hashlib
import json
import numpy as np
import os
import struct
import subprocess
import sys
import tempfile
import threading
from PIL import Image
from collections import OrderedDict
from concurrent.futures import CancelledError
from contextlib import contextmanager
from fractions import Fraction
from heapq import heappop, heappush
from pathlib import Path
from queue import Empty, Full, Queue
from threading import BoundedSemaphore, Event, Thread

if __package__:
    from .resources import tracked_video_process
    from .video_source import resolve_video_tools
else:
    from resources import tracked_video_process
    from video_source import resolve_video_tools


# Keyframe indexes and seek metadata
# Persistent seek metadata
def index_cache_directory():
    override=os.environ.get('MULIMGVIEWER_INDEX_CACHE')
    if override:return Path(override)
    if sys.platform=='win32':
        base=Path(os.environ.get('LOCALAPPDATA') or Path.home()/'AppData'/'Local')
    elif sys.platform=='darwin':base=Path.home()/'Library'/'Caches'
    else:base=Path(os.environ.get('XDG_CACHE_HOME') or Path.home()/'.cache')
    return base/'MulimgViewer'/'video_indexes'


class VideoIndexStore:
    """Source changes invalidate metadata; bounded LRU files contain no pixels."""
    MAX_BYTES=512*1024
    MAX_FILES=256
    MAX_TOTAL_BYTES=64*1024**2

    def __init__(self,path,time_base,directory=None):
        self.source=Path(path)
        self.time_base=str(time_base)
        self.directory=Path(directory) if directory is not None else index_cache_directory()
        self.signature=self._signature()
        payload=json.dumps([str(self.source.absolute()),self.signature,self.time_base],ensure_ascii=True)
        self.key=hashlib.sha256(payload.encode('ascii')).hexdigest()
        self.path=self.directory/(self.key+'.json')

    def _signature(self):
        info=self.source.stat()
        return [info.st_dev,info.st_ino,info.st_size,info.st_mtime_ns,info.st_ctime_ns]

    def load(self):
        try:
            if self._signature()!=self.signature:return None
            with self.path.open('rb') as stream:contents=stream.read(self.MAX_BYTES+1)
            if len(contents)>self.MAX_BYTES:return None
            data=json.loads(contents)
            if (data.get('version')!=1 or data.get('source')!=self.signature
                    or data.get('time_base')!=self.time_base):return None
            through=data['through'];anchors=data['anchors']
            checksum=hashlib.sha256(json.dumps([through,anchors],separators=(',',':')).encode('ascii')).hexdigest()
            if data.get('checksum')!=checksum:return None
            if type(through) is not int or through<0 or not isinstance(anchors,list) or not 1<=len(anchors)<=4096:
                return None
            previous=(-1,None)
            for pair in anchors:
                if not isinstance(pair,list) or len(pair)!=2 or any(type(x) is not int for x in pair):return None
                index,pts=pair
                if (index<=previous[0] or index>through
                        or (previous[1] is not None and pts<=previous[1])):return None
                previous=index,pts
            try:os.utime(self.path,None)
            except OSError:pass
            return through,anchors
        except (OSError,ValueError,TypeError,KeyError,AttributeError):return None

    def save(self,through,anchors):
        temporary=None
        try:
            if not anchors or self._signature()!=self.signature:return
            data=dict(version=1,source=self.signature,time_base=self.time_base,
                      through=through,anchors=list(anchors)[-4096:])
            data['checksum']=hashlib.sha256(json.dumps([through,data['anchors']],separators=(',',':')).encode('ascii')).hexdigest()
            contents=json.dumps(data,separators=(',',':')).encode('ascii')
            if len(contents)>self.MAX_BYTES:return
            self.directory.mkdir(parents=True,exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=self.directory,prefix='.index-',suffix='.tmp',delete=False) as stream:
                temporary=Path(stream.name)
                stream.write(contents)
            os.replace(temporary,self.path)
            self._prune()
        except (OSError,ValueError,TypeError):pass
        finally:
            if temporary is not None:
                try:temporary.unlink()
                except OSError:pass

    def _prune(self):
        entries=[]
        for path in self.directory.glob('*.json'):
            # Only remove files owned by this metadata store.
            if len(path.stem)!=64 or any(c not in '0123456789abcdef' for c in path.stem):continue
            try:
                info=path.stat();entries.append((info.st_mtime_ns,info.st_size,path))
            except OSError:continue
        entries.sort()
        size=sum(entry[1] for entry in entries)
        count=len(entries)
        for _,length,path in entries:
            if count<=self.MAX_FILES and size<=self.MAX_TOTAL_BYTES:break
            try:path.unlink()
            except OSError:continue
            size-=length;count-=1


# MP4 sample-table fast path
# Bound the vectorized fast path. Larger tables keep the streaming packet
# scanner, so this never becomes a video-length or playback restriction.
MAX_SAMPLES=250000
MAX_TABLE_BYTES=4*1024**2


def _boxes(stream,start,end):
    position=start
    boxes=0
    while position<end:
        boxes+=1
        if boxes>16384:raise ValueError('Excessive MP4 boxes')
        if position+8>end:raise ValueError('Truncated MP4 box')
        stream.seek(position)
        size,kind=struct.unpack('>I4s',stream.read(8));header=8
        if size==1:
            size=struct.unpack('>Q',stream.read(8))[0];header=16
        if size==0:size=end-position
        if size<header or position+size>end:raise ValueError('Invalid MP4 box')
        yield kind,(position+header,position+size)
        position+=size


def _find(stream,bounds,kind):
    matches=[box for name,box in _boxes(stream,*bounds) if name==kind]
    if len(matches)!=1:raise ValueError('Missing or duplicate MP4 table')
    return matches[0]


def _read(stream,bounds,length=None):
    size=bounds[1]-bounds[0] if length is None else length
    if size>MAX_TABLE_BYTES or size>bounds[1]-bounds[0]:raise ValueError('Oversized MP4 table')
    stream.seek(bounds[0]);data=stream.read(size)
    if len(data)!=size:raise ValueError('Truncated MP4 table')
    return data


def _entries(stream,bounds,columns=1,version=0,dtype='>u4'):
    data=_read(stream,bounds)
    if len(data)<8 or data[0]!=version:raise ValueError('Unsupported MP4 table version')
    count=struct.unpack_from('>I',data,4)[0]
    if count>MAX_SAMPLES or len(data)!=8+count*columns*np.dtype(dtype).itemsize:
        raise ValueError('Invalid MP4 table entries')
    return np.frombuffer(data,dtype=dtype,offset=8).reshape(count,columns)


def _simple_edits(stream,trak):
    edits=[box for kind,box in _boxes(stream,*trak) if kind==b'edts']
    if not edits:return
    if len(edits)!=1:raise ValueError('Duplicate MP4 edit list')
    data=_read(stream,_find(stream,edits[0],b'elst'))
    if len(data)<8 or data[0] not in (0,1):raise ValueError('Unsupported MP4 edits')
    count=struct.unpack_from('>I',data,4)[0];width=20 if data[0] else 12
    if not 1<=count<=2 or len(data)!=8+count*width:raise ValueError('Complex MP4 edits')
    media=[]
    for i in range(count):
        _,time,rate,fraction=struct.unpack_from('>Qqhh' if data[0] else '>Iihh',data,8+i*width)
        if (rate,fraction)!=(1,0):raise ValueError('Nonlinear MP4 edit')
        media.append(time)
    if sum(time>=0 for time in media)!=1 or (count==2 and media[0]!=-1):
        raise ValueError('Repeated or trimmed MP4 edit sequence')


def mp4_keyframes(path,opener,time_base,target):
    """Return (indexed ordinal, sparse anchors), or None for packet fallback."""
    try:
        with open(path,'rb') as stream:
            stream.seek(0,2);length=stream.tell()
            moov=_find(stream,(0,length),b'moov')
            for kind,trak in _boxes(stream,*moov):
                if kind!=b'trak':continue
                mdia=_find(stream,trak,b'mdia')
                if _read(stream,_find(stream,mdia,b'hdlr'),12)[8:12]!=b'vide':continue
                break
            else:return None
            _simple_edits(stream,trak)
            mdhd=_read(stream,_find(stream,mdia,b'mdhd'))
            if mdhd[0] not in (0,1):return None
            timescale=struct.unpack_from('>I',mdhd,20 if mdhd[0] else 12)[0]
            if not timescale or Fraction(1,timescale)!=time_base:return None
            stbl=_find(stream,_find(stream,mdia,b'minf'),b'stbl')
            tables={}
            for kind,box in _boxes(stream,*stbl):
                if kind in tables and kind in (b'stsd',b'stts',b'ctts',b'stss',b'stsz',b'stco',b'co64'):
                    raise ValueError('Duplicate MP4 sample table')
                tables[kind]=box
            description=_read(stream,tables[b'stsd'],16)
            if struct.unpack_from('>I',description,4)[0]!=1 or description[12:16] not in (
                    b'avc1',b'avc3',b'hvc1',b'hev1',b'mp4v'):return None
            timing=_entries(stream,tables[b'stts'],2).astype(np.int64)
            count=int(timing[:,0].sum())
            if not 0<count<=MAX_SAMPLES or np.any(timing<=0):return None
            size_data=_read(stream,tables[b'stsz'],12)
            if struct.unpack_from('>I',size_data,8)[0]!=count:return None
            durations=np.repeat(timing[:,1],timing[:,0])
            pts=np.cumsum(durations)-durations
            if b'ctts' in tables:
                data=_read(stream,tables[b'ctts'])
                if data[0] not in (0,1):return None
                composition=_entries(stream,tables[b'ctts'],2,version=data[0])
                repeats=composition[:,0].astype(np.int64)
                if int(repeats.sum())!=count:return None
                offsets=composition[:,1].astype(np.int64)
                if data[0]:offsets=np.where(offsets>=2**31,offsets-2**32,offsets)
                pts+=np.repeat(offsets,repeats)
            ordered=np.sort(pts)
            if np.any(np.diff(ordered)<=0) or pts[0]!=ordered[0]:return None
            keys=_entries(stream,tables[b'stss'])[:,0].astype(np.int64)-1
            if not len(keys) or keys[0]!=0 or keys[-1]>=count or np.any(np.diff(keys)<=0):return None
            chunks=_entries(stream,tables[b'stco']) if b'stco' in tables else _entries(
                stream,tables[b'co64'],dtype='>u8')
            if not len(chunks):return None
            first_position=int(chunks[0,0])
        # Edit lists may offset timestamps. Check the actual first sample,
        # including its file position and discard flag, before applying one
        # constant shift. Complex trim/repeat edits use the established scan.
        with opener(path,metadata_errors='replace') as container:
            video=container.streams.video[0]
            if video.time_base!=time_base or (video.frames and video.frames!=count):return None
            for packet in container.demux(video):
                if not packet.size:continue
                if (packet.pts is None or packet.pos!=first_position or not packet.is_keyframe
                        or getattr(packet,'is_discard',False) or packet.pts!=video.start_time):return None
                shift=int(packet.pts)-int(pts[0])
                break
            else:return None
        indices=np.searchsorted(ordered,pts[keys])
        selected=np.flatnonzero(indices<=target)[-4096:]
        anchors=sorted((int(indices[i]),int(pts[keys[i]])+shift) for i in selected)
        return min(target,count-1),anchors
    except (OSError,ValueError,KeyError,IndexError,struct.error,OverflowError):
        return None


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


# Decoder sessions and pool
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

    def _packet_seek_supported(self):
        codec=self.stream.codec_context.name
        if codec in ('rv30','rv40'):return True
        # MOV/MP4 and Matroska carry access-unit packets for these codecs.
        # Do not apply this to raw streams, packed AVI, VP9 superframes, etc.
        formats=set(getattr(getattr(self.container,'format',None),'name','').split(','))
        return codec in ('h264','hevc','mpeg4') and bool(formats & {'mov','mp4','matroska','webm'})

    def _seek(self, target, cancelled=lambda:False):
        # Known keyframe ordinals work for VFR and nonzero stream start times.
        anchors = [(index, pts) for index, pts in self.anchors.items() if index <= target]
        distance = target-max((index for index,_ in anchors), default=0)
        if (not self.fast_seek and not self.packet_index_failed and distance>128
                and self._packet_seek_supported()):
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
                   and (self.fast_seek or self._packet_seek_supported()))
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

    def release_idle(self):
        """Drop native codec buffers, retaining session seek anchors for resume."""
        with self.lock:
            for session in self.sessions.values():
                if session.users == 0:
                    session.close()
            self.idle_bytes = 0

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
