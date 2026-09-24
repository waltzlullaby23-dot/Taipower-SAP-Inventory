#!/usr/bin/env python3
# MaterialMind V3 - Windows Folder Auto-Sync Agent
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

HEADER_ALIASES = {
    "part_no": ["物料編號","料號","物料號碼","物料","Material","Material Number"],
    "material_name": ["名稱規範","材料名稱","物料名稱","名稱","Description","Material Description"],
    "rating": ["評價","評價類型","Valuation Type","Valuation"],
    "warehouse": ["儲存地點","倉庫","Storage Location","Plant Storage Location"],
    "storage_bin": ["儲格","Storage Bin","Bin"],
    "quantity": ["庫存量","庫存","數量","Unrestricted","Qty","Quantity"],
    "safety_stock": ["安全庫存","Safety Stock"],
    "received_date": ["最後收料日期","最後收料","Last Receipt Date"],
    "last_used_date": ["最後使用日期","最後使用","Last Issue Date"],
}

def log(msg, level="INFO"):
    DEFAULT_LOG.parent.mkdir(parents=True, exist_ok=True)
    line=f"{datetime.now().isoformat(timespec='seconds')} [{level}] {msg}"
    print(line, flush=True)
    try:
        with DEFAULT_LOG.open("a",encoding="utf-8") as f: f.write(line+"\n")
    except Exception: pass

def normalize_header(v):
    return re.sub(r"\s+","",str(v or "")).strip().lower()

def parse_date_from_name(name):
    for p in (r"(?<!\d)(20\d{2})[-_./](\d{1,2})[-_./](\d{1,2})(?!\d)",
              r"(?<!\d)(20\d{2})(\d{2})(\d{2})(?!\d)"):
        m=re.search(p,name)
        if m:
            try:return date(int(m.group(1)),int(m.group(2)),int(m.group(3)))
            except ValueError: pass
    return None

def parse_number(v):
    if v is None or v=="": return 0.0
    if isinstance(v,(int,float)): return float(v)
    s=str(v).strip().replace(",","")
    if not s:return 0.0
    if s.endswith(".0") and s[:-2].isdigit():s=s[:-2]
    try:return float(s)
    except ValueError:return 0.0

def normalize_part_no(v):
    s=str(v or "").strip().replace(" ","").replace("\t","")
    if s.endswith(".0") and s[:-2].isdigit():s=s[:-2]
    if not s.isdigit():return ""
    return s.zfill(10) if len(s)<=10 else ""

def excel_serial_to_date(v):
    try:return (datetime(1899,12,30)+timedelta(days=float(v))).date().isoformat()
    except Exception:return None

def normalize_date(v):
    if v is None or v=="":return None
    if isinstance(v,(int,float)):return excel_serial_to_date(v)
    s=str(v).strip()
    if re.fullmatch(r"\d+(?:\.\d+)?",s):
        try:
            n=float(s)
            if 20000<=n<=80000:return excel_serial_to_date(n)
        except Exception:pass
    for fmt in ("%Y/%m/%d","%Y-%m-%d","%Y.%m.%d","%Y%m%d","%Y/%m/%d %H:%M:%S","%Y-%m-%d %H:%M:%S"):
        try:return datetime.strptime(s,fmt).date().isoformat()
        except ValueError:pass
    return None

def col_to_num(ref):
    m=re.match(r"([A-Z]+)",ref.upper())
    if not m:return 0
    n=0
    for c in m.group(1):n=n*26+ord(c)-64
    return n

def read_shared_strings(z):
    if "xl/sharedStrings.xml" not in z.namelist():return []
    root=ET.fromstring(z.read("xl/sharedStrings.xml"));out=[]
    for si in root:
        out.append("".join((t.text or "") for t in si.iter(f"{{{NS_MAIN}}}t")))
    return out

