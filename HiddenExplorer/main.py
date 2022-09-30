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
from selenium import webdriver
from PIL import Image
from wx.lib.scrolledpanel import ScrolledPanel

warnings.simplefilter("ignore")

_win = platform.system() == "Windows"

TITLE = "HiddenExplorer"
FILL = b"\r"
IV = b"aaaaaaaaaaaaaaaa"
RESOURCE = os.path.join(os.path.dirname(__file__), "resources")
ROOT = os.path.join(os.getenv("LOCALAPPDATA"), ".HiddenExplorer") if _win else os.getenv("HOME")

if not os.path.isdir(ROOT):
    os.mkdir(ROOT)
crypto_file = os.path.join(ROOT, ".data")
key_file = os.path.join(ROOT, ".key")
config_file = os.path.join(ROOT, ".rc")
if os.path.isfile(key_file):
    with open(key_file, "rb") as f:
        KEY = f.read()
else:
    KEY = get_random_bytes(AES.block_size*2)
    with open(key_file, "wb") as f:
        f.write(KEY)

def make_cmd(path, notepad=False):
    if _win:
        path = path.strip('"')
        return 'start {} "{}"'.format("%windir%\\notepad.exe" if notepad else '"{}"'.format(os.path.basename(path)), path)
    else:
        return 'open "{}"'.format(path)

def reset(parent):
    dialog = wx.MessageDialog(parent, caption=TITLE+"  初期化", message="※初期化をすると現在登録されているファイル及びパスワードは全て消去され、HiddenExplorerは閉じられます\n初期化をしますか？", style=wx.YES_NO | wx.ICON_QUESTION)
    if dialog.ShowModal() == wx.ID_YES:
        parent.cleanup.register(ROOT)
        parent.Close()

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

