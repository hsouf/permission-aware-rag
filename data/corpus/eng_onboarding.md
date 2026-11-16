# Engineering Onboarding

## Your first week
Set up your laptop with the bootstrap script, get access to the monorepo, and pair with your onboarding buddy on a small bug fix.

## Development workflow
All changes go through pull requests with at least one review. CI runs lint, type checks and the test suite. Feature flags gate anything user-facing.

## On-call
Engineers join the on-call rotation after their third month. Interns shadow on-call but are never primary.

## Architecture overview
The platform is a set of Python services behind an API gateway, with Postgres for transactional data and a vector index for search.
