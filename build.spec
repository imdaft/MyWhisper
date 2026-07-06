# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec file for MyWhisper
# Build: pyinstaller build.spec
# Output: dist/MyWhisper/ (directory with MyWhisper.exe)

import sys
from pathlib import Path

block_cipher = None

a = Analysis(
    ['run.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[
        'sounddevice',
        'numpy',
        'pynput',
        'pynput.keyboard',
        'pynput.keyboard._win32',
        'pyperclip',
        'faster_whisper',
        'ctranslate2',
        'src.whisper_worker',
        'src.main',
        'src.app',
        'src.config',
        'src.audio_recorder',
        'src.transcriber',
        'src.text_inserter',
        'src.hotkey_manager',
        'src.overlay_widget',
        'src.tray_icon',
        'src.settings_window',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Keep the bundle lean regardless of the build environment. None of
        # these are used by MyWhisper (faster-whisper runs on CTranslate2, not
        # torch/transformers). onnxruntime is NOT excluded — it powers the VAD.
        'tkinter', 'matplotlib', 'PIL',
        'onnx', 'onnx.reference',
        'torch', 'torchvision', 'torchaudio',
        'transformers', 'tensorboard',
        'jax', 'jaxlib', 'cv2', 'altair',
        'scipy', 'pandas', 'numba', 'sympy', 'networkx', 'sklearn',
        'IPython', 'jupyter', 'notebook',
        'pytest', 'setuptools', 'pip',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# Use --onedir mode (directory) for reliable subprocess spawning
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='MyWhisper',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='MyWhisper',
)
