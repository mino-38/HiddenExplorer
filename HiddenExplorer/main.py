import traceback

import glob
import os
import stat
import subprocess
import time
import threading
import shutil
import tempfile
import zipfile

import win32api
import win32con
import win32gui
import win32ui
import wx
from Crypto.Random import get_random_bytes
from Crypto.Cipher import AES
from PIL import Image
from wx.lib.scrolledpanel import ScrolledPanel

TITLE = "HiddenExplorer"
FILL = b"\r"
IV = b"aaaaaaaaaaaaaaaa"

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
    file.seek(0)
    cipher1 = AES.new(KEY, AES.MODE_EAX, IV)
    password = password.encode() + FILL*(AES.block_size-(len(password) % AES.block_size))
    cipher2 = AES.new(password, AES.MODE_EAX, IV)
    with open(crypto_file, "wb") as g:
        g.write(cipher1.encrypt(cipher2.encrypt(file.read())))

def decrypt(password):
    cipher1 = AES.new(KEY, AES.MODE_EAX, IV)
    password = password.encode() + FILL*(AES.block_size-(len(password) % AES.block_size))
    cipher2 = AES.new(password, AES.MODE_EAX, IV)
    with open(crypto_file, "rb") as f:
        return cipher2.decrypt(cipher1.decrypt(f.read()))

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

def textwrap(text, length):
    if length < len(text):
        return text[:length-3]+"..."
    else:
        return text

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
        self.func(files[0])
        return True

