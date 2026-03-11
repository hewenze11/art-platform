#!/usr/bin/env python3
"""
美术资源审核平台 - Flask 后端
与项目解耦的独立工具，通过 project.yaml 绑定具体项目
"""

import os
import json
import uuid
import yaml
import requests
from datetime import datetime
from pathlib import Path
from flask import Flask, request, jsonify, send_from_directory, send_file
from flask_cors import CORS
import sqlite3

# ──────────────────────────────────────────────
# 配置加载
# ──────────────────────────────────────────────

CONFIG_PATH = os.environ.get("CONFIG_PATH", "/app/project.yaml")
DATA_DIR    = os.environ.get("DATA_DIR", "/data")
DB_PATH     = os.path.join(DATA_DIR, "artplatform.db")
UPLOAD_DIR  = os.path.join(DATA_DIR, "uploads")

def load_config():
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except Exception as e:
        print(f"[WARN] 无法加载 project.yaml: {e}，使用默认配置")
        return {}

# ──────────────────────────────────────────────
# Flask 初始化
# ──────────────────────────────────────────────

app = Flask(__name__, static_folder="static", template_folder="templates")
CORS(app)

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)

# ──────────────────────────────────────────────
# 数据库
# ──────────────────────────────────────────────

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS tasks (
            id          TEXT PRIMARY KEY,
            title       TEXT NOT NULL,
            description TEXT,
            category    TEXT,
            priority    TEXT DEFAULT '中',
            status      TEXT DEFAULT 'pending',
            assignee    TEXT,
            created_by  TEXT,
            created_at  TEXT NOT NULL,
            updated_at  TEXT NOT NULL,
            due_date    TEXT,
            attachments TEXT DEFAULT '[]'
        );

        CREATE TABLE IF NOT EXISTS assets (
            id          TEXT PRIMARY KEY,
            task_id     TEXT NOT NULL,
            filename    TEXT NOT NULL,
            original    TEXT NOT NULL,
            file_size   INTEGER,
            mime_type   TEXT,
            version     INTEGER DEFAULT 1,
            uploaded_at TEXT NOT NULL,
            FOREIGN KEY (task_id) REFERENCES tasks(id)
        );

        CREATE TABLE IF NOT EXISTS reviews (
            id          TEXT PRIMARY KEY,
            task_id     TEXT NOT NULL,
            reviewer    TEXT NOT NULL,
            status      TEXT NOT NULL,
            comment     TEXT,
            created_at  TEXT NOT NULL,
            FOREIGN KEY (task_id) REFERENCES tasks(id)
        );

        CREATE TABLE IF NOT EXISTS activity_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id     TEXT NOT NULL,
            action      TEXT NOT NULL,
            actor       TEXT,
            detail      TEXT,
            created_at  TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS comments (
            id          TEXT PRIMARY KEY,
            task_id     TEXT NOT NULL,
            author      TEXT NOT NULL,
            content     TEXT NOT NULL,
            created_at  TEXT NOT NULL,
            FOREIGN KEY (task_id) REFERENCES tasks(id)
        );
        """)
    print(f"[DB] 数据库初始化完成: {DB_PATH}")

def now_iso():
    return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

def log_activity(conn, task_id, action, actor="", detail=""):
    conn.execute(
        "INSERT INTO activity_log (task_id, action, actor, detail, created_at) VALUES (?,?,?,?,?)",
        (task_id, action, actor, detail, now_iso())
    )

# ──────────────────────────────────────────────
# 工具函数
# ──────────────────────────────────────────────

def notify(message: str, event_type: str = "info", extra: dict = None):
    """发送飞书通知，优先发卡片消息，失败则降级为文本"""
    cfg = load_config()
    feishu_url = cfg.get("notifications", {}).get("feishu_webhook", "")
    if not feishu_url:
        return

    extra = extra or {}
    proj = cfg.get("project", {}).get("name", "美术平台")

    # 颜色映射
    color_map = {"info": "blue", "warn": "yellow", "success": "green", "danger": "red"}
    color = color_map.get(event_type, "blue")

    # 构建卡片 elements
    elements = []
    for k, v in extra.items():
        if v:
            elements.append({"tag": "div", "text": {"tag": "lark_md", "content": f"**{k}**：{v}"}})

    card_payload = {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {"tag": "plain_text", "content": f"[{proj}] {message}"},
                "template": color
            },
            "elements": elements if elements else [
                {"tag": "div", "text": {"tag": "lark_md", "content": message}}
            ]
        }
    }

    try:
        resp = requests.post(feishu_url, json=card_payload, timeout=5)
        if resp.json().get("code", 0) != 0:
            raise ValueError(resp.text)
        print(f"[NOTIFY] 飞书卡片通知成功")
    except Exception as e:
        print(f"[NOTIFY] 飞书卡片失败({e})，降级发文本")
        try:
            requests.post(feishu_url, json={
                "msg_type": "text",
                "content": {"text": f"[{proj}] {message}"}
            }, timeout=5)
        except Exception as e2:
            print(f"[NOTIFY] 飞书文本也失败: {e2}")

def trigger_cicd(task_id: str, task_title: str = "", reviewer: str = ""):
    """任务完成后触发 CI/CD（支持自定义 Webhook / GitHub Actions / GitLab Pipeline）"""
    cfg = load_config()
    cicd = cfg.get("cicd", {})
    triggered = []

    # ── 方式1：自定义 Webhook ──
    webhook_url = cicd.get("webhook_url", "")
    if webhook_url and "github.com/repos" not in webhook_url:
        try:
            requests.post(webhook_url, json={
                "task_id": task_id, "event": "task_approved",
                "title": task_title, "reviewer": reviewer
            }, timeout=10)
            triggered.append("webhook")
            print(f"[CICD] 自定义 Webhook 触发成功: {webhook_url}")
        except Exception as e:
            print(f"[CICD] Webhook 失败: {e}")

    # ── 方式2：GitHub Actions repository_dispatch ──
    repo_url = cicd.get("repo_url", "")
    ci_token = cicd.get("ci_token", "")
    if ci_token and "github.com" in repo_url:
        try:
            # 从 https://github.com/owner/repo 提取 owner/repo
            parts = repo_url.rstrip("/").split("github.com/")[-1].split("/")
            owner, repo = parts[0], parts[1]
            dispatch_url = f"https://api.github.com/repos/{owner}/{repo}/dispatches"
            event_type = cicd.get("github_actions_event", "art_approved")
            resp = requests.post(dispatch_url, json={
                "event_type": event_type,
                "client_payload": {
                    "task_id": task_id,
                    "title": task_title,
                    "reviewer": reviewer,
                    "approved_at": now_iso()
                }
            }, headers={
                "Authorization": f"token {ci_token}",
                "Accept": "application/vnd.github.v3+json"
            }, timeout=15)
            if resp.status_code in (204, 200):
                triggered.append("github_actions")
                print(f"[CICD] GitHub Actions dispatch 成功: {owner}/{repo} event={event_type}")
            else:
                print(f"[CICD] GitHub Actions dispatch 失败 {resp.status_code}: {resp.text}")
        except Exception as e:
            print(f"[CICD] GitHub Actions 异常: {e}")

    # ── 方式3：GitLab Pipeline Trigger ──
    gitlab_token = cicd.get("gitlab_token", "")
    gitlab_trigger_url = cicd.get("gitlab_trigger_url", "")
    if gitlab_token and gitlab_trigger_url:
        try:
            resp = requests.post(gitlab_trigger_url, data={
                "token": gitlab_token,
                "ref": cicd.get("branch", "main"),
                "variables[ART_TASK_ID]": task_id,
                "variables[ART_TASK_TITLE]": task_title,
            }, timeout=15)
            if resp.status_code in (200, 201):
                triggered.append("gitlab_pipeline")
                print(f"[CICD] GitLab Pipeline 触发成功")
            else:
                print(f"[CICD] GitLab Pipeline 失败 {resp.status_code}")
        except Exception as e:
            print(f"[CICD] GitLab Pipeline 异常: {e}")

    return triggered

# ──────────────────────────────────────────────
# 静态文件
# ──────────────────────────────────────────────

@app.route("/")
def index():
    return send_file("templates/index.html")

@app.route("/static/<path:filename>")
def static_files(filename):
    return send_from_directory("static", filename)

@app.route("/api/docs")
def api_docs():
    """返回 AI 接口文档（Markdown 格式）"""
    doc_path = os.path.join(os.path.dirname(__file__), "API_REFERENCE.md")
    try:
        with open(doc_path, "r", encoding="utf-8") as f:
            content = f.read()
        return content, 200, {"Content-Type": "text/markdown; charset=utf-8"}
    except FileNotFoundError:
        return "API_REFERENCE.md not found", 404

# ──────────────────────────────────────────────
# API: 配置
# ──────────────────────────────────────────────

@app.route("/api/config")
def api_config():
    cfg = load_config()
    return jsonify({
        "project": cfg.get("project", {}),
        "review":  cfg.get("review", {
            "reviewers":  ["CTO", "主美", "程序"],
            "priorities": ["紧急", "高", "中", "低"],
            "categories": ["角色", "场景", "UI", "特效", "音效", "动画", "其他"],
        }),
    })

@app.route("/api/config/project", methods=["GET", "PUT"])
def api_config_project():
    """读写 project.yaml（JSON 补丁形式）"""
    if request.method == "GET":
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                return f.read(), 200, {"Content-Type": "text/plain; charset=utf-8"}
        except FileNotFoundError:
            return "配置文件不存在", 404
    else:
        data = request.get_json()
        if not data:
            return jsonify({"error": "需要 JSON body"}), 400
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f) or {}
            cfg.update(data)
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                yaml.dump(cfg, f, allow_unicode=True, default_flow_style=False)
            return jsonify({"ok": True})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

@app.route("/api/config/project/raw", methods=["PUT"])
def api_config_project_raw():
    """直接写入 project.yaml 原始文本（供前端编辑器使用）"""
    text = request.get_data(as_text=True)
    if not text.strip():
        return jsonify({"error": "内容不能为空"}), 400
    try:
        yaml.safe_load(text)  # 验证 YAML 格式
    except yaml.YAMLError as e:
        return jsonify({"error": f"YAML 格式错误: {e}"}), 400
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            f.write(text)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ──────────────────────────────────────────────
# API: 任务 CRUD
# ──────────────────────────────────────────────

@app.route("/api/tasks", methods=["GET"])
def list_tasks():
    status   = request.args.get("status")
    category = request.args.get("category")
    assignee = request.args.get("assignee")
    with get_db() as conn:
        query = "SELECT * FROM tasks WHERE 1=1"
        params = []
        if status:
            query += " AND status=?"
            params.append(status)
        if category:
            query += " AND category=?"
            params.append(category)
        if assignee:
            query += " AND assignee=?"
            params.append(assignee)
        query += " ORDER BY created_at DESC"
        rows = conn.execute(query, params).fetchall()
        tasks = []
        for r in rows:
            t = dict(r)
            t["attachments"] = json.loads(t.get("attachments") or "[]")
            tasks.append(t)
    return jsonify(tasks)

@app.route("/api/tasks", methods=["POST"])
def create_task():
    data = request.get_json()
    if not data or not data.get("title"):
        return jsonify({"error": "title 必填"}), 400
    task_id = str(uuid.uuid4())
    now = now_iso()
    with get_db() as conn:
        conn.execute(
            """INSERT INTO tasks (id,title,description,category,priority,status,
               created_by,created_at,updated_at,due_date)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (task_id, data["title"], data.get("description",""),
             data.get("category","其他"), data.get("priority","中"),
             "pending", data.get("created_by",""), now, now,
             data.get("due_date",""))
        )
        log_activity(conn, task_id, "created", data.get("created_by",""), data["title"])

    notify(f"📋 新任务", event_type="info", extra={
        "标题": data["title"],
        "分类": data.get("category", "其他"),
        "优先级": data.get("priority", "中"),
        "创建人": data.get("created_by", "")
    })
    return jsonify({"id": task_id, "ok": True}), 201

