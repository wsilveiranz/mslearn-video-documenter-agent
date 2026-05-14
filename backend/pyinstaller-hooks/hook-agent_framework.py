"""PyInstaller hook for agent_framework (Microsoft Agent Framework).

MAF uses lazy __getattr__ in namespace stubs to import from separate
implementation packages at runtime. PyInstaller cannot detect these.
We explicitly list only the packages this project uses.
"""

from PyInstaller.utils.hooks import collect_submodules

# Only include the MAF implementation packages we actually use.
# DO NOT auto-discover — the dev environment has 24+ providers installed.
hiddenimports = [
    *collect_submodules('agent_framework_foundry'),
    *collect_submodules('agent_framework_openai'),
    *collect_submodules('agent_framework_core'),
]