class MainFrame(wx.Frame):
    size = (800, 500)
    def __init__(self, bytes_=None, password=None):
        super().__init__(None, title=TITLE, size=MainFrame.size)
        self.bytes = bytes_
        self.password = password
        self.files = None
        self.SetDropTarget(FileDropTarget(self.add))
        self.func = {1: self.add_from_dialog, 2: lambda: self.add_from_dialog(True)}
        self.menu_func = {1: lambda p: self.run_file(p), 2: lambda p: self.run_file(p, notepad=True), 3: lambda p: RemoveDialog(p, self.bytes, self.password, self.build).ShowModal()}
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
            fdialog = wx.DirDialog(None, TITLE)
        else:
            fdialog = wx.FileDialog(None, TITLE)
        if fdialog.ShowModal() == wx.ID_OK:
            path = fdialog.GetPath()
            if path:
                self.add(path)

    def build(self):
        self.update_files()
        if hasattr(self, "sizer"):
            self.sizer.Clear(True)
        else:
            self.sizer = wx.BoxSizer()
        self.panel = ScrolledPanel(self, size=MainFrame.size)
        self.panel.SetupScrolling()
        if self.files:
            self.psizer = wx.GridSizer(cols=4)
            for p in self.files:
                if p.endswith("/") and p.count("/") < 2:
                    self.set_layout(p)
            self.panel.SetSizer(self.psizer)
        self.sizer.Add(self.panel)
        self.SetSizer(self.sizer)

    def add(self, path):
        if self.bytes:
            temp_zip = os.path.join(tempfile.gettempdir(), ".random_{}.{}".format(os.getpid(), time.time()))
            try:
                with open(temp_zip, "wb") as f:
                    f.write(self.bytes)
                with zipfile.ZipFile(temp_zip, "a") as z:
                    if isinstance(path, str):
                        z.write(path, os.path.basename(path))
                        if os.path.isdir(path):
                            for q in glob.iglob(os.path.join(path, "**"), recursive=True):
                                z.write(q, os.path.join(os.path.basename(path), os.path.relpath(q, path)))
                            shutil.rmtree(path)
                        else:
                            os.remove(path)
                    else:
                        for p in path:
                            z.write(p, os.path.basename(p))
                            if os.path.isdir(p):
                                shutil.rmtree(p)
                            else:
                                os.remove(p)
                with open(temp_zip, "rb") as f:
                    encrypt(f, self.password)
                    f.seek(0)
                    self.bytes = f.read()
                if isinstance(path, str):
                    self.set_layout(os.path.basename(path))
                else:
                    for p in path:
                        self.set_layout(os.path.basename(p))
            finally:
                os.remove(temp_zip)
        else:
            files = [path] if isinstance(path, str) else path
            init = InitDialog(self.set_layout, files)
            init.ShowModal()
            if hasattr(init, "password"):
                self.sizer.Clear(True)
                self.panel = ScrolledPanel(self, size=MainFrame.size)
                self.panel.SetupScrolling()
                self.psizer = wx.GridSizer(cols=4)
                self.password = init.password
                self.bytes = decrypt(self.password)
                self.files = files
                for p in files:
                    self.set_layout(os.path.basename(p))
                self.panel.SetSizer(self.psizer)
                self.sizer.Add(self.panel)
        self.update_files()
        self.Layout()
        self.Refresh()

    def update_files(self):
        if not self.bytes:
            return
        temp_zip = os.path.join(tempfile.gettempdir(), ".random_{}.{}".format(os.getpid(), time.time()))
        try:
            with open(temp_zip, "wb") as f:
                f.write(self.bytes)
            with zipfile.ZipFile(temp_zip, "a") as z:
                self.files = [p for p in z.namelist() if p.count(os.sep) < 2]
        finally:
            os.remove(temp_zip)

    def set_layout(self, path):
        sizer = wx.BoxSizer(wx.VERTICAL)
        panel = wx.Panel(self.panel, size=(150, 120))
        temp_zip = os.path.join(tempfile.gettempdir(), ".random_{}.{}".format(os.getpid(), time.time()))
        try:
            with open(temp_zip, "wb") as f:
                f.write(self.bytes)
            with tempfile.TemporaryDirectory() as d:
                with zipfile.ZipFile(temp_zip, "r") as z:
                    try:
                        file = z.extract(path, os.path.join(d, os.path.splitext(path)[1]))
                    except:
                        file = z.extract(path+"/", os.path.join(d, path))
                try:
                    img = get_icon(file).Scale(120, 90)
                    image = wx.EmptyImage(img.size[0], img.size[1])
                    image.SetData(img.convert("RGB").tostring())
                    bmp = wx.StaticBitmap(panel, wx.ID_ANY, image.ConvertToBitmap())
                except:
                    bmp = wx.StaticBitmap(panel, wx.ID_ANY, self.default_fileicon)
                    print(traceback.format_exc())
                bmp.Bind(wx.EVT_LEFT_DCLICK, RunFunction(self.run_file, path))
                bmp.Bind(wx.EVT_RIGHT_UP, RunFunction(self.show_menu, path))
                sizer.Add(bmp)
        finally:
            os.remove(temp_zip)
        sizer.Add(wx.StaticText(panel, wx.ID_ANY, textwrap(path, 15)), flag=wx.ALIGN_CENTER)
        panel.SetSizer(sizer)
        panel.Bind(wx.EVT_LEFT_DCLICK, RunFunction(self.run_file, path))
        panel.Bind(wx.EVT_RIGHT_UP, RunFunction(self.show_menu, path))
        self.psizer.Add(panel)

    def show_menu(self, path):
        menu = wx.Menu()
        menu.Append(wx.MenuItem(menu, 1, "実行"))
        menu.Append(wx.MenuItem(menu, 2, "メモ帳で開く"))
        menu.AppendSeparator()
        menu.Append(wx.MenuItem(menu, 3, "削除"))
        menu.Bind(wx.EVT_MENU, lambda e: self.run_popupmenu(e, path))
        self.PopupMenu(menu)

    def run_popupmenu(self, e, path):
        self.menu_func[e.GetId()](path)

    def run_file(self, path, notepad=False):
        threading.Thread(target=self._run_file, args=(path, notepad)).start()

    def _run_file(self, path, notepad):
        temp_zip = os.path.join(tempfile.gettempdir(), ".random_{}.{}".format(os.getpid(), time.time()))
        with tempfile.TemporaryDirectory() as d:
            try:
                with open(temp_zip, "wb") as f:
                    f.write(self.bytes)
                with zipfile.ZipFile(temp_zip, "r") as z:
                    try:
                        file = z.extract(path, d)
                    except:
                        file = z.extract(path+"/", d)
                        for p in [t for t in z.namelist() if t.startswith(file)]:
                            z.extract(p, d)
            finally:
                os.remove(temp_zip)
            if notepad and os.path.isfile(file):
                os.chmod(path=file, mode=stat.S_IREAD)
                subprocess.run(["call", "%windir%\\notepad.exe", file], shell=True)
            else:
                if os.path.isfile(file):
                    subprocess.run(["call", file], shell=True)
                else:
                    processes = []
                    def open_dir(directory):
                        fdialog = wx.FileDialog(self, TITLE, defaultDir=directory)
                        if fdialog.ShowModal() == wx.ID_OK:
                            path = fdialog.GetPath()
                            if path:
                                if os.path.isdir(path):
                                    return open_dir(path)
                                else:
                                    p = Process(target=subprocess.run, args=(["call", path],))
                                    p.start()
                                    processes.append(p)
                                    return True
                        else:
                            return False
                    while open_dir(file):
                        pass
                    for p in processes:
                        p.kill()

