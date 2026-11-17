"""Small, validated persistent seek metadata, separate from disposable pixels."""
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile


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
