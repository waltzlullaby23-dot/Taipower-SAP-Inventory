#!/usr/bin/env python3
# MaterialMind V2 - Windows Folder Auto-Sync Agent
# Standard library only. No pandas/openpyxl/watchdog required.

import base64
import ctypes
import ctypes.wintypes as wintypes
import getpass
import hashlib
import json
import os
import re
import sys
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
import zipfile
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta
from pathlib import Path

APP_NAME = "MaterialMind Auto-Sync Agent"
DEFAULT_CONFIG = Path(os.environ.get("PROGRAMDATA", Path.home())) / "MaterialMind" / "agent_config.json"
DEFAULT_LOG = Path(os.environ.get("PROGRAMDATA", Path.home())) / "MaterialMind" / "agent.log"
NS_MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
NS_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
NS_PKG_REL = "http://schemas.openxmlformats.org/package/2006/relationships"

HEADER_ALIASES = {
    "part_no": ["物料編號", "料號", "物料號碼", "物料", "Material", "Material Number"],
    "material_name": ["名稱規範", "材料名稱", "物料名稱", "名稱", "Description", "Material Description"],
    "rating": ["評價", "評價類型", "Valuation Type", "Valuation"],
    "warehouse": ["儲存地點", "倉庫", "Storage Location", "Plant Storage Location"],
    "storage_bin": ["儲格", "Storage Bin", "Bin"],
    "quantity": ["庫存量", "庫存", "數量", "Unrestricted", "Qty", "Quantity"],
    "safety_stock": ["安全庫存", "Safety Stock"],
    "received_date": ["最後收料日期", "最後收料", "Last Receipt Date"],
    "last_used_date": ["最後使用日期", "最後使用", "Last Issue Date"],
    "unit": ["單位", "Unit"],
    "material_category": ["材料類別", "物料類別", "Material Category"],
    "management_code": ["管理", "管理碼", "Management"],
    "old_part_no": ["舊物料號碼", "舊料號", "Old Material Number"],
}


def log(msg, level="INFO"):
    DEFAULT_LOG.parent.mkdir(parents=True, exist_ok=True)
    line = f"{datetime.now().isoformat(timespec='seconds')} [{level}] {msg}"
    print(line, flush=True)
    try:
        with DEFAULT_LOG.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def normalize_header(v):
    if v is None:
        return ""
    return re.sub(r"\s+", "", str(v)).strip().lower()


def parse_date_from_name(name):
    patterns = [
        r"(?<!\d)(20\d{2})[-_./](\d{1,2})[-_./](\d{1,2})(?!\d)",
        r"(?<!\d)(20\d{2})(\d{2})(\d{2})(?!\d)",
    ]
    for p in patterns:
        m = re.search(p, name)
        if m:
            try:
                d = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
                return d
            except ValueError:
                continue
    return None


def parse_number(v):
    if v is None or v == "":
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace(",", "")
    if not s:
        return 0.0
    if s.endswith(".0") and s[:-2].isdigit():
        s = s[:-2]
    try:
        return float(s)
    except ValueError:
        return 0.0


def normalize_part_no(v):
    if v is None:
        return ""
    s = str(v).strip().replace(" ", "")
    if s.endswith(".0") and s[:-2].isdigit():
        s = s[:-2]
    if s.isdigit():
        return s.zfill(10)
    return s


def excel_serial_to_date(v):
    try:
        n = float(v)
        return (datetime(1899, 12, 30) + timedelta(days=n)).date().isoformat()
    except Exception:
        return None


