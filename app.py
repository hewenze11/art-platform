#!/usr/bin/env python3
"""
Art Platform - 美术资源管理平台
  - ArtSlot（资源位）: 游戏中一个美术需求，有唯一 game_key
  - ArtResource（资源）: 资源位下的具体文件
    status: active(绿) | inactive(黄) | pending_delete(红)
  - PlaceholderResource（占位资源库）: 当资源位无 active 时随机返回同类型占位资源
  - Manifest: 游戏读取接口
"""
import os, json, uuid, mimetypes, html
from datetime import datetime
from flask import Flask, request, jsonify, send_from_directory, send_file, Response
from flask_cors import CORS
import sqlite3

DATA_DIR   = os.environ.get("DATA_DIR", "/data")
DB_PATH    = os.path.join(DATA_DIR, "artplatform.db")
UPLOAD_DIR = os.path.join(DATA_DIR, "uploads")

BUILTIN_PLACEHOLDERS = [
    {"name": "爱因斯坦",   "asset_type": "image", "url": "https://upload.wikimedia.org/wikipedia/commons/thumb/d/d3/Albert_Einstein_Head.jpg/480px-Albert_Einstein_Head.jpg"},
    {"name": "可爱橘猫",   "asset_type": "image", "url": "https://upload.wikimedia.org/wikipedia/commons/thumb/3/3a/Cat03.jpg/481px-Cat03.jpg"},
    {"name": "小蚂蚁",     "asset_type": "image", "url": "https://upload.wikimedia.org/wikipedia/commons/thumb/a/a7/Camponotus_flavomarginatus_ant.jpg/400px-Camponotus_flavomarginatus_ant.jpg"},
    {"name": "彩色方块",   "asset_type": "image", "url": "https://upload.wikimedia.org/wikipedia/commons/thumb/4/47/PNG_transparency_demonstration_1.png/280px-PNG_transparency_demonstration_1.png"},
    {"name": "生日快乐",   "asset_type": "audio", "url": "https://upload.wikimedia.org/wikipedia/commons/7/7e/Happy_Birthday_to_You.ogg"},
    {"name": "巴赫赋格曲", "asset_type": "audio", "url": "https://upload.wikimedia.org/wikipedia/commons/4/4e/BWV_543_fugue.ogg"},
    {"name": "月光奏鸣曲", "asset_type": "audio", "url": "https://upload.wikimedia.org/wikipedia/commons/6/6e/Piano_sonata_no_14_3rd_movement.ogg"},
    {"name": "示例视频",   "asset_type": "video", "url": "https://www.w3schools.com/html/mov_bbb.mp4"},
]

ALLOWED_EXT = {
    "image": {"png","jpg","jpeg","gif","webp","svg"},
    "audio": {"mp3","wav","ogg","aac"},
    "video": {"mp4","webm"},
}
MAX_MB = 50

app = Flask(__name__, template_folder="templates")
CORS(app)
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def now_iso():
    return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

