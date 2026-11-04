import os, json
from datetime import datetime
from zoneinfo import ZoneInfo
import gspread
from fastmcp import FastMCP

if os.environ.get("GOOGLE_CREDS_JSON"):
    gc = gspread.service_account_from_dict(json.loads(os.environ["GOOGLE_CREDS_JSON"]))
else:
    gc = gspread.service_account(filename=os.environ["GOOGLE_CREDS_FILE"])
ws = gc.open_by_key(os.environ["SHEET_ID"]).sheet1
mcp = FastMCP("line-registration")

def headers():
    return [h.strip() for h in ws.row_values(1)]

def find_row(uid):
    cell = ws.find(uid, in_column=1)
    return cell.row if cell else None

@mcp.tool()
def get_user(line_user_id: str) -> dict:
    """เช็กว่า user ลงทะเบียนแล้วหรือยัง และคืนข้อมูลทั้งหมด"""
    row = find_row(line_user_id)
    if not row:
        return {"registered": False}
    h = headers()
    v = ws.row_values(row)
    v += [""] * (len(h) - len(v))
    return {"registered": True, **dict(zip(h, v))}

@mcp.tool()
def register_user(
    line_user_id: str, nickname: str, province: str, district: str,
    subdistrict: str = "", occupation: str = "", vulnerable: str = "",
    active_hours: str = "", morning_time: str = "07:00",
    morning_enabled: bool = True, consent: bool = False,
) -> str:
    """ลงทะเบียนหรืออัปเดต เรียกหลังผู้ใช้ให้ข้อมูลครบและยินยอมแล้วเท่านั้น"""
    if not consent:
        return "error: ต้องได้รับความยินยอมจากผู้ใช้ก่อน"
    h = headers()
    now = datetime.now(ZoneInfo("Asia/Bangkok")).strftime("%Y-%m-%d %H:%M:%S")
    data = {
        "line_user_id": line_user_id, "nickname": nickname,
        "province": province, "district": district, "subdistrict": subdistrict,
        "occupation": occupation, "vulnerable": vulnerable,
        "active_hours": active_hours, "morning_time": morning_time,
        "morning_enabled": "TRUE" if morning_enabled else "FALSE",
    }
    row = find_row(line_user_id)
    if row:
        old = dict(zip(h, ws.row_values(row)))
        for k in ("consent_at", "last_sent_date", "created_at"):
            data[k] = old.get(k, "")
        data["consent_at"] = data["consent_at"] or now
        ws.update(values=[[data.get(c, "") for c in h]],
                  range_name=f"A{row}", value_input_option="RAW")
        return "updated"
    data["consent_at"] = now
    data["created_at"] = now
    ws.append_row([data.get(c, "") for c in h], value_input_option="RAW")
    return "registered"

mcp.run(transport="http", host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))