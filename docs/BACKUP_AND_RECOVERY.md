# CivicLens Disaster Recovery & Backup Runbook

## 1. Overview & Service Level Objectives (SLOs)

CivicLens operates as critical civic infrastructure coordinating public grievances, AI defect detection, and municipal work orders.

| Metric | Target Objective | Strategy |
| :--- | :--- | :--- |
| **RPO (Recovery Point Objective)** | &le; 5 minutes | Continuous Write-Ahead Log (WAL) archiving & Supabase PITR |
| **RTO (Recovery Time Objective)** | &le; 15 minutes | Automated container rebuild & managed database restore |
| **Data Retention** | 365 Days | Daily compressed cold backups replicated across regions |

---

## 2. PostgreSQL / Supabase Backup Procedures

### 2.1 Daily Automated Snapshots
Production databases on Supabase or managed PostgreSQL must take daily logical backups in addition to continuous WAL shipping:

```bash
#!/usr/bin/env bash
# scripts/backup_db.sh
set -euo pipefail

BACKUP_DIR="/var/backups/civiclens"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_FILE="${BACKUP_DIR}/civiclens_${TIMESTAMP}.dump"

mkdir -p "${BACKUP_DIR}"

# Run pg_dump in custom binary format with parallel compression
pg_dump \
  --dbname="${DATABASE_URL}" \
  --format=custom \
  --compress=9 \
  --file="${BACKUP_FILE}" \
  --exclude-table-data="audit_logs_archive"

echo "Backup created successfully: ${BACKUP_FILE}"
```

### 2.2 Evidence Assets Backup (Photos & Videos)
Grievance photo evidence stored in local disk `/app/uploads` or Supabase Storage / S3 buckets must be synced continuously:

```bash
# S3 / Cloud Bucket Synchronization
aws s3 sync /app/uploads s3://civiclens-evidence-cold-backup/uploads/ --delete
```

---

## 3. Disaster Recovery & Restoration Procedures

### 3.1 Point-in-Time Recovery (PITR) via Supabase
1. Open the **Supabase Dashboard** &rarr; Select Project &rarr; **Database** &rarr; **Backups**.
2. Select **Point-in-Time Recovery**.
3. Choose the target restoration timestamp (e.g. 5 minutes before incident onset).
4. Initiate PITR restore to a new staging database instance.
5. Validate database integrity using health queries:
   ```sql
   SELECT count(*) FROM incidents;
   SELECT count(*) FROM citizen_reports;
   SELECT count(*) FROM outbox_notifications WHERE status = 'PENDING';
   ```
6. Update application `DATABASE_URL` secret and restart WSGI workers.

### 3.2 Full Restoration from Custom Dump
When restoring to a fresh PostgreSQL 15+ database instance with PostGIS:

```bash
# 1. Ensure target PostgreSQL has PostGIS extension enabled
psql "${TARGET_DATABASE_URL}" -c "CREATE EXTENSION IF NOT EXISTS postgis;"

# 2. Restore schema and data using pg_restore
pg_restore \
  --dbname="${TARGET_DATABASE_URL}" \
  --clean \
  --if-exists \
  --no-owner \
  --no-privileges \
  --jobs=4 \
  "${BACKUP_FILE}"

# 3. Verify Alembic migration version matches codebase
psql "${TARGET_DATABASE_URL}" -c "SELECT version_num FROM alembic_version;"
```

---

## 4. Alembic Migration Rollback Procedures

If a newly deployed Alembic schema migration introduces bugs or lock contention:

```bash
# Check current migration revision
alembic current

# Step back 1 migration revision
alembic downgrade -1

# Roll back to a specific known stable revision (e.g., Step 9 baseline)
alembic downgrade c39d84e1b027
```

---

## 5. Emergency Incident Escalation & Health Verification

1. **Verify Backend Health:**
   ```bash
   curl -i http://localhost:5055/api/health
   # Expected: HTTP 200 OK {"status": "ok", "database": "connected"}
   ```

2. **Verify Public Statistics:**
   ```bash
   curl -i http://localhost:5055/api/v2/public/statistics
   # Expected: HTTP 200 OK with total_citizen_reports and canonical incidents
   ```

3. **Verify Outbox Queue:**
   ```sql
   SELECT status, count(*) FROM outbox_notifications GROUP BY status;
   ```