def init_db():
    with get_db() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS art_slots (
            id TEXT PRIMARY KEY, game_key TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL, description TEXT DEFAULT '',
            asset_type TEXT DEFAULT 'image', category TEXT DEFAULT '其他',
            metadata TEXT DEFAULT '{}', created_by TEXT DEFAULT 'user',
            placeholder_id TEXT DEFAULT NULL,
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS art_resources (
            id TEXT PRIMARY KEY, slot_id TEXT NOT NULL,
            filename TEXT NOT NULL, original_name TEXT NOT NULL,
            file_size INTEGER DEFAULT 0, mime_type TEXT DEFAULT '',
            status TEXT DEFAULT 'inactive', source_url TEXT DEFAULT '',
            note TEXT DEFAULT '', uploaded_by TEXT DEFAULT 'user',
            uploaded_at TEXT NOT NULL,
            FOREIGN KEY (slot_id) REFERENCES art_slots(id)
        );
        CREATE TABLE IF NOT EXISTS placeholder_resources (
            id TEXT PRIMARY KEY, name TEXT NOT NULL,
            asset_type TEXT NOT NULL, url TEXT NOT NULL,
            is_builtin INTEGER DEFAULT 0, created_at TEXT NOT NULL
        );
        """)
        existing_urls = {r["url"] for r in conn.execute("SELECT url FROM placeholder_resources WHERE is_builtin=1").fetchall()}
        now = now_iso()
        for p in BUILTIN_PLACEHOLDERS:
            if p["url"] not in existing_urls:
                conn.execute(
                    "INSERT INTO placeholder_resources (id,name,asset_type,url,is_builtin,created_at) VALUES (?,?,?,?,1,?)",
                    (str(uuid.uuid4()), p["name"], p["asset_type"], p["url"], now)
                )
    print(f"[DB] 初始化完成: {DB_PATH}")

def get_placeholder_url(conn, asset_type):
    rows = conn.execute("SELECT url FROM placeholder_resources WHERE asset_type=? ORDER BY RANDOM() LIMIT 1", (asset_type,)).fetchall()
    if rows: return rows[0]["url"]
    fallback = {"image": BUILTIN_PLACEHOLDERS[0]["url"], "audio": BUILTIN_PLACEHOLDERS[4]["url"], "video": BUILTIN_PLACEHOLDERS[7]["url"]}
    return fallback.get(asset_type, "")

def get_slot_placeholder_url(conn, slot):
    """占位优先级：手动指定占位库 > 文字SVG占位"""
    pid = slot.get("placeholder_id")
    if pid:
        row = conn.execute("SELECT url FROM placeholder_resources WHERE id=?", (pid,)).fetchone()
        if row:
            return row["url"], False
    # 文字SVG占位（动态生成）
    host = request.host_url.rstrip("/")
    return f"{host}/api/slots/{slot['id']}/placeholder.svg", False

def slot_to_dict(row, conn, include_resources=False):
    d = dict(row)
    try: d["metadata"] = json.loads(d.get("metadata") or "{}")
    except: d["metadata"] = {}
    active = conn.execute("SELECT * FROM art_resources WHERE slot_id=? AND status='active' LIMIT 1", (d["id"],)).fetchone()
    d["active_resource"] = dict(active) if active else None
    d["resource_count"] = conn.execute("SELECT COUNT(*) FROM art_resources WHERE slot_id=?", (d["id"],)).fetchone()[0]
    if include_resources:
        rows = conn.execute("SELECT * FROM art_resources WHERE slot_id=? ORDER BY uploaded_at DESC", (d["id"],)).fetchall()
        d["resources"] = [dict(r) for r in rows]
    return d

def file_url(slot_id, filename):
    return f"{request.host_url.rstrip('/')}/uploads/{slot_id}/{filename}"

# ── 静态 ──────────────────────────────────────────────────
@app.route("/")
def index(): return send_file("templates/index.html")

@app.route("/uploads/<slot_id>/<filename>")
def serve_file(slot_id, filename):
    return send_from_directory(os.path.join(UPLOAD_DIR, slot_id), filename)

# ── 文字占位 SVG ──────────────────────────────────────────

def make_text_placeholder_svg(name, asset_type="image"):
    """动态生成文字占位 SVG，无需任何图像库"""
    color_map = {
        "image": ("#6366f1", "#e0e7ff"),
        "audio": ("#8b5cf6", "#ede9fe"),
        "video": ("#ec4899", "#fce7f3"),
    }
    stroke, bg = color_map.get(asset_type, ("#6366f1", "#e0e7ff"))
    safe_name = html.escape(name[:8])  # 最多8字，防止溢出
    # 多行处理：超4字换行
    if len(name) > 4:
        line1 = html.escape(name[:4])
        line2 = html.escape(name[4:8])
        text_el = (
            f'<text x="100" y="95" text-anchor="middle" '
            f'font-family="PingFang SC,Microsoft YaHei,sans-serif" '
            f'font-size="22" fill="{stroke}" font-weight="bold">{line1}</text>'
            f'<text x="100" y="122" text-anchor="middle" '
            f'font-family="PingFang SC,Microsoft YaHei,sans-serif" '
            f'font-size="22" fill="{stroke}" font-weight="bold">{line2}</text>'
        )
    else:
        text_el = (
            f'<text x="100" y="110" text-anchor="middle" '
            f'font-family="PingFang SC,Microsoft YaHei,sans-serif" '
            f'font-size="24" fill="{stroke}" font-weight="bold">{safe_name}</text>'
        )
    svg = f'''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="200" height="200" viewBox="0 0 200 200">
  <circle cx="100" cy="100" r="90" fill="{bg}" stroke="{stroke}" stroke-width="3"/>
  <circle cx="100" cy="100" r="82" fill="none" stroke="{stroke}" stroke-width="1" stroke-dasharray="6,4" opacity="0.4"/>
  {text_el}
  <text x="100" y="158" text-anchor="middle" font-family="sans-serif" font-size="10" fill="{stroke}" opacity="0.5">占位资源</text>
</svg>'''
    return svg

@app.route("/api/slots/<sid>/placeholder.svg")
def slot_text_placeholder(sid):
    with get_db() as conn:
        row = conn.execute("SELECT name, asset_type FROM art_slots WHERE id=?", (sid,)).fetchone()
        if not row:
            return "not found", 404
    svg = make_text_placeholder_svg(row["name"], row["asset_type"])
    return Response(svg, mimetype="image/svg+xml",
                    headers={"Cache-Control": "public, max-age=3600"})

# ── 资源位 ────────────────────────────────────────────────
@app.route("/api/slots", methods=["GET"])
def list_slots():
    category = request.args.get("category")
    asset_type = request.args.get("asset_type")
    with get_db() as conn:
        q, p = "SELECT * FROM art_slots WHERE 1=1", []
        if category:   q += " AND category=?";   p.append(category)
        if asset_type: q += " AND asset_type=?"; p.append(asset_type)
        q += " ORDER BY category, created_at"
        rows = conn.execute(q, p).fetchall()
        return jsonify([slot_to_dict(r, conn) for r in rows])

@app.route("/api/slots", methods=["POST"])
def create_slot():
    data = request.get_json() or {}
    if not data.get("game_key"): return jsonify({"error": "game_key 必填"}), 400
    if not data.get("name"):     return jsonify({"error": "name 必填"}), 400
    game_key = data["game_key"].strip().lower().replace(" ","_")
    sid, now = str(uuid.uuid4()), now_iso()
    meta = data.get("metadata", {})
    if isinstance(meta, dict): meta = json.dumps(meta, ensure_ascii=False)
    with get_db() as conn:
        try:
            conn.execute(
                "INSERT INTO art_slots (id,game_key,name,description,asset_type,category,metadata,created_by,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (sid, game_key, data["name"], data.get("description",""),
                 data.get("asset_type","image"), data.get("category","其他"),
                 meta, data.get("created_by","user"), now, now)
            )
        except sqlite3.IntegrityError:
            return jsonify({"error": f"game_key '{game_key}' 已存在"}), 409
        row = conn.execute("SELECT * FROM art_slots WHERE id=?", (sid,)).fetchone()
        return jsonify(slot_to_dict(row, conn)), 201

@app.route("/api/slots/<sid>", methods=["GET"])
def get_slot(sid):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM art_slots WHERE id=?", (sid,)).fetchone()
        if not row: return jsonify({"error": "not found"}), 404
        return jsonify(slot_to_dict(row, conn, include_resources=True))

@app.route("/api/slots/<sid>", methods=["PUT"])
def update_slot(sid):
    data = request.get_json() or {}
    with get_db() as conn:
        if not conn.execute("SELECT id FROM art_slots WHERE id=?", (sid,)).fetchone():
            return jsonify({"error": "not found"}), 404
        sets, params = [], []
        for k in ["name","description","category","asset_type"]:
            if k in data: sets.append(f"{k}=?"); params.append(data[k])
        if "metadata" in data:
            meta = data["metadata"]
            if isinstance(meta, dict): meta = json.dumps(meta, ensure_ascii=False)
            sets.append("metadata=?"); params.append(meta)
        if "placeholder_id" in data:
            # None 表示清除，字符串表示指定
            sets.append("placeholder_id=?"); params.append(data["placeholder_id"])
        if not sets: return jsonify({"error": "无可更新字段"}), 400
        sets.append("updated_at=?"); params.append(now_iso()); params.append(sid)
        conn.execute(f"UPDATE art_slots SET {', '.join(sets)} WHERE id=?", params)
    return jsonify({"ok": True})

@app.route("/api/slots/<sid>/set-placeholder", methods=["POST"])
def set_slot_placeholder(sid):
    """为资源位手动指定占位资源（来自占位库）"""
    data = request.get_json() or {}
    placeholder_id = data.get("placeholder_id")  # None = 恢复文字SVG
    with get_db() as conn:
        if not conn.execute("SELECT id FROM art_slots WHERE id=?", (sid,)).fetchone():
            return jsonify({"error": "not found"}), 404
        if placeholder_id:
            if not conn.execute("SELECT id FROM placeholder_resources WHERE id=?", (placeholder_id,)).fetchone():
                return jsonify({"error": "占位资源不存在"}), 404
        conn.execute("UPDATE art_slots SET placeholder_id=?, updated_at=? WHERE id=?",
                     (placeholder_id, now_iso(), sid))
    return jsonify({"ok": True})

@app.route("/api/slots/<sid>", methods=["DELETE"])
def delete_slot(sid):
    with get_db() as conn:
        if not conn.execute("SELECT id FROM art_slots WHERE id=?", (sid,)).fetchone():
            return jsonify({"error": "not found"}), 404
        resources = conn.execute("SELECT * FROM art_resources WHERE slot_id=?", (sid,)).fetchall()
        for r in resources:
            fp = os.path.join(UPLOAD_DIR, sid, r["filename"])
            if os.path.exists(fp): os.remove(fp)
        conn.execute("DELETE FROM art_resources WHERE slot_id=?", (sid,))
        conn.execute("DELETE FROM art_slots WHERE id=?", (sid,))
    slot_dir = os.path.join(UPLOAD_DIR, sid)
    if os.path.isdir(slot_dir):
        try: os.rmdir(slot_dir)
        except: pass
    return jsonify({"ok": True})

# ── 资源 ──────────────────────────────────────────────────
@app.route("/api/slots/<sid>/upload", methods=["POST"])
def upload_resource(sid):
    with get_db() as conn:
        if not conn.execute("SELECT id FROM art_slots WHERE id=?", (sid,)).fetchone():
            return jsonify({"error": "资源位不存在"}), 404
    if "file" not in request.files: return jsonify({"error": "缺少 file 字段"}), 400
    f = request.files["file"]
    if not f.filename: return jsonify({"error": "文件名为空"}), 400
    ext = f.filename.rsplit(".",1)[-1].lower() if "." in f.filename else ""
    allowed = set()
    for exts in ALLOWED_EXT.values(): allowed |= exts
    if ext not in allowed: return jsonify({"error": f"不支持的文件类型: .{ext}"}), 400
    content = f.read()
    if len(content) > MAX_MB * 1024 * 1024: return jsonify({"error": f"文件超过 {MAX_MB}MB"}), 413
    rid, now = str(uuid.uuid4()), now_iso()
    safe_name = f"{rid}.{ext}"
    dest_dir = os.path.join(UPLOAD_DIR, sid)
    os.makedirs(dest_dir, exist_ok=True)
    with open(os.path.join(dest_dir, safe_name), "wb") as out: out.write(content)
    with get_db() as conn:
        conn.execute(
            "INSERT INTO art_resources (id,slot_id,filename,original_name,file_size,mime_type,status,source_url,note,uploaded_by,uploaded_at) VALUES (?,?,?,?,?,?,'inactive','',?,?,?)",
            (rid, sid, safe_name, f.filename, len(content), f.mimetype or "",
             request.form.get("note",""), request.form.get("uploaded_by","user"), now)
        )
        row = conn.execute("SELECT * FROM art_resources WHERE id=?", (rid,)).fetchone()
    r = dict(row); r["url"] = file_url(sid, safe_name)
    return jsonify(r), 201

@app.route("/api/slots/<sid>/add-url", methods=["POST"])
def add_url_resource(sid):
    data = request.get_json() or {}
    source_url = data.get("source_url","").strip()
    if not source_url: return jsonify({"error": "source_url 必填"}), 400
    with get_db() as conn:
        if not conn.execute("SELECT id FROM art_slots WHERE id=?", (sid,)).fetchone():
            return jsonify({"error": "资源位不存在"}), 404
    rid, now = str(uuid.uuid4()), now_iso()
    original_name = source_url.split("/")[-1].split("?")[0] or "remote_resource"
    ext = original_name.rsplit(".",1)[-1].lower() if "." in original_name else ""
    mime = mimetypes.guess_type(original_name)[0] or ""
    with get_db() as conn:
        conn.execute(
            "INSERT INTO art_resources (id,slot_id,filename,original_name,file_size,mime_type,status,source_url,note,uploaded_by,uploaded_at) VALUES (?,?,?,?,0,?,'inactive',?,?,?,?)",
            (rid, sid, f"url_{rid}.{ext}" if ext else f"url_{rid}", original_name,
             mime, source_url, data.get("note",""), data.get("uploaded_by","ai"), now)
        )
        row = conn.execute("SELECT * FROM art_resources WHERE id=?", (rid,)).fetchone()
    r = dict(row); r["url"] = source_url
    return jsonify(r), 201

@app.route("/api/resources/<rid>/status", methods=["PUT"])
def set_resource_status(rid):
    data = request.get_json() or {}
    status = data.get("status","")
    if status not in ("active","inactive","pending_delete"):
        return jsonify({"error": "status 必须是 active / inactive / pending_delete"}), 400
    with get_db() as conn:
        row = conn.execute("SELECT * FROM art_resources WHERE id=?", (rid,)).fetchone()
        if not row: return jsonify({"error": "not found"}), 404
        if status == "active":
            conn.execute("UPDATE art_resources SET status='inactive' WHERE slot_id=? AND id!=?", (row["slot_id"], rid))
        conn.execute("UPDATE art_resources SET status=? WHERE id=?", (status, rid))
    return jsonify({"ok": True})

@app.route("/api/resources/<rid>", methods=["DELETE"])
def delete_resource(rid):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM art_resources WHERE id=?", (rid,)).fetchone()
        if not row: return jsonify({"error": "not found"}), 404
        r = dict(row)
        if not r["source_url"]:
            fp = os.path.join(UPLOAD_DIR, r["slot_id"], r["filename"])
            if os.path.exists(fp): os.remove(fp)
        conn.execute("DELETE FROM art_resources WHERE id=?", (rid,))
    return jsonify({"ok": True})

# ── 占位资源库 ────────────────────────────────────────────
@app.route("/api/placeholders", methods=["GET"])
def list_placeholders():
    asset_type = request.args.get("asset_type")
    with get_db() as conn:
        q, p = "SELECT * FROM placeholder_resources WHERE 1=1", []
        if asset_type: q += " AND asset_type=?"; p.append(asset_type)
        q += " ORDER BY is_builtin DESC, created_at"
        rows = conn.execute(q, p).fetchall()
    return jsonify([dict(r) for r in rows])

@app.route("/api/placeholders", methods=["POST"])
def create_placeholder():
    data = request.get_json() or {}
    if not data.get("url"):        return jsonify({"error": "url 必填"}), 400
    if not data.get("asset_type"): return jsonify({"error": "asset_type 必填"}), 400
    pid, now = str(uuid.uuid4()), now_iso()
    with get_db() as conn:
        conn.execute(
            "INSERT INTO placeholder_resources (id,name,asset_type,url,is_builtin,created_at) VALUES (?,?,?,?,0,?)",
            (pid, data.get("name","自定义占位"), data["asset_type"], data["url"], now)
        )
        row = conn.execute("SELECT * FROM placeholder_resources WHERE id=?", (pid,)).fetchone()
    return jsonify(dict(row)), 201

@app.route("/api/placeholders/<pid>", methods=["DELETE"])
def delete_placeholder(pid):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM placeholder_resources WHERE id=?", (pid,)).fetchone()
        if not row: return jsonify({"error": "not found"}), 404
        if dict(row)["is_builtin"]: return jsonify({"error": "内置占位资源不可删除"}), 403
        conn.execute("DELETE FROM placeholder_resources WHERE id=?", (pid,))
    return jsonify({"ok": True})

# ── Sync & Manifest ───────────────────────────────────────
def build_manifest(conn):
    slots = conn.execute("SELECT * FROM art_slots ORDER BY category, created_at").fetchall()
    manifest = {}
    for slot in slots:
        s = dict(slot)
        gk = s["game_key"]
        active = conn.execute("SELECT * FROM art_resources WHERE slot_id=? AND status='active' LIMIT 1", (s["id"],)).fetchone()
        if active:
            a = dict(active)
            url = a["source_url"] if a["source_url"] else file_url(s["id"], a["filename"])
            manifest[gk] = {"game_key": gk, "slot_name": s["name"], "asset_type": s["asset_type"],
                            "category": s["category"], "url": url, "is_placeholder": False,
                            "resource_id": a["id"], "original_name": a["original_name"],
                            "metadata": json.loads(s.get("metadata") or "{}")}
        else:
            ph_url, _ = get_slot_placeholder_url(conn, s)
            manifest[gk] = {"game_key": gk, "slot_name": s["name"], "asset_type": s["asset_type"],
                            "category": s["category"], "url": ph_url,
                            "is_placeholder": True, "resource_id": None, "original_name": None,
                            "placeholder_type": "assigned" if s.get("placeholder_id") else "text_svg",
                            "metadata": json.loads(s.get("metadata") or "{}")}
    return manifest

@app.route("/api/sync/preview", methods=["GET"])
def sync_preview():
    with get_db() as conn:
        to_delete = conn.execute("SELECT r.*, s.game_key FROM art_resources r JOIN art_slots s ON r.slot_id=s.id WHERE r.status='pending_delete'").fetchall()
        manifest = build_manifest(conn)
    return jsonify({"will_delete": [dict(r) for r in to_delete], "manifest": manifest})

@app.route("/api/sync", methods=["POST"])
def do_sync():
    deleted = []
    with get_db() as conn:
        to_delete = conn.execute("SELECT * FROM art_resources WHERE status='pending_delete'").fetchall()
        for r in to_delete:
            r = dict(r)
            if not r["source_url"]:
                fp = os.path.join(UPLOAD_DIR, r["slot_id"], r["filename"])
                if os.path.exists(fp): os.remove(fp)
            conn.execute("DELETE FROM art_resources WHERE id=?", (r["id"],))
            deleted.append(r["id"])
        manifest = build_manifest(conn)
    return jsonify({"ok": True, "deleted_count": len(deleted), "deleted_ids": deleted, "manifest": manifest})

@app.route("/api/manifest", methods=["GET"])
def get_manifest():
    with get_db() as conn: return jsonify(build_manifest(conn))

@app.route("/api/manifest/<game_key>", methods=["GET"])
def get_manifest_key(game_key):
    with get_db() as conn:
        if not conn.execute("SELECT id FROM art_slots WHERE game_key=?", (game_key,)).fetchone():
            return jsonify({"error": f"game_key '{game_key}' 不存在"}), 404
        return jsonify(build_manifest(conn).get(game_key))

@app.route("/api/stats", methods=["GET"])
def stats():
    with get_db() as conn:
        return jsonify({
            "total_slots":    conn.execute("SELECT COUNT(*) FROM art_slots").fetchone()[0],
            "active":         conn.execute("SELECT COUNT(*) FROM art_resources WHERE status='active'").fetchone()[0],
            "inactive":       conn.execute("SELECT COUNT(*) FROM art_resources WHERE status='inactive'").fetchone()[0],
            "pending_delete": conn.execute("SELECT COUNT(*) FROM art_resources WHERE status='pending_delete'").fetchone()[0],
            "slots_no_active":conn.execute("SELECT COUNT(*) FROM art_slots WHERE id NOT IN (SELECT slot_id FROM art_resources WHERE status='active')").fetchone()[0],
            "placeholders":   conn.execute("SELECT COUNT(*) FROM placeholder_resources").fetchone()[0],
        })

if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 8899))
    print(f"[START] Art Platform 启动，端口 {port}")
    app.run(host="0.0.0.0", port=port, debug=False)
