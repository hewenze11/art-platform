#!/usr/bin/env python3
"""
ArtHub v3 - 个人创作者美术资源管理平台
核心概念：
  - Version（版本）: 一套美术方案，有一个"当前使用版本"
  - Asset（资源槽）: 属于某版本某分类的一个资源位
    status: confirmed(已确认使用) | pending(待定，在备选库) | empty(未填充，用占位资源)
  - 备选库: 所有 status=pending 的资源
  - 占位资源: status=empty 时前端显示彩色方块/默认音频
"""
import os, json, uuid, yaml, mimetypes
from datetime import datetime
from pathlib import Path
from flask import Flask, request, jsonify, send_from_directory, send_file
from flask_cors import CORS
import sqlite3

CONFIG_PATH = os.environ.get("CONFIG_PATH", "/app/project.yaml")
DATA_DIR    = os.environ.get("DATA_DIR", "/data")
DB_PATH     = os.path.join(DATA_DIR, "artplatform.db")
UPLOAD_DIR  = os.path.join(DATA_DIR, "uploads")

app = Flask(__name__, template_folder="templates")
CORS(app)
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)

def load_config():
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def now_iso():
    return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

def init_db():
    with get_db() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS versions (
            id           TEXT PRIMARY KEY,
            name         TEXT NOT NULL,
            description  TEXT DEFAULT '',
            is_current   INTEGER DEFAULT 0,
            created_at   TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS assets (
            id           TEXT PRIMARY KEY,
            version_id   TEXT NOT NULL,
            name         TEXT NOT NULL,
            category     TEXT DEFAULT '其他',
            asset_type   TEXT DEFAULT 'image',
            description  TEXT DEFAULT '',
            status       TEXT DEFAULT 'empty',
            sort_order   INTEGER DEFAULT 0,
            created_at   TEXT NOT NULL,
            updated_at   TEXT NOT NULL,
            FOREIGN KEY (version_id) REFERENCES versions(id)
        );
        CREATE TABLE IF NOT EXISTS files (
            id           TEXT PRIMARY KEY,
            asset_id     TEXT NOT NULL,
            filename     TEXT NOT NULL,
            original     TEXT NOT NULL,
            file_size    INTEGER DEFAULT 0,
            mime_type    TEXT DEFAULT '',
            is_active    INTEGER DEFAULT 1,
            uploaded_at  TEXT NOT NULL,
            FOREIGN KEY (asset_id) REFERENCES assets(id)
        );
        CREATE TABLE IF NOT EXISTS notes (
            id           TEXT PRIMARY KEY,
            asset_id     TEXT NOT NULL,
            content      TEXT NOT NULL,
            created_at   TEXT NOT NULL,
            FOREIGN KEY (asset_id) REFERENCES assets(id)
        );
        """)
    print(f"[DB] 初始化完成: {DB_PATH}")

# ── 静态 ──────────────────────────────────────────────────

@app.route("/")
def index():
    return send_file("templates/index.html")

@app.route("/api/docs")
def api_docs():
    try:
        with open(os.path.join(os.path.dirname(__file__), "USAGE.md"), "r", encoding="utf-8") as f:
            return f.read(), 200, {"Content-Type": "text/markdown; charset=utf-8"}
    except FileNotFoundError:
        return "文档不存在", 404

# ── 配置 ──────────────────────────────────────────────────

@app.route("/api/config")
def api_config():
    cfg = load_config()
    return jsonify({
        "project": cfg.get("project", {}),
        "categories": cfg.get("categories", ["角色", "场景", "UI", "特效", "音效", "动画", "其他"]),
        "asset_types": cfg.get("asset_types", ["image", "audio", "video", "file"]),
    })

@app.route("/api/config/project", methods=["GET", "PUT"])
def api_config_project():
    if request.method == "GET":
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                return f.read(), 200, {"Content-Type": "text/plain; charset=utf-8"}
        except FileNotFoundError:
            return "配置文件不存在", 404
    data = request.get_json()
    if not data:
        return jsonify({"error": "需要 JSON body"}), 400
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        def deep_merge(base, patch):
            for k, v in patch.items():
                if isinstance(v, dict) and isinstance(base.get(k), dict):
                    deep_merge(base[k], v)
                else:
                    base[k] = v
        deep_merge(cfg, data)
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            yaml.dump(cfg, f, allow_unicode=True, default_flow_style=False)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/config/project/raw", methods=["PUT"])
def api_config_raw():
    text = request.get_data(as_text=True)
    if not text.strip():
        return jsonify({"error": "内容不能为空"}), 400
    try:
        yaml.safe_load(text)
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            f.write(text)
        return jsonify({"ok": True})
    except yaml.YAMLError as e:
        return jsonify({"error": f"YAML 格式错误: {e}"}), 400

# ── 版本 ──────────────────────────────────────────────────

@app.route("/api/versions", methods=["GET"])
def list_versions():
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM versions ORDER BY created_at ASC").fetchall()
    return jsonify([dict(r) for r in rows])

@app.route("/api/versions", methods=["POST"])
def create_version():
    data = request.get_json() or {}
    if not data.get("name"):
        return jsonify({"error": "name 必填"}), 400
    vid = str(uuid.uuid4())
    now = now_iso()
    copy_from = data.get("copy_from")
    with get_db() as conn:
        conn.execute(
            "INSERT INTO versions (id,name,description,is_current,created_at) VALUES (?,?,?,0,?)",
            (vid, data["name"], data.get("description",""), now)
        )
        if copy_from:
            src = conn.execute("SELECT * FROM assets WHERE version_id=?", (copy_from,)).fetchall()
            for a in src:
                new_id = str(uuid.uuid4())
                conn.execute(
                    "INSERT INTO assets (id,version_id,name,category,asset_type,description,status,sort_order,created_at,updated_at) VALUES (?,?,?,?,?,?,'empty',?,?,?)",
                    (new_id, vid, a["name"], a["category"], a["asset_type"], a["description"], a["sort_order"], now, now)
                )
    return jsonify({"id": vid, "ok": True}), 201

@app.route("/api/versions/<vid>", methods=["GET"])
def get_version(vid):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM versions WHERE id=?", (vid,)).fetchone()
        if not row:
            return jsonify({"error": "not found"}), 404
        v = dict(row)
        assets = conn.execute("SELECT * FROM assets WHERE version_id=? ORDER BY category, sort_order, created_at", (vid,)).fetchall()
        v["assets"] = [dict(a) for a in assets]
    return jsonify(v)

@app.route("/api/versions/<vid>", methods=["PUT"])
def update_version(vid):
    data = request.get_json() or {}
    with get_db() as conn:
        if not conn.execute("SELECT id FROM versions WHERE id=?", (vid,)).fetchone():
            return jsonify({"error": "not found"}), 404
        sets, params = [], []
        for k in ["name", "description"]:
            if k in data:
                sets.append(f"{k}=?"); params.append(data[k])
        if sets:
            params.append(vid)
            conn.execute(f"UPDATE versions SET {', '.join(sets)} WHERE id=?", params)
    return jsonify({"ok": True})

@app.route("/api/versions/<vid>", methods=["DELETE"])
def delete_version(vid):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM versions WHERE id=?", (vid,)).fetchone()
        if not row:
            return jsonify({"error": "not found"}), 404
        if dict(row)["is_current"]:
            return jsonify({"error": "当前使用版本不可删除"}), 403
        # 删除该版本下的所有资源及关联
        aids = [r["id"] for r in conn.execute("SELECT id FROM assets WHERE version_id=?", (vid,)).fetchall()]
        for aid in aids:
            conn.execute("DELETE FROM files WHERE asset_id=?", (aid,))
            conn.execute("DELETE FROM notes WHERE asset_id=?", (aid,))
        conn.execute("DELETE FROM assets WHERE version_id=?", (vid,))
        conn.execute("DELETE FROM versions WHERE id=?", (vid,))
    return jsonify({"ok": True})

@app.route("/api/versions/<vid>/set-current", methods=["POST"])
def set_current_version(vid):
    with get_db() as conn:
        if not conn.execute("SELECT id FROM versions WHERE id=?", (vid,)).fetchone():
            return jsonify({"error": "not found"}), 404
        conn.execute("UPDATE versions SET is_current=0")
        conn.execute("UPDATE versions SET is_current=1 WHERE id=?", (vid,))
    return jsonify({"ok": True})

# ── 资源 ──────────────────────────────────────────────────

@app.route("/api/versions/<vid>/assets", methods=["GET"])
def list_assets(vid):
    status   = request.args.get("status")
    category = request.args.get("category")
    with get_db() as conn:
        q = "SELECT * FROM assets WHERE version_id=?"
        p = [vid]
        if status:   q += " AND status=?";   p.append(status)
        if category: q += " AND category=?"; p.append(category)
        q += " ORDER BY category, sort_order, created_at"
        rows = conn.execute(q, p).fetchall()
        result = []
        for r in rows:
            a = dict(r)
            a["active_file"] = None
            f = conn.execute("SELECT * FROM files WHERE asset_id=? AND is_active=1 ORDER BY uploaded_at DESC LIMIT 1", (r["id"],)).fetchone()
            if f:
                a["active_file"] = dict(f)
            result.append(a)
    return jsonify(result)

@app.route("/api/versions/<vid>/assets", methods=["POST"])
def create_asset(vid):
    data = request.get_json()
    if not data or not data.get("name"):
        return jsonify({"error": "name 必填"}), 400
    with get_db() as conn:
        if not conn.execute("SELECT id FROM versions WHERE id=?", (vid,)).fetchone():
            return jsonify({"error": "版本不存在"}), 404
        aid = str(uuid.uuid4())
        now = now_iso()
        conn.execute(
            "INSERT INTO assets (id,version_id,name,category,asset_type,description,status,sort_order,created_at,updated_at) VALUES (?,?,?,?,?,?,'empty',?,?,?)",
            (aid, vid, data["name"], data.get("category","其他"), data.get("asset_type","image"), data.get("description",""), data.get("sort_order",0), now, now)
        )
    return jsonify({"id": aid, "ok": True}), 201

@app.route("/api/assets/<aid>", methods=["GET"])
def get_asset(aid):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM assets WHERE id=?", (aid,)).fetchone()
        if not row:
            return jsonify({"error": "not found"}), 404
        a = dict(row)
        a["files"] = [dict(r) for r in conn.execute("SELECT * FROM files WHERE asset_id=? ORDER BY uploaded_at DESC", (aid,)).fetchall()]
        a["notes"] = [dict(r) for r in conn.execute("SELECT * FROM notes WHERE asset_id=? ORDER BY created_at ASC", (aid,)).fetchall()]
    return jsonify(a)

@app.route("/api/assets/<aid>", methods=["PUT"])
def update_asset(aid):
    data = request.get_json() or {}
    with get_db() as conn:
        if not conn.execute("SELECT id FROM assets WHERE id=?", (aid,)).fetchone():
            return jsonify({"error": "not found"}), 404
        allowed = ["name","description","category","asset_type","status","sort_order"]
        sets, params = [], []
        for k in allowed:
            if k in data:
                sets.append(f"{k}=?"); params.append(data[k])
        if not sets:
            return jsonify({"error": "无可更新字段"}), 400
        sets.append("updated_at=?"); params.append(now_iso()); params.append(aid)
        conn.execute(f"UPDATE assets SET {', '.join(sets)} WHERE id=?", params)
    return jsonify({"ok": True})

@app.route("/api/assets/<aid>", methods=["DELETE"])
def delete_asset(aid):
    with get_db() as conn:
        if not conn.execute("SELECT id FROM assets WHERE id=?", (aid,)).fetchone():
            return jsonify({"error": "not found"}), 404
        conn.execute("DELETE FROM files WHERE asset_id=?", (aid,))
        conn.execute("DELETE FROM notes WHERE asset_id=?", (aid,))
        conn.execute("DELETE FROM assets WHERE id=?", (aid,))
    return jsonify({"ok": True})

@app.route("/api/assets/<aid>/status", methods=["POST"])
def set_asset_status(aid):
    data = request.get_json() or {}
    status = data.get("status","")
    if status not in ("confirmed","pending","empty"):
        return jsonify({"error": "status 必须是 confirmed / pending / empty"}), 400
    with get_db() as conn:
        if not conn.execute("SELECT id FROM assets WHERE id=?", (aid,)).fetchone():
            return jsonify({"error": "not found"}), 404
        conn.execute("UPDATE assets SET status=?, updated_at=? WHERE id=?", (status, now_iso(), aid))
    return jsonify({"ok": True})

# ── 文件 ──────────────────────────────────────────────────

@app.route("/api/assets/<aid>/upload", methods=["POST"])
def upload_file(aid):
    cfg = load_config()
    allowed_ext = set(cfg.get("storage",{}).get("allowed_extensions", ["png","jpg","jpeg","gif","webp","psd","svg","mp4","mp3","wav","ogg","fbx","obj","unity3d"]))
    max_mb = cfg.get("storage",{}).get("max_file_size_mb", 50)
    with get_db() as conn:
        row = conn.execute("SELECT * FROM assets WHERE id=?", (aid,)).fetchone()
        if not row:
            return jsonify({"error": "not found"}), 404
    if "file" not in request.files:
        return jsonify({"error": "no file"}), 400
    f = request.files["file"]
    ext = f.filename.rsplit(".",1)[-1].lower() if "." in f.filename else ""
    if ext not in allowed_ext:
        return jsonify({"error": f"不支持的文件类型: {ext}"}), 400
    content = f.read()
    if len(content) > max_mb * 1024 * 1024:
        return jsonify({"error": f"文件超过 {max_mb}MB 限制"}), 413
    fid = str(uuid.uuid4())
    safe_name = f"{fid}.{ext}"
    dest_dir = os.path.join(UPLOAD_DIR, aid)
    os.makedirs(dest_dir, exist_ok=True)
    with open(os.path.join(dest_dir, safe_name), "wb") as out:
        out.write(content)
    now = now_iso()
    with get_db() as conn:
        # 旧文件设为非活跃
        conn.execute("UPDATE files SET is_active=0 WHERE asset_id=?", (aid,))
        conn.execute(
            "INSERT INTO files (id,asset_id,filename,original,file_size,mime_type,is_active,uploaded_at) VALUES (?,?,?,?,?,?,1,?)",
            (fid, aid, safe_name, f.filename, len(content), f.mimetype or "", now)
        )
        # 上传后自动确认
        conn.execute("UPDATE assets SET status='confirmed', updated_at=? WHERE id=?", (now, aid))
    return jsonify({"file_id": fid, "filename": safe_name, "ok": True}), 201

@app.route("/api/assets/<aid>/files/<fid>/activate", methods=["POST"])
def activate_file(aid, fid):
    with get_db() as conn:
        if not conn.execute("SELECT id FROM files WHERE id=? AND asset_id=?", (fid, aid)).fetchone():
            return jsonify({"error": "not found"}), 404
        conn.execute("UPDATE files SET is_active=0 WHERE asset_id=?", (aid,))
        conn.execute("UPDATE files SET is_active=1 WHERE id=?", (fid,))
    return jsonify({"ok": True})

@app.route("/api/uploads/<aid>/<filename>")
def serve_file(aid, filename):
    return send_from_directory(os.path.join(UPLOAD_DIR, aid), filename)

# ── 备注 ──────────────────────────────────────────────────

@app.route("/api/assets/<aid>/notes", methods=["GET"])
def list_notes(aid):
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM notes WHERE asset_id=? ORDER BY created_at ASC", (aid,)).fetchall()
    return jsonify([dict(r) for r in rows])

@app.route("/api/assets/<aid>/notes", methods=["POST"])
def create_note(aid):
    data = request.get_json() or {}
    if not data.get("content"):
        return jsonify({"error": "content 必填"}), 400
    with get_db() as conn:
        if not conn.execute("SELECT id FROM assets WHERE id=?", (aid,)).fetchone():
            return jsonify({"error": "not found"}), 404
        nid = str(uuid.uuid4())
        conn.execute("INSERT INTO notes (id,asset_id,content,created_at) VALUES (?,?,?,?)", (nid, aid, data["content"], now_iso()))
    return jsonify({"id": nid, "ok": True}), 201

@app.route("/api/assets/<aid>/notes/<nid>", methods=["DELETE"])
def delete_note(aid, nid):
    with get_db() as conn:
        if not conn.execute("SELECT id FROM notes WHERE id=? AND asset_id=?", (nid, aid)).fetchone():
            return jsonify({"error": "not found"}), 404
        conn.execute("DELETE FROM notes WHERE id=?", (nid,))
    return jsonify({"ok": True})

# ── 统计 ──────────────────────────────────────────────────

@app.route("/api/stats")
def stats():
    with get_db() as conn:
        versions = conn.execute("SELECT COUNT(*) FROM versions").fetchone()[0]
        total    = conn.execute("SELECT COUNT(*) FROM assets").fetchone()[0]
        confirmed= conn.execute("SELECT COUNT(*) FROM assets WHERE status='confirmed'").fetchone()[0]
        pending  = conn.execute("SELECT COUNT(*) FROM assets WHERE status='pending'").fetchone()[0]
        empty    = conn.execute("SELECT COUNT(*) FROM assets WHERE status='empty'").fetchone()[0]
    return jsonify({"versions": versions, "total": total, "confirmed": confirmed, "pending": pending, "empty": empty})

if __name__ == "__main__":
    init_db()
    cfg = load_config()
    port  = cfg.get("server",{}).get("port", 8899)
    debug = cfg.get("server",{}).get("debug", False)
    print(f"[START] ArtHub v3 启动，端口 {port}")
    app.run(host="0.0.0.0", port=port, debug=debug)
