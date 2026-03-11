#!/usr/bin/env python3
"""
ArtHub 美术资源审核平台 v2 - 版本快照驱动架构
核心概念：
  - Snapshot（快照）：某一时刻所有美术资源的状态集合
  - is_refining: 完善中（可以新增/修改资源）
  - is_applied:  已应用（已触发CI/CD上线）
  - 两个状态独立，可并存
  - 最多保留3个活跃快照，超出自动归档
"""
import os, json, uuid, yaml, requests
from datetime import datetime
from pathlib import Path
from flask import Flask, request, jsonify, send_from_directory, send_file
from flask_cors import CORS
import sqlite3

CONFIG_PATH = os.environ.get("CONFIG_PATH", "/app/project.yaml")
DATA_DIR    = os.environ.get("DATA_DIR", "/data")
DB_PATH     = os.path.join(DATA_DIR, "artplatform.db")
UPLOAD_DIR  = os.path.join(DATA_DIR, "uploads")

def load_config():
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}

app = Flask(__name__, static_folder="static", template_folder="templates")
CORS(app)
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)

# ── DB ──────────────────────────────────────────────────────

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS snapshots (
            id           TEXT PRIMARY KEY,
            version      TEXT NOT NULL,
            name         TEXT DEFAULT '',
            is_refining  INTEGER DEFAULT 0,
            is_applied   INTEGER DEFAULT 0,
            is_archived  INTEGER DEFAULT 0,
            created_at   TEXT NOT NULL,
            applied_at   TEXT,
            created_by   TEXT DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS assets (
            id           TEXT PRIMARY KEY,
            snapshot_id  TEXT NOT NULL,
            name         TEXT NOT NULL,
            category     TEXT DEFAULT '其他',
            description  TEXT DEFAULT '',
            priority     TEXT DEFAULT '中',
            status       TEXT DEFAULT 'pending',
            assignee     TEXT DEFAULT '',
            created_by   TEXT DEFAULT '',
            created_at   TEXT NOT NULL,
            updated_at   TEXT NOT NULL,
            FOREIGN KEY (snapshot_id) REFERENCES snapshots(id)
        );

        CREATE TABLE IF NOT EXISTS files (
            id           TEXT PRIMARY KEY,
            asset_id     TEXT NOT NULL,
            filename     TEXT NOT NULL,
            original     TEXT NOT NULL,
            file_size    INTEGER DEFAULT 0,
            mime_type    TEXT DEFAULT '',
            uploaded_at  TEXT NOT NULL,
            FOREIGN KEY (asset_id) REFERENCES assets(id)
        );

        CREATE TABLE IF NOT EXISTS reviews (
            id           TEXT PRIMARY KEY,
            asset_id     TEXT NOT NULL,
            reviewer     TEXT NOT NULL,
            status       TEXT NOT NULL,
            comment      TEXT DEFAULT '',
            created_at   TEXT NOT NULL,
            FOREIGN KEY (asset_id) REFERENCES assets(id)
        );

        CREATE TABLE IF NOT EXISTS comments (
            id           TEXT PRIMARY KEY,
            asset_id     TEXT NOT NULL,
            author       TEXT NOT NULL,
            content      TEXT NOT NULL,
            created_at   TEXT NOT NULL,
            FOREIGN KEY (asset_id) REFERENCES assets(id)
        );

        CREATE TABLE IF NOT EXISTS activity_log (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            snapshot_id  TEXT,
            asset_id     TEXT,
            action       TEXT NOT NULL,
            actor        TEXT DEFAULT '',
            detail       TEXT DEFAULT '',
            created_at   TEXT NOT NULL
        );
        """)
    print(f"[DB] 初始化完成: {DB_PATH}")

def now_iso():
    return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

def log_act(conn, action, actor="", detail="", snapshot_id=None, asset_id=None):
    conn.execute(
        "INSERT INTO activity_log (snapshot_id,asset_id,action,actor,detail,created_at) VALUES (?,?,?,?,?,?)",
        (snapshot_id, asset_id, action, actor, detail, now_iso())
    )

# ── 通知 & CI/CD ────────────────────────────────────────────

def notify(message: str, event_type: str = "info", extra: dict = None):
    cfg = load_config()
    feishu_url = cfg.get("notifications", {}).get("feishu_webhook", "")
    if not feishu_url:
        return
    extra = extra or {}
    proj = cfg.get("project", {}).get("name", "ArtHub")
    color_map = {"info": "blue", "warn": "yellow", "success": "green", "danger": "red"}
    elements = [{"tag": "div", "text": {"tag": "lark_md", "content": f"**{k}**：{v}"}} for k, v in extra.items() if v]
    card = {
        "msg_type": "interactive",
        "card": {
            "header": {"title": {"tag": "plain_text", "content": f"[{proj}] {message}"}, "template": color_map.get(event_type, "blue")},
            "elements": elements or [{"tag": "div", "text": {"tag": "lark_md", "content": message}}]
        }
    }
    try:
        r = requests.post(feishu_url, json=card, timeout=5)
        if r.json().get("code", 0) != 0:
            raise ValueError(r.text)
    except Exception as e:
        print(f"[NOTIFY] 卡片失败({e})，降级文本")
        try:
            requests.post(feishu_url, json={"msg_type": "text", "content": {"text": f"[{proj}] {message}"}}, timeout=5)
        except Exception:
            pass

def trigger_cicd(snapshot_id: str, snapshot_version: str = "", actor: str = ""):
    cfg = load_config()
    cicd = cfg.get("cicd", {})
    triggered = []
    webhook_url = cicd.get("webhook_url", "")
    if webhook_url and "github.com/repos" not in webhook_url:
        try:
            requests.post(webhook_url, json={"snapshot_id": snapshot_id, "version": snapshot_version, "event": "snapshot_applied", "actor": actor}, timeout=10)
            triggered.append("webhook")
        except Exception as e:
            print(f"[CICD] Webhook 失败: {e}")
    repo_url = cicd.get("repo_url", "")
    ci_token = cicd.get("ci_token", "")
    if ci_token and "github.com" in repo_url:
        try:
            parts = repo_url.rstrip("/").split("github.com/")[-1].split("/")
            owner, repo = parts[0], parts[1]
            event_type = cicd.get("github_actions_event", "art_snapshot_applied")
            r = requests.post(
                f"https://api.github.com/repos/{owner}/{repo}/dispatches",
                json={"event_type": event_type, "client_payload": {"snapshot_id": snapshot_id, "version": snapshot_version, "actor": actor, "applied_at": now_iso()}},
                headers={"Authorization": f"token {ci_token}", "Accept": "application/vnd.github.v3+json"}, timeout=15
            )
            if r.status_code in (200, 204):
                triggered.append("github_actions")
                print(f"[CICD] GitHub Actions dispatch 成功: {owner}/{repo}")
            else:
                print(f"[CICD] GitHub Actions 失败 {r.status_code}: {r.text}")
        except Exception as e:
            print(f"[CICD] GitHub Actions 异常: {e}")
    gitlab_token = cicd.get("gitlab_token", "")
    gitlab_trigger_url = cicd.get("gitlab_trigger_url", "")
    if gitlab_token and gitlab_trigger_url:
        try:
            r = requests.post(gitlab_trigger_url, data={"token": gitlab_token, "ref": cicd.get("branch", "main"), "variables[SNAPSHOT_ID]": snapshot_id, "variables[SNAPSHOT_VERSION]": snapshot_version}, timeout=15)
            if r.status_code in (200, 201):
                triggered.append("gitlab_pipeline")
        except Exception as e:
            print(f"[CICD] GitLab 异常: {e}")
    return triggered

# ── 快照保留限制（最多3个活跃）────────────────────────────

def enforce_snapshot_limit(conn):
    rows = conn.execute(
        "SELECT id FROM snapshots WHERE is_archived=0 ORDER BY created_at ASC"
    ).fetchall()
    if len(rows) > 3:
        for row in rows[:-3]:
            conn.execute("UPDATE snapshots SET is_archived=1 WHERE id=?", (row["id"],))
            print(f"[SNAPSHOT] 自动归档快照: {row['id']}")

# ── 辅助：快照统计 ──────────────────────────────────────────

def snapshot_stats(conn, snapshot_id):
    total    = conn.execute("SELECT COUNT(*) FROM assets WHERE snapshot_id=?", (snapshot_id,)).fetchone()[0]
    pending  = conn.execute("SELECT COUNT(*) FROM assets WHERE snapshot_id=? AND status='pending'", (snapshot_id,)).fetchone()[0]
    in_rev   = conn.execute("SELECT COUNT(*) FROM assets WHERE snapshot_id=? AND status='in_review'", (snapshot_id,)).fetchone()[0]
    approved = conn.execute("SELECT COUNT(*) FROM assets WHERE snapshot_id=? AND status='approved'", (snapshot_id,)).fetchone()[0]
    rejected = conn.execute("SELECT COUNT(*) FROM assets WHERE snapshot_id=? AND status='rejected'", (snapshot_id,)).fetchone()[0]
    changes  = conn.execute("SELECT COUNT(*) FROM assets WHERE snapshot_id=? AND status='changes_requested'", (snapshot_id,)).fetchone()[0]
    return {"total": total, "pending": pending, "in_review": in_rev, "approved": approved, "rejected": rejected, "changes_requested": changes}

# ── 静态 / 文档 ─────────────────────────────────────────────

@app.route("/")
def index():
    return send_file("templates/index.html")

@app.route("/static/<path:filename>")
def static_files(filename):
    return send_from_directory("static", filename)

@app.route("/api/docs")
def api_docs():
    doc_path = os.path.join(os.path.dirname(__file__), "USAGE.md")
    try:
        with open(doc_path, "r", encoding="utf-8") as f:
            return f.read(), 200, {"Content-Type": "text/markdown; charset=utf-8"}
    except FileNotFoundError:
        return "文档不存在", 404

# ── 配置 API ────────────────────────────────────────────────

@app.route("/api/config")
def api_config():
    cfg = load_config()
    return jsonify({
        "project": cfg.get("project", {}),
        "review": cfg.get("review", {
            "reviewers": ["CTO", "主美", "程序"],
            "priorities": ["紧急", "高", "中", "低"],
            "categories": ["角色", "场景", "UI", "特效", "音效", "动画", "其他"],
        }),
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
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ── 快照 API ────────────────────────────────────────────────

@app.route("/api/snapshots", methods=["GET"])
def list_snapshots():
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM snapshots ORDER BY created_at DESC").fetchall()
        result = []
        for r in rows:
            s = dict(r)
            s["stats"] = snapshot_stats(conn, s["id"])
            result.append(s)
    return jsonify(result)

@app.route("/api/snapshots", methods=["POST"])
def create_snapshot():
    data = request.get_json() or {}
    if not data.get("version"):
        return jsonify({"error": "version 必填"}), 400
    sid = str(uuid.uuid4())
    now = now_iso()
    with get_db() as conn:
        conn.execute(
            "INSERT INTO snapshots (id,version,name,is_refining,is_applied,is_archived,created_at,created_by) VALUES (?,?,?,1,0,0,?,?)",
            (sid, data["version"], data.get("name", ""), now, data.get("created_by", ""))
        )
        # 继承上一个快照的资源
        inherit_from = data.get("inherit_from")
        if inherit_from:
            src_assets = conn.execute("SELECT * FROM assets WHERE snapshot_id=?", (inherit_from,)).fetchall()
            for a in src_assets:
                new_id = str(uuid.uuid4())
                conn.execute(
                    "INSERT INTO assets (id,snapshot_id,name,category,description,priority,status,assignee,created_by,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (new_id, sid, a["name"], a["category"], a["description"], a["priority"],
                     "pending",  # 继承时重置为 pending
                     "", a["created_by"], now, now)
                )
        log_act(conn, "snapshot_created", data.get("created_by",""), data["version"], snapshot_id=sid)
    cfg = load_config()
    proj = cfg.get("project", {}).get("name", "ArtHub")
    notify(f"📸 新快照创建", event_type="info", extra={"版本": data["version"], "名称": data.get("name",""), "继承自": inherit_from or "无"})
    return jsonify({"id": sid, "ok": True}), 201

@app.route("/api/snapshots/<sid>", methods=["GET"])
def get_snapshot(sid):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM snapshots WHERE id=?", (sid,)).fetchone()
        if not row:
            return jsonify({"error": "not found"}), 404
        s = dict(row)
        s["stats"] = snapshot_stats(conn, sid)
        assets = conn.execute("SELECT * FROM assets WHERE snapshot_id=? ORDER BY created_at DESC", (sid,)).fetchall()
        s["assets"] = [dict(a) for a in assets]
        logs = conn.execute("SELECT * FROM activity_log WHERE snapshot_id=? ORDER BY created_at DESC LIMIT 30", (sid,)).fetchall()
        s["activity"] = [dict(l) for l in logs]
    return jsonify(s)

@app.route("/api/snapshots/<sid>/refine", methods=["POST"])
def refine_snapshot(sid):
    data = request.get_json() or {}
    with get_db() as conn:
        row = conn.execute("SELECT * FROM snapshots WHERE id=?", (sid,)).fetchone()
        if not row:
            return jsonify({"error": "not found"}), 404
        conn.execute("UPDATE snapshots SET is_refining=1 WHERE id=?", (sid,))
        log_act(conn, "snapshot_refine", data.get("actor",""), "开始完善", snapshot_id=sid)
    notify("🔧 快照进入完善状态", event_type="warn", extra={"版本": dict(row)["version"]})
    return jsonify({"ok": True})

@app.route("/api/snapshots/<sid>/stop-refine", methods=["POST"])
def stop_refine_snapshot(sid):
    data = request.get_json() or {}
    with get_db() as conn:
        row = conn.execute("SELECT * FROM snapshots WHERE id=?", (sid,)).fetchone()
        if not row:
            return jsonify({"error": "not found"}), 404
        conn.execute("UPDATE snapshots SET is_refining=0 WHERE id=?", (sid,))
        log_act(conn, "snapshot_stop_refine", data.get("actor",""), "停止完善", snapshot_id=sid)
    return jsonify({"ok": True})

@app.route("/api/snapshots/<sid>/apply", methods=["POST"])
def apply_snapshot(sid):
    data = request.get_json() or {}
    now = now_iso()
    with get_db() as conn:
        row = conn.execute("SELECT * FROM snapshots WHERE id=?", (sid,)).fetchone()
        if not row:
            return jsonify({"error": "not found"}), 404
        conn.execute("UPDATE snapshots SET is_applied=1, applied_at=? WHERE id=?", (now, sid))
        enforce_snapshot_limit(conn)
        log_act(conn, "snapshot_applied", data.get("actor",""), f"版本 {dict(row)['version']} 已应用", snapshot_id=sid)
    s = dict(row)
    triggered = trigger_cicd(sid, s["version"], data.get("actor",""))
    notify("🚀 快照已应用", event_type="success", extra={"版本": s["version"], "操作人": data.get("actor",""), "CI/CD": ", ".join(triggered) or "未配置"})
    return jsonify({"ok": True, "triggered": triggered})

@app.route("/api/snapshots/<sid>/diff/<other_id>", methods=["GET"])
def diff_snapshots(sid, other_id):
    with get_db() as conn:
        a_assets = {a["name"]: dict(a) for a in conn.execute("SELECT * FROM assets WHERE snapshot_id=?", (sid,)).fetchall()}
        b_assets = {a["name"]: dict(a) for a in conn.execute("SELECT * FROM assets WHERE snapshot_id=?", (other_id,)).fetchall()}
    added   = [b_assets[k] for k in b_assets if k not in a_assets]
    removed = [a_assets[k] for k in a_assets if k not in b_assets]
    changed = []
    for k in a_assets:
        if k in b_assets:
            a, b = a_assets[k], b_assets[k]
            if a["status"] != b["status"] or a["priority"] != b["priority"]:
                changed.append({"name": k, "from": {"status": a["status"], "priority": a["priority"]}, "to": {"status": b["status"], "priority": b["priority"]}})
    return jsonify({"added": added, "removed": removed, "changed": changed})

# ── 资源 API ────────────────────────────────────────────────

@app.route("/api/snapshots/<sid>/assets", methods=["GET"])
def list_assets(sid):
    status   = request.args.get("status")
    category = request.args.get("category")
    assignee = request.args.get("assignee")
    with get_db() as conn:
        q = "SELECT * FROM assets WHERE snapshot_id=?"
        p = [sid]
        if status:   q += " AND status=?";   p.append(status)
        if category: q += " AND category=?"; p.append(category)
        if assignee: q += " AND assignee=?"; p.append(assignee)
        q += " ORDER BY created_at DESC"
        rows = conn.execute(q, p).fetchall()
    return jsonify([dict(r) for r in rows])

@app.route("/api/snapshots/<sid>/assets", methods=["POST"])
def create_asset(sid):
    data = request.get_json()
    if not data or not data.get("name"):
        return jsonify({"error": "name 必填"}), 400
    with get_db() as conn:
        snap = conn.execute("SELECT * FROM snapshots WHERE id=?", (sid,)).fetchone()
        if not snap:
            return jsonify({"error": "快照不存在"}), 404
        if not dict(snap)["is_refining"]:
            return jsonify({"error": "快照未处于「完善中」状态，无法添加资源"}), 403
        aid = str(uuid.uuid4())
        now = now_iso()
        conn.execute(
            "INSERT INTO assets (id,snapshot_id,name,category,description,priority,status,created_by,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (aid, sid, data["name"], data.get("category","其他"), data.get("description",""),
             data.get("priority","中"), "pending", data.get("created_by",""), now, now)
        )
        log_act(conn, "asset_created", data.get("created_by",""), data["name"], snapshot_id=sid, asset_id=aid)
    cfg = load_config()
    notify("📋 新资源", event_type="info", extra={"名称": data["name"], "分类": data.get("category",""), "优先级": data.get("priority","中")})
    return jsonify({"id": aid, "ok": True}), 201

@app.route("/api/assets/batch", methods=["POST"])
def batch_assets():
    data = request.get_json() or {}
    ids = data.get("ids", [])
    action = data.get("action", "")
    if not ids or action not in ("delete", "update"):
        return jsonify({"error": "ids 和 action(delete/update) 必填"}), 400
    processed, skipped, skip_reasons = 0, 0, []
    with get_db() as conn:
        for aid in ids:
            row = conn.execute("SELECT a.*, s.is_refining FROM assets a JOIN snapshots s ON a.snapshot_id=s.id WHERE a.id=?", (aid,)).fetchone()
            if not row:
                skipped += 1; skip_reasons.append(f"{aid}: 不存在"); continue
            t = dict(row)
            if not t["is_refining"]:
                skipped += 1; skip_reasons.append(f"{t['name']}: 快照非完善中状态"); continue
            if action == "delete":
                if t["status"] != "pending":
                    skipped += 1; skip_reasons.append(f"{t['name']}: 非pending不可删除"); continue
                conn.execute("DELETE FROM reviews WHERE asset_id=?", (aid,))
                conn.execute("DELETE FROM comments WHERE asset_id=?", (aid,))
                conn.execute("DELETE FROM files WHERE asset_id=?", (aid,))
                conn.execute("DELETE FROM assets WHERE id=?", (aid,))
                processed += 1
            elif action == "update":
                upd = data.get("data", {})
                allowed = ["priority","category","assignee","status"]
                sets, params = [], []
                for k in allowed:
                    if k in upd: sets.append(f"{k}=?"); params.append(upd[k])
                if sets:
                    sets.append("updated_at=?"); params.append(now_iso()); params.append(aid)
                    conn.execute(f"UPDATE assets SET {', '.join(sets)} WHERE id=?", params)
                    log_act(conn, "batch_update", data.get("actor",""), str(upd), asset_id=aid)
                    processed += 1
    return jsonify({"ok": True, "processed": processed, "skipped": skipped, "skip_reasons": skip_reasons})

@app.route("/api/assets/<aid>", methods=["GET"])
def get_asset(aid):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM assets WHERE id=?", (aid,)).fetchone()
        if not row:
            return jsonify({"error": "not found"}), 404
        a = dict(row)
        a["files"]    = [dict(r) for r in conn.execute("SELECT * FROM files WHERE asset_id=? ORDER BY uploaded_at DESC", (aid,)).fetchall()]
        a["reviews"]  = [dict(r) for r in conn.execute("SELECT * FROM reviews WHERE asset_id=? ORDER BY created_at DESC", (aid,)).fetchall()]
        a["comments"] = [dict(r) for r in conn.execute("SELECT * FROM comments WHERE asset_id=? ORDER BY created_at ASC", (aid,)).fetchall()]
        a["activity"] = [dict(r) for r in conn.execute("SELECT * FROM activity_log WHERE asset_id=? ORDER BY created_at DESC LIMIT 20", (aid,)).fetchall()]
    return jsonify(a)

@app.route("/api/assets/<aid>", methods=["PUT"])
def update_asset(aid):
    data = request.get_json() or {}
    with get_db() as conn:
        row = conn.execute("SELECT a.*, s.is_refining FROM assets a JOIN snapshots s ON a.snapshot_id=s.id WHERE a.id=?", (aid,)).fetchone()
        if not row:
            return jsonify({"error": "not found"}), 404
        if not dict(row)["is_refining"]:
            return jsonify({"error": "快照未处于「完善中」状态，无法修改资源"}), 403
        allowed = ["name","description","category","priority","assignee"]
        sets, params = [], []
        for k in allowed:
            if k in data: sets.append(f"{k}=?"); params.append(data[k])
        if not sets:
            return jsonify({"error": "无可更新字段"}), 400
        sets.append("updated_at=?"); params.append(now_iso()); params.append(aid)
        conn.execute(f"UPDATE assets SET {', '.join(sets)} WHERE id=?", params)
        log_act(conn, "asset_updated", data.get("actor",""), str(data), asset_id=aid)
    return jsonify({"ok": True})

@app.route("/api/assets/<aid>", methods=["DELETE"])
def delete_asset(aid):
    with get_db() as conn:
        row = conn.execute("SELECT a.*, s.is_refining FROM assets a JOIN snapshots s ON a.snapshot_id=s.id WHERE a.id=?", (aid,)).fetchone()
        if not row:
            return jsonify({"error": "not found"}), 404
        t = dict(row)
        if not t["is_refining"]:
            return jsonify({"error": "快照未处于「完善中」状态，无法删除资源"}), 403
        if t["status"] != "pending":
            return jsonify({"error": f"无法删除：资源已处于「{t['status']}」状态，只有 pending 的资源可以删除"}), 403
        conn.execute("DELETE FROM reviews WHERE asset_id=?", (aid,))
        conn.execute("DELETE FROM comments WHERE asset_id=?", (aid,))
        conn.execute("DELETE FROM files WHERE asset_id=?", (aid,))
        conn.execute("DELETE FROM assets WHERE id=?", (aid,))
    return jsonify({"ok": True})

@app.route("/api/assets/<aid>/claim", methods=["POST"])
def claim_asset(aid):
    data = request.get_json() or {}
    assignee = data.get("assignee","").strip()
    if not assignee:
        return jsonify({"error": "assignee 必填"}), 400
    with get_db() as conn:
        row = conn.execute("SELECT a.*, s.is_refining FROM assets a JOIN snapshots s ON a.snapshot_id=s.id WHERE a.id=?", (aid,)).fetchone()
        if not row:
            return jsonify({"error": "not found"}), 404
        t = dict(row)
        if not t["is_refining"]:
            return jsonify({"error": "快照非完善中状态"}), 403
        if t["status"] != "pending":
            return jsonify({"error": "资源已被认领或已完成"}), 409
        conn.execute("UPDATE assets SET status='in_review', assignee=?, updated_at=? WHERE id=?", (assignee, now_iso(), aid))
        log_act(conn, "asset_claimed", assignee, f"认领: {assignee}", asset_id=aid)
    notify("🙋 资源被认领", event_type="warn", extra={"资源": t["name"], "认领人": assignee})
    return jsonify({"ok": True})

@app.route("/api/assets/<aid>/review", methods=["POST"])
def review_asset(aid):
    data = request.get_json() or {}
    reviewer = data.get("reviewer","").strip()
    status   = data.get("status","").strip()
    comment  = data.get("comment","")
    if not reviewer or status not in ("approved","rejected","changes_requested"):
        return jsonify({"error": "reviewer 和 status 必填"}), 400
    now = now_iso()
    with get_db() as conn:
        row = conn.execute("SELECT * FROM assets WHERE id=?", (aid,)).fetchone()
        if not row:
            return jsonify({"error": "not found"}), 404
        rid = str(uuid.uuid4())
        conn.execute("INSERT INTO reviews (id,asset_id,reviewer,status,comment,created_at) VALUES (?,?,?,?,?,?)", (rid, aid, reviewer, status, comment, now))
        conn.execute("UPDATE assets SET status=?, updated_at=? WHERE id=?", (status, now, aid))
        log_act(conn, f"review:{status}", reviewer, comment, asset_id=aid)
    t = dict(row)
    et = {"approved":"success","rejected":"danger","changes_requested":"warn"}.get(status,"info")
    notify(f"审核结果：{'✅通过' if status=='approved' else '❌拒绝' if status=='rejected' else '🔄需修改'}", event_type=et, extra={"资源": t["name"], "审核员": reviewer, "意见": comment})
    return jsonify({"ok": True, "review_id": rid})

@app.route("/api/assets/<aid>/upload", methods=["POST"])
def upload_file(aid):
    cfg = load_config()
    allowed_ext = set(cfg.get("storage",{}).get("allowed_extensions", ["png","jpg","jpeg","gif","webp","psd","svg","mp4","fbx","obj","unity3d"]))
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
        conn.execute("INSERT INTO files (id,asset_id,filename,original,file_size,mime_type,uploaded_at) VALUES (?,?,?,?,?,?,?)", (fid, aid, safe_name, f.filename, len(content), f.mimetype, now))
        log_act(conn, "file_uploaded", "", f.filename, asset_id=aid)
    return jsonify({"file_id": fid, "filename": safe_name, "ok": True}), 201

@app.route("/api/assets/<aid>/files", methods=["GET"])
def list_files(aid):
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM files WHERE asset_id=? ORDER BY uploaded_at DESC", (aid,)).fetchall()
    return jsonify([dict(r) for r in rows])

@app.route("/api/uploads/<aid>/<filename>")
def serve_file(aid, filename):
    return send_from_directory(os.path.join(UPLOAD_DIR, aid), filename)

@app.route("/api/assets/<aid>/comments", methods=["GET"])
def list_comments(aid):
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM comments WHERE asset_id=? ORDER BY created_at ASC", (aid,)).fetchall()
    return jsonify([dict(r) for r in rows])

@app.route("/api/assets/<aid>/comments", methods=["POST"])
def create_comment(aid):
    data = request.get_json() or {}
    if not data.get("author") or not data.get("content"):
        return jsonify({"error": "author 和 content 必填"}), 400
    with get_db() as conn:
        if not conn.execute("SELECT id FROM assets WHERE id=?", (aid,)).fetchone():
            return jsonify({"error": "not found"}), 404
        cid = str(uuid.uuid4())
        conn.execute("INSERT INTO comments (id,asset_id,author,content,created_at) VALUES (?,?,?,?,?)", (cid, aid, data["author"], data["content"], now_iso()))
    return jsonify({"id": cid, "ok": True}), 201

@app.route("/api/assets/<aid>/comments/<cid>", methods=["DELETE"])
def delete_comment(aid, cid):
    with get_db() as conn:
        if not conn.execute("SELECT id FROM comments WHERE id=? AND asset_id=?", (cid, aid)).fetchone():
            return jsonify({"error": "not found"}), 404
        conn.execute("DELETE FROM comments WHERE id=?", (cid,))
    return jsonify({"ok": True})

@app.route("/api/assets/<aid>/trigger-cicd", methods=["POST"])
def manual_trigger(aid):
    with get_db() as conn:
        row = conn.execute("SELECT a.*, s.version FROM assets a JOIN snapshots s ON a.snapshot_id=s.id WHERE a.id=?", (aid,)).fetchone()
        if not row:
            return jsonify({"error": "not found"}), 404
    t = dict(row)
    triggered = trigger_cicd(t["snapshot_id"], t["version"], reviewer="manual-test")
    return jsonify({"ok": True, "triggered": triggered})

@app.route("/api/stats")
def stats():
    with get_db() as conn:
        snaps = conn.execute("SELECT COUNT(*) FROM snapshots WHERE is_archived=0").fetchone()[0]
        total = conn.execute("SELECT COUNT(*) FROM assets").fetchone()[0]
        pending = conn.execute("SELECT COUNT(*) FROM assets WHERE status='pending'").fetchone()[0]
        in_rev  = conn.execute("SELECT COUNT(*) FROM assets WHERE status='in_review'").fetchone()[0]
        approved= conn.execute("SELECT COUNT(*) FROM assets WHERE status='approved'").fetchone()[0]
        rejected= conn.execute("SELECT COUNT(*) FROM assets WHERE status='rejected'").fetchone()[0]
        changes = conn.execute("SELECT COUNT(*) FROM assets WHERE status='changes_requested'").fetchone()[0]
    return jsonify({"active_snapshots": snaps, "total_assets": total, "pending": pending, "in_review": in_rev, "approved": approved, "rejected": rejected, "changes_requested": changes})

if __name__ == "__main__":
    init_db()
    cfg = load_config()
    port  = cfg.get("server",{}).get("port", 8899)
    debug = cfg.get("server",{}).get("debug", False)
    print(f"[START] ArtHub v2 启动，端口 {port}")
    app.run(host="0.0.0.0", port=port, debug=debug)
