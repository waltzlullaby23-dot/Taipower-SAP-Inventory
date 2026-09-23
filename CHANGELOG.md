# Changelog

## V2.0.0 — 2026-09-21

- Added Windows Folder Auto-Sync Agent.
- Added automatic latest-date file detection.
- Added SHA-256 duplicate protection.
- Added transactional Supabase import path.
- Added role-gated import (`admin` / `operator`).
- Added Agent heartbeat and health dashboard.
- Added Windows DPAPI protection for refresh tokens.
- Removed pandas/openpyxl/watchdog requirement from the Agent.
- Added standard-library XLSX parser for `.xlsx/.xlsm`.
- Added all-sheet scanning and 10-digit Taipower material number validation.
- Added low-row-count safety gate.
- Added automatic 60-second web dashboard refresh.
- Added paginated loading of inventory changes instead of a fixed 5,000-row ceiling.
- Added explicit refusal to auto-date files whose names contain no recognizable date.
