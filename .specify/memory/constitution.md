
<!--
Sync Impact Report
------------------
Version change: (none) → 1.0.0
List of modified principles: All placeholders replaced with concrete rules for Telegram app development
Added sections: All (Core Principles, Constraints, Workflow, Governance)
Removed sections: None
Templates requiring updates: plan-template.md (✅ updated), spec-template.md (✅ updated), tasks-template.md (✅ updated)
Follow-up TODOs: None
-->

# LMStudioBot Constitution

## Core Principles

### I. Security & Privacy First
All code MUST protect user data and credentials. Sensitive information (tokens, user IDs, messages) MUST NOT be logged or exposed. All API keys and secrets MUST be stored in environment variables or secure vaults, never hardcoded. User consent and privacy requirements MUST be respected at all times.

### II. Telegram API Discipline
All interactions with the Telegram API MUST use official libraries (e.g., python-telegram-bot, Telethon, aiogram) and follow Telegram's rate limits and best practices. Bots MUST handle API errors gracefully and implement exponential backoff for retries. Only documented Telegram features are permitted.

### III. Robust Error Handling & Validation
All user input MUST be validated before processing. The application MUST handle all known error cases (network, API, logic) with clear user feedback and safe fallback behavior. Unhandled exceptions are forbidden in production code.

### IV. Test Coverage & Automation
All core logic MUST be covered by automated tests (unit and integration). Pull requests MUST include or update tests for new features and bug fixes. CI/CD pipelines MUST run all tests before deployment.

### V. Logging & Observability
Structured logging (with timestamps, severity, and context) is REQUIRED for all critical actions and errors. Logs MUST NOT contain sensitive data. Application health and key metrics (e.g., uptime, error rates, message throughput) MUST be observable via logs or monitoring tools.

## Additional Constraints

- The codebase MUST use Python 3.11+.
- All dependencies MUST be listed in requirements.txt or pyproject.toml and reviewed for security.
- External integrations (databases, webhooks, etc.) MUST be documented and mockable for tests.
- All third-party code MUST be open source and compatible with the project license.

## Development Workflow

- All changes MUST be made via pull requests and reviewed by at least one other contributor.
- Code style MUST follow PEP8 and be checked with linters (e.g., flake8, black).
- Commits MUST reference related issues or features.
- Releases MUST be versioned using semantic versioning (MAJOR.MINOR.PATCH).
- Documentation MUST be updated with every feature or breaking change.

## Governance

This constitution supersedes all other development practices for LMStudioBot. Amendments require a pull request, explicit documentation of changes, and approval by at least two maintainers. All reviews MUST verify compliance with these rules. The constitution version MUST be incremented according to the versioning policy. Compliance reviews are expected at least quarterly.

**Version**: 1.0.0 | **Ratified**: 2026-04-05 | **Last Amended**: 2026-04-05
