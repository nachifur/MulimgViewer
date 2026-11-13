"""Custom virtual-list behavior used by the FormBuilder-generated layout."""
import wx


class VirtualIndexList(wx.ListCtrl):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.get_row = lambda index: ('',)*8

    def OnGetItemText(self, item, column):
        row = self.get_row(item)
        return row[column] if 0 <= column < len(row) else ''
