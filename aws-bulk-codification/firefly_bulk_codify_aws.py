#!/usr/bin/env python3
"""
Firefly AWS bulk codify (embedded config, pretty HCL) with optional filters.
"""

import json
import re
import shutil
import subprocess
import sys
import time
from typing import Any, Dict, Iterable, List, Tuple
from pathlib import Path
import requests

# ================= CONFIG =================
ACCESS_KEY = "ACCESS_KEY"
SECRET_KEY = "SECRET_KEY"

DATA_SOURCE_NAME = "DATA_SOURCE_NAME"  # Used if ACCOUNT_NUMBER is empty
ACCOUNT_NUMBER = ""  # Optional: 12-digit AWS account; if set, skips lookup

# Optional filters for inventory API
ASSET_STATE = "unmanaged"  # e.g., "unmanaged", "codified", "drifted", "ghost"
ASSET_TYPES = []  # e.g., ["aws_s3_bucket", "aws_iam_role"]
NAMES = []  # exact name matches
ARNS = []  # exact ARN matches
DAY_RANGE_EPOCH = None  # integer number of days
SORT_FIELD = ""  # e.g., "assetType"
SORT_ORDER = ""  # "asc" or "desc"
SOURCE_FIELDS = []  # fields to include
EXTRA_PROVIDER_IDS = []  # extra AWS account IDs
SIZE = 10000  # inventory page size


# Optional tag filter (client-side)
TAG_KEY = ""
TAG_VALUE = ""

# Output
OUTPUT_DIR = "codified_assets"        # folder for per-type .tf files
OUT_IMPORT_CMDS = "import_commands.sh"
REMOVE_COMMENTS = False
AUTO_TERRAFORM_FMT = True
INCLUDE_PROVIDER = False
INCLUDE_IMPORTS = True

# ===========================================


BASE_URL = "https://api.firefly.ai/api/v1.0"
SESSION = requests.Session()
SESSION.headers.update({"Content-Type": "application/json"})



class APIError(RuntimeError):
    pass


def _raise_for_status(resp: requests.Response) -> None:
    try:
        resp.raise_for_status()
    except requests.HTTPError as e:
        raise APIError(f"HTTP {resp.status_code}: {resp.text}") from e


def login(access_key: str, secret_key: str) -> str:
    url = f"{BASE_URL}/login"
    resp = SESSION.post(url, data=json.dumps({"accessKey": access_key, "secretKey": secret_key}))
    _raise_for_status(resp)
    tok = resp.json().get("accessToken")
    if not tok:
        raise APIError("Missing accessToken in login response")
    SESSION.headers.update({"Authorization": f"Bearer {tok}"})
    return tok


def resolve_account_number(data_source_name: str) -> str:
    url = f"{BASE_URL}/integrations/aws"
    r = SESSION.get(url)
    if r.status_code == 200:
        for item in r.json():
            if item.get("name") == data_source_name:
                acc = item.get("accountNumber")
                if acc:
                    return acc
    raise APIError(f"Data source '{data_source_name}' not found for provider 'aws'")


def list_inventory(account_number: str, size: int = SIZE) -> Dict[str, Any]:
    url = f"{BASE_URL}/inventory"
    body = {
        "size": size,
        "providerTypes": {"provider": ["aws"]},
        "providerIds": [account_number] + EXTRA_PROVIDER_IDS,
    }
    if ASSET_STATE:
        body["assetState"] = ASSET_STATE
    if ASSET_TYPES:
        body["assetTypes"] = ASSET_TYPES
    if NAMES:
        body["names"] = NAMES
    if ARNS:
        body["arns"] = ARNS
    if DAY_RANGE_EPOCH is not None:
        body["dayRangeEpoch"] = int(DAY_RANGE_EPOCH)
    if SOURCE_FIELDS:
        body["source"] = SOURCE_FIELDS
    if SORT_FIELD and SORT_ORDER:
        body["sorting"] = {"field": SORT_FIELD, "order": SORT_ORDER}

    resp = SESSION.post(url, data=json.dumps(body))
    _raise_for_status(resp)
    return resp.json()


def _tag_match(tf_obj: Dict[str, Any], key: str, val: str) -> bool:
    for fld in ("tags", "tags_all", "resource_tags"):
        m = tf_obj.get(fld) or {}
        if isinstance(m, dict) and m.get(key) == val:
            return True
    return False


def filter_assets(inv: Dict[str, Any], tag_key: str = "", tag_val: str = "") -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for r in inv.get("responseObjects", []) or []:
        tf = r.get("tfObject") or {}
        if tag_key and tag_val and not _tag_match(tf, tag_key, tag_val):
            continue

        asset_type = r.get("assetType") or ""
        preferred_id = r.get("arn") or r.get("resourceId") or r.get("assetId")

        if not preferred_id:
            continue

        # aws_config_config_rule must use ARN; skip if not ARN
        if asset_type == "aws_config_config_rule" and not str(preferred_id).startswith("arn:aws:config:"):
            continue

        out.append({
            "assetType": asset_type,
            "assetId": preferred_id,
            "iacType": "terraform",
            "provider": "aws",
            "accountNumber": r.get("providerId") or r.get("accountNumber") or ACCOUNT_NUMBER,
        })
    return out


