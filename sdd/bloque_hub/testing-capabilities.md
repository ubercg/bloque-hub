# SDD Testing Capabilities for bloque_hub

## Project Overview
*   **Project Name:** bloque_hub
*   **SDD Mode:** openspec
*   **Strict TDD:** true

## Detected Stack
*   **Backend:** Python
    *   **Frameworks/Libraries:** Detected based on `requirements.txt`, `pytest.ini`, `alembic`.
    *   **Containerization:** Docker (`Dockerfile`)
*   **Frontend:** Next.js 15
    *   **Frameworks/Libraries:** Next.js, React, TypeScript, Tailwind CSS
    *   **Build Tools:** Webpack (integrated with Next.js), ESLint, TypeScript compiler

## Testing Capabilities

### Backend (Python)
| Capability | Details | Status |
| :--------- | :------ | :----- |
| **Test Runner** | Pytest (confirmed by `pytest.ini` and `tests/` directory) | ✅ Available |
| **Unit Tests** | Supported via Pytest | ✅ Available |
| **Integration Tests** | Supported via Pytest, typically using fixtures for database/service mocking | ✅ Available |
| **End-to-End (E2E) Tests** | Not directly detected for backend, but could be part of overall system E2E with frontend | 🔲 Not directly detected |
| **Test Coverage** | Integrates with `pytest-cov` | ✅ Integrable |
| **Linter** | `flake8` or `pylint` are common; configuration needs verification | 🔲 Needs verification |
| **Type Checker** | `mypy` is common; configuration needs verification | 🔲 Needs verification |
| **Formatter** | `black` is common; configuration needs verification | 🔲 Needs verification |

### Frontend (Next.js/TypeScript/React)
| Capability | Details | Status |
| :--------- | :------ | :----- |
| **Test Runner (E2E)** | Playwright (confirmed by `playwright.config.ts` and test reports) | ✅ Available |
| **Unit/Component Tests** | Common runners: Jest, React Testing Library, Vitest. Presence of `tests/` directory suggests intent. | 🔲 Needs verification (runner) |
| **Integration Tests** | Can be done via Playwright for feature integration or dedicated component testing frameworks | ✅ Integrable |
| **End-to-End (E2E) Tests** | Full support via Playwright | ✅ Available |
| **Test Coverage** | Playwright has built-in reporting; unit/component tests use Istanbul/V8 | ✅ Available |
| **Linter** | ESLint (confirmed by `eslint.config.mjs`) | ✅ Available |
| **Type Checker** | TypeScript (confirmed by `tsconfig.json`) | ✅ Available |
| **Formatter** | Prettier is common; configuration needs verification | 🔲 Needs verification |

## Project Context
The `bloque_hub` project is a full-stack application with a Python backend and a Next.js/TypeScript frontend. It utilizes Docker for containerization. The project demonstrates a strong commitment to testing with dedicated test runners and configuration for both frontend and backend. The `openspec` mode will facilitate artifact generation and management.
