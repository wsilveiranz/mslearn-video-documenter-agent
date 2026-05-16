"""Unit tests for the rule-based style graders.

Tests graders against known-good and known-bad content to ensure
they correctly detect MS Learn style violations.
"""

from __future__ import annotations

import pytest

from tests.eval.graders import (
    StyleFinding,
    check_contractions,
    check_doc_type_h1,
    check_frontmatter,
    check_grounding,
    check_headings,
    check_markdown_extensions,
    check_serial_comma,
    check_step_count,
    check_structure,
    check_terminology,
    run_all_style_checks,
)

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Frontmatter
# ---------------------------------------------------------------------------

_GOOD_FRONTMATTER = '''---
title: "Tutorial: Clone a repository in Azure DevOps"
description: "Learn how to clone an Azure DevOps Git repository to your local machine using the portal and command line."
ms.topic: tutorial
ms.custom: ai-assisted
ms.date: 05/09/2026
author: test-author
ms.author: test-alias
---

# Tutorial: Clone a repository in Azure DevOps
'''

_BAD_FRONTMATTER = '''---
title: "Short"
ms.date: 2026-05-09
---

# Some heading
'''


def test_good_frontmatter():
    findings = check_frontmatter(_GOOD_FRONTMATTER, "tutorial")
    errors = [f for f in findings if f.severity == "error"]
    assert len(errors) == 0


def test_missing_frontmatter():
    findings = check_frontmatter("# No frontmatter here\n\nJust content.")
    errors = [f for f in findings if f.severity == "error"]
    assert any(f.rule == "frontmatter-present" for f in errors)


def test_bad_frontmatter_fields():
    findings = check_frontmatter(_BAD_FRONTMATTER, "tutorial")
    rules = {f.rule for f in findings}
    assert "frontmatter-title-length" in rules  # "Short" is <43 chars
    assert "frontmatter-date-format" in rules  # YYYY-MM-DD not MM/DD/YYYY


def test_missing_description():
    findings = check_frontmatter(_BAD_FRONTMATTER, "tutorial")
    rules = {f.rule for f in findings}
    assert "frontmatter-description" in rules


# ---------------------------------------------------------------------------
# Headings
# ---------------------------------------------------------------------------

def test_sentence_case_headings():
    content = '''---
title: "test"
---

# Tutorial: Deploy a web app

## Create a resource group

## This Is Title Case
'''
    findings = check_headings(content, "tutorial")
    case_findings = [f for f in findings if f.rule == "heading-sentence-case"]
    assert len(case_findings) >= 1  # "This Is Title Case"
    assert "This Is Title Case" in case_findings[0].message


def test_h1_gerund():
    content = '''---
title: "test"
---

# Tutorial: Deploying your application
'''
    findings = check_headings(content, "tutorial")
    gerund_findings = [f for f in findings if f.rule == "heading-h1-no-gerund"]
    assert len(gerund_findings) == 1


def test_numbered_h2():
    content = '''---
title: "test"
---

# Tutorial: Deploy a web app

## 1. First step

## Step 2: Second step
'''
    findings = check_headings(content, "tutorial")
    numbered = [f for f in findings if f.rule == "heading-h2-no-numbers"]
    assert len(numbered) == 2


# ---------------------------------------------------------------------------
# Contractions
# ---------------------------------------------------------------------------

def test_missing_contractions():
    content = '''---
title: "test"
---

# Title

You will need to install Git. It is important that you do not skip this step.
If you can not connect, you are missing the prerequisite.
'''
    findings = check_contractions(content)
    rules_matched = {f.suggestion for f in findings}
    assert "you'll" in rules_matched
    assert "it's" in rules_matched
    assert "don't" in rules_matched


def test_contractions_skip_code_blocks():
    content = '''---
title: "test"
---

# Title

```bash
echo "It is fine in code blocks"
```
'''
    findings = check_contractions(content)
    # Should not flag content inside code blocks
    assert len(findings) == 0


# ---------------------------------------------------------------------------
# Terminology
# ---------------------------------------------------------------------------

def test_click_terminology():
    content = '''---
title: "test"
---

# Title

Click the **Save** button. Then click on **Deploy**.
'''
    findings = check_terminology(content)
    click_findings = [f for f in findings if f.rule == "term-click"]
    assert len(click_findings) == 2


