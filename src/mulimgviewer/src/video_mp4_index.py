"""Read exact presentation-order keyframes from bounded MP4 sample tables.

Unsupported/fragmented/encrypted files retain the packet scanner. No media
payload is scanned or decoded; a demuxed first packet validates table timing.
"""
import struct
from fractions import Fraction
import numpy as np


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
