"""Unit tests for the rule-based style graders.

Tests graders against known-good and known-bad content to ensure
they correctly detect MS Learn style violations.
"""

from __future__ import annotations

import pytest

from tests.eval.graders import (
    StyleFinding,
    check_contractions,
    check_frontmatter,
    check_grounding,
    check_headings,
    check_markdown_extensions,
    check_serial_comma,
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
# Aggregate
# ---------------------------------------------------------------------------

def test_run_all_style_checks():
    report = run_all_style_checks(_GOOD_FRONTMATTER, "tutorial")
    assert isinstance(report.findings, list)
    assert report.summary()
