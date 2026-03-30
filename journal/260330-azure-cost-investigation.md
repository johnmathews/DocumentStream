# Azure Cost Investigation and Documentation

**Date:** 2026-03-30

## What happened

Noticed Azure free credits dropped from $200 to ~$170. Investigated what was consuming
credits and how to stop the bleeding.

## Key findings

- The AKS cluster (2x Standard_B2s_v2) was running continuously since provisioning on
  March 29, costing ~$6/day in total (compute + disks + load balancer + IP + ACR).
- The $30 spend over ~1.5 days is slightly higher than the ~$9 expected — may include a
  PostgreSQL Flexible Server that was provisioned and subsequently deleted (it's not
  running now).
- The `az costmanagement query` CLI command was removed by Microsoft in 2023. Cost breakdown
  via CLI requires `az rest` calling the Cost Management Query API directly.
- Even `az rest` returns empty results for free credit / sponsorship subscriptions — the
  Azure Portal is the only reliable way to check cost breakdown for our subscription type.

## Actions taken

- Stopped the AKS cluster with `az aks stop` to preserve remaining ~$170 credits.
- Updated `docs/dictionary.md` with:
  - Corrected pricing based on actual Azure retail prices (was using rough estimates before)
  - Added `az rest` cost query command with free credits limitation note
  - Added `az aks get-credentials` reminder after cluster start
  - Added MC_ resource group listing command
  - Added `az postgres flexible-server list` command

## Decisions

- Interview is Friday April 3rd at 10:00 AM — 4 days after the 3-day build window ends.
  This gives time to polish and rehearse without time pressure.
- Keep the cluster stopped when not actively working. Start 5 minutes before needed.
- Remaining ~$170 in credits is plenty for the remaining work and demo day.