def test_login_terminology():
    content = '''---
title: "test"
---

# Title

Log in to the Azure portal. After you login, navigate to your resource.
'''
    findings = check_terminology(content)
    login_findings = [f for f in findings if f.rule == "term-login"]
    assert len(login_findings) >= 1


def test_wordy_phrases():
    content = '''---
title: "test"
---

# Title

In order to deploy, you need to utilize the CLI.
'''
    findings = check_terminology(content)
    wordy = [f for f in findings if f.rule == "term-wordy"]
    assert len(wordy) >= 2  # "in order to", "utilize"


# ---------------------------------------------------------------------------
# Markdown extensions
# ---------------------------------------------------------------------------

def test_standard_markdown_images():
    content = '''---
title: "test"
---

# Title

![screenshot](./media/step1.png)
'''
    findings = check_markdown_extensions(content)
    assert any(f.rule == "md-image-syntax" for f in findings)


def test_code_block_no_language():
    content = '''---
title: "test"
---

# Title

```
echo "no language tag"
```
'''
    findings = check_markdown_extensions(content)
    assert any(f.rule == "md-code-lang" for f in findings)


def test_good_image_syntax():
    content = '''---
title: "test"
---

# Title

:::image type="content" source="./media/step1.png" alt-text="Azure portal dashboard showing resource groups":::
'''
    findings = check_markdown_extensions(content)
    assert not any(f.rule == "md-image-syntax" for f in findings)


def test_generic_alt_text():
    content = '''---
title: "test"
---

# Title

:::image type="content" source="./media/step1.png" alt-text="Screenshot of the portal":::
'''
    findings = check_markdown_extensions(content)
    assert any(f.rule == "md-alt-generic" for f in findings)


# ---------------------------------------------------------------------------
# Structure
# ---------------------------------------------------------------------------

def test_missing_prerequisites():
    content = '''---
title: "test"
---

# Tutorial: Deploy a web app

Some intro text.

## Deploy the app

Steps here.
'''
    findings = check_structure(content, "tutorial")
    assert any(f.rule == "structure-prerequisites" for f in findings)


def test_missing_next_steps():
    content = '''---
title: "test"
---

# Tutorial: Deploy a web app

## Prerequisites

- Something

## Deploy

Steps.
'''
    findings = check_structure(content, "tutorial")
    assert any(f.rule == "structure-next-steps" for f in findings)


def test_complete_tutorial_structure():
    content = '''---
title: "test"
---

# Tutorial: Deploy a web app

In this tutorial, you learn how to deploy.

> [!div class="checklist"]
> - Deploy a web app
> - Configure settings

## Prerequisites

- Azure subscription

## Deploy the app

1. Step one.

## Clean up resources

Delete the resource group.

## Next steps

> [!div class="nextstepaction"]
> [Next article](next.md)
'''
    findings = check_structure(content, "tutorial")
    structural_findings = [f for f in findings if f.category == "structure"]
    # Should have no warnings or errors
    structural_warnings = [f for f in structural_findings if f.severity in ("warning", "error")]
    assert len(structural_warnings) == 0


# ---------------------------------------------------------------------------
# Grounding
# ---------------------------------------------------------------------------

def test_grounding_good_coverage():
    transcript = [
        "Welcome to this tutorial on cloning a repository in Azure DevOps.",
        "First navigate to the Azure DevOps portal and select your project.",
        "Click on the Repos section in the left navigation.",
    ]
    content = '''---
title: "test"
---

# Tutorial: Clone a repository in Azure DevOps

Navigate to the Azure DevOps portal and select your project.
In the left navigation, select **Repos**.
Clone the repository to your local machine.
'''
    findings = check_grounding(content, transcript, min_coverage=0.3)
    low_coverage = [f for f in findings if f.rule == "grounding-low-coverage"]
    assert len(low_coverage) == 0, "Should have adequate coverage"


def test_grounding_low_coverage():
    transcript = [
        "Welcome to deploying Kubernetes clusters on Azure.",
        "We'll use kubectl to manage pods and services.",
    ]
    content = '''---
title: "test"
---

# Tutorial: Create a web app

This tutorial shows you how to create a static website.
Upload your HTML files to the storage account.
'''
    findings = check_grounding(content, transcript, min_coverage=0.3)
    low_coverage = [f for f in findings if f.rule == "grounding-low-coverage"]
    assert len(low_coverage) > 0, "Should detect low coverage (mismatched content)"


