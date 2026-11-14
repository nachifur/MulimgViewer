"""Bounded text-metric reuse; rasterization and font instances stay local."""
from collections import OrderedDict
import threading
from PIL import ImageFont

_lock=threading.Lock()
_metrics=OrderedDict()
_limit=1024
_masks=OrderedDict()
_mask_bytes=0
_mask_limit=8*1024**2


def _key(value):
    if isinstance(value,(list,tuple)):return tuple(_key(v) for v in value)
    return value


class MeasuredFont(ImageFont.FreeTypeFont):
    def __setstate__(self,state):
        super().__setstate__(state)
        self._metric_identity=(str(self.path),self.size,self.index,self.encoding,self.layout_engine)

    @classmethod
    def wrap(cls,font):
        if not isinstance(font,ImageFont.FreeTypeFont):return font
        result=object.__new__(cls)
        result.__dict__.update(font.__dict__)
        result._metric_identity=(str(font.path),font.size,font.index,font.encoding,font.layout_engine)
        return result

    def _measure(self,method,text,args,kwargs):
        original=getattr(super(),method)
        if not isinstance(text,str) or len(text)>512:
            return original(text,*args,**kwargs)
        key=(self._metric_identity,method,text,args,tuple(sorted(kwargs.items())))
        try:hash(key)
        except TypeError:return original(text,*args,**kwargs)
        with _lock:
            if key in _metrics:
                _metrics.move_to_end(key)
                return _metrics[key]
        value=original(text,*args,**kwargs)
        with _lock:
            _metrics[key]=value
            while len(_metrics)>_limit:_metrics.popitem(last=False)
        return value

    def getbbox(self,text,*args,**kwargs):
        return self._measure('getbbox',text,args,kwargs)

    def getlength(self,text,*args,**kwargs):
        return self._measure('getlength',text,args,kwargs)

    def getmask2(self,text,*args,**kwargs):
        # Pillow mutates color glyphs after getmask2; only share read-only
        # monochrome masks. Limit both byte retention and dictionary entries.
        global _mask_bytes
        mode=args[0] if args else kwargs.get('mode','')
        if mode=='RGBA' or not isinstance(text,str) or len(text)>512:
            return super().getmask2(text,*args,**kwargs)
        key=(self._metric_identity,text,_key(args),tuple((k,_key(v)) for k,v in sorted(kwargs.items())))
        try:hash(key)
        except TypeError:return super().getmask2(text,*args,**kwargs)
        with _lock:
            if key in _masks:
                _masks.move_to_end(key)
                return _masks[key][0]
        result=super().getmask2(text,*args,**kwargs)
        weight=result[0].size[0]*result[0].size[1]*4
        if weight>_mask_limit:return result
        with _lock:
            previous=_masks.pop(key,None)
            if previous is not None:_mask_bytes-=previous[1]
            _masks[key]=(result,weight);_mask_bytes+=weight
            while _mask_bytes>_mask_limit or len(_masks)>_limit:
                _,(_,removed)=_masks.popitem(last=False);_mask_bytes-=removed
        return result
