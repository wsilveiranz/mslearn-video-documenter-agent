# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for MS Learn Video Documenter backend."""

a = Analysis(
    ['src/main.py'],
    pathex=['.'],
    binaries=[],
    datas=[
        ('src/prompts', 'src/prompts'),
        ('src/templates', 'src/templates'),
    ],
    hiddenimports=[
        'uvicorn.logging',
        'uvicorn.loops',
        'uvicorn.loops.auto',
        'uvicorn.protocols',
        'uvicorn.protocols.http',
        'uvicorn.protocols.http.auto',
        'uvicorn.protocols.websockets',
        'uvicorn.protocols.websockets.auto',
        'uvicorn.lifespan',
        'uvicorn.lifespan.on',
        'uvicorn.lifespan.off',
        'multipart',
        'multipart.multipart',
        'email.mime.multipart',
        'email.mime.text',
        'structlog',
        'src',
        'src.api',
        'src.api.routes',
        'src.api.websocket',
        'src.config',
        'src.agents',
        'src.models',
        'src.services',
        'src.utils',
        'src.utils.paths',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['pytest', 'ruff', 'pyright', 'tkinter', 'matplotlib'],
    noarchive=False,
)

# Exclude Universal CRT DLLs — they ship with Windows 10+ and the bundled
# copies can trigger 0xc0e90002 ("Bad Image") on some machines.
a.binaries = [
    b for b in a.binaries
    if not b[0].lower().startswith('api-ms-win-')
    and b[0].lower() != 'ucrtbase.dll'
]

pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    name='backend',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
)
