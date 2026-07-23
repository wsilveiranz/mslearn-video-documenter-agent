# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for MS Learn Video Documenter backend.

Uses **onedir** mode so all DLLs (including python311.dll) live alongside
backend.exe in a permanent directory.  This avoids onefile's temp-directory
extraction, which is blocked by Windows Application Control / AppLocker
policies on many corporate machines.
"""

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# Magika ships data files (model, config, metadata) that PyInstaller won't
# discover automatically. markitdown uses magika for file-type detection.
# Collect all subdirs — both models/ and config/ are required at runtime.
magika_datas = collect_data_files('magika')

# agent_framework (>=1.x) exposes core symbols such as ``workflow`` through a
# lazy ``__getattr__`` on the package, so PyInstaller cannot statically trace
# modules like ``agent_framework._workflows._functional``. Collect every core
# internal submodule (plus the Foundry connector we use) while skipping the
# optional provider namespaces we don't ship (anthropic, ollama, bedrock, ...).
_AF_SKIP_NAMESPACES = (
    'a2a', 'ag_ui', 'amazon', 'anthropic', 'azure', 'chatkit', 'declarative',
    'devui', 'github', 'google', 'hyperlight', 'lab', 'mem0', 'microsoft',
    'ollama', 'openai', 'orchestrations', 'redis',
)
agent_framework_hidden = [
    _m
    for _m in collect_submodules('agent_framework')
    if not any(
        _m == f'agent_framework.{_ns}' or _m.startswith(f'agent_framework.{_ns}.')
        for _ns in _AF_SKIP_NAMESPACES
    )
]

a = Analysis(
    ['src/main.py'],
    pathex=['.'],
    binaries=[],
    datas=[
        ('src/prompts', 'src/prompts'),
        ('src/templates', 'src/templates'),
    ] + magika_datas,
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
        'src.services.blob_storage_service',
        'src.services.speech_service',
        'src.services.video_indexer_service',
        'azure.ai.inference',
        'azure.ai.inference.aio',
        'azure.ai.inference.models',
        'azure.ai.projects',
        'azure.ai.projects.aio',
        'azure.ai.projects.models',
        # --- Azure Blob Storage (async client, lazy imports) ---
        'azure.storage.blob',
        'azure.storage.blob.aio',
        'azure.storage.blob._shared',
        'azure.storage.blob._shared.policies',
        'azure.storage.blob._shared.policies_async',
        'azure.storage.blob._serialize',
        'azure.storage.blob._deserialize',
        'azure.storage.blob._blob_client',
        'azure.storage.blob._container_client',
        'azure.storage.blob._blob_service_client',
        'azure.storage.blob.aio._blob_client_async',
        'azure.storage.blob.aio._container_client_async',
        'azure.storage.blob.aio._blob_service_client_async',
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
        # --- MCP SDK (lazy imports in mcp_client.py) ---
        'mcp',
        'mcp.client',
        'mcp.client.streamable_http',
        'mcp.client.stdio',
        'mcp.types',
        # --- MarkItDown (lazy import in document_converter.py) ---
        'markitdown',
        'markitdown._markitdown',
        # MarkItDown converter submodules (lazy-loaded per file type)
        'markitdown.converters',
        'markitdown.converters._docx_converter',
        'markitdown.converters._pdf_converter',
        'markitdown.converters._pptx_converter',
        'markitdown.converters._html_converter',
        'markitdown.converters._xlsx_converter',
        'markitdown.converters._csv_converter',
        'markitdown.converters._plain_text_converter',
        'markitdown.converters._llm_caption',
        'markitdown.converter_utils',
        'markitdown.converter_utils.docx',
        'markitdown.converter_utils.docx.pre_process',
        'markitdown.converter_utils.docx.math',
        'markitdown.converter_utils.docx.math.omml',
        'markitdown.converter_utils.docx.math.latex_dict',
        # MarkItDown third-party dependencies (imported inside try/except)
        'mammoth',
        'pdfminer',
        'pdfminer.high_level',
        'pdfplumber',
        'pptx',
        'openpyxl',
        # Magika — file-type detection used by markitdown
        'magika',
        'magika.magika',
        'onnxruntime',
        # --- New service modules (lazy imports in routes.py / orchestrator.py) ---
        'src.services.mcp_client',
        'src.services.learn_mcp_tools',
        'src.services.workiq_mcp_tools',
        'src.services.document_converter',
    ] + agent_framework_hidden,
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