@app.route("/api/tasks/batch", methods=["POST"])
def batch_tasks():
    data = request.get_json() or {}
    ids = data.get("ids", [])
    action = data.get("action", "")
    if not ids or action not in ("delete", "update"):
        return jsonify({"error": "ids 和 action(delete/update) 必填"}), 400

    processed, skipped, skip_reasons = 0, 0, []
    with get_db() as conn:
        for tid in ids:
            row = conn.execute("SELECT * FROM tasks WHERE id=?", (tid,)).fetchone()
            if not row:
                skipped += 1; skip_reasons.append(f"{tid}: 不存在"); continue
            t = dict(row)
            if action == "delete":
                if t["status"] != "pending":
                    skipped += 1; skip_reasons.append(f"{t['title']}: 非pending状态不可删除"); continue
                conn.execute("DELETE FROM reviews WHERE task_id=?", (tid,))
                conn.execute("DELETE FROM activity_log WHERE task_id=?", (tid,))
                conn.execute("DELETE FROM assets WHERE task_id=?", (tid,))
                conn.execute("DELETE FROM tasks WHERE id=?", (tid,))
                processed += 1
            elif action == "update":
                upd = data.get("data", {})
                allowed = ["priority", "category", "assignee", "due_date"]
                sets, params = [], []
                for k in allowed:
                    if k in upd:
                        sets.append(f"{k}=?"); params.append(upd[k])
                if sets:
                    sets.append("updated_at=?"); params.append(now_iso()); params.append(tid)
                    conn.execute(f"UPDATE tasks SET {', '.join(sets)} WHERE id=?", params)
                    log_activity(conn, tid, "batch_update", data.get("actor",""), str(upd))
                    processed += 1
    return jsonify({"ok": True, "processed": processed, "skipped": skipped, "skip_reasons": skip_reasons})

