# Security policy

This repository is a reference implementation for teaching and evaluation. It is not a hosted service.

## Reporting a vulnerability

If you find a way for a user to retrieve content their permissions should exclude, please open a [private security advisory](https://github.com/hsouf/permission-aware-rag/security/advisories/new) instead of a public issue. A failing adversarial test case is the most useful report.

## Demo-only components

These exist so the project runs offline. Do not deploy them:

- The HS256 development token issuer and the default `PA_RAG_JWT_SECRET` (the app refuses to start with it when `PA_RAG_ENV` is not `dev`).
- The JSON directory and sharing manifest in `data/`.
- The database passwords in `db/init.sql`, `docker-compose.yml` and CI.

All people, companies and figures in `data/` are fictional.
