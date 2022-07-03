import atexit
import json
import glob
import os
import stat
import sys
import subprocess
import platform
import time
import threading
import shutil
import signal
import tempfile
import warnings
import zipfile

import psutil
import win32api
import win32con
import win32gui
import win32ui
import wx
from multiprocessing import Process
from Crypto.Random import get_random_bytes
from Crypto.Cipher import AES
from PIL import Image
from wx.lib.scrolledpanel import ScrolledPanel

warnings.simplefilter("ignore")

_win = platform.system() == "Windows"

TITLE = "HiddenExplorer"
FILL = b"\r"
IV = b"aaaaaaaaaaaaaaaa"
RESOURCE = os.path.join(os.path.dirname(__file__), "resources")

root = os.path.join(os.getenv("USERPROFILE" if _win else "HOME"), ".HiddenExplorer")
if not os.path.isdir(root):
    os.mkdir(root)
crypto_file = os.path.join(root, ".data")
key_file = os.path.join(root, ".key")
config_file = os.path.join(root, ".rc")
if os.path.isfile(key_file):
    with open(key_file, "rb") as f:
        KEY = f.read()
else:
    KEY = get_random_bytes(AES.block_size*2)
    with open(key_file, "wb") as f:
        f.write(KEY)

def make_cmd(path, notepad=False):
    if _win:
        return "start " + ("%windir%\\notepad.exe " if notepad else '"{}" '.format(os.path.basename(path))) + path
    else:
        return 'open "{}"'.format(path)

def cleanup(path, parent):
    app = wx.App()
    progress = wx.ProgressDialog(TITLE, "プロセス情報を取得中...", style=wx.PD_ELAPSED_TIME | wx.PD_REMAINING_TIME | wx.PD_AUTO_HIDE) 
    progress.Pulse()
    progress.Show()
    processes = list(psutil.process_iter())
    length = len(processes)
    progress.Update(0, newmsg="クリーンアップ中...")
    for n, p in enumerate(processes, start=1):
        try:
            for q in p.open_files():
                if q.path.startswith(path):
                    p.kill()
        except:
            continue
        progress.Update(round(n / length * 100))
    if configmanager["0"]:
        temp_zip = os.path.join(tempfile.gettempdir(), ".random_{}.{}".format(os.getpid(), time.time()))
        try:
            with open(temp_zip, "wb") as f:
                f.write(parent.bytes)
            with zipfile.ZipFile(temp_zip, "a") as z:
                for p in glob.glob(os.path.join(path, "**"), recursive=True)[1:]:
                    z.write(p, os.path.relpath(p, path))
            with open(temp_zip, "rb") as f:
                encrypt(f, parent.password)
        finally:
            os.remove(temp_zip)
    progress.Update(100)
    if os.path.isfile(path):
        os.remove(path)
    elif os.path.isdir(path):
        shutil.rmtree(path)
    progress.Destroy()

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

def register_on_exit(func):
    atexit.register(func)
    signal.signal(signal.SIGTERM, lambda: (func(), sys.exit(1)))

class ConfigManager(dict):
    configs = {"0": "ファイル、ディレクトリの変更を保持する", "options": ""}
    def __init__(self):
        super().__init__()
        if os.path.isfile(config_file):
            with open(config_file, "r") as f:
                self.update(json.load(f))
        else:
            self.update({"0": True})

    def save(self):
        with open(config_file, "w") as f:
            json.dump(self, f, indent=4)

    def gettext(self, num):
        return ConfigManager.configs[num]

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
        wx.CallLater(10, self.func, files[0])
        return True