def normalize_date(v):
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        return excel_serial_to_date(v)
    s = str(v).strip()
    if not s:
        return None
    # XLSX stores many dates as numeric serials; XML parsing returns them as strings.
    if re.fullmatch(r"\d+(?:\.\d+)?", s):
        try:
            n = float(s)
            if 20000 <= n <= 80000:
                return excel_serial_to_date(n)
        except Exception:
            pass
    for fmt in ("%Y/%m/%d", "%Y-%m-%d", "%Y.%m.%d", "%Y%m%d", "%Y/%m/%d %H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            pass
    return None


def col_to_num(ref):
    letters = re.match(r"([A-Z]+)", ref.upper())
    if not letters:
        return 0
    n = 0
    for c in letters.group(1):
        n = n * 26 + ord(c) - 64
    return n


def read_shared_strings(z):
    if "xl/sharedStrings.xml" not in z.namelist():
        return []
    root = ET.fromstring(z.read("xl/sharedStrings.xml"))
    out = []
    for si in root:
        parts = []
        for t in si.iter(f"{{{NS_MAIN}}}t"):
            parts.append(t.text or "")
        out.append("".join(parts))
    return out


def resolve_sheet_paths(z):
    wb = ET.fromstring(z.read("xl/workbook.xml"))
    rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
    relmap = {r.attrib.get("Id"): r.attrib.get("Target") for r in rels}
    sheets = wb.find(f"{{{NS_MAIN}}}sheets")
    if sheets is None or not list(sheets):
        raise ValueError("Excel沒有工作表")
    paths = []
    for sh in list(sheets):
        rid = sh.attrib.get(f"{{{NS_REL}}}id")
        target = relmap.get(rid)
        if not target:
            continue
        if target.startswith("/"):
            path = target.lstrip("/")
        elif target.startswith("xl/"):
            path = target
        else:
            path = "xl/" + target
        paths.append(path)
    if not paths:
        raise ValueError("無法解析工作表")
    return paths


def parse_xlsx(path):
    with zipfile.ZipFile(path, "r") as z:
        shared = read_shared_strings(z)
        sheet_paths = resolve_sheet_paths(z)
        rows = []
        for sheet_path in sheet_paths:
            with z.open(sheet_path) as fh:
                context = ET.iterparse(fh, events=("end",))
                for event, elem in context:
                    if elem.tag == f"{{{NS_MAIN}}}row":
                        row = {}
                        for c in elem.findall(f"{{{NS_MAIN}}}c"):
                            ref = c.attrib.get("r", "")
                            idx = col_to_num(ref)
                            t = c.attrib.get("t")
                            v = c.find(f"{{{NS_MAIN}}}v")
                            is_el = c.find(f"{{{NS_MAIN}}}is")
                            value = ""
                            if t == "s" and v is not None and v.text is not None:
                                try:
                                    value = shared[int(v.text)]
                                except Exception:
                                    value = v.text
                            elif t == "inlineStr" and is_el is not None:
                                value = "".join((x.text or "") for x in is_el.iter(f"{{{NS_MAIN}}}t"))
                            elif v is not None:
                                value = v.text or ""
                            row[idx] = value
                        if row:
                            rows.append(row)
                        elem.clear()
    return rows


def rows_to_records(rows):
    if not rows:
        raise ValueError("Excel沒有資料")
    header_index = None
    mapping = {}
    for i, row in enumerate(rows[:30]):
        labels = {normalize_header(v): idx for idx, v in row.items()}
        found = {}
        for key, aliases in HEADER_ALIASES.items():
            for alias in aliases:
                a = normalize_header(alias)
                if a in labels:
                    found[key] = labels[a]
                    break
        if "part_no" in found and "quantity" in found and "warehouse" in found:
            header_index = i
            mapping = found
            break
    if header_index is None:
        raise ValueError("找不到必要欄位：物料編號/料號、儲存地點/倉庫、庫存量/數量")

    records = []
    skipped = 0
    for row in rows[header_index + 1:]:
        def get(key):
            idx = mapping.get(key)
            return row.get(idx, "") if idx else ""
        part = normalize_part_no(get("part_no"))
        # Taipower SAP material numbers in this workflow are 10-digit numeric IDs.
        # This also prevents repeated sheet headers from being imported as data.
        if not part or not re.fullmatch(r"\d{10}", part):
            skipped += 1
            continue
        rating = str(get("rating") or "").strip()
        warehouse = str(get("warehouse") or "").strip()
        storage_bin = str(get("storage_bin") or "").strip()
        if not warehouse:
            skipped += 1
            continue
        records.append({
            "part_no": part,
            "material_name": str(get("material_name") or "").strip(),
            "rating": rating,
            "warehouse": warehouse,
            "storage_bin": storage_bin,
            "quantity": parse_number(get("quantity")),
            "safety_stock": parse_number(get("safety_stock")),
            "received_date": normalize_date(get("received_date")),
            "last_used_date": normalize_date(get("last_used_date")),
        })

    if not records:
        raise ValueError("解析後沒有有效庫存資料")

    # Deduplicate exact part/rating/warehouse/bin rows. This mirrors the DB primary key.
    agg = {}
    for r in records:
        k = (r["part_no"], r["rating"], r["warehouse"], r["storage_bin"])
        if k not in agg:
            agg[k] = dict(r)
        else:
            agg[k]["quantity"] += r["quantity"]
            agg[k]["safety_stock"] = max(agg[k]["safety_stock"], r["safety_stock"])
            if not agg[k]["material_name"]:
                agg[k]["material_name"] = r["material_name"]
    return list(agg.values()), {"raw_rows": len(records), "valid_rows": len(agg), "skipped_rows": skipped}


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(1024 * 1024)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def file_is_stable_and_valid_xlsx(path, wait_seconds=3):
    s1 = path.stat()
    time.sleep(wait_seconds)
    s2 = path.stat()
    if s1.st_size != s2.st_size or s1.st_mtime_ns != s2.st_mtime_ns:
        return False, "檔案仍在寫入或變動中"
    try:
        with zipfile.ZipFile(path, "r") as z:
            bad = z.testzip()
            if bad:
                return False, f"Excel ZIP 損壞：{bad}"
            required = {"xl/workbook.xml"}
            if not required.issubset(set(z.namelist())):
                return False, "不是有效的 XLSX/XLSM 工作簿"
    except zipfile.BadZipFile:
        return False, "Excel 尚未完成寫入（ZIP 尚未完整）"
    return True, ""


def dpapi_protect(text):
    if os.name != "nt":
        raise RuntimeError("DPAPI僅支援Windows")
    data = text.encode("utf-8")
    class DATA_BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]
    buf = ctypes.create_string_buffer(data)
    blob = DATA_BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
    out = DATA_BLOB()
    crypt = ctypes.windll.crypt32.CryptProtectData
    crypt.argtypes = [ctypes.POINTER(DATA_BLOB), wintypes.LPCWSTR, ctypes.POINTER(DATA_BLOB), wintypes.LPVOID, wintypes.LPVOID, wintypes.DWORD, ctypes.POINTER(DATA_BLOB)]
    if not crypt(ctypes.byref(blob), APP_NAME, None, None, None, 0, ctypes.byref(out)):
        raise ctypes.WinError()
    raw = ctypes.string_at(out.pbData, out.cbData)
    ctypes.windll.kernel32.LocalFree(out.pbData)
    return base64.b64encode(raw).decode("ascii")


