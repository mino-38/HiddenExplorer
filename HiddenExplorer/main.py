import os
import tempfile
import zipfile

import wx

from Crypto.Random import get_random_bytes
from Crypto.Cipher import AES

TITLE = "HiddenExplorer"

root = os.path.join(os.environ.get("USERPROFILE"), ".HiddenExplorer")
if not os.path.isdir(root):
    os.mkdir(root)
crypto_file = os.path.join(root, ".data")
key_file = os.path.join(root, ".key")
if os.path.isfile(key_file):
    with open(key_file, "rb") as f:
        KEY = f.read()
else:
    KEY = get_random_bytes(AES.block_size*2)
    with open(key_file, "wb") as f:
        f.write(KEY)

def encrypt(file, password):
    cipher1 = AES.new(KEY, AES.MODE_EAX)
    cipher2 = AES.new(password, AES.MODE_EAX)
    with open(file, "rb") as f, open(crypto_file, "wb") as g:
        g.write(cipher1.encrypt(cipher2.encrypt(f.read())))

def decrypt(password):
    cipher1 = AES.new(KEY, AES.MODE_EAX)
    with open(crypto_file, "rb") as f:
        data = cipher1.decrypt(f.read())
    cipher2 = AES.new(password, AES.MODE_EAX)
    with open(crypto_file, "rb") as f:
        return cipher2.decrypt(data)

class FileDropTarget(wx.FileDropTarget):
    def __init__(self, func):
        super().__init__()
        self.func = func

    def OnDropFiles(self, x, y, files):
        self.func(files[-1])

class MainFrame(wx.Frame):
    size = (800, 500)
    def __init__(self, bytes_=None, files=None, password=None):
        super().__init__(None, title=TITLE, size=MainFrame.size)
        self.bytes = bytes_
        self.files = files
        self.password = password
        self.SetDropTarget(FileDropTarget(self.add))
        self.build()

    def build(self):
        if hasattr(self, "sizer"):
            self.sizer.Clear(True)
        else:
            self.sizer = wx.BoxSizer()
        self.panel = wx.Panel(self)
        if self.files:
            self.psizer = wx.GridSizer(cols=4)
            for p in self.files:
                self.set_layout(p)
            self.panel.SetSizer(self.psizer)
            self.sizer.Add(self.panel)
        else:
            self.sizer.Add(wx.StaticText(self, wx.ID_ANY, "まだ何もありません"))
            self.sizer.Add(self.panel)
        self.SetSizer(self.sizer)

    def add(self, path):
        if self.bytes_:
            with tempfile.NamedTemporaryFile("wb") as f:
                f.write(self.bytes)
                with zipfile.ZipFile(f.name, "a") as z:
                    if isinstance(path, str):
                        z.write(path)
                    else:
                        for p in path:
                            z.write(p)
                if os.path.isdir(path):
                    shutil.rmtree(path)
                else:
                    os.remove(path)
                encrypt(f.name, self.password)
                self.set_layout(path)
        else:
            files = [path] if isinstance(path, str) else path
            init = InitDialog(self.set_layout, files)
            init.ShowModal()
            self.password = init.password
            self.bytes = decrypt(self.password)
            self.files = files
        self.Refresh()

    def set_layout(self, path):
        sizer = wx.BoxSizer(wx.VERTICAL)
        panel = wx.Panel(self.panel)
        sizer.Add(wx.StaticText(panel, wx.ID_ANY, textwrap(os.path.basename(path))))
        panel.SetSizer(sizer)
        self.psizer.Add(panel)

class AskPasswordFrame(wx.Frame):
    size = (300, 200)
    def __init__(self):
        super().__init__(None, title=TITLE, size=AskPasswordFrame.size)
        self.build()

    def build(self):
        self.sizer = wx.BoxSizer(wx.VERTICAL)
        self.panel = wx.Panel(self)
        self.sizer.Add(wx.StaticText(self.panel, wx.ID_ANY, "HiddenExplorerを利用するパスワードを入力してください"))
        self.ctrl = wx.TextCtrl(self.panel, size=(200, 50))
        self.sizer.Add(self.ctrl)
        self.error = wx.StaticText(self.panel)
        self.sizer.Add(self.error)
        self.button = wx.Button(self.panel, wx.ID_ANY, "決定")
        self.button.Bind(wx.EVT_BUTTON, self.login)
        self.sizer.Add(self.panel)
        self.SetSizer(self.sizer)

    def login(self):
        password = self.ctrl.GetValue()
        bytes_ = decrypt(password)
        with tempfile.NamedTemporaryFile("wb") as f:
            f.write(bytes_)
            f.flush()
            if zipfile.is_zipfile(f.name):
                MainFrame(bytes_, zipfile.ZipFile(f.name).namelist(), password)
            else:
                self.error.SetLabel("パスワードが違います")
                self.Refresh()

class InitDialog(wx.Dialog):
    size = (500, 300)
    def __init__(self, func, files):
        super().__init__(None, title=TITLE+"  初期化", size=InitFrame.size)
        self.run_func = func
        self.files = files
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
        self.password = self.ctrl1.GetValue()
        if self.password == self.ctrl2.GetValue():
            with tempfile.TemporaryDirectory() as d:
                for p in self.files:
                    shutil.move(p, d)
                    self.run_func(p)
                with tempfile.NamedTemporaryFile("wb+") as z:
                    shutil.make_archive(z.name, "zip", d)
                    shutil.move(z.name+".zip", crypto_file)
                    encrypt(z.name, self.password)
            self.Destroy()
        else:
            self.error.SetLabel("パスワードが一致していません")
            self.Refresh()

def main():
    app = wx.App()
    if os.path.isfile(crypto_file):
        AskPasswordFrame().Show()
    else:
        MainFrame().Show()
    app.MainLoop()

if __name__ == "__main__":
    main()
