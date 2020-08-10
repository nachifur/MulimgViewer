import wx
from select_image import SelectImgFrame
from path_select import PathSelectFrame

class GuiManager():
    def __init__(self, UpdateUI):
        self.UpdateUI = UpdateUI
        self.frameDict = {}

    def GetFrame(self, type):
        frame = self.frameDict.get(type)

        if frame is None:
            frame = self.CreateFrame(type)
            self.frameDict[type] = frame

        return frame

    def CreateFrame(self, type):
        if type == 0:
            return SelectImgFrame(None, self.UpdateUI)
        elif type == 1:
            return PathSelectFrame(None, self.UpdateUI)


class MainAPP(wx.App):


    def OnInit(self):
        self.manager = GuiManager(self.UpdateUI)
        self.frame = []
        self.frame.append(self.manager.GetFrame(0))
        self.frame.append(self.manager.GetFrame(1))
        self.frame[0].Show()
        self.SetTopWindow(self.frame[0])
        return True

    def UpdateUI(self, type, input_path=0):
        if input_path != 0:
            self.frame[0].input_paths = input_path
            if len(input_path) != 0:
                self.frame[0].show_img_init()
                self.frame[0].show_img()

        if type == -1:
            self.Destroy()
        elif type == 0:
            self.frame[1].Show(False)

        self.frame[type].Show(True)


def main():
    app = MainAPP()

    app.MainLoop()


if __name__ == '__main__':
    main()
