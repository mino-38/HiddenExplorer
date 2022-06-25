pip install --user -U pip setuptools virtualenv nuitka zstandard ordered-set Cython

rem virtualenv compile

rem call ./compile/Scripts/activate

pip install --user -U -r requirements.txt

rem pyinstaller --clean --onefile --noconsole --add-data "./HiddenExplorer/resources;resources" --icon=./HiddenExplorer/resources/HiddenExplorer.ico -n HiddenExplorer.exe ./HiddenExplorer/main.py

python -m nuitka  --mingw64 --windows-disable-console --follow-imports --standalone --onefile --include-data-dir=./HiddenExplorer/resources=resources --windows-icon-from-ico=./HiddenExplorer/resources/HiddenExplorer.ico -o HiddenExplorer.exe ./HiddenExplorer/main.py

rem deactivate

rem del /Q ./compile
