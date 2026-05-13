# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for MS Learn Video Documenter backend.

Uses **onedir** mode so all DLLs (including python311.dll) live alongside
backend.exe in a permanent directory.  This avoids onefile's temp-directory
extraction, which is blocked by Windows Application Control / AppLocker
policies on many corporate machines.
"""

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
        'azure.ai.inference',
        'azure.ai.inference.aio',
        'azure.ai.inference.models',
        'azure.ai.projects',
        'azure.ai.projects.aio',
        'azure.ai.projects.models',
        # --- Azure async transport chain (lazy imports missed by PyInstaller) ---
        'aiohttp',
        'aiohttp.client',
        'aiohttp.client_exceptions',
        'aiohttp.connector',
        'aiohttp.cookiejar',
        'aiohttp.formdata',
        'aiohttp.hdrs',
        'aiohttp.helpers',
        'aiohttp.http',
        'aiohttp.http_parser',
        'aiohttp.http_writer',
        'aiohttp.http_websocket',
        'aiohttp.multipart',
        'aiohttp.resolver',
        'aiohttp.streams',
        'aiohttp.tcp_helpers',
        'aiohttp.tracing',
        'aiohttp.typedefs',
        'aiohttp.web',
        'aiohttp._http_parser',
        'aiohttp._http_writer',
        'aiohttp._websocket',
        'multidict',
        'multidict._multidict',
        'yarl',
        'yarl._url',
        'frozenlist',
        'frozenlist._frozenlist',
        'aiosignal',
        'aiohappyeyeballs',
        'attrs',
        'attr',
        'propcache',
        'propcache._helpers',
        'charset_normalizer',
        'isodate',
        'isodate.isodates',
        'isodate.isotime',
        'isodate.isoduration',
        'isodate.isoerror',
        'isodate.tzinfo',
    ],
    hookspath=['./pyinstaller-hooks'],
    hooksconfig={},
    runtime_hooks=['./pyinstaller-hooks/rthook_suppress_warnings.py'],
    excludes=[
        'pytest', 'ruff', 'pyright', 'tkinter', 'matplotlib',
        'agent_framework_anthropic',
        'agent_framework_bedrock',
        'agent_framework_a2a',
        'agent_framework_ag_ui',
        'agent_framework_chatkit',
        'agent_framework_claude',
        'agent_framework_copilotstudio',
        'agent_framework_declarative',
        'agent_framework_devui',
        'agent_framework_durabletask',
        'agent_framework_foundry_local',
        'agent_framework_github_copilot',
        'agent_framework_hyperlight',
        'agent_framework_lab',
        'agent_framework_mem0',
        'agent_framework_ollama',
        'agent_framework_orchestrations',
        'agent_framework_purview',
        'agent_framework_redis',
        'agent_framework_azure_ai_search',
        'agent_framework_azure_cosmos',
        'agent_framework_azurefunctions',
    ],
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

# onedir EXE: contains only the bootloader + scripts (no binaries/datas).
exe = EXE(
    pyz,
    a.scripts,
    exclude_binaries=True,
    name='backend',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
)

# COLLECT places binaries and datas alongside the exe in dist/backend/.
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name='backend',
)