def dpapi_unprotect(token):
    if os.name != "nt":
        raise RuntimeError("DPAPI僅支援Windows")
    raw = base64.b64decode(token.encode("ascii"))
    class DATA_BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]
    buf = ctypes.create_string_buffer(raw)
    blob = DATA_BLOB(len(raw), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
    out = DATA_BLOB()
    crypt = ctypes.windll.crypt32.CryptUnprotectData
    crypt.argtypes = [ctypes.POINTER(DATA_BLOB), ctypes.POINTER(wintypes.LPWSTR), ctypes.POINTER(DATA_BLOB), wintypes.LPVOID, wintypes.LPVOID, wintypes.DWORD, ctypes.POINTER(DATA_BLOB)]
    if not crypt(ctypes.byref(blob), None, None, None, None, 0, ctypes.byref(out)):
        raise ctypes.WinError()
    plain = ctypes.string_at(out.pbData, out.cbData).decode("utf-8")
    ctypes.windll.kernel32.LocalFree(out.pbData)
    return plain


def http_json(url, method="GET", payload=None, headers=None):
    data = None
    h = {"Accept": "application/json"}
    if headers:
        h.update(headers)
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        h["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {e.code}: {body[:1000]}")


def save_config(cfg):
    DEFAULT_CONFIG.parent.mkdir(parents=True, exist_ok=True)
    tmp = DEFAULT_CONFIG.with_suffix(".tmp")
    tmp.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, DEFAULT_CONFIG)


def load_config():
    if not DEFAULT_CONFIG.exists():
        return None
    return json.loads(DEFAULT_CONFIG.read_text(encoding="utf-8"))


def supabase_base(cfg):
    return cfg["supabase_url"].rstrip("/")


def login_and_store(cfg):
    email = input("Supabase登入 Email: ").strip()
    password = getpass.getpass("Supabase登入密碼: ")
    key = cfg["supabase_publishable_key"]
    url = supabase_base(cfg) + "/auth/v1/token?grant_type=password"
    data = http_json(url, "POST", {"email": email, "password": password}, {"apikey": key})
    refresh = data.get("refresh_token")
    if not refresh:
        raise RuntimeError("登入成功但沒有取得 refresh_token")
    cfg["agent_email"] = email
    cfg["refresh_token_dpapi"] = dpapi_protect(refresh)
    save_config(cfg)
    log("首次登入完成，refresh token 已使用 Windows DPAPI 加密保存")


