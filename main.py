import wx
from mulimg_viewer import MulimgViewer
from path_select import PathSelectFrame
import wx.lib.inspection


class GuiManager():
    def __init__(self, UpdateUI, get_type):
        self.UpdateUI = UpdateUI
        self.get_type = get_type
        self.frameDict = {}

    def GetFrame(self, type):
        frame = self.frameDict.get(type)

        if frame is None:
            frame = self.CreateFrame(type)
            self.frameDict[type] = frame

        return frame

    def CreateFrame(self, type):
        if type == 0:
            return MulimgViewer(None, self.UpdateUI, self.get_type)
        elif type == 1:
            return PathSelectFrame(None, self.UpdateUI, self.get_type)


class MainAPP(wx.App):

    def OnInit(self):
        self.manager = GuiManager(self.UpdateUI, self.get_type)
        self.frame = []
        self.frame.append(self.manager.GetFrame(0))
        self.frame.append(self.manager.GetFrame(1))
        self.frame[0].Show()
        self.SetTopWindow(self.frame[0])
        self.type = 0
        return True

    def UpdateUI(self, type, input_path=0):
        self.type = type
        if input_path != 0:
            if len(input_path) != 0:
                self.frame[0].ImgManager = self.frame[0].create_ImgManager(
                    input_path, 1)
                self.frame[0].ImgManager.set_action_count(0)
                self.frame[0].show_img()
        if type == -1:
            self.frame[0].Close(None)
            self.frame[1].Close(None)
        elif type == 0:
            self.frame[1].Show(False)
        self.frame[type].Show(True)
        return True

    def get_type(self):
        return self.type


def main():
    app = MainAPP()
    # debug
    # wx.lib.inspection.InspectionTool().Show()
    app.MainLoop()


if __name__ == '__main__':
    main()