@app.route("/api/tasks/<task_id>", methods=["GET"])
def get_task(task_id):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
        if not row:
            return jsonify({"error": "not found"}), 404
        t = dict(row)
        t["attachments"] = json.loads(t.get("attachments") or "[]")
        # 附带审核记录
        reviews = conn.execute(
            "SELECT * FROM reviews WHERE task_id=? ORDER BY created_at DESC", (task_id,)
        ).fetchall()
        t["reviews"] = [dict(r) for r in reviews]
        # 活动日志
        logs = conn.execute(
            "SELECT * FROM activity_log WHERE task_id=? ORDER BY created_at DESC LIMIT 20", (task_id,)
        ).fetchall()
        t["activity"] = [dict(l) for l in logs]
    return jsonify(t)

@app.route("/api/tasks/<task_id>", methods=["PUT"])
def update_task(task_id):
    data = request.get_json()
    if not data:
        return jsonify({"error": "需要 JSON body"}), 400
    with get_db() as conn:
        row = conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
        if not row:
            return jsonify({"error": "not found"}), 404

        allowed = ["title","description","category","priority","status","assignee","due_date"]
        sets = []
        params = []
        for k in allowed:
            if k in data:
                sets.append(f"{k}=?")
                params.append(data[k])
        if not sets:
            return jsonify({"error": "无可更新字段"}), 400

        sets.append("updated_at=?")
        params.append(now_iso())
        params.append(task_id)
        conn.execute(f"UPDATE tasks SET {', '.join(sets)} WHERE id=?", params)
        log_activity(conn, task_id, "updated", data.get("actor",""), str(data))

    return jsonify({"ok": True})

