pip install --user -U pip setuptools nuitka zstandard
pip install --user -U -r requirements.txt

nuitka --onefile --windows-disable-console --standalone --mingw64 --follow-imports --include-data-dir=./HiddenExplorer/resources=resources --windows-icon-from-ico=./HiddenExplorer/resources/HiddenExplorer.ico -o HiddenExplorer.exe ./HiddenExplorer/main.py