def resolve_sheet_paths(z):
    wb=ET.fromstring(z.read("xl/workbook.xml"))
    rels=ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
    relmap={r.attrib.get("Id"):r.attrib.get("Target") for r in rels}
    sheets=wb.find(f"{{{NS_MAIN}}}sheets")
    if sheets is None:raise ValueError("Excel沒有工作表")
    paths=[]
    for sh in list(sheets):
        rid=sh.attrib.get(f"{{{NS_REL}}}id");target=relmap.get(rid)
        if not target:continue
        if target.startswith("/"):path=target.lstrip("/")
        elif target.startswith("xl/"):path=target
        else:path="xl/"+target
        paths.append((sh.attrib.get("name",""),path))
    if not paths:raise ValueError("無法解析工作表")
    return paths

def parse_xlsx(path):
    with zipfile.ZipFile(path,"r") as z:
        shared=read_shared_strings(z);sheets=[]
        for sheet_name,sheet_path in resolve_sheet_paths(z):
            rows=[]
            with z.open(sheet_path) as fh:
                for _,elem in ET.iterparse(fh,events=("end",)):
                    if elem.tag==f"{{{NS_MAIN}}}row":
                        row={}
                        for c in elem.findall(f"{{{NS_MAIN}}}c"):
                            idx=col_to_num(c.attrib.get("r",""));typ=c.attrib.get("t")
                            v=c.find(f"{{{NS_MAIN}}}v");is_el=c.find(f"{{{NS_MAIN}}}is");value=""
                            if typ=="s" and v is not None and v.text is not None:
                                try:value=shared[int(v.text)]
                                except Exception:value=v.text
                            elif typ=="inlineStr" and is_el is not None:
                                value="".join((x.text or "") for x in is_el.iter(f"{{{NS_MAIN}}}t"))
                            elif v is not None:value=v.text or ""
                            row[idx]=value
                        if row:rows.append(row)
                        elem.clear()
            sheets.append((sheet_name,rows))
    return sheets

def rows_to_records(sheets):
    total_raw=valid=skipped=0;agg={}
    for sheet_name,rows in sheets:
        if not rows:continue
        header_index=None;mapping={}
        for i,row in enumerate(rows[:50]):
            labels={normalize_header(v):idx for idx,v in row.items()}
            found={}
            for key,aliases in HEADER_ALIASES.items():
                for alias in aliases:
                    a=normalize_header(alias)
                    if a in labels:found[key]=labels[a];break
            if "part_no" in found and "quantity" in found and "warehouse" in found:
                header_index=i;mapping=found;break
        if header_index is None:continue
        for row in rows[header_index+1:]:
            total_raw+=1
            def get(key):
                idx=mapping.get(key)
                return row.get(idx,"") if idx is not None else ""
            part=normalize_part_no(get("part_no"))
            if not part or not re.fullmatch(r"\d{10}",part):skipped+=1;continue
            warehouse=str(get("warehouse") or "").strip()
            if not warehouse:skipped+=1;continue
            rec={"part_no":part,"material_name":str(get("material_name") or "").strip(),
                 "rating":str(get("rating") or "").strip(),"warehouse":warehouse,
                 "storage_bin":str(get("storage_bin") or "").strip(),
                 "quantity":parse_number(get("quantity")),
                 "safety_stock":parse_number(get("safety_stock")),
                 "received_date":normalize_date(get("received_date")),
                 "last_used_date":normalize_date(get("last_used_date"))}
            k=(rec["part_no"],rec["rating"],rec["warehouse"],rec["storage_bin"])
            if k in agg:
                agg[k]["quantity"]+=rec["quantity"]
                agg[k]["safety_stock"]=max(agg[k]["safety_stock"],rec["safety_stock"])
                if not agg[k]["material_name"]:agg[k]["material_name"]=rec["material_name"]
            else:agg[k]=rec
            valid+=1
    if not agg:raise ValueError("解析後沒有有效庫存資料")
    return list(agg.values()),{"raw_rows":total_raw,"valid_rows":len(agg),"skipped_rows":skipped}