def test_grounding_no_transcript():
    findings = check_grounding("Some content", [], min_coverage=0.3)
    assert any(f.rule == "grounding-no-transcript" for f in findings)


# ---------------------------------------------------------------------------
# Step count
# ---------------------------------------------------------------------------

def test_step_count_under_limit():
    """Test that 5 steps in a section produces no finding."""
    content = '''---
title: "Test article"
description: "Test description for testing purposes"
ms.topic: tutorial
ms.custom: ai-assisted
ms.date: 05/09/2026
---

# Tutorial: Test article

## Deploy the app

1. First step
2. Second step
3. Third step
4. Fourth step
5. Fifth step
'''
    findings = check_step_count(content)
    step_findings = [f for f in findings if f.rule == "structure-step-count"]
    assert len(step_findings) == 0


def test_step_count_over_limit():
    """Test that 15 steps in a section produces a finding."""
    content = '''---
title: "Test article"
description: "Test description for testing purposes"
ms.topic: tutorial
ms.custom: ai-assisted
ms.date: 05/09/2026
---

# Tutorial: Test article

## Deploy the app

1. First step
2. Second step
3. Third step
4. Fourth step
5. Fifth step
6. Sixth step
7. Seventh step
8. Eighth step
9. Ninth step
10. Tenth step
11. Eleventh step
12. Twelfth step
13. Thirteenth step
14. Fourteenth step
15. Fifteenth step
'''
    findings = check_step_count(content)
    step_findings = [f for f in findings if f.rule == "structure-step-count"]
    assert len(step_findings) >= 1
    assert any("15 steps" in f.message for f in step_findings)


# ---------------------------------------------------------------------------
# Doc type H1
# ---------------------------------------------------------------------------

def test_doc_type_h1_quickstart_correct():
    """Test that 'Quickstart: Deploy...' matches quickstart format."""
    content = '''---
title: "Quickstart: Deploy a web app"
description: "This quickstart shows you how to deploy a web application"
ms.topic: quickstart
ms.custom: ai-assisted
ms.date: 05/09/2026
---

# Quickstart: Deploy a web app
'''
    findings = check_doc_type_h1(content, "quickstart")
    doctype_findings = [f for f in findings if f.rule == "heading-h1-doctype"]
    assert len(doctype_findings) == 0


def test_doc_type_h1_quickstart_wrong():
    """Test that 'How to deploy...' doesn't match quickstart format."""
    content = '''---
title: "How to deploy a web app"
description: "This quickstart shows you how to deploy a web application"
ms.topic: quickstart
ms.custom: ai-assisted
ms.date: 05/09/2026
---

# How to deploy a web app
'''
    findings = check_doc_type_h1(content, "quickstart")
    doctype_findings = [f for f in findings if f.rule == "heading-h1-doctype"]
    assert len(doctype_findings) >= 1
    assert any("quickstart" in f.message.lower() for f in doctype_findings)


def test_doc_type_h1_tutorial_correct():
    """Test that 'Tutorial: Clone...' matches tutorial format."""
    content = '''---
title: "Tutorial: Clone a repository"
description: "In this tutorial, you learn how to clone a repository"
ms.topic: tutorial
ms.custom: ai-assisted
ms.date: 05/09/2026
---

# Tutorial: Clone a repository
'''
    findings = check_doc_type_h1(content, "tutorial")
    doctype_findings = [f for f in findings if f.rule == "heading-h1-doctype"]
    assert len(doctype_findings) == 0


def test_doc_type_h1_howto_correct():
    """Test that 'Configure logging' matches how-to format (no prefix)."""
    content = '''---
title: "Configure logging"
description: "Learn how to configure logging for your application"
ms.topic: how-to
ms.custom: ai-assisted
ms.date: 05/09/2026
---

# Configure logging
'''
    findings = check_doc_type_h1(content, "how-to")
    doctype_findings = [f for f in findings if f.rule == "heading-h1-doctype"]
    assert len(doctype_findings) == 0


def test_doc_type_h1_howto_wrong_prefix():
    """Test that 'How-to: Configure...' doesn't match how-to format."""
    content = '''---
title: "How-to: Configure logging"
description: "Learn how to configure logging for your application"
ms.topic: how-to
ms.custom: ai-assisted
ms.date: 05/09/2026
---

# How-to: Configure logging
'''
    findings = check_doc_type_h1(content, "how-to")
    doctype_findings = [f for f in findings if f.rule == "heading-h1-doctype"]
    assert len(doctype_findings) >= 1


