# -*- mode: python -*-

block_cipher = None

# Integrate astropy as data directory instead of module:
import astropy
astropy_path, = astropy.__path__

a = Analysis(['planetary_system_stacker.py'],
             pathex=['D:\\SW-Development\\Python\\PlanetarySystemStacker\\Source'],
             binaries=[],
             datas=[( 'D:\\SW-Development\\Python\\PlanetarySystemStacker\\Documentation\\Icon\\PSS-Icon-64.ico', '.' ),
             (astropy_path, 'astropy')],
             hiddenimports=['pywt._extensions._cwt', 'scipy._lib.messagestream', 'shelve', 'csv'],
             hookspath=[],
             runtime_hooks=[],
             excludes=['astropy'],
             win_no_prefer_redirects=False,
             win_private_assemblies=False,
             cipher=block_cipher,
             noarchive=False)
pyz = PYZ(a.pure, a.zipped_data,
             cipher=block_cipher)
exe = EXE(pyz,
          a.scripts,
          [],
          exclude_binaries=True,
          name='planetary_system_stacker',
          debug=False,
          bootloader_ignore_signals=False,
          strip=False,
          upx=True,
          console=True )    # To get rid of the console window, change value to False.
coll = COLLECT(exe,
               a.binaries,
               a.zipfiles,
               a.datas,
               strip=False,
               upx=True,
               name='PlanetarySystemStacker')