def codify_one(payload: Dict[str, Any]) -> Dict[str, Any]:
    url = f"{BASE_URL}/codify"
    resp = SESSION.post(url, data=json.dumps(payload))
    _raise_for_status(resp)
    return resp.json()


def strip_headers(text: str) -> str:
    out = []
    for ln in text.splitlines():
        if REMOVE_COMMENTS and ln.strip().startswith("# ---"):
            continue
        out.append(ln)
    return "\n".join(out)


def pretty_hcl(hcl: str) -> str:
    hcl = strip_headers(hcl).strip()

    # Convert JSON-style keys (often inside jsonencode payloads):  "Key": -> "Key" =
    hcl = re.sub(r'"([^"]+)"\s*:', r'"\1" =', hcl)
    # Also handle unquoted keys with a colon:  key: -> key =
    hcl = re.sub(r'(?<!")\b([A-Za-z0-9_]+)\b\s*:', r'\1 =', hcl)

    # Ensure a break before the next quoted key on same line
    hcl = re.sub(r'("\s*=\s*[^{}\n]+)\s+(")', r'\1\n\2', hcl)

    res = []
    indent = 0
    i = 0
    in_str = False

    while i < len(hcl):
        ch = hcl[i]

        # strings
        if ch == '"' and (i == 0 or hcl[i - 1] != "\\"):
            in_str = not in_str
            res.append(ch); i += 1; continue
        if in_str:
            res.append(ch); i += 1; continue

        if ch == "{":
            res.append(" {\n")
            indent += 1
            res.append("  " * indent)
            i += 1; continue

        if ch == "}":
            indent = max(0, indent - 1)
            while res and res[-1] == " ":
                res.pop()
            res.append("\n" + "  " * indent + "}\n" + ("  " * indent))
            i += 1; continue

        if ch == "=":
            while res and res[-1] == " ":
                res.pop()
            res.append(" = ")
            i += 1
            while i < len(hcl) and hcl[i] == " ":
                i += 1
            continue

        if ch == " ":
            j = i
            while j < len(hcl) and hcl[j] == " ":
                j += 1
            k = j
            if j < len(hcl) and hcl[j] == '"':
                k = j + 1
                while k < len(hcl) and hcl[k] != '"':
                    if hcl[k] == "\\" and k + 1 < len(hcl):
                        k += 2; continue
                    k += 1
                k = min(k + 1, len(hcl))
            else:
                while k < len(hcl) and (hcl[k].isalnum() or hcl[k] in "_-"):
                    k += 1
            n = k
            while n < len(hcl) and hcl[n] == " ":
                n += 1
            if k > j and n < len(hcl) and hcl[n] in ("=", "{"):
                res.append("\n" + "  " * indent)
                i = j
                continue
            if not res or res[-1] != " ":
                res.append(" ")
            i += 1; continue

        if ch == "\n":
            res.append("\n" + "  " * indent)
            i += 1; continue

        res.append(ch); i += 1

    pretty = "".join(res)

    # Post-passes
    pretty = re.sub(r'([^\s{\n])\s+([A-Za-z0-9_-]+\s*=)', r'\1\n\2', pretty)   # unquoted key =
    pretty = re.sub(r'([^\s{\n])\s+(".*?"\s*=)', r'\1\n\2', pretty)            # quoted key =
    pretty = re.sub(r'([^\s{\n])\s+([A-Za-z0-9_-]+\s*\{)', r'\1\n\2', pretty)  # nested block start
    pretty = re.sub(r'\n\s+,', r',\n', pretty)                                  # stray commas to prev line
    pretty = re.sub(                                                            # merge split headers
        r'^(resource|data)\s+(".*?")\s*\n\s*(".*?")\s*\{',
        r'\1 \2 \3 {',
        pretty,
        flags=re.M,
    )
    pretty = re.sub(r'=\s*\n\s*', r'= ', pretty)                                # '=' followed by newline
    pretty = re.sub(r"\n{3,}", "\n\n", pretty)                                  # squeeze blanks

    return pretty.strip() + "\n"


