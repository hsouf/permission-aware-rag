# Postmortem: search outage, August 2026

## Summary
Search was unavailable for 47 minutes after an index migration exhausted memory on the vector database nodes.

## Root cause
The migration rebuilt the payload indexes for every collection at once instead of one collection at a time.

## Action items
Run index migrations collection by collection, add a memory alert at 80 percent, and rehearse the rollback in staging.
