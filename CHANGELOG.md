# Changelog

All notable changes to this project will be documented in this file.

## [2026-05-26] - Security and Documentation Hardening

### Fixed

- Fixed password update/reset flows in `api/employee_management_api.py`:
  - Replaced incorrect `password_hash` assignments with model-safe password handling.
  - Updated existing user password updates to use `set_password(...)`.

- Hardened backup file handling in `api/backup_api.py`:
  - Added backup filename/path validation to prevent path traversal.
  - Applied safe path resolution for restore, delete, and download endpoints.

- Added role-based authorization for import endpoints in `api/import_api.py`:
  - `POST /api/import/analyze` now requires `admin` or `manager`.
  - `POST /api/import/attendance` now requires `admin` or `manager`.

- Hardened app security defaults in `app.py`:
  - Removed hardcoded fallback secret key.
  - If `SECRET_KEY` is missing, the app generates a temporary runtime key and logs a warning.
  - CORS now uses explicit allowed origins from `CORS_ORIGINS`.

### Docs

- Rewrote `README.md` to align with current code and deployment expectations:
  - Unified runtime/version requirements.
  - Added `.env` configuration examples including `CORS_ORIGINS`.
  - Added deployment and security notes.