class AskPasswordFrame(wx.Frame):
    size = (300, 200)
    def __init__(self):
        super().__init__(None, title=TITLE, size=AskPasswordFrame.size)
        self.build()

    def build(self):
        self.sizer = wx.BoxSizer(wx.VERTICAL)
        sizer = wx.BoxSizer(wx.VERTICAL)
        self.panel = wx.Panel(self, size=AskPasswordFrame.size)
        sizer.Add(wx.StaticText(self.panel, wx.ID_ANY, "HiddenExplorerを利用するパスワードを入力してください"))
        self.ctrl = wx.TextCtrl(self.panel, size=(200, 20))
        sizer.Add(self.ctrl)
        self.error = wx.StaticText(self.panel)
        self.error.SetForegroundColour("#FF0000")
        sizer.Add(self.error)
        self.button = wx.Button(self.panel, wx.ID_ANY, "決定")
        self.button.Bind(wx.EVT_BUTTON, self.login)
        sizer.Add(self.button)
        self.panel.SetSizer(sizer)
        self.sizer.Add(self.panel)
        self.SetSizer(self.sizer)

    def login(self, e):
        password = self.ctrl.GetValue()
        bytes_ = decrypt(password)
        temp = os.path.join(tempfile.gettempdir(), ".random_{}.{}".format(os.getpid(), time.time()))
        try:
            with open(temp, "wb") as f:
                f.write(bytes_)
                f.flush()
            if zipfile.is_zipfile(temp):
                MainFrame(bytes_, password).Show()
                self.Close()
            else:
                self.error.SetLabel("パスワードが違います")
                self.Refresh()
        finally:
            os.remove(temp)

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
        self.panel = wx.Panel(self, size=InitDialog.size)
        sizer.Add(wx.StaticText(self.panel, wx.ID_ANY, "HiddenExplorerを利用するパスワードを入力してください"))
        self.ctrl1 = wx.TextCtrl(self.panel, size=(300, 20))
        sizer.Add(self.ctrl1)
        sizer.Add(wx.StaticText(self.panel, wx.ID_ANY, "確認"))
        self.ctrl2 = wx.TextCtrl(self.panel, size=(300, 20))
        sizer.Add(self.ctrl2)
        self.error = wx.StaticText(self.panel)
        self.error.SetForegroundColour("#FF0000")
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
                temp_zip = os.path.join(tempfile.gettempdir(), ".random_{}.{}".format(os.getpid(), time.time()))
                try:
                    shutil.make_archive(temp_zip, "zip", d)
                    with open(temp_zip+".zip", "rb") as z:
                        encrypt(z, self.password)
                finally:
                    os.remove(temp_zip+".zip")
            self.Close()
        else:
            self.error.SetLabel("パスワードが一致していません")
            self.Refresh()

class RemoveDialog(wx.Dialog):
    size = (500, 300)
    def __init__(self, file, bytes_, password, draw):
        super().__init__(None, title=TITLE, size=RemoveDialog.size)
        self.target = file
        self.bytes = bytes_
        self.password = password
        self.draw = draw
        self.build()

    def build(self):
        self.sizer = wx.BoxSizer(wx.VERTICAL)
        sizer = wx.BoxSizer(wx.VERTICAL)
        self.panel = wx.Panel(self, size=RemoveDialog.size)
        text = wx.StaticText(self.panel, wx.ID_ANY, "HiddenExplorerから{}を削除します".format(self.target))
        text.Wrap(300)
        sizer.Add(text)
        sizer.Add(wx.StaticText(self.panel, wx.ID_ANY, ""))
        sizer.Add(wx.StaticText(self.panel, wx.ID_ANY, "このファイルの移動先のディレクトリを指定してください(移動しない場合は空欄)"))
        sizer2 = wx.BoxSizer(wx.HORIZONTAL)
        self.ctrl = wx.TextCtrl(self.panel, size=(300, 20))
        sizer2.Add(self.ctrl)
        self.button1 = wx.Button(self.panel, wx.ID_ANY, "参照")
        self.button1.Bind(wx.EVT_BUTTON, self.set_from_dialog)
        sizer2.Add(self.button1)
        sizer.Add(sizer2)
        sizer.Add(wx.StaticText(self.panel, wx.ID_ANY, ""))
        self.button2 = wx.Button(self.panel, wx.ID_ANY, "削除")
        self.button2.Bind(wx.EVT_BUTTON, self.run)
        sizer.Add(self.button2)
        self.panel.SetSizer(sizer)
        self.sizer.Add(self.panel)
        self.SetSizer(self.sizer)

    def set_from_dialog(self, e):
        fdialog = wx.DirDialog(None, TITLE)
        if fdialog.ShowModal() == wx.ID_OK:
            directory = fdialog.GetPath()
            if directory:
                self.ctrl.SetValue(directory)

    def run(self, e):
        temp_zip = os.path.join(tempfile.gettempdir(), ".random_{}.{}".format(os.getpid(), time.time()))
        with open(temp_zip, "wb") as f:
            f.write(self.bytes)
        with tempfile.TemporaryDirectory() as d:
            try:
                with zipfile.ZipFile(temp_zip, "r") as z:
                    z.extractall(d)
            finally:
                os.remove(temp_zip)
            directory = self.ctrl.GetValue()
            target = os.path.join(d, self.target)
            if directory:
                shutil.move(target, directory)
            else:
                if os.path.isfile(target):
                    os.remove(target)
                else:
                    shutil.rmtree(target)
            shutil.make_archive(temp_zip, "zip", d)
            with open(temp_zip+".zip", "rb") as z:
                encrypt(z, self.password)
        self.draw()
        self.Close()

def main():
    app = wx.App()
    if os.path.isfile(crypto_file):
        AskPasswordFrame().Show()
    else:
        MainFrame().Show()
    app.MainLoop()

if __name__ == "__main__":
    main()
