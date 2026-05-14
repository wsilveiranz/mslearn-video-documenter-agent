"""Document-type–specific MS Learn style eval tests.

Validates that generated documents for Quickstart and How-to types conform to
MS Learn structural and formatting rules.  These are deterministic rule-based
checks (no LLM calls) that run against synthetic fixtures.
"""

from __future__ import annotations

import re

import pytest

pytestmark = [pytest.mark.eval, pytest.mark.style]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract_frontmatter_fields(content: str) -> dict[str, str]:
    match = re.match(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
    if not match:
        return {}
    fields: dict[str, str] = {}
    for line in match.group(1).splitlines():
        line = line.strip()
        if line.startswith("#") or not line:
            continue
        kv = line.split(":", 1)
        if len(kv) == 2:
            key = kv[0].strip().strip('"').strip("'")
            val = kv[1].strip().strip('"').strip("'")
            fields[key] = val
    return fields


def _h1_text(content: str) -> str | None:
    body = re.sub(r"^---\n.*?\n---\n", "", content, flags=re.DOTALL)
    m = re.search(r"^# (.+)$", body, re.MULTILINE)
    return m.group(1).strip() if m else None


def _numbered_steps_in_section(content: str, section_heading: str) -> list[str]:
    """Return ordered list items that appear under *section_heading* (H2)."""
    body = re.sub(r"^---\n.*?\n---\n", "", content, flags=re.DOTALL)
    pattern = rf"^## {re.escape(section_heading)}.*?(?=^##|\Z)"
    section_match = re.search(pattern, body, re.MULTILINE | re.DOTALL)
    if not section_match:
        return []
    section_text = section_match.group(0)
    return re.findall(r"^\d+\.", section_text, re.MULTILINE)


def _has_prerequisites_section(content: str) -> bool:
    body = re.sub(r"^---\n.*?\n---\n", "", content, flags=re.DOTALL)
    return bool(re.search(r"^## Prerequisites", body, re.MULTILINE | re.IGNORECASE))


def _h1_starts_with_gerund(h1: str, prefix: str = "") -> bool:
    verb_text = h1
    if prefix and h1.startswith(prefix):
        verb_text = h1[len(prefix):].strip()
    words = verb_text.split()
    if not words:
        return False
    non_gerund_ing = {"string", "ring", "king", "thing", "bring", "spring", "using"}
    first = words[0].rstrip(".,;:")
    return first.endswith("ing") and first.lower() not in non_gerund_ing


# ---------------------------------------------------------------------------
# Synthetic Quickstart document fixture
# ---------------------------------------------------------------------------

_QUICKSTART_DOCUMENT = """\
---
title: "Quickstart: Deploy a web app to Azure App Service"
description: "Learn how to deploy a Node.js web app to Azure App Service using the Azure CLI in under 10 minutes."
author: video-documenter
ms.author: video-documenter
ms.date: 05/09/2026
ms.topic: quickstart
ms.service: azure-app-service
ms.custom: ai-assisted
# Customer intent: As a developer, I want to deploy my web app so that it's accessible on the internet.
---

# Quickstart: Deploy a web app to Azure App Service

In this quickstart, you deploy a Node.js web app to Azure App Service using the Azure CLI.

## Prerequisites

- An Azure account with an active subscription. [Create one for free](https://azure.microsoft.com/free/).
- [Node.js](https://nodejs.org/) 18 or later
- [Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli) installed

## Sign in to Azure

1. Open a terminal.
1. Sign in to your Azure account:

```azurecli
az login
```

## Create the App Service resources

1. Create a resource group:

```azurecli
az group create --name myResourceGroup --location eastus
```

1. Create an App Service plan:

```azurecli
az appservice plan create --name myPlan --resource-group myResourceGroup --sku FREE
```

1. Create the web app:

```azurecli
az webapp create --name myUniqueApp --resource-group myResourceGroup --plan myPlan --runtime "NODE:18-lts"
```

## Deploy the app

1. Navigate to your app directory.
1. Deploy the code:

```azurecli
az webapp up --name myUniqueApp --resource-group myResourceGroup
```

## Verify the deployment

Open a browser and navigate to `https://myUniqueApp.azurewebsites.net` to see your running app.

## Clean up resources

```azurecli
az group delete --name myResourceGroup --yes
```

## Next steps

> [!div class="nextstepaction"]
> [Configure a custom domain](configure-custom-domain.md)
"""

# ---------------------------------------------------------------------------
# Synthetic How-to document fixture
# ---------------------------------------------------------------------------

_HOWTO_DOCUMENT = """\
---
title: "Configure a custom domain for Azure App Service"
description: "Learn how to map a custom DNS domain name to your Azure App Service app using the Azure portal or the Azure CLI."
author: video-documenter
ms.author: video-documenter
ms.date: 05/09/2026
ms.topic: how-to
ms.service: azure-app-service
ms.custom: ai-assisted
# Customer intent: As a developer, I want to use my own domain name so that my app has a professional URL.
---

# Configure a custom domain for Azure App Service

This article explains how to map a custom DNS domain name to your Azure App Service app.

## Prerequisites

- An Azure App Service app in the Basic tier or higher
- Access to your domain registrar's DNS settings
- [Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli) installed (optional)

## Verify domain ownership

1. Sign in to the [Azure portal](https://portal.azure.com).
1. Navigate to your App Service app.
1. Select **Custom domains** from the left menu.
1. Select **Add custom domain**.
1. Enter your domain name and select **Validate**.
1. Copy the TXT record value displayed.

## Add the DNS record

1. Sign in to your domain registrar.
1. Open the DNS management page for your domain.
1. Add a TXT record with the value copied from the Azure portal.
1. Save the DNS changes.

## Map the custom domain

1. Return to the Azure portal custom domains page.
1. Select **Add custom domain** again.
1. Enter your domain name and select **Add custom domain**.

## Verify the configuration

Browse to your custom domain to confirm it resolves to your app.

## Next steps

> [!div class="nextstepaction"]
> [Secure a custom domain with TLS](configure-ssl-certificate.md)
"""

# ---------------------------------------------------------------------------
# Quickstart eval tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_quickstart_h1_prefix():
    """Quickstart H1 must start with 'Quickstart: '."""
    h1 = _h1_text(_QUICKSTART_DOCUMENT)
    assert h1 is not None, "Document must have an H1 heading"
    assert h1.startswith("Quickstart: "), (
        f"Quickstart H1 must start with 'Quickstart: ', got: '{h1}'"
    )


@pytest.mark.asyncio
async def test_quickstart_ms_topic():
    """Quickstart frontmatter must declare ms.topic: quickstart."""
    fields = _extract_frontmatter_fields(_QUICKSTART_DOCUMENT)
    topic = fields.get("ms.topic") or fields.get("ms_topic", "")
    assert topic == "quickstart", (
        f"Expected ms.topic: quickstart, got: '{topic}'"
    )


@pytest.mark.asyncio
async def test_quickstart_has_prerequisites():
    """Quickstart must include a Prerequisites section."""
    assert _has_prerequisites_section(_QUICKSTART_DOCUMENT), (
        "Quickstart document must have a '## Prerequisites' section"
    )


@pytest.mark.asyncio
async def test_quickstart_procedure_steps_le_12():
    """No numbered procedure in a Quickstart should exceed 12 steps."""
    body = re.sub(r"^---\n.*?\n---\n", "", _QUICKSTART_DOCUMENT, flags=re.DOTALL)
    # Find every H2 section and count its ordered-list items.
    sections = re.findall(r"^## .+$", body, re.MULTILINE)
    for heading in sections:
        heading_text = heading.lstrip("# ").strip()
        steps = _numbered_steps_in_section(_QUICKSTART_DOCUMENT, heading_text)
        assert len(steps) <= 12, (
            f"Section '{heading_text}' has {len(steps)} steps — MS Learn limit is 12"
        )


@pytest.mark.asyncio
async def test_quickstart_h1_no_gerund():
    """Quickstart H1 verb must not be a gerund."""
    h1 = _h1_text(_QUICKSTART_DOCUMENT)
    assert h1 is not None, "Document must have an H1 heading"
    assert not _h1_starts_with_gerund(h1, prefix="Quickstart: "), (
        f"Quickstart H1 verb must be imperative (not gerund), got: '{h1}'"
    )


@pytest.mark.asyncio
async def test_quickstart_style_compliance():
    """Quickstart passes rule-based MS Learn style graders with no errors."""
    from tests.eval.graders import run_all_style_checks

    report = run_all_style_checks(_QUICKSTART_DOCUMENT, doc_type="quickstart")
    assert report.passed, (
        f"Quickstart style check failed with {len(report.errors)} errors: "
        + "; ".join(f.message for f in report.errors)
    )


# ---------------------------------------------------------------------------
# How-to eval tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_howto_h1_no_prefix():
    """How-to H1 must NOT start with 'How-to: ' or 'Tutorial: ' prefix."""
    h1 = _h1_text(_HOWTO_DOCUMENT)
    assert h1 is not None, "Document must have an H1 heading"
    assert not h1.startswith("How-to: "), (
        f"How-to H1 must not have a 'How-to: ' prefix, got: '{h1}'"
    )
    assert not h1.startswith("Tutorial: "), (
        f"How-to H1 must not have a 'Tutorial: ' prefix, got: '{h1}'"
    )
    assert not h1.startswith("Quickstart: "), (
        f"How-to H1 must not have a 'Quickstart: ' prefix, got: '{h1}'"
    )


@pytest.mark.asyncio
async def test_howto_h1_verb_noun_format():
    """How-to H1 must start with an imperative verb (verb-noun format)."""
    h1 = _h1_text(_HOWTO_DOCUMENT)
    assert h1 is not None, "Document must have an H1 heading"
    # H1 must begin with a capital letter (imperative verb)
    assert h1[0].isupper(), f"How-to H1 must start with a capital letter: '{h1}'"
    # Must not be a question ("What is")
    assert not h1.startswith("What is"), (
        f"How-to H1 must be verb-noun format, not a question: '{h1}'"
    )


@pytest.mark.asyncio
async def test_howto_ms_topic():
    """How-to frontmatter must declare ms.topic: how-to."""
    fields = _extract_frontmatter_fields(_HOWTO_DOCUMENT)
    topic = fields.get("ms.topic") or fields.get("ms_topic", "")
    assert topic == "how-to", (
        f"Expected ms.topic: how-to, got: '{topic}'"
    )


@pytest.mark.asyncio
async def test_howto_has_prerequisites():
    """How-to must include a Prerequisites section."""
    assert _has_prerequisites_section(_HOWTO_DOCUMENT), (
        "How-to document must have a '## Prerequisites' section"
    )


@pytest.mark.asyncio
async def test_howto_h1_no_gerund():
    """How-to H1 verb must not be a gerund."""
    h1 = _h1_text(_HOWTO_DOCUMENT)
    assert h1 is not None, "Document must have an H1 heading"
    # For how-to there is no prefix to strip
    assert not _h1_starts_with_gerund(h1), (
        f"How-to H1 verb must be imperative (not gerund), got: '{h1}'"
    )


@pytest.mark.asyncio
async def test_howto_task_focused_structure():
    """How-to must have task-focused H2 sections (action verbs or clear task names)."""
    body = re.sub(r"^---\n.*?\n---\n", "", _HOWTO_DOCUMENT, flags=re.DOTALL)
    h2_headings = re.findall(r"^## (.+)$", body, re.MULTILINE)
    assert len(h2_headings) >= 2, (
        f"How-to must have at least 2 H2 sections, found: {len(h2_headings)}"
    )
    # H2s must not be numbered
    for heading in h2_headings:
        assert not re.match(r"^\d+[\.\):\s]", heading), (
            f"How-to H2 sections must not be numbered: '## {heading}'"
        )


@pytest.mark.asyncio
async def test_howto_style_compliance():
    """How-to passes rule-based MS Learn style graders with no errors."""
    from tests.eval.graders import run_all_style_checks

    report = run_all_style_checks(_HOWTO_DOCUMENT, doc_type="how-to")
    assert report.passed, (
        f"How-to style check failed with {len(report.errors)} errors: "
        + "; ".join(f.message for f in report.errors)
    )