class MainFrame(wx.Frame):
    size = (800, 500)
    def __init__(self, bytes_=None, password=None):
        super().__init__(None, title=TITLE, size=MainFrame.size)
        self.bytes = bytes_
        self.password = password
        self.files = None
        self.SetDropTarget(FileDropTarget(self.add))
        self.frame_menu_func = {1: self.add_from_dialog, 2: lambda: self.add_from_dialog(True), 3: lambda: SettingFrame(self).Show()}
        self.menu_func = {1: lambda p: self.run_file(p), 2: lambda p: self.run_file(p, notepad=True), 3: lambda p: RemoveDialog(self, p).ShowModal()}
        menu_file = wx.Menu()
        menu_file.Append(1, "ファイルを追加")
        menu_file.Append(2, "ディレクトリを追加")
        menu_config = wx.Menu()
        menu_config.Append(3, "設定を開く")
        menu_bar = wx.MenuBar()
        menu_bar.Append(menu_file, "ファイル")
        menu_bar.Append(menu_config, "設定")
        self.SetMenuBar(menu_bar)
        self.Bind(wx.EVT_MENU, self.run_menu)
        self.default_fileicon = wx.Image(os.path.join(RESOURCE, "default_icon.png")).Scale(90, 100).ConvertToBitmap()
        self.default_diricon = wx.Image(os.path.join(RESOURCE, "directory_icon.png")).Scale(90, 100).ConvertToBitmap()
        self.icon = wx.Icon(os.path.join(RESOURCE, "HiddenExplorer.ico"), wx.BITMAP_TYPE_ICO)
        self.SetIcon(self.icon)
        self.Bind(wx.EVT_SIZE, self.resize_panel)
        self.app_dir = tempfile.TemporaryDirectory().name
        register_on_exit(RunFunction(cleanup, self.app_dir, self))
        self.build()

    def resize_panel(self, e):
        if hasattr(self, "panel"):
            self.panel.SetSize((self.Size.width-15, self.Size.height-60))
            self.Refresh()

    def run_menu(self, e):
        self.frame_menu_func[e.GetId()]()

    def add_from_dialog(self, directory=False):
        if directory:
            fdialog = wx.DirDialog(None, TITLE, style=wx.DD_DIR_MUST_EXIST)
        else:
            fdialog = wx.FileDialog(None, TITLE, style=wx.FD_MULTIPLE | wx.FD_FILE_MUST_EXIST)
        if fdialog.ShowModal() == wx.ID_OK:
            path = fdialog.GetPath() if directory else fdialog.GetPaths()
            if path:
                self.add(path)

    def build(self):
        progress = wx.ProgressDialog(TITLE, "描画中...")
        progress.SetIcon(self.icon)
        progress.Show()
        self.update_files()
        if hasattr(self, "sizer"):
            self.sizer.Clear(True)
        else:
            self.sizer = wx.BoxSizer(wx.VERTICAL)
        self.panel = ScrolledPanel(self, size=(self.Size.width-15, self.Size.height-110))
        self.psizer = wx.GridSizer(cols=4)
        if self.files:
            temp_zip = os.path.join(tempfile.gettempdir(), ".random_{}.{}".format(os.getpid(), time.time()))
            with open(temp_zip, "wb") as f:
                f.write(self.bytes)
            try:
                for n, p in enumerate(self.files, start=1):
                    if "/" not in p or (p.endswith("/") and p.count("/") == 1):
                        self.set_layout(p, temp_zip)
                    progress.Update(round((n / len(self.files))*100))
            finally:
                os.remove(temp_zip)
        self.panel.SetSizer(self.psizer)
        self.sizer.Add(self.panel, proportion=1)
        self.SetSizer(self.sizer)
        self.Layout()
        self.panel.SetupScrolling()
        self.Refresh()
        progress.Close()

    def add(self, path):
        if self.bytes:
            progress = wx.ProgressDialog(TITLE, "追加中...", style=wx.PD_ELAPSED_TIME | wx.PD_REMAINING_TIME)
            progress.SetIcon(self.icon)
            progress.Show()
            progress.Pulse()
            temp_zip = os.path.join(tempfile.gettempdir(), ".random_{}.{}".format(os.getpid(), time.time()))
            try:
                with open(temp_zip, "wb") as f:
                    f.write(self.bytes)
                with zipfile.ZipFile(temp_zip, "a") as z:
                    if isinstance(path, str):
                        z.write(path, os.path.basename(path))
                        if os.path.isdir(path):
                            for q in glob.iglob(os.path.join(path, "**"), recursive=True):
                                z.write(q, "/".join([os.path.basename(path), os.path.relpath(q, path)]))
                            shutil.rmtree(path)
                        else:
                            os.remove(path)
                    else:
                        for p in path:
                            z.write(p, os.path.basename(p))
                            if os.path.isdir(p):
                                for q in glob.iglob(os.path.join(p, "**"), recursive=True):
                                    z.write(q, "/".join([os.path.basename(p), os.path.relpath(q, p)]))
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
                progress.Close()
        else:
            files = [path] if isinstance(path, str) else path
            init = InitDialog(self, self.set_layout, files)
            init.ShowModal()
            if hasattr(init, "password"):
                self.sizer.Clear(True)
                self.panel = ScrolledPanel(self, size=self.Size)
                self.panel.SetupScrolling()
                self.psizer = wx.GridSizer(cols=4)
                self.password = init.password
                self.bytes = decrypt(self.password)
                self.files = files
                for p in files:
                    self.set_layout(os.path.basename(p))
                self.panel.SetSizer(self.psizer)
                self.sizer.Add(self.panel, proportion=1)
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
                self.files = [p for p in set(z.namelist()) if p.count(os.sep) < 2]
        finally:
            os.remove(temp_zip)

    def set_layout(self, path, zip=None):
        sizer = wx.BoxSizer(wx.VERTICAL)
        panel = wx.Panel(self.panel, size=(150, 120))
        temp_zip = os.path.join(tempfile.gettempdir(), ".random_{}.{}".format(os.getpid(), time.time()))
        try:
            if zip:
                temp_zip = zip
            else:
                with open(temp_zip, "wb") as f:
                    f.write(self.bytes)
            with tempfile.TemporaryDirectory() as d:
                with zipfile.ZipFile(temp_zip, "r") as z:
                    try:
                        file = z.extract(path, os.path.join(d, os.path.splitext(path)[1]))
                    except:
                        file = z.extract(path+"/", os.path.join(d, path))
                try:
                    img = get_icon(file).resize((90, 100))
                    image = wx.Image(img.size[0], img.size[1])
                    image.SetData(img.convert("RGB").tobytes())
                    bmp = wx.StaticBitmap(panel, wx.ID_ANY, image.ConvertToBitmap())
                except:
                    bmp = wx.StaticBitmap(panel, wx.ID_ANY, self.default_fileicon if os.path.isfile(file) else self.default_diricon)
                bmp.Bind(wx.EVT_LEFT_DCLICK, RunFunction(self.run_file, path))
                bmp.Bind(wx.EVT_RIGHT_UP, RunFunction(self.show_menu, path, os.path.isdir(file)))
                sizer.Add(bmp, proportion=1)
        finally:
            if not zip:
                os.remove(temp_zip)
        sizer.Add(wx.StaticText(panel, wx.ID_ANY, textwrap(path, 15)), proportion=1)
        panel.SetSizer(sizer)
        panel.Bind(wx.EVT_LEFT_DCLICK, RunFunction(self.run_file, path))
        panel.Bind(wx.EVT_RIGHT_UP, RunFunction(self.show_menu, path))
        panel.Bind(wx.EVT_ENTER_WINDOW, RunFunction(panel.SetBackgroundColour, "#444444"))
        panel.Bind(wx.EVT_LEAVE_WINDOW, RunFunction(panel.SetBackgroundColour, wx.NullColour))
        self.psizer.Add(panel, proportion=1)

    def show_menu(self, path, directory=False):
        menu = wx.Menu()
        menu.Append(wx.MenuItem(menu, 1, "開く"))
        if directory:
            menu.Append(wx.MenuItem(menu, 2, "ファイルエクスプローラーで開く"))
        elif _win:
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
        if not os.path.splitext(path)[1]:
            notepad = True
        temp_zip = os.path.join(tempfile.gettempdir(), ".random_{}.{}".format(os.getpid(), time.time()))
        try:
            with open(temp_zip, "wb") as f:
                f.write(self.bytes)
            with zipfile.ZipFile(temp_zip, "r") as z:
                try:
                    file = z.extract(path, self.app_dir)
                except:
                    file = z.extract(path+"/", self.app_dir)
                if os.path.isdir(file):
                    for p in [t for t in z.namelist() if t.startswith(os.path.basename(file))]:
                        z.extract(p, self.app_dir)
        finally:
            os.remove(temp_zip)
        if notepad and os.path.isfile(file):
            subprocess.run(make_cmd('"{}"'.format(file), notepad=True), shell=True)
        else:
            if os.path.isfile(file):
                subprocess.run(make_cmd('"{}"'.format(file)), shell=True)
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
                                p = Process(target=subprocess.run, args=(make_cmd('"{}"'.format(path)),), kwargs={"shell": True})
                                p.start()
                                processes.append(p)
                                return True
                    else:
                        return False
                while open_dir(file):
                    pass
                for p in processes:
                    p.kill()

