import glob
import os
import tempfile
import tarfile

import wx

from HiddenExplorer.lib.crypto import encrypto, decrypto

TITLE = "HiddenExplorer"

root = os.path.join(os.environ.get("USERPROFILE"), ".HiddenExplorer")
if not os.path.isdir(root):
    os.mkdir(root)
crypto_file = os.path.join(root, ".data")

class MainFrame(wx.Frame):
    size = (800, 500)
    def __init__(self, bytes_):
        super().__init__(None, title=TITLE, size=MainFrame.size)
        self.bytes = bytes_
        self.build()

    def build(self):
        with NamedTemporaryFile("wb") as t, tempfile.TemporaryDirectory() as d:
            t.write(self.bytes)
            with tarfile.open(t.name, "r") as g:
                g.extractall(d)
                updater = wx.UpdateDialog(None)
                updater.Show()
                for i in glob.iglob(os.path.join(d, "**"), recursive=True):
                    pass
                updater.Destroy()

class InitFrame(wx.Frame):
    size = (500, 300)
    def __init__(self):
        super().__init__(None, title=TITLE+"  初期化", size=InitFrame.size)
        self.build()

    def build(self):
        self.sizer = wx.BoxSizer(wx.VERTICAL)
        self.panel = wx.Panel(self)
        self.sizer.Add(wx.StaticText(self.panel, wx.ID_ANY, "HiddenExplorerを利用するパスワードを入力してください"))
        self.ctrl1 = wx.TextCtrl(self.panel, size=(300, 50))
        self.sizer.Add(self.ctrl1)
        self.sizer.Add(wx.StaticText(self.panel, wx.ID_ANY, "確認"))
        self.ctrl2 = wx.TextCtrl(self.panel, size=(300, 50))
        self.sizer.Add(self.ctrl2)
        self.error = wx.StaticText(self.panel)
        self.sizer.Add(self.error)
        self.button = wx.Button(self.panel, wx.ID_ANY, "決定")
        self.button.Bind(wx.EVT_BUTTON, self.set_password)
        self.sizer.Add(self.panel)
        self.SetSizer(self.sizer)

    def set_password(self, e):
        password = self.ctrl1.GetValue()
        if password == self.ctrl2.GetValue():
            with open(crypto_file, "w") as f:
                f.write("")
            MainFrame(password).Show()
            self.Destroy()
        else:
            self.error.SetLabel("パスワードが一致していません")
            self.Refresh()

def main():
    app = wx.App()
    if os.path.isfile(crypto_file):
        AskPasswordFrame().Show()
    else:
        InitFrame().Show()
    app.MainLoop()

if __name__ == "__main__":
    main()
