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
        self.viewport_backed=max(image.size)>32767
        self.SetImage(image)
        if self.viewport_backed:
            viewport.Bind(wx.EVT_SCROLLWIN,self._viewport_changed)
            viewport.Bind(wx.EVT_SIZE,self._viewport_changed)
            viewport.Bind(wx.EVT_PAINT,self._viewport_painted)
            self.Bind(wx.EVT_WINDOW_DESTROY,self._destroy_viewport_bindings)

    def _destroy_viewport_bindings(self,event):
        if event.GetEventObject() is self and self.viewport and not self.viewport.IsBeingDeleted():
            self.viewport.Unbind(wx.EVT_SCROLLWIN,handler=self._viewport_changed)
            self.viewport.Unbind(wx.EVT_SIZE,handler=self._viewport_changed)
            self.viewport.Unbind(wx.EVT_PAINT,handler=self._viewport_painted)
        event.Skip()

    def _viewport_changed(self,event):
        # ScrolledWindow moves children before the scroll event completes.
        wx.CallAfter(self._sync_viewport)
        event.Skip()

    def _viewport_painted(self,event):
        # Programmatic Scroll() (keyboard/panning) does not emit EVT_SCROLLWIN.
        if self.GetPosition()!=(0,0):wx.CallAfter(self._sync_viewport)
        event.Skip()

    def _sync_viewport(self):
        if not self or not self.viewport:return
        self.SetPosition((0,0))
        self.SetSize(self.viewport.GetClientSize())
        self.Refresh(False)
        self.Update()

    def image_origin(self):
        return self.viewport.CalcUnscrolledPosition((0,0)) if self.viewport_backed else wx.Point(0,0)

    def bind_image_mouse(self,event_type,handler):
        def logical_event(event):
            if self.viewport_backed:
                event=wx.MouseEvent(event)
                event.SetPosition(event.GetPosition()+self.image_origin())
            handler(event)
        self.Bind(event_type,logical_event)

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
        origin=(self.image_origin() if self.viewport_backed else
                self.ScreenToClient(self.viewport.ClientToScreen((0,0))))
        return wx.Rect(origin,self.viewport.GetClientSize()).Intersect(wx.Rect(0,0,*self.image.size))

    def _paint(self,event):
        origin=self.image_origin()
        update=self.GetUpdateRegion().GetBox()
        update.Offset(origin)
        visible=self.visible_rect().Intersect(update)
        # BeginPaint validates the native update region on Windows. Capture
        # it before constructing PaintDC, otherwise repaint can look empty.
        dc=wx.PaintDC(self)
        if visible.IsEmpty():return
        try:
            local=wx.Rect(visible)
            local.Offset(-origin.x,-origin.y)
            with wx.DCClipper(dc,local):
                dc.SetBackground(wx.Brush(self.GetBackgroundColour()))
                dc.Clear()
                step=self.tile_size
                for y in range(visible.y//step*step,visible.y+visible.height,step):
                    for x in range(visible.x//step*step,visible.x+visible.width,step):
                        dc.DrawBitmap(self._tile(x,y),x-origin.x,y-origin.y,True)
        except (RuntimeError,MemoryError) as error:
            # Do not let an OS graphics allocation error escape an EVT_PAINT
            # callback or trigger a perpetual refresh/redecode loop.
            dc.DrawText(f'Display unavailable: {error}',visible.x-origin.x,visible.y-origin.y)