class SettingFrame(wx.Frame):
    size = (500, 300)
    def __init__(self, parent):
        super().__init__(parent, title=TITLE, size=SettingFrame.size, style=wx.DEFAULT_FRAME_STYLE ^ wx.RESIZE_BORDER ^ wx.MAXIMIZE_BOX)
        self.icon = wx.Icon(os.path.join(RESOURCE, "HiddenExplorer.ico"), wx.BITMAP_TYPE_ICO)
        self.SetIcon(self.icon)
        self.build()

    def build(self):
        self.panel = ScrolledPanel(self, size=(self.Size.width-15, self.Size.height-30))
        self.sizer = wx.BoxSizer(wx.VERTICAL)
        sizer = wx.BoxSizer(wx.VERTICAL)
        self.panel.SetupScrolling()
        self.boxes = []
        for k, v in configmanager.items():
            chbox = wx.CheckBox(self.panel, wx.ID_ANY, configmanager.gettext(k))
            chbox.SetValue(v)
            sizer.Add(chbox)
            self.boxes.append(chbox)
        sizer.Add(wx.StaticText(self.panel))
        sizer.Add(wx.StaticText(self.panel))
        button = wx.Button(self.panel, wx.ID_ANY, "変更")
        button.Bind(wx.EVT_BUTTON, self.save)
        sizer.Add(button)
        self.panel.SetSizer(sizer)
        self.sizer.Add(self.panel)
        self.SetSizer(self.sizer)

    def save(self, e):
        for n, b in enumerate(self.boxes):
            configmanager[str(n)] = b.GetValue()
        configmanager.save()
        self.Close()
        

