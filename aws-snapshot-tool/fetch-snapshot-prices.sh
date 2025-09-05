#!/usr/bin/env bash
set -euo pipefail

# Usage:
#   ./fetch-snapshot-prices.sh [--profile PROFILE_NAME]
#
# Output:
#   ./aws/snapshot-prices.json

OUT_DIR="./aws"
OUT_FILE="${OUT_DIR}/snapshot-prices.json"
PRICING_REGION="us-east-1"
CURRENCY="USD"

AWS_PROFILE_OPT=""
if [[ "${1:-}" == "--profile" && -n "${2:-}" ]]; then
  AWS_PROFILE_OPT="--profile $2"
fi

mkdir -p "$OUT_DIR"

# --- Discover regions (fallback to static list if perms are missing)
REGIONS=$(aws ec2 describe-regions \
  $AWS_PROFILE_OPT \
  --region us-east-1 \
  --all-regions \
  --filters Name=opt-in-status,Values=opt-in-not-required,opted-in \
  --query 'Regions[].RegionName' \
  --output text || true)

if [[ -z "${REGIONS:-}" ]]; then
  REGIONS="us-east-1 us-east-2 us-west-1 us-west-2 ca-central-1 eu-central-1 eu-central-2 eu-west-1 eu-west-2 eu-west-3 eu-north-1 eu-south-1 eu-south-2 ap-south-1 ap-south-2 ap-southeast-1 ap-southeast-2 ap-southeast-3 ap-southeast-4 ap-northeast-1 ap-northeast-2 ap-northeast-3 me-south-1 me-central-1 sa-east-1 af-south-1 il-central-1"
fi

# --- region code -> AWS Pricing "location" display name
region_to_location() {
  case "$1" in
    us-east-1) echo "US East (N. Virginia)";;
    us-east-2) echo "US East (Ohio)";;
    us-west-1) echo "US West (N. California)";;
    us-west-2) echo "US West (Oregon)";;
    ca-central-1) echo "Canada (Central)";;
    eu-west-1) echo "EU (Ireland)";;
    eu-west-2) echo "EU (London)";;
    eu-west-3) echo "EU (Paris)";;
    eu-north-1) echo "EU (Stockholm)";;
    eu-south-1) echo "EU (Milan)";;
    eu-south-2) echo "EU (Spain)";;
    eu-central-1) echo "EU (Frankfurt)";;
    eu-central-2) echo "EU (Zurich)";;
    ap-south-1) echo "Asia Pacific (Mumbai)";;
    ap-south-2) echo "Asia Pacific (Hyderabad)";;
    ap-southeast-1) echo "Asia Pacific (Singapore)";;
    ap-southeast-2) echo "Asia Pacific (Sydney)";;
    ap-southeast-3) echo "Asia Pacific (Jakarta)";;
    ap-southeast-4) echo "Asia Pacific (Melbourne)";;
    ap-northeast-1) echo "Asia Pacific (Tokyo)";;
    ap-northeast-2) echo "Asia Pacific (Seoul)";;
    ap-northeast-3) echo "Asia Pacific (Osaka)";;
    me-south-1) echo "Middle East (Bahrain)";;
    me-central-1) echo "Middle East (UAE)";;
    sa-east-1) echo "South America (Sao Paulo)";;
    af-south-1) echo "Africa (Cape Town)";;
    il-central-1) echo "Israel (Tel Aviv)";;
    *) echo "";;
  esac
}

# --- jq: take FIRST matching USD price with GB-Mo, after filtering usagetype suffix
# suffix arg examples: "EBS:SnapshotUsage" or ":ChargedBackupUsage"
pick_first_price_by_usage_suffix() {
  local suffix="$1"
  jq -r --arg suf "$suffix" '
    map(fromjson)
    # keep SKUs whose usagetype ends with the suffix
    | map(select(.product.attributes.usagetype? | test($suf + "$")))
    # flatten ondemand price dimensions
    | [ .[] | .terms.OnDemand
        | to_entries[] .value.priceDimensions
        | to_entries[] .value
        | select(.unit=="GB-Mo")
        | .pricePerUnit.USD
      ]
    | map(select(. != null and . != ""))
    | .[0] // empty
  '
}

get_ebs_snapshot_price() {
  local location="$1"
  aws pricing get-products \
    $AWS_PROFILE_OPT \
    --region us-east-1 \
    --service-code AmazonEC2 \
    --filters \
      Type=TERM_MATCH,Field=productFamily,Value="Storage Snapshot" \
      Type=TERM_MATCH,Field=location,Value="${location}" \
    --max-results 100 \
    --query 'PriceList' \
    --output json 2>/dev/null \
  | pick_first_price_by_usage_suffix "EBS:SnapshotUsage"
}

get_rds_snapshot_price() {
  local location="$1"
  aws pricing get-products \
    $AWS_PROFILE_OPT \
    --region us-east-1 \
    --service-code AmazonRDS \
    --filters \
      Type=TERM_MATCH,Field=productFamily,Value="Storage Snapshot" \
      Type=TERM_MATCH,Field=location,Value="${location}" \
    --max-results 100 \
    --query 'PriceList' \
    --output json 2>/dev/null \
  | pick_first_price_by_usage_suffix ":ChargedBackupUsage"
}

# --- Build JSON
TMP=$(mktemp)
echo '{"generated_at":"","currency":"","regions":{}}' | jq '.' > "$TMP"
NOW_UTC=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
jq --arg now "$NOW_UTC" --arg cur "$CURRENCY" '.generated_at=$now | .currency=$cur' "$TMP" > "${TMP}.1" && mv "${TMP}.1" "$TMP"

for REGION in $REGIONS; do
  LOCATION=$(region_to_location "$REGION")
  if [[ -z "$LOCATION" ]]; then
    >&2 echo "Skipping $REGION (no Pricing location mapping)"
    continue
  fi

  >&2 echo "Fetching $REGION ($LOCATION)..."
  EBS_PRICE=$(get_ebs_snapshot_price "$LOCATION" || true)
  RDS_PRICE=$(get_rds_snapshot_price "$LOCATION" || true)

  [[ "$EBS_PRICE" =~ ^[0-9]*\.?[0-9]+$ ]] || EBS_PRICE="null"
  [[ "$RDS_PRICE" =~ ^[0-9]*\.?[0-9]+$ ]] || RDS_PRICE="null"

  jq --arg r "$REGION" --argjson e "${EBS_PRICE:-null}" --argjson d "${RDS_PRICE:-null}" '
    .regions[$r] = { ebs_snapshot_gb_month: $e, rds_snapshot_gb_month: $d }
  ' "$TMP" > "${TMP}.1" && mv "${TMP}.1" "$TMP"
done

mv "$TMP" "$OUT_FILE"
echo "Wrote ${OUT_FILE}"