"""Runtime hook: suppress ExperimentalWarning from agent_framework.

These warnings appear on stderr from frozen abc imports and confuse users
when emitted from a bundled executable.
"""

import warnings

warnings.filterwarnings('ignore', category=FutureWarning, module=r'.*agent_framework.*')
warnings.filterwarnings('ignore', message=r'.*ExperimentalWarning.*')
warnings.filterwarnings('ignore', message=r'.*experimental.*', module=r'.*abc.*')
