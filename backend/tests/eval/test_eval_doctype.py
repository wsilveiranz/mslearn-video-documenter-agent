"""Document-type–specific MS Learn style eval tests.

Validates that generated documents for Quickstart, How-to, Overview, and Concept types
conform to MS Learn structural and formatting rules. These are deterministic rule-based
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
    non_gerund_ing = {"string", "ring", "king", "thing", "bring", "spring"}
    first = words[0].rstrip(".,;:")
    return first.endswith("ing") and first.lower() not in non_gerund_ing


def _has_section(content: str, heading: str) -> bool:
    """Check if document has an H2 section with the given heading (case-insensitive)."""
    body = re.sub(r"^---\n.*?\n---\n", "", content, flags=re.DOTALL)
    pattern = rf"^## {re.escape(heading)}"
    return bool(re.search(pattern, body, re.MULTILINE | re.IGNORECASE))


def _has_numbered_procedures(content: str) -> bool:
    """Check if document contains any numbered lists (numbered procedures)."""
    body = re.sub(r"^---\n.*?\n---\n", "", content, flags=re.DOTALL)
    return bool(re.search(r"^\d+\.", body, re.MULTILINE))


def _count_steps_per_section(content: str) -> int:
    """Return the maximum number of steps in any procedure section."""
    body = re.sub(r"^---\n.*?\n---\n", "", content, flags=re.DOTALL)
    sections = re.findall(r"^## .+$", body, re.MULTILINE)
    max_steps = 0
    for heading in sections:
        heading_text = heading.lstrip("# ").strip()
        steps = _numbered_steps_in_section(content, heading_text)
        max_steps = max(max_steps, len(steps))
    return max_steps


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
# Synthetic Overview document fixture
# ---------------------------------------------------------------------------

_OVERVIEW_DOCUMENT = """\
---
title: "What is Azure Cosmos DB?"
description: "Explore Azure Cosmos DB, a globally distributed NoSQL database service with guaranteed performance, availability, and scalability."
author: video-documenter
ms.author: video-documenter
ms.date: 05/09/2026
ms.topic: overview
ms.service: azure-cosmos-db
ms.custom: ai-assisted
# Customer intent: As a database architect, I want to understand Azure Cosmos DB's capabilities so that I can choose the right database for my application.
---

# What is Azure Cosmos DB?

Azure Cosmos DB is a fully managed NoSQL database service that delivers single-digit millisecond response times and automatic scaling. It enables you to build highly responsive applications with guaranteed availability and throughput.

:::image type="content" source="./media/cosmos-db-overview.png" alt-text="Azure Cosmos DB architecture diagram showing global distribution and multi-model support":::

## Key features

| Feature | Description |
|---------|-------------|
| Global distribution | Replicate your data across any Azure region with automatic failover |
| Multiple data models | Support for document, key-value, graph, and time-series data |
| Single-digit millisecond latency | Guaranteed response times for read and write operations |
| Automatic scaling | Scale throughput and storage on-demand with no manual intervention |
| Multiple consistency levels | Choose from five well-defined consistency levels for your use case |

## Document model

Azure Cosmos DB's document database model is ideal for content-rich applications. Store and query JSON documents with powerful SQL queries.

## Multi-master replication

With multi-master replication, you can write to any region and enjoy automatic conflict resolution. Your data is always available, even during regional outages.

## Requirements

