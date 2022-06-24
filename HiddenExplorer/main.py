import os
import shutil
import tempfile
import zipfile

import win32api
import win32gui
import win32ui
import wx
from Crypto.Random import get_random_bytes
from Crypto.Cipher import AES
from PIL import Image
from wx.lib.scrolledpanel import ScrolledPanel

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

def get_icon(path):
    icoX = win32api.GetSystemMetrics(win32con.SM_CXICON)
    icoY = win32api.GetSystemMetrics(win32con.SM_CXICON)
    large, small = win32gui.ExtractIconEx(path, 0)
    win32gui.DestroyIcon(small[0])
    hdc = win32ui.CreateDCFromHandle(win32gui.GetDC(0))
    hbmp = win32ui.CreateBitmap()
    hbmp.CreateCompatibleBitmap(hdc, icoX, icoX)
    hdc = hdc.CreateCompatibleDC()
    hdc.SelectObject(hbmp)
    hdc.DrawIcon((0,0), large[0])
    bmpstr = hbmp.GetBitmapBits(True)
    return Image.frombuffer("RGBA", (32, 32), bmpstr, "raw", "BGRA", 0, 1)

class RunFunction:
    def __init__(self, func, *args, **kwargs):
        self.func = func
        self.args = args
        self.kwargs = kwargs

    def __call__(self, *_, **__):
        self.func(*self.args, **self.kwargs)

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
        self.func = {1: self.add_from_dialog, 2: lambda: self.add_from_dialog(True)}
        menu_file = wx.Menu()
        menu_file.Append(1, "ファイルを追加")
        menu_file.Append(2, "ディレクトリを追加")
        menu_bar = wx.MenuBar()
        menu_bar.Append(menu_file, "ファイル")
        self.SetMenuBar(menu_bar)
        self.Bind(wx.EVT_MENU, self.run_menu)
        self.default_fileicon = wx.Image(os.path.join(os.path.dirname(__file__), "resources", "default_icon.png")).Scale(120, 90).ConvertToBitmap()
        self.build()

    def run_menu(self, e):
        self.func[e.GetId()]()

    def add_from_dialog(self, directory=False):
        if directory:
            fdialog = wx.DirDialog(None, TITLE, style=wx.DD_MULTIPLE)
        else:
            fdialog = wx.FileDialog(None, TITLE, style=wx.FD_MULTIPLE)
        if fdialog.ShowModal() == wx.ID_OK:
            paths = fdialog.GetPaths()
            if paths:
                self.add(paths)

    def build(self):
        if hasattr(self, "sizer"):
            self.sizer.Clear(True)
        else:
            self.sizer = wx.BoxSizer()
        self.panel = ScrolledPanel(self)
        self.panel.SetupScrolling()
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
        if self.bytes:
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
            for p in files:
                self.set_layout(p)
        self.Refresh()

    def set_layout(self, path):
        sizer = wx.BoxSizer(wx.VERTICAL)
        panel = wx.Panel(self.panel, size=(150, 120))
        with tempfile.NamedTemporaryFile("wb") as f, tempfile.NamedTemporaryFile("wb") as g:
            f.write(self.bytes)
            with zipfile.ZipFile(f.name, "r") as z:
                z.extract(path, g.name)
            try:
                img = get_icon(g.name).Scale(120, 90)
                image = wx.EmptyImage(img.size[0], img.size[1])
                image.SetData(img.convert("RGB").tostring())
                sizer.Add(wx.StaticBitmap(panel, wx.ID_ANY, image.ConvertToBitmap()))
            except:
                sizer.Add(wx.StaticBitmap(panel, wx.ID_ANY, self.default_fileicon))
        sizer.Add(wx.StaticText(panel, wx.ID_ANY, textwrap(os.path.basename(path))))
        panel.SetSizer(sizer)
        panel.Bind(wx.EVT_LEFT_DCLICK, RunFunction(self.run_file, path))
        self.psizer.Add(panel)

    def run_file(self, path):
        threading.Thread(target=self._run_file, args=(path,)).start()

    def _run_file(self, path):
        with NamedTemporaryFile("wb") as f, NamedTemporaryFile("wb") as g:
            f.write(self.bytes)
            with zipfile.ZipFile(f.name, "r") as z:
                z.extract(path, g.name)
            subprocess.run(["call", g.name], close_fds=True)

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
        super().__init__(None, title=TITLE+"  初期化", size=InitDialog.size)
        self.run_func = func
        self.files = files
        self.build()

    def build(self):
        self.sizer = wx.BoxSizer(wx.VERTICAL)
        sizer = wx.BoxSizer(wx.VERTICAL)
        self.panel = wx.Panel(self)
        sizer.Add(wx.StaticText(self.panel, wx.ID_ANY, "HiddenExplorerを利用するパスワードを入力してください"))
        self.ctrl1 = wx.TextCtrl(self.panel, size=(300, 20))
        sizer.Add(self.ctrl1)
        sizer.Add(wx.StaticText(self.panel, wx.ID_ANY, "確認"))
        self.ctrl2 = wx.TextCtrl(self.panel, size=(300, 20))
        sizer.Add(self.ctrl2)
        self.error = wx.StaticText(self.panel)
        sizer.Add(self.error)
        self.button = wx.Button(self.panel, wx.ID_ANY, "決定")
        self.button.Bind(wx.EVT_BUTTON, self.set_password)
        sizer.Add(self.button)
        self.panel.SetSizer(sizer)
        self.sizer.Add(self.panel)
        self.SetSizer(self.sizer)

    def set_password(self, e):
        self.password = self.ctrl1.GetValue()
        if self.password == self.ctrl2.GetValue():
            with tempfile.TemporaryDirectory() as d:
                for p in self.files:
                    shutil.move(p, d)
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
