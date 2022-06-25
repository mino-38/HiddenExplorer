pip install --user -U pip setuptools pyinstaller virtualenv

virtualenv compile

./compile/Scripts/activate

pip install -U -r requirements.txt

pyinstaller --clean --onefile --noconsole --add-data "./HiddenExplorer/resources;resources" --icon=./HiddenExplorer/resources/HiddenExplorer.ico -n HiddenExplorer.exe ./HiddenExplorer/main.py

deactivate

del /Q ./compile
