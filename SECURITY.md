# Security policy

## Supported versions

| Version | Supported |
|---------|-----------|
| Latest release | ✅ |
| Previous releases | ❌ |

## Reporting a vulnerability

**Please do not open a public issue for security vulnerabilities.**

Use GitHub's private vulnerability reporting to submit a report:

1. Go to the [Security tab](../../security) of this repository
2. Click **"Report a vulnerability"**
3. Fill in the details and submit

## Response timeline

| Stage | Target |
|-------|--------|
| Acknowledgement | 48 hours |
| Initial assessment | 5 business days |
| Fix or mitigation | 30 days (critical), 90 days (other) |

## Scope

The following are considered security issues:

- Secrets or credentials accidentally committed to the repository
- Vulnerabilities in the backend API or VS Code extension
- Unsafe handling of user-provided video files
- Prompt injection that bypasses agent guardrails

The following are **not** security issues:

- Bugs in generated documentation content
- Feature requests
- Issues requiring physical access to the developer's machine

## Security practices

- All Azure service authentication uses `DefaultAzureCredential` (no hardcoded keys)
- Video files are processed with time-limited SAS tokens; no permanent cloud storage
- All AI-generated content is marked with `ms.custom: ai-assisted` metadata
- Environment secrets are managed via `.env` files (gitignored) and GitHub Actions secrets