@app.route("/api/tasks/<task_id>", methods=["DELETE"])
def delete_task(task_id):
    """只允许删除状态为 pending（未被接手）的任务"""
    with get_db() as conn:
        row = conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
        if not row:
            return jsonify({"error": "任务不存在"}), 404
        task = dict(row)
        if task["status"] != "pending":
            return jsonify({
                "error": f"无法删除：任务已处于「{task['status']}」状态，只有未被接手的任务（pending）才能删除"
            }), 403
        # 删除关联数据
        conn.execute("DELETE FROM reviews WHERE task_id=?", (task_id,))
        conn.execute("DELETE FROM activity_log WHERE task_id=?", (task_id,))
        conn.execute("DELETE FROM assets WHERE task_id=?", (task_id,))
        conn.execute("DELETE FROM tasks WHERE id=?", (task_id,))
    return jsonify({"ok": True})

# ──────────────────────────────────────────────
# API: 任务认领 / 状态流转
# ──────────────────────────────────────────────

@app.route("/api/tasks/<task_id>/claim", methods=["POST"])
def claim_task(task_id):
    """认领任务（pending → in_review）"""
    data = request.get_json() or {}
    assignee = data.get("assignee", "").strip()
    if not assignee:
        return jsonify({"error": "assignee 必填"}), 400
    with get_db() as conn:
        row = conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
        if not row:
            return jsonify({"error": "not found"}), 404
        if dict(row)["status"] != "pending":
            return jsonify({"error": "任务已被认领或已完成"}), 409
        conn.execute(
            "UPDATE tasks SET status='in_review', assignee=?, updated_at=? WHERE id=?",
            (assignee, now_iso(), task_id)
        )
        log_activity(conn, task_id, "claimed", assignee, f"认领人: {assignee}")

    cfg = load_config()
    task_title = dict(row)["title"]
    notify(f"🙋 任务被认领", event_type="warn", extra={
        "任务": task_title,
        "认领人": assignee
    })
    return jsonify({"ok": True})

