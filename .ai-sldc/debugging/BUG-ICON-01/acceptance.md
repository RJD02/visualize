# Acceptance Criteria — BUG-ICON-001

## Must Fix
1) Kafka icon is visible for nodes that represent Kafka:
   - "Kafka"
   - "Kafka/Streaming Pool"
   - "Kafka topics"
   - "Kafka/CDC"

2) MinIO icon is visible for nodes that represent MinIO:
   - "MinIO/Ceph"
   - "Storage Cluster: MinIO/Ceph"
   - "DC Object Store"
   - "DR Object Store"

## Robust Matching
3) Matching must be case-insensitive and punctuation-tolerant:
   - kafka, Kafka, KAFKA
   - MinIO, minio, MinIO/Ceph, MinIO-Ceph

4) Unknown tech labels must not break rendering.
5) If icon asset missing, fallback to generic icon (visible).

## Testing Requirements (non-negotiable)
6) Unit tests must cover:
   - normalization function (label -> key)
   - mapping lookup
   - fallback behavior

7) Cypress tests (headless) must:
   - generate diagram using reproduction prompt fixture
   - assert kafka + minio icons exist in SVG DOM
   - assert icons are visible (non-zero bounding box or rendered element presence)
   - assert no duplicate injection per node
   - assert no console errors

## Definition of Done
8) All unit tests pass.
9) Cypress passes headless.
10) Audit report shows acceptance checklist as PASS.