def write_outputs(items: Iterable[Tuple[Dict[str, Any], Dict[str, Any]]]) -> None:
    """
    Write Terraform by asset type into codified_assets/<asset_type>.tf.
    - provider block (if enabled) goes to codified_assets/provider.tf (once).
    - import blocks appended into the same per-type file as the resource.
    - import_commands.sh saved in the folder.
    """
    out_dir = Path(OUTPUT_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)

    per_type: Dict[str, List[str]] = {}
    provider_written = False
    import_cmds_path = out_dir / OUT_IMPORT_CMDS

    with import_cmds_path.open("w", encoding="utf-8") as sh:
        for req, resp in items:
            asset_type = (req.get("assetType") or "misc").strip()
            buf = per_type.setdefault(asset_type, [])

            # provider block (once)
            if INCLUDE_PROVIDER and not provider_written:
                pb = resp.get("providerBlock")
                if pb:
                    (out_dir / "provider.tf").write_text(pretty_hcl(pb), encoding="utf-8")
                    provider_written = True

            # resource HCL
            cr = resp.get("codifiedResult") or ""
            if cr:
                buf.append(pretty_hcl(cr))

            # import blocks + commands
            if INCLUDE_IMPORTS:
                ib = resp.get("importBlocks") or ""
                if ib:
                    buf.append(pretty_hcl(ib))
                ic = resp.get("importCommand") or ""
                if ic:
                    sh.write(ic + "\n")

    # Write per-type files
    written = 0
    for asset_type, chunks in per_type.items():
        safe_name = re.sub(r"[^A-Za-z0-9_]+", "_", asset_type).strip("_") or "misc"
        tf_path = out_dir / f"{safe_name}.tf"
        tf_path.write_text("".join(chunks), encoding="utf-8")
        written += 1

    # Optional terraform fmt on the whole folder
    if AUTO_TERRAFORM_FMT and shutil.which("terraform"):
        try:
            subprocess.run(["terraform", "fmt", str(out_dir)], check=False)
        except Exception:
            pass

    print(f"Wrote {written} .tf files to: {out_dir}")
    print(f"Helper import commands: {import_cmds_path}")


def codify_assets(assets: List[Dict[str, Any]], sleep_sec: float = 0.02) -> List[Tuple[Dict[str, Any], Dict[str, Any]]]:
    """
    Codify all assets with detailed progress logging (per-item line + periodic ETA).
    Returns list of (request, response) tuples for successes.
    """
    total = len(assets)
    ok = 0
    fail = 0
    out: List[Tuple[Dict[str, Any], Dict[str, Any]]] = []
    t0 = time.time()

    for idx, req in enumerate(assets, start=1):
        at = req.get("assetType", "?")
        aid = (req.get("assetId") or "")[:150]
        print(f"    [{idx}/{total}] {at} → {aid}", flush=True)

        missing = [k for k in ("assetType", "assetId", "iacType", "provider", "accountNumber") if not req.get(k)]
        if missing:
            print(f"      ⨯ skip (missing {missing})", flush=True)
            fail += 1
            continue

        try:
            t_call = time.time()
            resp = codify_one(req)
            dt = time.time() - t_call
            out.append((req, resp))
            ok += 1
            print(f"      ✓ ok ({dt:.2f}s)", flush=True)
        except APIError as e:
            fail += 1
            msg = str(e)
            if len(msg) > 300:
                msg = msg[:300] + "…"
            print(f"      ⨯ failed: {msg}", flush=True)

        if sleep_sec > 0:
            time.sleep(sleep_sec)

        if idx % 25 == 0 or idx == total:
            elapsed = time.time() - t0
            rate = idx / elapsed if elapsed > 0 else 0.0
            remaining = total - idx
            eta = remaining / rate if rate > 0 else 0.0
            print(f"    — progress: {idx}/{total} | ok={ok} fail={fail} | {rate:.1f}/s | ETA ~{eta:.0f}s", flush=True)

    elapsed = time.time() - t0
    print(f"    Done codifying: ok={ok}, fail={fail}, total={total}, elapsed={elapsed:.1f}s", flush=True)
    return out


def main() -> None:
    print("[1/6] Authenticating…", file=sys.stderr)
    login(ACCESS_KEY, SECRET_KEY)

    if ACCOUNT_NUMBER:
        account_number = ACCOUNT_NUMBER
        print(f"[2/6] Using provided account number: {account_number}", file=sys.stderr)
    else:
        print(f"[2/6] Resolving data source → accountNumber (name='{DATA_SOURCE_NAME}')…", file=sys.stderr)
        account_number = resolve_account_number(DATA_SOURCE_NAME)

    print(f"[3/6] Listing inventory for account {account_number}…", file=sys.stderr)
    inv = list_inventory(account_number, size=SIZE)

    print("[4/6] Filtering assets…", file=sys.stderr)
    assets = filter_assets(inv, tag_key=TAG_KEY, tag_val=TAG_VALUE)
    print(f"    matched assets: {len(assets)}", file=sys.stderr)
    if not assets:
        print("No assets matched the provided filters.")
        return

    print("[5/6] Codifying assets…", file=sys.stderr)
    codified_pairs = codify_assets(assets, sleep_sec=0.02)

    print("[6/6] Writing outputs…", file=sys.stderr)
    write_outputs(codified_pairs)


if __name__ == "__main__":
    try:
        main()
    except APIError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        sys.exit(130)