class CleanUp:
    def __init__(self):
        self.path = []

    def register(self, value):
        self.path.append(value)

    def __call__(self, parent):
        if not self.path:
            return
        if not wx.GetApp():
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
                    for t in self.path:
                        if ".." not in os.path.relpath(q.path, t):
                            p.kill()
                            break
                for t in self.path:
                    if ".." not in os.path.relpath(p.exe(), t):
                        p.kill()
                        break
            except:
                continue
            progress.Update(round(n / length * 100))
        if parent.bytes and configmanager["0"] and ROOT not in self.path:
            temp_zip = os.path.join(tempfile.gettempdir(), ".random_{}.{}".format(os.getpid(), time.time()))
            try:
                with open(temp_zip, "wb") as f:
                    f.write(parent.bytes)
                with tempfile.TemporaryDirectory() as d:
                    with zipfile.ZipFile(temp_zip, "r") as z:
                        z.extractall(d)
                    for t in self.path:
                        for p in glob.iglob(os.path.join(t, "*")):
                            to = os.path.join(d, os.path.basename(p.rstrip(os.sep)))
                            if os.path.isdir(to):
                                shutil.rmtree(to)
                            shutil.move(p, to)
                    shutil.make_archive(temp_zip, format="zip", root_dir=d)
                    with open(temp_zip+".zip", "rb") as f:
                        encrypt(f, parent.password)
                    os.remove(temp_zip+".zip")
            finally:
                os.remove(temp_zip)
        progress.Update(100)
        for t in self.path:
            if os.path.isfile(t):
                os.remove(t)
            elif os.path.isdir(t):
                shutil.rmtree(t)
        progress.Destroy()

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
    def __init__(self, func, *args, _at_exit=lambda: "", **kwargs):
        self.func = func
        self.args = args
        self.atexit = _at_exit
        self.kwargs = kwargs

    def __call__(self, *_, **__):
        self.func(*self.args, **self.kwargs)
        self.atexit()

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
        self.selected_widget = None
        self.SetDropTarget(FileDropTarget(self.add))
        self.frame_menu_func = {1: self.add_from_dialog, 2: lambda: self.add_from_dialog(True), 3: lambda: OpenBrowserDialog(self, self.app_dir).ShowModal(), 4: lambda: SettingFrame(self).Show(), 5: lambda: ResetPasswordDialog(self).ShowModal(), 6: lambda: reset(self)}
        self.menu_func = {1: lambda p: self.run_file(p), 2: lambda p: self.run_file(p, notepad=True), 3: lambda p: RemoveDialog(self, p).ShowModal(), 4: lambda p: OpenBrowserDialog(self, p).ShowModal()}
        menu_file = wx.Menu()
        menu_file.Append(1, "ファイルを追加")
        menu_file.Append(2, "ディレクトリを追加")
        menu_config = wx.Menu()
        menu_config.Append(4, "設定を開く")
        if os.path.isfile(crypto_file):
            menu_config.Append(5, "パスワードの変更")
        menu_config.Append(6, "初期化")
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
        self.cleanup = CleanUp()
        self.cleanup.register(self.app_dir)
        register_on_exit(RunFunction(self.cleanup, self))
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
        self.panel.Bind(wx.EVT_LEFT_DOWN, lambda _: self.release_selected())
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
                self.password = init.password
                self.bytes = decrypt(self.password)
                self.files = files
                for p in files:
                    self.set_layout(os.path.basename(p))
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
        panel = wx.Panel(self.panel, size=(120, 150))
        sizer.Add(wx.StaticText(panel))
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
                isdir = os.path.isdir(file)
                try:
                    img = get_icon(file).resize((90, 100))
                    image = wx.Image(img.size[0], img.size[1])
                    image.SetData(img.convert("RGB").tobytes())
                    bmp = wx.StaticBitmap(panel, wx.ID_ANY, image.ConvertToBitmap())
                except:
                    bmp = wx.StaticBitmap(panel, wx.ID_ANY, self.default_diricon if isdir else self.default_fileicon)
                bmp.Bind(wx.EVT_LEFT_DOWN, lambda _: self.release_selected())
                bmp.Bind(wx.EVT_LEFT_DCLICK, RunFunction(self.run_file, path, _at_exit=RunFunction(self.paint_selected_color, panel)))
                bmp.Bind(wx.EVT_RIGHT_UP, RunFunction(self.show_menu, path, isdir))
                bmp.Bind(wx.EVT_ENTER_WINDOW, RunFunction(self.paint_on_monse_color, panel, "#CCFFFF"))
                bmp.Bind(wx.EVT_LEAVE_WINDOW, RunFunction(self.paint_on_monse_color, panel, wx.NullColour))
                sizer.Add(bmp, flag=wx.ALIGN_CENTER, proportion=1)
        finally:
            if not zip:
                os.remove(temp_zip)
        sizer.Add(wx.StaticText(panel, wx.ID_ANY, textwrap(path, 15)), flag=wx.ALIGN_CENTER, proportion=1)
        panel.SetSizer(sizer)
        panel.Bind(wx.EVT_LEFT_DOWN, lambda _: self.release_selected())
        panel.Bind(wx.EVT_LEFT_DCLICK, RunFunction(self.run_file, path, _at_exit=RunFunction(self.paint_selected_color, panel)))
        panel.Bind(wx.EVT_RIGHT_UP, RunFunction(self.show_menu, path, isdir))
        self.psizer.Add(panel, proportion=1)

    def paint_on_monse_color(self, widget, color):
        if widget != self.selected_widget:
            widget.SetBackgroundColour(color)
            self.Refresh()

    def release_selected(self):
        if self.selected_widget:
            self.selected_widget.SetBackgroundColour(wx.NullColour)
            self.selected_widget = None
            self.Refresh()

    def paint_selected_color(self, widget):
        self.release_selected()
        widget.SetBackgroundColour("#8EB8FF")
        self.selected_widget = widget
        self.Refresh()

    def show_menu(self, path, directory=False):
        menu = wx.Menu()
        menu.Append(wx.MenuItem(menu, 1, "開く"))
        if directory:
            menu.Append(wx.MenuItem(menu, 2, "ファイルエクスプローラーで開く"))
            menu.Append(wx.MenuItem(menu, 4, "このディレクトリをダウンロード先としたブラウザを開く"))
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
        file = os.path.join(self.app_dir, os.path.basename(path.rstrip("/")))
        if not os.path.exists(file):
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
        progress = wx.ProgressDialog(TITLE, "復号化中...")
        progress.SetIcon(self.icon)
        progress.Show()
        progress.Pulse()
        password = self.ctrl.GetValue()
        bytes_ = decrypt(password)
        temp = os.path.join(tempfile.gettempdir(), ".random_{}.{}".format(os.getpid(), time.time()))
        try:
            with open(temp, "wb") as f:
                f.write(bytes_)
                f.flush()
            progress.Close()
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