def get_access_token(cfg):
    token = cfg.get("refresh_token_dpapi")
    if not token:
        login_and_store(cfg)
        token = cfg.get("refresh_token_dpapi")
    refresh = dpapi_unprotect(token)
    key = cfg["supabase_publishable_key"]
    url = supabase_base(cfg) + "/auth/v1/token?grant_type=refresh_token"
    data = http_json(url, "POST", {"refresh_token": refresh}, {"apikey": key})
    if data.get("refresh_token"):
        cfg["refresh_token_dpapi"] = dpapi_protect(data["refresh_token"])
        save_config(cfg)
    return data["access_token"]


def rpc(cfg, access_token, fn, payload):
    url = supabase_base(cfg) + f"/rest/v1/rpc/{fn}"
    headers = {"apikey": cfg["supabase_publishable_key"], "Authorization": f"Bearer {access_token}"}
    return http_json(url, "POST", payload, headers)


def get_status(cfg, token):
    return rpc(cfg, token, "get_agent_status", {"p_machine_name": cfg.get("machine_name", os.environ.get("COMPUTERNAME", "Windows-Agent"))}) or {}


def heartbeat(cfg, token, status):
    return rpc(cfg, token, "agent_heartbeat", status)


def import_snapshot(cfg, token, path, snapshot_date, file_hash, rows):
    payload = {
        "p_snapshot_date": snapshot_date.isoformat(),
        "p_source_file_name": path.name,
        "p_source_file_hash": file_hash,
        "p_rows": rows,
    }
    return rpc(cfg, token, "import_inventory_snapshot", payload)


def candidate_files(folder, extensions):
    out = []
    if not folder.exists():
        return out
    for p in folder.iterdir():
        if not p.is_file() or p.suffix.lower() not in extensions:
            continue
        d = parse_date_from_name(p.name)
        if d:
            out.append((d, p.stat().st_mtime, p))
    out.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return out


def ensure_config():
    cfg = load_config()
    if cfg:
        return cfg
    print("尚未設定 MaterialMind Agent。")
    print(f"設定檔將建立於：{DEFAULT_CONFIG}")
    folder = input("監控資料夾 [D:\\excel庫存]: ").strip() or r"D:\excel庫存"
    url = input("Supabase URL: ").strip()
    key = input("Supabase Publishable Key: ").strip()
    cfg = {
        "supabase_url": url,
        "supabase_publishable_key": key,
        "watch_folder": folder,
        "scan_interval_seconds": 300,
        "extensions": [".xlsx", ".xlsm"],
        "machine_name": os.environ.get("COMPUTERNAME", "Windows-Agent"),
        "minimum_rows": 20,
        "max_file_age_days": 30,
        "auto_import_only_newer_date": True,
    }
    save_config(cfg)
    return cfg


