"""PyInstaller hook for agent_framework_foundry.

Ensures all private submodules (_agent, _chat_client, _embedding_client,
_foundry_evals, _memory_provider, _oauth_helpers, _tools) are collected.
"""

from PyInstaller.utils.hooks import collect_submodules

hiddenimports = collect_submodules('agent_framework_foundry')