- An Azure subscription. [Create one for free](https://azure.microsoft.com/free/).
- Familiarity with NoSQL database concepts
- Basic understanding of JSON

## Pricing

For pricing information, see [Azure Cosmos DB pricing](https://azure.microsoft.com/pricing/details/cosmos-db/).

## Next steps

> [!div class="nextstepaction"]
> [Quickstart: Create an Azure Cosmos DB account](quickstart-create-account.md)

- [Key concepts](concepts-keys-values.md)
- [Tutorial: Build a web app with Cosmos DB](tutorial-build-web-app.md)
"""

# ---------------------------------------------------------------------------
# Synthetic Concept document fixture
# ---------------------------------------------------------------------------

_CONCEPT_DOCUMENT = """\
---
title: "What is eventual consistency?"
description: "Learn about eventual consistency, a key concept for distributed databases that balances availability and correctness."
author: video-documenter
ms.author: video-documenter
ms.date: 05/09/2026
ms.topic: concept-article
ms.service: azure-cosmos-db
ms.custom: ai-assisted
# Customer intent: As a developer, I want to understand eventual consistency so that I can design correct distributed applications.
---

# What is eventual consistency?

Eventual consistency is a consistency model used in distributed systems where data replicas may temporarily diverge but eventually converge to the same state. It helps you balance availability, latency, and correctness.

## Key concepts

### Strong consistency

Strong consistency guarantees that all reads return the most recent write. This provides correctness but at the cost of higher latency and reduced availability during network partitions.

### Weak consistency

Weak consistency allows reads to return stale data. This maximizes availability and minimizes latency but increases the burden on the application to handle inconsistent state.

### Eventual consistency

Eventual consistency sits between strong and weak consistency. If no new writes occur to an item, all replicas eventually converge to identical values.

## How eventual consistency works

:::image type="content" source="./media/eventual-consistency-flow.png" alt-text="Diagram showing how eventual consistency propagates updates across replicas over time":::

When a write operation completes on one replica, the system begins propagating the update to other replicas asynchronously. Reads from any replica may temporarily see different values, but the system guarantees that all replicas will eventually show the same data.

## When to use eventual consistency

Use eventual consistency when you need to:

- Maximize availability across multiple regions
- Minimize read latency for your application
- Tolerate temporary inconsistencies between replicas
- Build cost-effective systems that scale globally

## Limitations

- Reads may return stale data temporarily
- Handling conflicts between concurrent writes requires application logic
- Not suitable for critical financial transactions requiring immediate consistency

## Next steps

- [Quickstart: Get started with Azure Cosmos DB](quickstart-create-account.md)
- [Tutorial: Build a globally distributed app](tutorial-global-app.md)
"""

# ---------------------------------------------------------------------------
# Synthetic additional How-to document fixture
# ---------------------------------------------------------------------------

_HOWTO_ADDITIONAL_DOCUMENT = """\
---
title: "Scale an Azure Cosmos DB container"
description: "Learn how to update the provisioned throughput for an Azure Cosmos DB container using the Azure portal or Azure CLI."
author: video-documenter
ms.author: video-documenter
ms.date: 05/09/2026
ms.topic: how-to
ms.service: azure-cosmos-db
ms.custom: ai-assisted
# Customer intent: As a database administrator, I want to scale my Cosmos DB container so that my application can handle more traffic.
---

# Scale an Azure Cosmos DB container

This article shows you how to adjust the provisioned throughput for a container in Azure Cosmos DB to meet your application's performance needs.

## Prerequisites

- An existing Azure Cosmos DB account and database
- Container with provisioned throughput
- Owner or Contributor permissions on the Azure subscription

## Update throughput via the Azure portal

1. Sign in to the [Azure portal](https://portal.azure.com).
1. Navigate to your Azure Cosmos DB account.
1. Select **Data Explorer** from the left menu.
1. Expand your database and locate your container.
1. Select the container to view its properties.
1. Click **Settings** to open the throughput configuration page.
1. Enter the new throughput value (minimum 400 RU/s, maximum depends on your account).
1. Select **Save** to apply the changes.

## Update throughput via Azure CLI

1. Open a terminal or command prompt.
1. Run the Azure CLI command to update the throughput:

```azurecli
az cosmosdb sql container throughput update --account-name myCosmosAccount --database-name myDatabase --name myContainer --resource-group myResourceGroup --throughput 5000
```

1. Verify the update was applied successfully.

## Monitor scaling progress

After you update the throughput, Azure Cosmos DB begins scaling your container. You can monitor the progress in the Azure portal by:

1. Navigating to your container's **Metrics** page
1. Observing the **Provisioned Throughput** chart
1. Waiting for the scale operation to complete (typically 1-5 minutes)

## Next steps

- [How-to: Set autoscale throughput](autoscale-throughput.md)
- [Concept: Request units and throughput](concepts-request-units.md)
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


# ---------------------------------------------------------------------------
# Overview eval tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_overview_h1_format():
    """Overview H1 must start with 'What is'."""
    h1 = _h1_text(_OVERVIEW_DOCUMENT)
    assert h1 is not None, "Document must have an H1 heading"
    assert h1.startswith("What is"), (
        f"Overview H1 must start with 'What is', got: '{h1}'"
    )


@pytest.mark.asyncio
async def test_overview_ms_topic():
    """Overview frontmatter must declare ms.topic: overview."""
    fields = _extract_frontmatter_fields(_OVERVIEW_DOCUMENT)
    topic = fields.get("ms.topic") or fields.get("ms_topic", "")
    assert topic == "overview", (
        f"Expected ms.topic: overview, got: '{topic}'"
    )


@pytest.mark.asyncio
async def test_overview_has_key_features():
    """Overview must include a Key features section."""
    assert _has_section(_OVERVIEW_DOCUMENT, "Key features"), (
        "Overview document must have a '## Key features' section"
    )


@pytest.mark.asyncio
async def test_overview_has_requirements():
    """Overview must include a Requirements section."""
    assert _has_section(_OVERVIEW_DOCUMENT, "Requirements"), (
        "Overview document must have a '## Requirements' section"
    )


@pytest.mark.asyncio
async def test_overview_has_next_steps():
    """Overview must include a Next steps section."""
    assert _has_section(_OVERVIEW_DOCUMENT, "Next steps"), (
        "Overview document must have a '## Next steps' section"
    )


@pytest.mark.asyncio
async def test_overview_no_numbered_procedures():
    """Overview must not have numbered procedures (no step-by-step instructions)."""
    assert not _has_numbered_procedures(_OVERVIEW_DOCUMENT), (
        "Overview document must not contain numbered procedures (1. 2. 3.)"
    )


@pytest.mark.asyncio
async def test_overview_style_compliance():
    """Overview passes rule-based MS Learn style graders with no errors."""
    from tests.eval.graders import run_all_style_checks

    report = run_all_style_checks(_OVERVIEW_DOCUMENT, doc_type="overview")
    assert report.passed, (
        f"Overview style check failed with {len(report.errors)} errors: "
        + "; ".join(f.message for f in report.errors)
    )


# ---------------------------------------------------------------------------
# Concept eval tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_concept_h1_format():
    """Concept H1 must start with 'What is'."""
    h1 = _h1_text(_CONCEPT_DOCUMENT)
    assert h1 is not None, "Document must have an H1 heading"
    assert h1.startswith("What is"), (
        f"Concept H1 must start with 'What is', got: '{h1}'"
    )


@pytest.mark.asyncio
async def test_concept_ms_topic():
    """Concept frontmatter must declare ms.topic: concept-article."""
    fields = _extract_frontmatter_fields(_CONCEPT_DOCUMENT)
    topic = fields.get("ms.topic") or fields.get("ms_topic", "")
    assert topic == "concept-article", (
        f"Expected ms.topic: concept-article, got: '{topic}'"
    )


@pytest.mark.asyncio
async def test_concept_has_key_concepts():
    """Concept must include a Key concepts section."""
    assert _has_section(_CONCEPT_DOCUMENT, "Key concepts"), (
        "Concept document must have a '## Key concepts' section"
    )


@pytest.mark.asyncio
async def test_concept_has_next_steps():
    """Concept must include a Next steps section."""
    assert _has_section(_CONCEPT_DOCUMENT, "Next steps"), (
        "Concept document must have a '## Next steps' section"
    )


@pytest.mark.asyncio
async def test_concept_no_numbered_procedures():
    """Concept must not have numbered procedures (explanatory content only)."""
    assert not _has_numbered_procedures(_CONCEPT_DOCUMENT), (
        "Concept document must not contain numbered procedures (1. 2. 3.)"
    )


@pytest.mark.asyncio
async def test_concept_style_compliance():
    """Concept passes rule-based MS Learn style graders with no errors."""
    from tests.eval.graders import run_all_style_checks

    report = run_all_style_checks(_CONCEPT_DOCUMENT, doc_type="concept-article")
    assert report.passed, (
        f"Concept style check failed with {len(report.errors)} errors: "
        + "; ".join(f.message for f in report.errors)
    )


# ---------------------------------------------------------------------------
# How-to additional eval tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_howto_additional_h1_no_prefix():
    """How-to H1 must NOT start with 'How-to: ' or 'Tutorial: ' prefix."""
    h1 = _h1_text(_HOWTO_ADDITIONAL_DOCUMENT)
    assert h1 is not None, "Document must have an H1 heading"
    assert not h1.startswith("How-to: "), (
        f"How-to H1 must not have a 'How-to: ' prefix, got: '{h1}'"
    )
    assert not h1.startswith("Tutorial: "), (
        f"How-to H1 must not have a 'Tutorial: ' prefix, got: '{h1}'"
    )


@pytest.mark.asyncio
async def test_howto_additional_h1_no_gerund():
    """How-to H1 verb must not be a gerund."""
    h1 = _h1_text(_HOWTO_ADDITIONAL_DOCUMENT)
    assert h1 is not None, "Document must have an H1 heading"
    assert not _h1_starts_with_gerund(h1), (
        f"How-to H1 verb must be imperative (not gerund), got: '{h1}'"
    )


@pytest.mark.asyncio
async def test_howto_additional_ms_topic():
    """How-to frontmatter must declare ms.topic: how-to."""
    fields = _extract_frontmatter_fields(_HOWTO_ADDITIONAL_DOCUMENT)
    topic = fields.get("ms.topic") or fields.get("ms_topic", "")
    assert topic == "how-to", (
        f"Expected ms.topic: how-to, got: '{topic}'"
    )


@pytest.mark.asyncio
async def test_howto_additional_has_prerequisites():
    """How-to must include a Prerequisites section."""
    assert _has_prerequisites_section(_HOWTO_ADDITIONAL_DOCUMENT), (
        "How-to document must have a '## Prerequisites' section"
    )


@pytest.mark.asyncio
async def test_howto_additional_max_steps():
    """No procedure section in a How-to should exceed 12 steps."""
    max_steps = _count_steps_per_section(_HOWTO_ADDITIONAL_DOCUMENT)
    assert max_steps <= 12, (
        f"How-to has a section with {max_steps} steps — MS Learn limit is 12"
    )


@pytest.mark.asyncio
async def test_howto_additional_style_compliance():
    """How-to passes rule-based MS Learn style graders with no errors."""
    from tests.eval.graders import run_all_style_checks

    report = run_all_style_checks(_HOWTO_ADDITIONAL_DOCUMENT, doc_type="how-to")
    assert report.passed, (
        f"How-to style check failed with {len(report.errors)} errors: "
        + "; ".join(f.message for f in report.errors)
    )
