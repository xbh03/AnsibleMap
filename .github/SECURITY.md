# Security Policy

## Supported Versions

Security fixes are applied on a best-effort basis to the latest version on the default branch.

## Reporting a Vulnerability

Please report vulnerabilities privately to the maintainers.

Do not open public issues for sensitive security reports.

Your report should include:

- A clear description of the issue.
- Steps to reproduce.
- Potential impact.
- Suggested mitigation (if available).

## Response Process

The maintainers will:

- Acknowledge receipt as soon as possible.
- Validate and assess severity.
- Work on a fix and coordinate disclosure timing.

## Disclosure Guidelines

- Use responsible disclosure.
- Avoid sharing exploit details publicly until a fix is available.
- Credit the reporter, if desired, after coordinated disclosure.

## Security Best Practices for Deployments

- Store secrets in a secure vault or CI secret manager.
- Use least-privilege credentials for database and SCM access.
- Rotate tokens/passwords regularly.
- Avoid logging sensitive values.