@app.route("/api/tasks/<task_id>/review", methods=["POST"])
def submit_review(task_id):
    """提交审核结果（approved / rejected / changes_requested）"""
    data = request.get_json() or {}
    reviewer = data.get("reviewer", "").strip()
    status   = data.get("status", "").strip()
    comment  = data.get("comment", "")
    if not reviewer or status not in ("approved", "rejected", "changes_requested"):
        return jsonify({"error": "reviewer 和 status(approved/rejected/changes_requested) 必填"}), 400

    review_id = str(uuid.uuid4())
    now = now_iso()
    with get_db() as conn:
        row = conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
        if not row:
            return jsonify({"error": "not found"}), 404

        conn.execute(
            "INSERT INTO reviews (id,task_id,reviewer,status,comment,created_at) VALUES (?,?,?,?,?,?)",
            (review_id, task_id, reviewer, status, comment, now)
        )
        # 更新任务状态
        new_status = {
            "approved":           "approved",
            "rejected":           "rejected",
            "changes_requested":  "changes_requested",
        }[status]
        conn.execute(
            "UPDATE tasks SET status=?, updated_at=? WHERE id=?",
            (new_status, now, task_id)
        )
        log_activity(conn, task_id, f"review:{status}", reviewer, comment)

    if status == "approved":
        cfg = load_config()
        task_title = dict(row)["title"]
        trigger_cicd(task_id, task_title, reviewer)
        notify(f"✅ 任务通过审核", event_type="success", extra={
            "任务": task_title,
            "审核人": reviewer,
            "仓库": cfg.get("cicd", {}).get("repo_url", "")
        })
    return jsonify({"ok": True, "review_id": review_id})

# ──────────────────────────────────────────────
# API: 文件上传
# ──────────────────────────────────────────────

@app.route("/api/tasks/<task_id>/upload", methods=["POST"])
def upload_asset(task_id):
    cfg = load_config()
    allowed_ext = set(cfg.get("storage", {}).get("allowed_extensions", [
        "png","jpg","jpeg","gif","webp","psd","svg","mp4","fbx","obj"
    ]))
    max_mb = cfg.get("storage", {}).get("max_file_size_mb", 50)

    with get_db() as conn:
        row = conn.execute("SELECT id FROM tasks WHERE id=?", (task_id,)).fetchone()
        if not row:
            return jsonify({"error": "task not found"}), 404

    if "file" not in request.files:
        return jsonify({"error": "no file"}), 400

    f = request.files["file"]
    ext = f.filename.rsplit(".", 1)[-1].lower() if "." in f.filename else ""
    if ext not in allowed_ext:
        return jsonify({"error": f"不支持的文件类型: {ext}"}), 400

    content = f.read()
    if len(content) > max_mb * 1024 * 1024:
        return jsonify({"error": f"文件超过 {max_mb}MB 限制"}), 413

    asset_id  = str(uuid.uuid4())
    safe_name = f"{asset_id}.{ext}"
    dest_dir  = os.path.join(UPLOAD_DIR, task_id)
    os.makedirs(dest_dir, exist_ok=True)
    dest_path = os.path.join(dest_dir, safe_name)
    with open(dest_path, "wb") as out:
        out.write(content)

    now = now_iso()
    with get_db() as conn:
        conn.execute(
            "INSERT INTO assets (id,task_id,filename,original,file_size,mime_type,uploaded_at) VALUES (?,?,?,?,?,?,?)",
            (asset_id, task_id, safe_name, f.filename, len(content), f.mimetype, now)
        )
        log_activity(conn, task_id, "asset_uploaded", "", f.filename)

    return jsonify({"asset_id": asset_id, "filename": safe_name, "ok": True}), 201

