# Reproduction — BUG-ICON-001

## Steps
1) Open the diagram generation UI.
2) Generate a diagram using the prompt below (copy-paste exactly).
3) Observe the output SVG/diagram nodes:
   - Kafka / Kafka/Streaming Pool
   - MinIO/Ceph storage cluster
4) Expected: Icons should appear on/near corresponding nodes.
5) Actual: Icons are missing for Kafka/MinIO.

## Prompt used to reproduce

Generate a diagram based on below:
1) Infrastructure Diagram Prompt (Production + DR + Environments)
Goal: Show DC + DR topology, network segmentation, Kubernetes, storage, compute pools, observability, security, and replication.
Prompt: “Infrastructure / Deployment View”
Title: Enterprise Open-Stack Lakehouse – Infrastructure & Deployment (DC + DR)
Style: clean enterprise architecture diagram, AWS/Azure-like icon style but vendor-neutral
Perspective: deployment/infrastructure topology
Draw the following as grouped zones:
A. Top-level Layout (left-to-right)
Users & Channels (far left)
Business Users (BI)
Data Engineers
Data Scientists
Admin/SRE
External Systems (optional)
Data Center (DC / Primary Site) (center-left big box)
Disaster Recovery (DR / Secondary Site) (center-right big box)
External Integrations (far right)
Active Directory/LDAP
SIEM
ITSM/CMDB (Jira/ServiceNow)
Email/SMS/Chat for alerting (optional)
B. Inside DC / Primary Site — draw these layers
B1. Network Segmentation (at top of DC box)

Create 3 horizontal lanes:
DMZ / Ingress Zone
Application / Services Zone
Data / Storage Zone
B2. Ingress / DMZ lane
Load Balancer / Ingress Controller (HA)
WAF (optional)
API Gateway (optional)
Connect “Users” → “Load Balancer/Ingress”.
B3. Application / Services Zone

Create a large component group: Kubernetes Cluster (PROD)

Inside it, draw these sub-groups:
Control Plane (HA)
3× Kubernetes control-plane nodes (label: “3-node HA control plane”)
Worker Node Pools (separate boxes)
Spark ETL Pool (8 workers)
Trino SQL Pool (4 workers + 2 coordinators)
Kafka/Streaming Pool (3 brokers)
Platform Services Pool (Airflow, OpenMetadata, Superset, Postgres Metastore, Vault, CI/CD runners)
Observability Pool (Prometheus, Grafana, Loki/ELK, Alertmanager, OpenTelemetry collector)
Label each pool with “scale-out by adding nodes”.
Security Services (within K8s or adjacent)
Vault (secrets)
OPA/Gatekeeper (policy)
Keycloak (if not using AD directly)
Certificate manager (TLS)
Connect AD/LDAP → Keycloak/SSO → all UIs (Airflow/Superset/OpenMetadata).
B4. Data / Storage Zone

Create a Storage Cluster: MinIO/Ceph (S3 Object Store)
6 storage nodes (label: “~1.3 PB raw, EC enabled”)
Show erasure coding + replication policy
Add Metadata DB (Postgres HA/PITR) (can be in Platform Services Pool, but visually tie it to storage/backups)
C. Inside DR / Secondary Site
Mirror the same major blocks but smaller compute:
Kubernetes Cluster (DR) control plane HA
Storage Cluster (MinIO/Ceph DR) same capacity (mirrored)
Spark Pool 4–6 nodes
Trino Pool 2–3 nodes
Kafka DR (either MirrorMaker or standby cluster)
Draw replication arrows:
DC Object Store → DR Object Store (label: “Async replication, encrypted”)
DC Postgres (metadata) → DR Postgres (label: “PITR/WAL shipping”)
Kafka topics → DR Kafka (label: “MirrorMaker / replication”)
Add a Failover Runbook callout: “Promote DR K8s services; re-point DNS/Ingress; validate data; resume pipelines.”
D. Environment boxes (DEV/SIT/UAT) – bottom lane or separate panel
Add smaller boxes for DEV, SIT, UAT clusters with reduced sizing, each referencing:
same architecture pattern
isolated namespaces or separate clusters
masking/synthetic data for UAT where needed
E. Cross-cutting Callouts (show as side notes)
Encryption in transit (TLS)
Encryption at rest (LUKS / object SSE)
RBAC/ABAC + audit logs
Monitoring + alerting aligned to SLA
Backup: Velero + object snapshots + Postgres PITR
Network: 25GbE recommended in PROD
Connections to draw clearly
Sources → Kafka/CDC → Spark → Object Store (Iceberg tables)
Trino → Object Store
Superset/BI → Trino
OpenMetadata connects to Airflow/Spark/Trino/Superset
Observability connects to all components
Vault supplies secrets to all runtime services