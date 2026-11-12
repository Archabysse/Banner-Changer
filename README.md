# Changer of Banners (Banner-Changer) - Source Files

## Prerequisites
* Python 3.x installed
* PyInstaller (`pip install pyinstaller`)
* Any additional libraries required by your environment (e.g., `pip install pillow`, etc., if applicable)

## How to Build
1. Download or clone this repository.
2. Open a terminal/command prompt in the root folder containing `Changer_of_Banners.py`, `BC.ico`, and the `moteur` folder.
3. Run the following command:

```
pyinstaller --onefile --windowed --name Changer_of_Banners --paths moteur Changer_of_Banners.py --icon BC.ico
```

4. The compiled executable (`Changer_of_Banners.exe`) will be generated in the `dist` directory.
