"""Human-readable cache/export layout; identity stays in metadata, not names."""
import json
import os
import shutil
import threading
import uuid
import stat
from pathlib import Path
from PIL import Image


def canonical_path(path):
    value=str(Path(path).resolve())
    # Windows may add its extended prefix while another thread creates an
    # ancestor. It names the same directory, not a different cache root.
    if os.name=='nt':
        if value.startswith('\\\\?\\UNC\\'):value='\\\\'+value[8:]
        elif value.startswith('\\\\?\\'):value=value[4:]
    return Path(value)


class CachedCanvas:
    """An already encoded canvas: final publication can link it without reencoding."""
    def __init__(self,path):
        self.path=Path(path)
        with Image.open(path) as image:self.size=image.size
        self.width,self.height=self.size
    def save(self,path,**kwargs):
        try:os.link(self.path,path)
        except OSError:shutil.copyfile(self.path,path)


def page_name(batch):
    return f'page_{batch+1:06d}.png'


def component(name):
    # Algorithm names are existing folder names. Do not allow reserved traversal.
    value=str(name)
    if not value or value in ('.','..') or Path(value).name!=value or '/' in value or '\\' in value:
        raise ValueError('Invalid cache component')
    return value


def source_names(manager, paths):
    from .status_info import key
    index=getattr(manager,'_status_source_index',None)
    folders={key(Path(p).absolute()):i for p,i in index.folders.items()} if index is not None else {
        key(Path(p).absolute()):i for i,p in enumerate(getattr(manager,'path_list',()))}
    result=[];seen={}
    for path in paths:
        source=key(Path(path).parent.absolute())
        if source not in folders:folders[source]=len(folders)
        name=Path(f'source_{folders[source]+1:03d}')/(Path(path).stem+'.png')
        count=seen.get(str(name),0)+1;seen[str(name)]=count
        if count>1:name=name.parent/f'entry_{count:03d}'/name.name
        result.append(name.as_posix())
    return result


def processed_names(manager, paths):
    """Same source IDs and frame stems as the raw layer, without page folders."""
    return [(Path(name).parent/'frames'/Path(name).name).as_posix()
            for name in source_names(manager,paths)]


def source_record(manager, number, path):
    """Describe a source without enumerating its images or decoded frames."""
    originals=getattr(manager,'_cache_original_paths',())
    layout=getattr(manager,'layout_params',())
    value=dict(source=number+1,media='video' if getattr(manager,'video_mode',False) else 'image',
        path=str(Path(originals[number] if number<len(originals) else path).absolute()),
        input_mode=getattr(manager,'_cache_input_mode',''),
        parallel_to_sequential=bool(getattr(manager,'parallel_to_sequential',False)),
        parallel_sequential=bool(layout[22]) if len(layout)>22 else False,
        input=str(getattr(manager,'input_path','')))
    if getattr(manager,'video_mode',False):
        fps=getattr(manager,'video_fps_list',())
        counts=getattr(manager,'video_num_list',())
        value.update(fps=float(fps[number]) if number<len(fps) else None,
            frames=int(counts[number]) if number<len(counts) else None,step=int(getattr(manager,'skip',0))+1)
    return value


def write_source_catalog(manager, root, split_media=False):
    from .status_info import key
    root=Path(root)/'sources'
    if split_media:root=root/('video' if getattr(manager,'video_mode',False) else 'image')
    index=getattr(manager,'_status_source_index',None)
    folders=(index.folders if index is not None else
             {key(path):i for i,path in enumerate(getattr(manager,'path_list',()))})
    for path,number in folders.items():
        target=root/f'source_{number+1:03d}'/'source.json'
        target.parent.mkdir(parents=True,exist_ok=True)
        value=source_record(manager,number,path)
        temporary=target.with_name('__tmp_'+uuid.uuid4().hex)
        temporary.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
        os.replace(temporary,target)