class ResetPasswordDialog(wx.Dialog):
    size = (320, 200)
    def __init__(self, parent):
        super().__init__(parent, title=TITLE, size=ResetPasswordDialog.size, style=wx.DEFAULT_FRAME_STYLE ^ wx.RESIZE_BORDER ^ wx.MAXIMIZE_BOX)
        self.parent = parent
        self.running = False
        self.icon = wx.Icon(os.path.join(RESOURCE, "HiddenExplorer.ico"), wx.BITMAP_TYPE_ICO)
        self.SetIcon(self.icon)
        self.build()

    def build(self):
        self.sizer = wx.BoxSizer()
        self.panel = wx.Panel(self, size=self.Size)
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(wx.StaticText(self.panel, wx.ID_ANY, "現在のパスワード"))
        self.ctrl1 = wx.TextCtrl(self.panel, size=(400, 20), style=wx.TE_PROCESS_ENTER | wx.TE_PASSWORD)
        sizer.Add(self.ctrl1)
        sizer.Add(wx.StaticText(self.panel, wx.ID_ANY, "新しいパスワード"))
        self.ctrl2 = wx.TextCtrl(self.panel, size=(400, 20), style=wx.TE_PROCESS_ENTER | wx.TE_PASSWORD)
        sizer.Add(self.ctrl2)
        sizer.Add(wx.StaticText(self.panel, wx.ID_ANY, "確認"))
        self.ctrl3 = wx.TextCtrl(self.panel, size=(400, 20), style=wx.TE_PROCESS_ENTER | wx.TE_PASSWORD)
        sizer.Add(self.ctrl3)
        self.button = wx.Button(self.panel, wx.ID_ANY, "変更")
        self.button.Bind(wx.EVT_BUTTON, self.run)
        sizer.Add(self.button)
        self.error = wx.StaticText(self.panel)
        self.error.SetForegroundColour("#FF0000")
        sizer.Add(self.error)
        self.ctrl1.Bind(wx.EVT_TEXT_ENTER, RunFunction(self.ctrl2.SetFocus))
        self.ctrl2.Bind(wx.EVT_TEXT_ENTER, RunFunction(self.ctrl3.SetFocus))
        self.ctrl3.Bind(wx.EVT_TEXT_ENTER, self.run)
        self.panel.SetSizer(sizer)
        self.sizer.Add(self.panel)
        self.SetSizer(self.sizer)

    def run(self, e):
        if self.running:
            return
        self.button.Disable()
        self.running = True
        bytes_ = decrypt(self.ctrl1.GetValue())
        temp = os.path.join(tempfile.gettempdir(), ".random_{}.{}".format(os.getpid(), time.time()))
        try:
            with open(temp, "wb") as f:
                f.write(bytes_)
                f.flush()
            if zipfile.is_zipfile(temp):
                new_password = self.ctrl2.GetValue()
                if new_password == self.ctrl3.GetValue():
                    with open(temp, "rb") as f:
                        encrypt(f, new_password)
                    self.parent.password = new_password
                    self.Close()
                else:
                    self.error.SetLabel("新しいパスワードが確認用と一致していません")
                    self.button.Enable()
                    self.running = False
                    self.Refresh()
            else:
                self.error.SetLabel("現在のパスワードが違います")
                self.button.Enable()
                self.running = False
                self.Refresh()
        finally:
            os.remove(temp)

class InitDialog(wx.Dialog):
    size = (320, 200)
    def __init__(self, parent, func, files):
        super().__init__(parent, title=TITLE+"  初期設定", size=InitDialog.size, style=wx.DEFAULT_FRAME_STYLE ^ wx.RESIZE_BORDER ^ wx.MAXIMIZE_BOX)
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
        self.button1 = wx.Button(self.panel, wx.ID_ANY, "参照", size=(wx.DefaultSize.width, 20))
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
                os.remove(temp_zip+".zip")
        finally:
            progress.Close()
        self.draw()
        self.Close()