class AskPasswordFrame(wx.Frame):
    size = (250, 140)
    def __init__(self):
        super().__init__(None, title=TITLE, size=AskPasswordFrame.size, style=wx.DEFAULT_FRAME_STYLE ^ wx.RESIZE_BORDER ^ wx.MAXIMIZE_BOX)
        self.running = False
        self.icon = wx.Icon(os.path.join(RESOURCE, "HiddenExplorer.ico"), wx.BITMAP_TYPE_ICO)
        self.SetIcon(self.icon)
        self.build()

    def build(self):
        self.sizer = wx.BoxSizer(wx.VERTICAL)
        sizer = wx.BoxSizer(wx.VERTICAL)
        self.panel = wx.Panel(self, size=self.Size)
        sizer.Add(wx.StaticText(self.panel, wx.ID_ANY, "パスワードを入力してください"))
        self.ctrl = wx.TextCtrl(self.panel, size=(200, 20), style=wx.TE_PROCESS_ENTER | wx.TE_PASSWORD)
        self.ctrl.Bind(wx.EVT_TEXT_ENTER, self.login)
        sizer.Add(self.ctrl)
        self.error = wx.StaticText(self.panel)
        self.error.SetForegroundColour("#FF0000")
        sizer.Add(self.error)
        self.button = wx.Button(self.panel, wx.ID_ANY, "アクセス")
        self.button.Bind(wx.EVT_BUTTON, self.login)
        sizer.Add(self.button)
        self.panel.SetSizer(sizer)
        self.sizer.Add(self.panel)
        self.SetSizer(self.sizer)

    def login(self, e):
        if self.running:
            return
        self.running = True
        self.button.Disable()
        self.Refresh()
        self.Update()
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
                self.button.Enable()
                self.running = False
                self.Refresh()
        finally:
            os.remove(temp)

