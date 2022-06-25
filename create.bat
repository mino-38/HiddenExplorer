pip install --user -U pip setuptools pyinstaller
pip install --user -U -r requirements.txt

pyinstaller --onefile --noconsole --add-data "./HiddenExplorer/resources;resources" --icon=./HiddenExplorer/resources/HiddenExplorer.ico -n HiddenExplorer.exe ./HiddenExplorer/main.py