def test_doc_type_h1_concept_correct():
    """Test that 'What is Azure Functions?' matches concept format."""
    content = '''---
title: "What is Azure Functions?"
description: "Learn about Azure Functions serverless computing"
ms.topic: concept-article
ms.custom: ai-assisted
ms.date: 05/09/2026
---

# What is Azure Functions?
'''
    findings = check_doc_type_h1(content, "concept")
    doctype_findings = [f for f in findings if f.rule == "heading-h1-doctype"]
    assert len(doctype_findings) == 0


def test_doc_type_h1_overview_correct():
    """Test that 'What is Azure?' matches overview format."""
    content = '''---
title: "What is Microsoft Azure?"
description: "Microsoft Azure cloud platform overview"
ms.topic: overview
ms.custom: ai-assisted
ms.date: 05/09/2026
---

# What is Microsoft Azure?
'''
    findings = check_doc_type_h1(content, "overview")
    doctype_findings = [f for f in findings if f.rule == "heading-h1-doctype"]
    assert len(doctype_findings) == 0


# ---------------------------------------------------------------------------
# Structure doc-type-specific sections
# ---------------------------------------------------------------------------

def test_structure_overview_sections():
    """Test that overview without 'Key features' produces a finding."""
    content = '''---
title: "What is Azure?"
description: "Azure overview"
ms.topic: overview
ms.custom: ai-assisted
ms.date: 05/09/2026
---

# What is Azure?

## Next steps

More information.
'''
    findings = check_structure(content, "overview")
    feature_findings = [f for f in findings if f.rule == "structure-overview-features"]
    assert len(feature_findings) >= 1


def test_structure_overview_requirements():
    """Test that overview without 'Requirements' produces a finding."""
    content = '''---
title: "What is Azure?"
description: "Azure overview"
ms.topic: overview
ms.custom: ai-assisted
ms.date: 05/09/2026
---

# What is Azure?

## Key features

Cool features here.

## Next steps

More information.
'''
    findings = check_structure(content, "overview")
    req_findings = [f for f in findings if f.rule == "structure-overview-requirements"]
    assert len(req_findings) >= 1


def test_structure_overview_complete():
    """Test that complete overview has no structural findings."""
    content = '''---
title: "What is Azure?"
description: "Azure platform with key features and requirements"
ms.topic: overview
ms.custom: ai-assisted
ms.date: 05/09/2026
---

# What is Azure?

## Key features

Cool features here.

## Requirements

Azure subscription.

## Next steps

More information.
'''
    findings = check_structure(content, "overview")
    structural_findings = [f for f in findings if f.category == "structure"]
    critical = [f for f in structural_findings if f.rule in (
        "structure-overview-features",
        "structure-overview-requirements"
    )]
    assert len(critical) == 0


def test_structure_concept_sections():
    """Test that concept without 'Key concepts' produces a finding."""
    content = '''---
title: "What is cloud computing?"
description: "Learn about cloud computing concepts"
ms.topic: concept-article
ms.custom: ai-assisted
ms.date: 05/09/2026
---

# What is cloud computing?

Cloud computing is...

## Next steps

More info.
'''
    findings = check_structure(content, "concept")
    concept_findings = [f for f in findings if f.rule == "structure-concept-sections"]
    assert len(concept_findings) >= 1


def test_structure_concept_complete():
    """Test that concept with 'Key concepts' has no finding."""
    content = '''---
title: "What is cloud computing?"
description: "Learn about cloud computing concepts"
ms.topic: concept-article
ms.custom: ai-assisted
ms.date: 05/09/2026
---

# What is cloud computing?

## Key concepts

Important concepts.

## Next steps

More info.
'''
    findings = check_structure(content, "concept")
    concept_findings = [f for f in findings if f.rule == "structure-concept-sections"]
    assert len(concept_findings) == 0


# ---------------------------------------------------------------------------
# Aggregate
# ---------------------------------------------------------------------------

def test_run_all_style_checks():
    report = run_all_style_checks(_GOOD_FRONTMATTER, "tutorial")
    assert isinstance(report.findings, list)
    assert report.summary()