class InitDialog(wx.Dialog):
    size = (320, 200)
    def __init__(self, parent, func, files):
        super().__init__(parent, title=TITLE+"  初期化", size=InitDialog.size, style=wx.DEFAULT_FRAME_STYLE ^ wx.RESIZE_BORDER ^ wx.MAXIMIZE_BOX)
        self.run_func = func
        self.files = files
        self.icon = wx.Icon(os.path.join(RESOURCE, "HiddenExplorer.ico"), wx.BITMAP_TYPE_ICO)
        self.SetIcon(self.icon)
        self.build()

    def build(self):
        self.sizer = wx.BoxSizer(wx.VERTICAL)
        sizer = wx.BoxSizer(wx.VERTICAL)
        self.panel = wx.Panel(self, size=self.Size)
        sizer.Add(wx.StaticText(self.panel, wx.ID_ANY, "設定するパスワードを入力してください"))
        self.ctrl1 = wx.TextCtrl(self.panel, size=(300, 20), style=wx.TE_PROCESS_ENTER | wx.TE_PASSWORD)
        sizer.Add(self.ctrl1)
        sizer.Add(wx.StaticText(self.panel, wx.ID_ANY, "確認"))
        self.ctrl2 = wx.TextCtrl(self.panel, size=(300, 20), style=wx.TE_PROCESS_ENTER | wx.TE_PASSWORD)
        sizer.Add(self.ctrl2)
        self.error = wx.StaticText(self.panel)
        self.error.SetForegroundColour("#FF0000")
        sizer.Add(self.error)
        self.button = wx.Button(self.panel, wx.ID_ANY, "決定")
        self.button.Bind(wx.EVT_BUTTON, self.set_password)
        sizer.Add(self.button)
        self.ctrl1.Bind(wx.EVT_TEXT_ENTER, RunFunction(self.ctrl2.SetFocus))
        self.ctrl2.Bind(wx.EVT_TEXT_ENTER, self.set_password)
        self.panel.SetSizer(sizer)
        self.sizer.Add(self.panel)
        self.SetSizer(self.sizer)

    def set_password(self, e):
        self.password = self.ctrl1.GetValue()
        if not self.password:
            self.error.SetLabel("設定するパスワードを入力してください")
            self.Refresh()
        elif self.password == self.ctrl2.GetValue():
            progress = wx.ProgressDialog(TITLE, "追加中...", style=wx.PD_ELAPSED_TIME | wx.PD_REMAINING_TIME)
            progress.SetIcon(self.icon)
            progress.Show()
            progress.Pulse()
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
            progress.Close()
            self.Close()
        else:
            self.error.SetLabel("パスワードが一致していません")
            self.Refresh()

class RemoveDialog(wx.Dialog):
    size = (500, 200)
    def __init__(self, parent, file):
        super().__init__(parent, title=TITLE, size=RemoveDialog.size, style=wx.DEFAULT_FRAME_STYLE ^ wx.RESIZE_BORDER)
        self.target = file
        self.bytes = parent.bytes
        self.password = parent.password
        self.draw = parent.build
        self.parent = parent
        self.icon = wx.Icon(os.path.join(RESOURCE, "HiddenExplorer.ico"), wx.BITMAP_TYPE_ICO)
        self.SetIcon(self.icon)
        self.build()

    def build(self):
        self.sizer = wx.BoxSizer(wx.VERTICAL)
        sizer = wx.BoxSizer(wx.VERTICAL)
        self.panel = wx.Panel(self, size=self.Size)
        text = wx.StaticText(self.panel, wx.ID_ANY, "HiddenExplorerから{}を削除します".format(self.target))
        text.Wrap(400)
        sizer.Add(text, flag=wx.ALIGN_CENTER)
        sizer.Add(wx.StaticText(self.panel, wx.ID_ANY, ""))
        sizer.Add(wx.StaticText(self.panel, wx.ID_ANY, "このファイル、またはディレクトリの移動先のディレクトリを指定してください(移動しない場合は空欄)"), flag=wx.ALIGN_CENTER)
        sizer2 = wx.BoxSizer(wx.HORIZONTAL)
        self.ctrl = wx.TextCtrl(self.panel, size=(250, 20))
        sizer2.Add(self.ctrl)
        self.button1 = wx.Button(self.panel, wx.ID_ANY, "参照")
        self.button1.Bind(wx.EVT_BUTTON, self.set_from_dialog)
        sizer2.Add(self.button1)
        sizer.Add(sizer2, flag=wx.ALIGN_CENTER)
        sizer.Add(wx.StaticText(self.panel, wx.ID_ANY, ""))
        self.button2 = wx.Button(self.panel, wx.ID_ANY, "削除")
        self.button2.Bind(wx.EVT_BUTTON, self.run)
        sizer.Add(self.button2, flag=wx.ALIGN_CENTER)
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
        progress = wx.ProgressDialog(TITLE, "削除中...", style=wx.PD_ELAPSED_TIME | wx.PD_REMAINING_TIME)
        progress.SetIcon(self.icon)
        progress.Show()
        progress.Pulse()
        try:
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
                with open(temp_zip+".zip", "rb") as f:
                    encrypt(f, self.password)
                    f.seek(0)
                    self.parent.bytes = f.read()
        finally:
            progress.Close()
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
    configmanager = ConfigManager()
    main()