def sha256_file(path):
    h=hashlib.sha256()
    with open(path,"rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""):h.update(b)
    return h.hexdigest()

def file_is_stable_and_valid_xlsx(path,wait_seconds=3):
    s1=path.stat();time.sleep(wait_seconds);s2=path.stat()
    if s1.st_size!=s2.st_size or s1.st_mtime_ns!=s2.st_mtime_ns:return False,"檔案仍在寫入或變動中"
    try:
        with zipfile.ZipFile(path,"r") as z:
            bad=z.testzip()
            if bad:return False,f"Excel ZIP 損壞：{bad}"
            if "xl/workbook.xml" not in z.namelist():return False,"不是有效的 XLSX/XLSM 工作簿"
    except zipfile.BadZipFile:return False,"Excel 尚未完成寫入（ZIP 尚未完整）"
    return True,""

def dpapi_protect(text):
    if os.name!="nt":raise RuntimeError("DPAPI僅支援Windows")
    data=text.encode("utf-8")
    class DATA_BLOB(ctypes.Structure):_fields_=[("cbData",wintypes.DWORD),("pbData",ctypes.POINTER(ctypes.c_char))]
    buf=ctypes.create_string_buffer(data);blob=DATA_BLOB(len(data),ctypes.cast(buf,ctypes.POINTER(ctypes.c_char)));out=DATA_BLOB()
    crypt=ctypes.windll.crypt32.CryptProtectData
    crypt.argtypes=[ctypes.POINTER(DATA_BLOB),wintypes.LPCWSTR,ctypes.POINTER(DATA_BLOB),wintypes.LPVOID,wintypes.LPVOID,wintypes.DWORD,ctypes.POINTER(DATA_BLOB)]
    if not crypt(ctypes.byref(blob),APP_NAME,None,None,None,0,ctypes.byref(out)):raise ctypes.WinError()
    raw=ctypes.string_at(out.pbData,out.cbData);ctypes.windll.kernel32.LocalFree(out.pbData)
    return base64.b64encode(raw).decode("ascii")

def dpapi_unprotect(token):
    if os.name!="nt":raise RuntimeError("DPAPI僅支援Windows")
    raw=base64.b64decode(token.encode("ascii"))
    class DATA_BLOB(ctypes.Structure):_fields_=[("cbData",wintypes.DWORD),("pbData",ctypes.POINTER(ctypes.c_char))]
    buf=ctypes.create_string_buffer(raw);blob=DATA_BLOB(len(raw),ctypes.cast(buf,ctypes.POINTER(ctypes.c_char)));out=DATA_BLOB()
    crypt=ctypes.windll.crypt32.CryptUnprotectData
    crypt.argtypes=[ctypes.POINTER(DATA_BLOB),ctypes.POINTER(wintypes.LPWSTR),ctypes.POINTER(DATA_BLOB),wintypes.LPVOID,wintypes.LPVOID,wintypes.DWORD,ctypes.POINTER(DATA_BLOB)]
    if not crypt(ctypes.byref(blob),None,None,None,None,0,ctypes.byref(out)):raise ctypes.WinError()
    plain=ctypes.string_at(out.pbData,out.cbData).decode("utf-8");ctypes.windll.kernel32.LocalFree(out.pbData);return plain

def http_json(url,method="GET",payload=None,headers=None):
    data=None;h={"Accept":"application/json"}
    if headers:h.update(headers)
    if payload is not None:data=json.dumps(payload,ensure_ascii=False).encode("utf-8");h["Content-Type"]="application/json"
    try:
        with urllib.request.urlopen(urllib.request.Request(url,data=data,headers=h,method=method),timeout=45) as resp:
            raw=resp.read().decode("utf-8");return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        body=e.read().decode("utf-8",errors="replace");raise RuntimeError(f"HTTP {e.code}: {body[:1000]}")

def save_config(cfg):
    DEFAULT_CONFIG.parent.mkdir(parents=True,exist_ok=True);tmp=DEFAULT_CONFIG.with_suffix(".tmp")
    tmp.write_text(json.dumps(cfg,ensure_ascii=False,indent=2),encoding="utf-8");os.replace(tmp,DEFAULT_CONFIG)

def load_config():
    if not DEFAULT_CONFIG.exists():return None
    return json.loads(DEFAULT_CONFIG.read_text(encoding="utf-8"))

def supabase_base(cfg):return cfg["supabase_url"].rstrip("/")

def login_and_store(cfg):
    email=input("Supabase登入 Email: ").strip();password=getpass.getpass("Supabase登入密碼: ")
    data=http_json(supabase_base(cfg)+"/auth/v1/token?grant_type=password","POST",{"email":email,"password":password},{"apikey":cfg["supabase_publishable_key"]})
    refresh=data.get("refresh_token")
    if not refresh:raise RuntimeError("登入成功但沒有取得 refresh_token")
    cfg["agent_email"]=email;cfg["refresh_token_dpapi"]=dpapi_protect(refresh);save_config(cfg);log("首次登入完成")

def get_access_token(cfg):
    token=cfg.get("refresh_token_dpapi")
    if not token:login_and_store(cfg);token=cfg.get("refresh_token_dpapi")
    data=http_json(supabase_base(cfg)+"/auth/v1/token?grant_type=refresh_token","POST",{"refresh_token":dpapi_unprotect(token)},{"apikey":cfg["supabase_publishable_key"]})
    if data.get("refresh_token"):cfg["refresh_token_dpapi"]=dpapi_protect(data["refresh_token"]);save_config(cfg)
    if not data.get("access_token"):raise RuntimeError("重新取得 Access Token 失敗")
    return data["access_token"]

def rpc(cfg,token,fn,payload):return http_json(supabase_base(cfg)+f"/rest/v1/rpc/{fn}","POST",payload,{"apikey":cfg["supabase_publishable_key"],"Authorization":f"Bearer {token}"})

def heartbeat(cfg,token,status):return rpc(cfg,token,"agent_heartbeat",status)
def get_status(cfg,token):return rpc(cfg,token,"get_agent_status",{"p_machine_name":cfg.get("machine_name",os.environ.get("COMPUTERNAME","Windows-Agent"))}) or {}
def get_latest_snapshot(cfg,token):return rpc(cfg,token,"get_latest_snapshot_status",{}) or {}
def import_snapshot(cfg,token,path,snapshot_date,file_hash,rows):
    return rpc(cfg,token,"import_inventory_snapshot",{"p_snapshot_date":snapshot_date.isoformat(),"p_source_file_name":path.name,"p_source_file_hash":file_hash,"p_rows":rows})

def candidate_files(folder,extensions):
    out=[]
    if not folder.exists():return out
    for p in folder.iterdir():
        if not p.is_file() or p.suffix.lower() not in extensions:continue
        d=parse_date_from_name(p.name)
        if d:out.append((d,p.stat().st_mtime_ns,p))
    return sorted(out,key=lambda x:(x[0],x[1]),reverse=True)

def ensure_config():
    cfg=load_config()
    if cfg:return cfg
    folder=input(r"監控資料夾 [D:\excel庫存]: ").strip() or r"D:\excel庫存"
    url=input("Supabase URL: ").strip();key=input("Supabase Publishable Key: ").strip()
    cfg={"supabase_url":url,"supabase_publishable_key":key,"watch_folder":folder,"scan_interval_seconds":300,
         "extensions":[".xlsx",".xlsm"],"machine_name":os.environ.get("COMPUTERNAME","Windows-Agent"),
         "minimum_rows":20,"max_file_age_days":30}
    save_config(cfg);return cfg

def main_once(cfg,token):
    folder=Path(cfg["watch_folder"]);files=candidate_files(folder,set(x.lower() for x in cfg.get("extensions",[".xlsx",".xlsm"])))
    machine=cfg.get("machine_name") or os.environ.get("COMPUTERNAME","Windows-Agent")
    if not files:
        heartbeat(cfg,token,{"p_machine_name":machine,"p_status":"WAITING","p_last_error":None,"p_last_scan":datetime.now().astimezone().isoformat()});return
    latest_date,_,latest_path=files[0]
    if latest_date>date.today():raise RuntimeError(f"最新檔案日期 {latest_date} 超過今天 {date.today()}，停止自動匯入")
    age_days=(date.today()-latest_date).days;max_age=int(cfg.get("max_file_age_days",30))
    if age_days>max_age:
        msg=f"檔案日期過舊：{latest_date}（{age_days}天）"
        heartbeat(cfg,token,{"p_machine_name":machine,"p_status":"WARNING","p_last_file":latest_path.name,"p_last_error":msg,"p_last_scan":datetime.now().astimezone().isoformat()});return
    stable,msg=file_is_stable_and_valid_xlsx(latest_path)
    if not stable:
        heartbeat(cfg,token,{"p_machine_name":machine,"p_status":"WARNING","p_last_file":latest_path.name,"p_last_error":msg,"p_last_scan":datetime.now().astimezone().isoformat()});return
    file_hash=sha256_file(latest_path)
    central=get_latest_snapshot(cfg,token)
    central_date=central.get("snapshot_date");central_hash=central.get("source_file_hash")
    if central_date:
        cd=date.fromisoformat(central_date)
        if latest_date<cd:
            heartbeat(cfg,token,{"p_machine_name":machine,"p_status":"UP_TO_DATE","p_last_file":latest_path.name,"p_last_scan":datetime.now().astimezone().isoformat()});return
        if latest_date==cd and central_hash==file_hash:
            heartbeat(cfg,token,{"p_machine_name":machine,"p_status":"UP_TO_DATE","p_last_file":latest_path.name,"p_last_imported_date":central_date,"p_last_imported_hash":central_hash,"p_last_scan":datetime.now().astimezone().isoformat()});return
        if latest_date==cd and central_hash!=file_hash:
            msg="同一日期已有不同 SHA-256 的快照；系統停止自動覆蓋，請人工確認。"
            heartbeat(cfg,token,{"p_machine_name":machine,"p_status":"WARNING","p_last_file":latest_path.name,"p_last_error":msg,"p_last_scan":datetime.now().astimezone().isoformat()});return
    heartbeat(cfg,token,{"p_machine_name":machine,"p_status":"PARSING","p_last_file":latest_path.name,"p_last_scan":datetime.now().astimezone().isoformat()})
    sheets=parse_xlsx(latest_path);rows,stats=rows_to_records(sheets)
    if len(rows)<int(cfg.get("minimum_rows",20)):raise RuntimeError(f"有效資料只有 {len(rows)} 筆，低於安全門檻 {cfg.get('minimum_rows',20)}")
    result=import_snapshot(cfg,token,latest_path,latest_date,file_hash,rows)
    heartbeat(cfg,token,{"p_machine_name":machine,"p_status":"SYNCED","p_last_file":latest_path.name,"p_last_imported_date":latest_date.isoformat(),"p_last_imported_hash":file_hash,"p_last_scan":datetime.now().astimezone().isoformat(),"p_last_error":None})
    log(f"自動同步完成：{latest_path.name} | rows={stats['valid_rows']} | changes={result.get('change_count')}")

def run():
    cfg=ensure_config()
    while True:
        try:main_once(cfg,get_access_token(cfg))
        except KeyboardInterrupt:log("Agent已停止");break
        except Exception as e:
            log(f"錯誤：{e}","ERROR")
            try:
                heartbeat(cfg,get_access_token(cfg),{"p_machine_name":cfg.get("machine_name",os.environ.get("COMPUTERNAME","Windows-Agent")),"p_status":"ERROR","p_last_error":str(e),"p_last_scan":datetime.now().astimezone().isoformat()})
            except Exception:pass
        time.sleep(max(60,int(cfg.get("scan_interval_seconds",300))))

def setup_interactive():
    cfg=ensure_config()
    if not cfg.get("supabase_url") or "YOUR_PROJECT" in cfg.get("supabase_url","") or not cfg.get("supabase_publishable_key") or "YOUR_PUBLISHABLE" in cfg.get("supabase_publishable_key",""):
        cfg["supabase_url"]=input("Supabase URL: ").strip();cfg["supabase_publishable_key"]=input("Supabase Publishable Key: ").strip();save_config(cfg)
    login_and_store(cfg);print("設定完成。可執行 install_agent.ps1 建立 Windows 自動啟動工作。")

def dry_run(path):
    rows=parse_xlsx(Path(path));records,stats=rows_to_records(rows)
    print(json.dumps({"file":path,"stats":stats,"sample":records[:5]},ensure_ascii=False,indent=2))

if __name__=="__main__":
    if len(sys.argv)==3 and sys.argv[1]=="--dry-run":dry_run(sys.argv[2])
    elif len(sys.argv)==2 and sys.argv[1]=="--setup":setup_interactive()
    else:run()
