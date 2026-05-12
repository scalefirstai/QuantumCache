#!/bin/bash
# LocalStack init hook — runs once when LocalStack is "ready".
# Creates the S3 buckets named in DATA-PLAN §3.2 and ddq.md §5.
#
# Object Lock (Compliance mode) per ddq.md §1 invariant 2 and §2:
# enabled at bucket creation; cannot be disabled afterward.

set -euo pipefail

REGION="${AWS_DEFAULT_REGION:-us-east-1}"
ENDPOINT="http://localhost:4566"

# AWS CLI inside LocalStack uses dummy creds.
export AWS_ACCESS_KEY_ID="test"
export AWS_SECRET_ACCESS_KEY="test"

# Bucket names from DATA-PLAN §3.2 + ddq.md §L04, §L05, §L01.
BUCKETS=(
  "bny-ddq-knowledge-raw"
  "bny-ddq-knowledge-parquet"
  "bny-ddq-library-sealed"
  "bny-ddq-taxonomy-snapshots"
  "bny-ddq-runs-sealed"        # ddq.md §L01 sealed runs (Object Lock)
)

# Buckets that MUST have Object Lock per ddq.md invariant 2.
# Library + taxonomy + runs are immutable by spec.
OBJECT_LOCK_BUCKETS=(
  "bny-ddq-library-sealed"
  "bny-ddq-taxonomy-snapshots"
  "bny-ddq-runs-sealed"
)

is_object_lock_bucket() {
  local b="$1"
  for ol in "${OBJECT_LOCK_BUCKETS[@]}"; do
    if [[ "$ol" == "$b" ]]; then
      return 0
    fi
  done
  return 1
}

for bucket in "${BUCKETS[@]}"; do
  if aws --endpoint-url="$ENDPOINT" s3api head-bucket --bucket "$bucket" 2>/dev/null; then
    echo "[localstack-init] bucket exists: $bucket"
    continue
  fi

  if is_object_lock_bucket "$bucket"; then
    echo "[localstack-init] creating $bucket  (Object Lock enabled)"
    # --object-lock-enabled-for-bucket implies versioning; AWS rejects an
    # explicit put-bucket-versioning afterward (InvalidBucketState).
    aws --endpoint-url="$ENDPOINT" s3api create-bucket \
      --bucket "$bucket" \
      --region "$REGION" \
      --object-lock-enabled-for-bucket
  else
    echo "[localstack-init] creating $bucket"
    aws --endpoint-url="$ENDPOINT" s3api create-bucket \
      --bucket "$bucket" \
      --region "$REGION"
  fi
done

# CORS on bny-ddq-knowledge-raw so the operator UI (Vite dev server) can
# PUT files directly via presigned URLs. The API gateway also ensures this
# at runtime; this keeps fresh containers self-sufficient.
#
# Wildcard origin is intentional for the dev bucket — LocalStack is local-
# only and Vite drifts ports (5173 → 5174 → 5175 when prior runs hold the
# port, and the dataset e2e suite uses 5175). Real S3 in M1 should pin the
# origin to the production host.
echo "[localstack-init] put-bucket-cors on bny-ddq-knowledge-raw"
aws --endpoint-url="$ENDPOINT" s3api put-bucket-cors \
  --bucket "bny-ddq-knowledge-raw" \
  --cors-configuration '{
    "CORSRules": [{
      "AllowedHeaders": ["*"],
      "AllowedMethods": ["PUT", "GET", "HEAD"],
      "AllowedOrigins": ["*"],
      "ExposeHeaders": ["ETag"],
      "MaxAgeSeconds": 3600
    }]
  }'

echo "[localstack-init] done."
