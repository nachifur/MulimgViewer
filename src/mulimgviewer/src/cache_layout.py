"""Human-readable cache/export layout; identity stays in metadata, not names."""
import json
import os
import shutil
import threading
import uuid
from pathlib import Path
from PIL import Image


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
    folders=dict(index.folders) if index is not None else {
        key(Path(p)):i for i,p in enumerate(getattr(manager,'path_list',()))}
    result=[];seen={}
    for path in paths:
        source=key(Path(path).parent)
        if source not in folders:folders[source]=len(folders)
        name=Path(f'source_{folders[source]+1:03d}')/(Path(path).stem+'.png')
        count=seen.get(str(name),0)+1;seen[str(name)]=count
        if count>1:name=name.parent/f'entry_{count:03d}'/name.name
        result.append(name.as_posix())
    return result


def write_source_catalog(manager, root, split_media=False):
    from .status_info import key
    root=Path(root)/'sources'
    if split_media:root=root/('video' if getattr(manager,'video_mode',False) else 'image')
    index=getattr(manager,'_status_source_index',None)
    folders=(index.folders if index is not None else
             {key(path):i for i,path in enumerate(getattr(manager,'path_list',()))})
    originals=getattr(manager,'_cache_original_paths',())
    for path,number in folders.items():
        target=root/f'source_{number+1:03d}'/'source.json'
        target.parent.mkdir(parents=True,exist_ok=True)
        value=dict(source=number+1,media='video' if getattr(manager,'video_mode',False) else 'image',
            path=str(Path(originals[number] if number<len(originals) else path).absolute()),
            input_mode=getattr(manager,'_cache_input_mode',''),
            parallel_to_sequential=bool(manager.parallel_to_sequential),
            parallel_sequential=bool(manager.layout_params[22]),
            input=str(getattr(manager,'input_path','')))
        if getattr(manager,'video_mode',False):
            fps=getattr(manager,'video_fps_list',())
            counts=getattr(manager,'video_num_list',())
            value.update(fps=float(fps[number]) if number<len(fps) else None,
                frames=int(counts[number]) if number<len(counts) else None,step=int(getattr(manager,'skip',0))+1)
        temporary=target.with_name('__tmp_'+uuid.uuid4().hex)
        temporary.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
        os.replace(temporary,target)


class VisibleCache:
    """Publish readable views; readers keep immutable private artifacts.

    Keeping a private hard link while publishing deterministic names lets a new
    page/version replace a public view without changing any active reader's data.
    """
    def __init__(self, root, reserve=None, release=None):
        self.root=Path(root).resolve();self.lock=threading.RLock();self.owners={}
        self.reserve=reserve;self.release=release

    def _inside(self, path):
        value=Path(path).resolve()
        if self.root not in value.parents:raise ValueError('Cache target escaped its root')
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
            self.owners.clear()

    def publish(self, target, files, owner, valid=lambda:True):
        target=self._inside(target)
        owner_key=(target,owner.get('page'))
        with self.lock:
            if not valid():return
            target.mkdir(parents=True,exist_ok=True)
            previous=self.owners.get(owner_key)
            old_names=set(previous.get('_visible_names',())) if previous is not None else set()
            names=[];copied=0
            for name,source in files.items():
                path=self._inside(target/name);path.parent.mkdir(parents=True,exist_ok=True)
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
            for name in old_names-set(names):self._inside(target/name).unlink(missing_ok=True)
            owner['_visible_names']=tuple(names);owner['_visible_target']=target
            owner['_visible_key']=owner_key;self.owners[owner_key]=owner
            if previous is not None and self.release is not None:
                self.release(previous,previous.get('_visible_copied',0))
            owner['_visible_copied']=copied

    def current(self,owner):
        with self.lock:return self.owners.get(owner.get('_visible_key')) is owner

    def remove(self, owner):
        target=owner.get('_visible_target')
        if target is None:return
        with self.lock:
            key=owner['_visible_key']
            if self.owners.get(key) is not owner:return
            for name in owner.get('_visible_names',()):self._inside(target/name).unlink(missing_ok=True)
            self.owners.pop(key,None)
            if self.release is not None:self.release(owner,owner.get('_visible_copied',0))
            owner['_visible_copied']=0
            # Empty containers are cosmetic; never recursively remove peers.
            for directory in sorted(target.rglob('*'),reverse=True):
                if directory.is_dir():
                    try:directory.rmdir()
                    except OSError:pass
            try:target.rmdir()
            except OSError:pass
            parent=target.parent
            while parent!=self.root and self.root in parent.parents:
                try:parent.rmdir()
                except OSError:break
                parent=parent.parent