class OpenBrowserDialog(wx.Dialog):
    size = (300, 200)
    def __init__(self, parent, download_dir):
        super().__init__(parent, title=TITLE, size=OpenBrowserDialog.size, style=wx.DEFAULT_FRAME_STYLE ^ wx.RESIZE_BORDER ^ wx.MAXIMIZE_BOX)
        self.parent = parent
        self.download_dir = download_dir
        self.icon = wx.Icon(os.path.join(RESOURCE, "HiddenExplorer.ico"), wx.BITMAP_TYPE_ICO)
        self.SetIcon(self.icon)
        self.browsers = ["Chrome", "Firefox", "Edge", "Ie", "Opera"]
        self.build()

    def build(self):
        self.sizer = wx.BoxSizer(wx.VERTICAL)
        panel = wx.Panel(self, size=OpenBrowserDialog.size)
        sizer = wx.GridSizer(cols=3)
        for n, b in enumerate(self.browsers):
            button = wx.Button(panel, wx.ID_ANY, b)
            button.Bind(wx.EVT_BUTTON, RunFunction(self.run, n))
            sizer.Add(button)
        panel.SetSizer(sizer)
        self.sizer.Add(panel)
        self.SetSizer(self.sizer)

    def run(self, index):
        directory = os.path.join(self.parent.app_dir, os.path.basename(self.download_dir.rstrip("/")))
        if not os.path.isdir(directory):
            temp_zip = os.path.join(tempfile.gettempdir(), ".random_{}.{}".format(os.getpid(), time.time()))
            try:
                with open(temp_zip, "wb") as f:
                    f.write(self.parent.bytes)
                with zipfile.ZipFile(temp_zip, "r") as z:
                    try:
                        file = z.extract(self.download_dir, self.parent.app_dir)
                    except:
                        file = z.extract(self.download_dir+"/", self.parent.app_dir)
                    for p in [t for t in z.namelist() if t.startswith(os.path.basename(directory))]:
                        z.extract(p, self.parent.app_dir)
            finally:
                os.remove(temp_zip)
        if index == 0:
            from webdriver_manager.chrome import ChromeDriverManager as manager
            options = webdriver.ChromeOptions()
            options.add_experimental_option("prefs", {"download.default_directory": directory})
            options.add_argument("--user-data-dir={}".format(os.path.join(os.getenv("LOCALAPPDATA"), "Google", "Chrome", "User Data")))
        elif index == 1:
            from webdriver_manager.firefox import GeckoDriverManager as manager
            options = webdriver.FirefoxProfile()
            options.set_preference("browser.download.dir", directory)
        elif index == 2:
            from webdriver_manager.microsoft import EdgeChromiumDriverManager as manager
            options = webdriver.EdgeChromiumOptions()
            options.add_experimental_option("prefs", {"download.default_directory": directory})
            options.add_argument("--user-data-dir={}".format(os.path.join(os.getenv("LOCALAPPDATA"), "Microsoft", "Edge", "User Data")))
        elif index == 3:
            from webdriver_manager.microsoft import IEDriverManager as manager
            options = webdriver.FirefoxOptions()
            options.add_experimental_option("prefs", {"download.default_directory": directory})
            options.add_argument("--user-data-dir={}".format(os.path.join(os.getenv("LOCALAPPDATA"), "Microsoft", "IE", "User Data")))
        else:
            from webdriver_manager.opera import OperaDriverManager as manager
            options = webdriver.OperaOptions()
            options.add_experimental_option("prefs", {"download.default_directory": directory})
        progress = wx.ProgressDialog(TITLE, "ブラウザを開いています...", style=wx.PD_ELAPSED_TIME | wx.PD_REMAINING_TIME)
        progress.SetIcon(self.icon)
        progress.Show()
        progress.Pulse()
        try:
            self.driver = getattr(webdriver, self.browsers[index])(manager().install(), options=options)
            progress.Close()
        except:
            progress.Close()
            wx.MessageBox("ブラウザの起動に失敗しました\nブラウザがインストールされていない可能性があります")
        finally:
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
