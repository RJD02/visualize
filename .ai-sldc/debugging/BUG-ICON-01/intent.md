# BUG-ICON-001 — Icons not visible for Kafka / MinIO (and other services)

## Summary
In generated diagrams, nodes labeled with technologies like Kafka and MinIO do not render their expected service icons, even though icon injection is intended to work.

## Impact
Reduced diagram clarity and perceived quality. The diagram agent appears incomplete or unreliable for commonly used services.

## Suspected Area
SVG icon injection pipeline:
- service detection / normalization
- mapping key mismatch (kafka vs Kafka vs "Kafka/Streaming Pool")
- asset lookup path or bundling
- UI renderer not including injected symbols
- icons injected but invisible due to CSS, size, or positioning
- icon injection guarded behind a feature flag
- icon injection only runs for some node types (not for pool/group nodes)

## Goal
Icons must render for Kafka and MinIO in both:
- UI render
- headless Cypress test environment