def main_once(cfg, token):
    folder = Path(cfg["watch_folder"])
    files = candidate_files(folder, set(x.lower() for x in cfg.get("extensions", [".xlsx", ".xlsm"])))
    machine = cfg.get("machine_name") or os.environ.get("COMPUTERNAME", "Windows-Agent")
    if not files:
        heartbeat(cfg, token, {"p_machine_name": machine, "p_status": "WAITING", "p_last_error": None, "p_last_scan": datetime.now().isoformat()})
        log(f"找不到含日期的 Excel：{folder}")
        return

    latest_date, _, latest_path = files[0]
    if latest_date > date.today():
        raise RuntimeError(f"最新檔案日期 {latest_date} 超過今天 {date.today()}，停止自動匯入")
    age_days = (date.today() - latest_date).days
    max_age = int(cfg.get("max_file_age_days", 30))
    if age_days > max_age:
        log(f"最新檔案已經 {age_days} 天未更新（門檻 {max_age} 天），等待新檔", "WARN")
        heartbeat(cfg, token, {"p_machine_name": cfg.get("machine_name", os.environ.get("COMPUTERNAME", "Windows-Agent")), "p_status": "WARNING", "p_last_file": latest_path.name, "p_last_error": f"檔案日期過舊：{latest_date}", "p_last_scan": datetime.now().isoformat()})
        return
    stable, stable_msg = file_is_stable_and_valid_xlsx(latest_path)
    if not stable:
        log(f"暫不處理：{stable_msg}", "WARN")
        heartbeat(cfg, token, {"p_machine_name": cfg.get("machine_name", os.environ.get("COMPUTERNAME", "Windows-Agent")), "p_status": "WARNING", "p_last_file": latest_path.name, "p_last_error": stable_msg, "p_last_scan": datetime.now().isoformat()})
        return
    file_hash = sha256_file(latest_path)
    log(f"偵測最新檔案：{latest_path.name} | 日期={latest_date} | SHA256={file_hash[:16]}...")

    status = get_status(cfg, token)
    last_date = status.get("last_imported_date") if isinstance(status, dict) else None
    last_hash = status.get("last_imported_hash") if isinstance(status, dict) else None
    if last_date and latest_date.isoformat() < last_date:
        log(f"最新檔案日期 {latest_date} 早於資料庫最後同步日 {last_date}，跳過")
        heartbeat(cfg, token, {"p_machine_name": machine, "p_status": "UP_TO_DATE", "p_last_file": latest_path.name, "p_last_scan": datetime.now().isoformat()})
        return
    if last_date and latest_date.isoformat() == last_date and last_hash == file_hash:
        heartbeat(cfg, token, {"p_machine_name": machine, "p_status": "UP_TO_DATE", "p_last_file": latest_path.name, "p_last_scan": datetime.now().isoformat()})
        log("最新檔案已同步，無需再次匯入")
        return
    if last_date and latest_date.isoformat() == last_date and last_hash != file_hash:
        msg = "同一日期出現不同內容的 Excel；為避免覆蓋已確認的日快照，V2預設停止自動匯入。"
        log(msg, "WARN")
        heartbeat(cfg, token, {"p_machine_name": machine, "p_status": "WARNING", "p_last_file": latest_path.name, "p_last_error": msg, "p_last_scan": datetime.now().isoformat()})
        return

    heartbeat(cfg, token, {"p_machine_name": machine, "p_status": "PARSING", "p_last_file": latest_path.name, "p_last_scan": datetime.now().isoformat()})
    rows_raw = parse_xlsx(latest_path)
    rows, stats = rows_to_records(rows_raw)
    if len(rows) < int(cfg.get("minimum_rows", 20)):
        raise RuntimeError(f"有效資料只有 {len(rows)} 筆，低於安全門檻 {cfg.get('minimum_rows',20)}，停止匯入")

    result = import_snapshot(cfg, token, latest_path, latest_date, file_hash, rows)
    heartbeat(cfg, token, {"p_machine_name": machine, "p_status": "SYNCED", "p_last_file": latest_path.name, "p_last_imported_date": latest_date.isoformat(), "p_last_imported_hash": file_hash, "p_last_scan": datetime.now().isoformat(), "p_last_error": None})
    log(f"自動同步完成：{latest_path.name} | rows={stats['valid_rows']} | changes={result.get('change_count')} | previous={result.get('previous_snapshot_id')}")


def run():
    cfg = ensure_config()
    while True:
        try:
            token = get_access_token(cfg)
            main_once(cfg, token)
        except KeyboardInterrupt:
            log("Agent已停止")
            break
        except Exception as e:
            log(f"錯誤：{e}", "ERROR")
            try:
                token = get_access_token(cfg)
                heartbeat(cfg, token, {"p_machine_name": cfg.get("machine_name", os.environ.get("COMPUTERNAME", "Windows-Agent")), "p_status": "ERROR", "p_last_error": str(e), "p_last_scan": datetime.now().isoformat()})
            except Exception:
                pass
        time.sleep(max(60, int(cfg.get("scan_interval_seconds", 300))))


def setup_interactive():
    cfg = ensure_config()
    if not cfg.get("supabase_url") or "YOUR_PROJECT" in cfg.get("supabase_url", "") or not cfg.get("supabase_publishable_key") or "YOUR_PUBLISHABLE" in cfg.get("supabase_publishable_key", ""):
        cfg["supabase_url"] = input("Supabase URL: ").strip()
        cfg["supabase_publishable_key"] = input("Supabase Publishable Key: ").strip()
        save_config(cfg)
    login_and_store(cfg)
    print("設定完成。現在可以執行 install_agent.ps1 建立 Windows 自動啟動工作。")


def dry_run(path):
    rows = parse_xlsx(Path(path))
    records, stats = rows_to_records(rows)
    print(json.dumps({"file": path, "stats": stats, "sample": records[:5]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--dry-run":
        dry_run(sys.argv[2])
    elif len(sys.argv) == 2 and sys.argv[1] == "--setup":
        setup_interactive()
    else:
        run()