@app.route("/api/tasks/<task_id>/assets", methods=["GET"])
def list_assets(task_id):
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM assets WHERE task_id=? ORDER BY uploaded_at DESC", (task_id,)
        ).fetchall()
    return jsonify([dict(r) for r in rows])

@app.route("/api/uploads/<task_id>/<filename>")
def serve_asset(task_id, filename):
    return send_from_directory(os.path.join(UPLOAD_DIR, task_id), filename)

# ──────────────────────────────────────────────
# API: 统计
# ──────────────────────────────────────────────

@app.route("/api/stats")
def stats():
    with get_db() as conn:
        total    = conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
        pending  = conn.execute("SELECT COUNT(*) FROM tasks WHERE status='pending'").fetchone()[0]
        in_rev   = conn.execute("SELECT COUNT(*) FROM tasks WHERE status='in_review'").fetchone()[0]
        approved = conn.execute("SELECT COUNT(*) FROM tasks WHERE status='approved'").fetchone()[0]
        rejected = conn.execute("SELECT COUNT(*) FROM tasks WHERE status='rejected'").fetchone()[0]
        changes  = conn.execute("SELECT COUNT(*) FROM tasks WHERE status='changes_requested'").fetchone()[0]
    return jsonify({
        "total": total,
        "pending": pending,
        "in_review": in_rev,
        "approved": approved,
        "rejected": rejected,
        "changes_requested": changes,
    })

# ──────────────────────────────────────────────
# API: 评论
# ──────────────────────────────────────────────

@app.route("/api/tasks/<task_id>/comments", methods=["GET"])
def list_comments(task_id):
    with get_db() as conn:
        row = conn.execute("SELECT id FROM tasks WHERE id=?", (task_id,)).fetchone()
        if not row:
            return jsonify({"error": "task not found"}), 404
        rows = conn.execute(
            "SELECT * FROM comments WHERE task_id=? ORDER BY created_at ASC", (task_id,)
        ).fetchall()
    return jsonify([dict(r) for r in rows])

@app.route("/api/tasks/<task_id>/comments", methods=["POST"])
def create_comment(task_id):
    data = request.get_json() or {}
    author  = data.get("author", "").strip()
    content = data.get("content", "").strip()
    if not author or not content:
        return jsonify({"error": "author 和 content 必填"}), 400
    with get_db() as conn:
        row = conn.execute("SELECT id FROM tasks WHERE id=?", (task_id,)).fetchone()
        if not row:
            return jsonify({"error": "task not found"}), 404
        comment_id = str(uuid.uuid4())
        now = now_iso()
        conn.execute(
            "INSERT INTO comments (id, task_id, author, content, created_at) VALUES (?,?,?,?,?)",
            (comment_id, task_id, author, content, now)
        )
        log_activity(conn, task_id, "comment_added", author, content[:60])
    return jsonify({"id": comment_id, "ok": True}), 201

@app.route("/api/tasks/<task_id>/comments/<comment_id>", methods=["DELETE"])
def delete_comment(task_id, comment_id):
    with get_db() as conn:
        row = conn.execute(
            "SELECT id FROM comments WHERE id=? AND task_id=?", (comment_id, task_id)
        ).fetchone()
        if not row:
            return jsonify({"error": "comment not found"}), 404
        conn.execute("DELETE FROM comments WHERE id=?", (comment_id,))
        log_activity(conn, task_id, "comment_deleted", "", comment_id)
    return jsonify({"ok": True})

@app.route("/api/tasks/<task_id>/trigger-cicd", methods=["POST"])
def manual_trigger_cicd(task_id):
    """手动触发 CI/CD，用于测试配置"""
    with get_db() as conn:
        row = conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
        if not row:
            return jsonify({"error": "not found"}), 404
        t = dict(row)
    triggered = trigger_cicd(task_id, t["title"], reviewer="manual-test")
    return jsonify({"ok": True, "triggered": triggered})


# ──────────────────────────────────────────────
# 入口
# ──────────────────────────────────────────────

if __name__ == "__main__":
    init_db()
    cfg = load_config()
    port  = cfg.get("server", {}).get("port", 8899)
    debug = cfg.get("server", {}).get("debug", False)
    print(f"[START] 美术资源审核平台启动，端口 {port}")
    app.run(host="0.0.0.0", port=port, debug=debug)
