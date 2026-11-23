# Durable Storage for Production (G1-01)

## Problem

ApexEstateHub writes user assets to local disk under `app/assets/<society_id>/`
(signed Agreement/NOC PDFs, WebP backgrounds/logos, signatures, uploaded
evidence, camera captures). Render's filesystem is **ephemeral**: every
redeploy or restart wipes these files.

## Required fix

Before production deploy, move persisted assets to durable storage:

1. **Object storage (recommended)** — S3-compatible bucket (Render Disks,
   AWS S3, GCS, etc.) for:
      - `app/assets/<society_id>/agreements/*.pdf`
      - `app/assets/<society_id>/NOCs/*.pdf`
      - `app/assets/<society_id>/<entity>/<id>.webp` (backgrounds/logos/signatures)
      - `app/static/uploads/` (camera captures, evidence)
2. **Render Persistent Disk** — mount at `app/assets/` if object storage is
   not immediately available. Note: a single persistent disk is shared across
   gunicorn workers, which works for append-only writes but requires care
   for concurrent overwrites.

## Code changes needed

- `app/services/document_archive.py` — write to object storage instead of
  `app/assets/<society_id>/...` (atomic `.part` pattern already used).
- `app/dash_apps/callbacks/drilldown_callbacks.py:519` — route camera
  captures to object storage or treat as transient (re-uploaded after redeploy).