class VisibleCache:
    """Publish readable views; readers keep immutable private artifacts.

    Keeping a private hard link while publishing deterministic names lets a new
    page/version replace a public view without changing any active reader's data.
    """
    def __init__(self, root, reserve=None, release=None):
        self.root=canonical_path(root);self.lock=threading.RLock();self.owners={}
        self.reserve=reserve;self.release=release
        self.file_users={};self.metadata={};self.algorithm_locks={}

    def _algorithm_lock(self, path):
        # Independent algorithms publish to disjoint trees. Keep only their
        # own IO serialized; the registry lock never spans filesystem work.
        value=Path(os.path.abspath(path))
        try:
            name=value.relative_to(self.root).parts[:2]
            if not name:raise ValueError('Cache target must name a layer')
        except (ValueError,IndexError):raise ValueError('Cache target escaped its root')
        with self.lock:return self.algorithm_locks.setdefault(name,threading.RLock())

    def _inside(self, path, checked=None):
        value=Path(os.path.abspath(path))
        if checked is None:checked={}
        root=checked.get('root')
        if root is None:root=checked['root']=canonical_path(self.root)
        # Validate directory containment, not the final hard-linked filename.
        # On Windows a hard link may canonicalize to its private work alias;
        # that does not mean the public pathname escaped its directory.
        parent=checked.get(value.parent)
        if parent is None:parent=checked[value.parent]=canonical_path(value.parent)
        if self.root not in value.parents or (parent!=root and root not in parent.parents):
            raise ValueError(f'Cache target escaped its root: {value!r} (parent {parent!r}, root {root!r}, lexical root {self.root!r})')
        try:info=value.lstat()
        except FileNotFoundError:info=None
        if info is not None and (stat.S_ISLNK(info.st_mode) or getattr(info,'st_file_attributes',0)&getattr(stat,'FILE_ATTRIBUTE_REPARSE_POINT',0x400)):
            raise ValueError('Cache target must not be a symlink or junction')
        return value

    def clear_owned(self):
        """Clear a previous run's generated layers, preserving unrelated files."""
        if not self.root.exists():return
        with self.lock:
            for algorithm in self.root.iterdir():
                if not algorithm.is_dir():continue
                for kind in ('processed','stitched'):
                    target=self._inside(algorithm/kind)
                    if target.is_dir():shutil.rmtree(str(target))
                try:algorithm.rmdir()
                except OSError:pass
            self.owners.clear();self.file_users.clear();self.metadata.clear()

    def publish(self, target, files, owner, valid=lambda:True, metadata=None):
        with self._algorithm_lock(target):
            if not valid():return
            # Canonicalization must share the publication/cleanup lock too:
            # the parent directory may otherwise disappear while resolving it.
            checked={}
            target=self._inside(target,checked)
            owner_key=(target,owner.get('page'))
            target.mkdir(parents=True,exist_ok=True)
            previous=self.owners.get(owner_key)
            old_names=set(previous.get('_visible_names',())) if previous is not None else set()
            names=[];copied=0
            for name,source in files.items():
                path=self._inside(target/name,checked);path.parent.mkdir(parents=True,exist_ok=True)
                temporary=path.with_name('__tmp_'+uuid.uuid4().hex)
                try:
                    try:os.link(source,temporary)
                    except OSError:
                        size=Path(source).stat().st_size
                        if self.reserve is not None:self.reserve(owner,size)
                        shutil.copyfile(source,temporary);copied+=size
                    os.replace(temporary,path)
                finally:temporary.unlink(missing_ok=True)
                names.append(name)
                self.file_users.setdefault(path,set()).add(owner_key)
            for name,value in (metadata or {}).items():
                path=Path(os.path.abspath(target/name))
                # Source descriptors are shared by pages and are immutable until
                # their source/algorithm configuration changes. No per-frame IO.
                if self.metadata.get(path)!=value:
                    path=self._inside(path,checked)
                    path.parent.mkdir(parents=True,exist_ok=True)
                    temporary=path.with_name('__tmp_'+uuid.uuid4().hex)
                    encoded=json.dumps(value,ensure_ascii=False,indent=2).encode('utf-8')
                    try:
                        if self.reserve is not None:self.reserve(owner,len(encoded))
                        temporary.write_bytes(encoded)
                        os.replace(temporary,path)
                    finally:temporary.unlink(missing_ok=True)
                    self.metadata[path]=value;copied+=len(encoded)
                names.append(name)
                self.file_users.setdefault(path,set()).add(owner_key)
            for name in old_names-set(names):
                path=self._inside(target/name,checked)
                users=self.file_users.get(path,set());users.discard(owner_key)
                if not users:
                    path.unlink(missing_ok=True);self.file_users.pop(path,None);self.metadata.pop(path,None)
            owner['_visible_names']=tuple(names);owner['_visible_target']=target
            owner['_visible_key']=owner_key;self.owners[owner_key]=owner
            if previous is not None and self.release is not None:
                self.release(previous,previous.get('_visible_copied',0))
            owner['_visible_copied']=copied

    def current(self,owner):
        target=owner.get('_visible_target')
        if target is None:return False
        with self._algorithm_lock(target):return self.owners.get(owner.get('_visible_key')) is owner

    def remove(self, owner):
        target=owner.get('_visible_target')
        if target is None:return
        with self._algorithm_lock(target):
            key=owner['_visible_key']
            if self.owners.get(key) is not owner:return
            for name in owner.get('_visible_names',()):
                path=self._inside(target/name)
                users=self.file_users.get(path,set());users.discard(key)
                if not users:
                    path.unlink(missing_ok=True);self.file_users.pop(path,None);self.metadata.pop(path,None)
            self.owners.pop(key,None)
            if self.release is not None:self.release(owner,owner.get('_visible_copied',0))
            owner['_visible_copied']=0
            # Empty containers are cosmetic; never recursively remove peers.
            directories=set()
            for name in owner.get('_visible_names',()):
                directory=(target/name).parent
                while directory!=target and target in directory.parents:
                    directories.add(directory);directory=directory.parent
            for directory in sorted(directories,key=lambda path:len(path.parts),reverse=True):
                try:directory.rmdir()
                except OSError:pass
            try:target.rmdir()
            except OSError:pass
            parent=target.parent
            while parent!=self.root and self.root in parent.parents:
                try:parent.rmdir()
                except OSError:break
                parent=parent.parent
