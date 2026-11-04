import os, json
from datetime import datetime
from zoneinfo import ZoneInfo
import gspread
from fastmcp import FastMCP

# ---------- เชื่อม Google Sheets ----------
if os.environ.get("GOOGLE_CREDS_JSON"):
    gc = gspread.service_account_from_dict(json.loads(os.environ["GOOGLE_CREDS_JSON"]))
else:
    gc = gspread.service_account(filename=os.environ["GOOGLE_CREDS_FILE"])

ws = gc.open_by_key(os.environ["SHEET_ID"]).sheet1
mcp = FastMCP("line-registration")


# ---------- ฟังก์ชันช่วย ----------
def headers():
    return [h.strip() for h in ws.row_values(1)]


def find_row(uid):
    cell = ws.find(uid, in_column=1)
    return cell.row if cell else None


def s(v):
    return "" if v is None else str(v).strip()


# ---------- หน้าตรวจสุขภาพ (ใช้ให้ cron ปลุกเซิร์ฟเวอร์) ----------
if hasattr(mcp, "custom_route"):
    from starlette.responses import PlainTextResponse

    @mcp.custom_route("/health", methods=["GET"])
    async def health(request):
        return PlainTextResponse("ok")


# ---------- Tool 1: เช็กผู้ใช้ ----------
@mcp.tool()
def get_user(line_user_id: str) -> dict:
    """เช็กว่า user ลงทะเบียนแล้วหรือยัง และคืนข้อมูลทั้งหมด"""
    print("get_user called:", repr(line_user_id), flush=True)
    try:
        uid = s(line_user_id)
        if not uid:
            return {"registered": False, "error": "line_user_id is empty"}
        row = find_row(uid)
        if not row:
            return {"registered": False}
        h = headers()
        v = ws.row_values(row)
        v += [""] * (len(h) - len(v))
        return {"registered": True, **dict(zip(h, v))}
    except Exception as e:
        print("get_user error:", repr(e), flush=True)
        return {"registered": False, "error": str(e)}


# ---------- Tool 2: ลงทะเบียน/อัปเดต ----------
@mcp.tool()
def register_user(
    line_user_id: str,
    nickname: str,
    province: str,
    district: str,
    subdistrict: str = "",
    occupation: str = "",
    vulnerable: str = "",
    active_hours: str = "",
    morning_time: str = "",
    morning_enabled: bool = True,
    consent: bool = False,
) -> str:
    """ลงทะเบียนหรืออัปเดต เรียกหลังผู้ใช้ให้ข้อมูลครบและยินยอมแล้วเท่านั้น"""
    print("register_user called:", line_user_id, nickname, province, district,
          "consent=", consent, flush=True)
    try:
        if not consent:
            return "error: ต้องได้รับความยินยอมจากผู้ใช้ก่อน"
        uid = s(line_user_id)
        if not uid:
            return "error: line_user_id is empty"

        h = headers()
        now = datetime.now(ZoneInfo("Asia/Bangkok")).strftime("%Y-%m-%d %H:%M:%S")

        new = {
            "line_user_id": uid,
            "nickname": s(nickname),
            "province": s(province),
            "district": s(district),
        }
        optional = {
            "subdistrict": subdistrict,
            "occupation": occupation,
            "vulnerable": vulnerable,
            "active_hours": active_hours,
            "morning_time": morning_time,
        }
        for k, v in optional.items():
            if s(v):
                new[k] = s(v)
        new["morning_enabled"] = "TRUE" if morning_enabled else "FALSE"

        row = find_row(uid)
        if row:
            old = dict(zip(h, ws.row_values(row)))
            data = {**old, **new}
            data["consent_at"] = old.get("consent_at") or now
            ws.update(values=[[data.get(c, "") for c in h]],
                      range_name=f"A{row}", value_input_option="RAW")
            return "updated"

        new.setdefault("morning_time", "07:00")
        new["consent_at"] = now
        new["created_at"] = now
        ws.append_row([new.get(c, "") for c in h], value_input_option="RAW")
        return "registered"
    except Exception as e:
        print("register_user error:", repr(e), flush=True)
        return f"error: {e}"


# ---------- เริ่มเซิร์ฟเวอร์ ----------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    try:
        mcp.run(transport="http", host="0.0.0.0", port=port, stateless_http=True)
    except TypeError:
        # FastMCP เวอร์ชันที่ไม่รองรับ stateless_http
        mcp.run(transport="http", host="0.0.0.0", port=port)
