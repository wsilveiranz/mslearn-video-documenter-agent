"""PyInstaller hook for agent_framework_openai.

Ensures all private submodules (_chat_client, _chat_completion_client,
_embedding_client, _exceptions, _shared) are collected.
"""

from PyInstaller.utils.hooks import collect_submodules

hiddenimports = collect_submodules('agent_framework_openai')
