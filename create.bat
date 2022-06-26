pip install --user -U pip setuptools nuitka zstandard ordered-set Cython

pip install --user -U -r requirements.txt

python -m nuitka  --mingw64 --windows-disable-console --follow-imports --standalone --onefile --include-data-dir=./HiddenExplorer/resources=resources --windows-icon-from-ico=./HiddenExplorer/resources/HiddenExplorer.ico -o HiddenExplorer.exe ./HiddenExplorer/main.py
