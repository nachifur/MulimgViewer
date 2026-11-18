"""Bounded native tiles for mosaics too large for a platform bitmap."""
from collections import OrderedDict

import wx


class TiledImageCanvas(wx.Panel):
    tile_size=512
    cache_limit=8*1024**2

    def __init__(self,parent,viewport,image):
        super().__init__(parent)
        self.viewport=viewport
        self.tiles=OrderedDict()
        self.tile_bytes=0
        self.SetBackgroundStyle(wx.BG_STYLE_PAINT)
        self.Bind(wx.EVT_PAINT,self._paint)
        self.SetImage(image)

    def SetImage(self,image):
        # Pixels belong to the immutable displayed frame. No full wx bitmap
        # or second RGBA byte buffer is needed for this backend.
        self.image=image
        self.tiles.clear();self.tile_bytes=0
        self.Refresh(False)

    def _tile(self,x,y):
        key=x,y
        if key in self.tiles:
            self.tiles.move_to_end(key)
            return self.tiles[key][0]
        box=(x,y,min(x+self.tile_size,self.image.width),min(y+self.tile_size,self.image.height))
        with self.image.crop(box) as crop:
            converted=None
            try:
                rgba=crop
                if crop.mode!='RGBA':converted=rgba=crop.convert('RGBA')
                bitmap=wx.Bitmap.FromBufferRGBA(rgba.width,rgba.height,rgba.tobytes())
            finally:
                if converted is not None:converted.close()
        if not bitmap.IsOk():raise RuntimeError('Cannot allocate a display tile')
        amount=(box[2]-x)*(box[3]-y)*4
        while self.tiles and self.tile_bytes+amount>self.cache_limit:
            _,(_,old)=self.tiles.popitem(last=False);self.tile_bytes-=old
        self.tiles[key]=bitmap,amount;self.tile_bytes+=amount
        return bitmap

    def visible_rect(self):
        # A native child can be much larger than the viewport. Never allocate
        # an AutoBufferedPaintDC of the whole child, or visit invisible tiles.
        origin=self.ScreenToClient(self.viewport.ClientToScreen((0,0)))
        return wx.Rect(origin,self.viewport.GetClientSize()).Intersect(wx.Rect(0,0,*self.image.size))

    def _paint(self,event):
        visible=self.visible_rect().Intersect(self.GetUpdateRegion().GetBox())
        # BeginPaint validates the native update region on Windows. Capture
        # it before constructing PaintDC, otherwise repaint can look empty.
        dc=wx.PaintDC(self)
        if visible.IsEmpty():return
        try:
            with wx.DCClipper(dc,visible):
                dc.SetBackground(wx.Brush(self.GetBackgroundColour()))
                dc.Clear()
                step=self.tile_size
                for y in range(visible.y//step*step,visible.y+visible.height,step):
                    for x in range(visible.x//step*step,visible.x+visible.width,step):
                        dc.DrawBitmap(self._tile(x,y),x,y,True)
        except (RuntimeError,MemoryError) as error:
            # Do not let an OS graphics allocation error escape an EVT_PAINT
            # callback or trigger a perpetual refresh/redecode loop.
            dc.DrawText(f'Display unavailable: {error}',visible.x,visible.y)
