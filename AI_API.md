# AI 调用说明 — Art Platform API

本文档供 AI（或其他程序）调用美术资源平台接口使用。

---

## 基础信息

- 默认地址：`http://<服务器IP>:8899`
- 无需鉴权，直接调用
- 所有请求/响应均为 JSON（上传文件除外）

---

## game_key 命名规范

`game_key` 是资源在游戏代码中的唯一标识，命名规则：
- **全小写 + 下划线**，不含空格和特殊字符
- 见名知意，体现资源的用途和位置

示例：
```
player_idle          玩家站立
player_run           玩家奔跑
player_jump          玩家跳跃
enemy_slime_walk     史莱姆行走
bg_music_main        主界面背景音乐
bg_music_battle      战斗背景音乐
ui_btn_start         开始按钮
ui_hp_bar            血量条
sfx_sword_hit        剑击音效
card_fire_attack     火焰攻击卡牌
```

---

## 1. 注册资源位（AI 最常用）

游戏做好基底后，AI 调用此接口声明游戏需要哪些美术资源。

**POST /api/slots**

```json
{
  "game_key":    "player_idle",
  "name":        "玩家站立动画",
  "description": "玩家在待机状态下的循环动画，朝右",
  "asset_type":  "image",
  "category":    "角色",
  "metadata":    { "width": 64, "height": 64, "fps": 0, "frames": 1 },
  "created_by":  "ai"
}
```

字段说明：

| 字段 | 必填 | 说明 |
|------|------|------|
| game_key | ✅ | 唯一标识，小写+下划线 |
| name | ✅ | 中文显示名称 |
| description | 否 | 用途说明，越详细越好，方便美术人员理解需求 |
| asset_type | 否 | `image`（默认）/ `audio` / `video` |
| category | 否 | 角色/场景/UI/特效/音效/其他 |
| metadata | 否 | JSON对象，图片填宽高帧数，音频填时长格式等 |
| created_by | 否 | 填 `"ai"` 标注来源 |

响应：
```json
{ "id": "uuid", "ok": true }
```

---

## 2. 批量注册资源位

循环调用 POST /api/slots 即可，示例（Python）：

```python
import requests

BASE = "http://服务器IP:8899"

slots = [
    { "game_key": "player_idle",    "name": "玩家站立", "asset_type": "image", "category": "角色",  "metadata": {"width":64,"height":64} },
    { "game_key": "player_run",     "name": "玩家奔跑", "asset_type": "image", "category": "角色",  "metadata": {"width":64,"height":64,"fps":8,"frames":4} },
    { "game_key": "bg_music_main",  "name": "主菜单BGM","asset_type": "audio", "category": "音效",  "metadata": {"loop":True,"format":"mp3"} },
    { "game_key": "ui_btn_start",   "name": "开始按钮", "asset_type": "image", "category": "UI",    "metadata": {"width":200,"height":60} },
]

for s in slots:
    s["created_by"] = "ai"
    r = requests.post(f"{BASE}/api/slots", json=s)
    print(s["game_key"], r.status_code, r.json())
```

---

## 3. 查看所有资源位

**GET /api/slots**

可选过滤参数：
- `?asset_type=audio` — 只看音频类资源位
- `?category=音效` — 只看某分类

响应示例：
```json
[
  {
    "id": "uuid",
    "game_key": "bg_music_main",
    "name": "主菜单BGM",
    "asset_type": "audio",
    "category": "音效",
    "active_resource": null,
    "resource_count": 0
  }
]
```

---

## 4. 添加音乐资源（AI 通过 URL 添加）

AI 擅长查找音乐资源，可通过 URL 方式添加，无需下载上传。

**POST /api/slots/{slot_id}/add-url**

```json
{
  "source_url":  "https://example.com/battle-theme.mp3",
  "note":        "来自 freemusicarchive.org，CC0 授权，节奏紧张适合战斗场景",
  "uploaded_by": "ai"
}
```

添加后状态默认为 `inactive`（黄色），需用户在 UI 上审核后手动激活为 `active`。

---

## 5. 上传本地文件资源

**POST /api/slots/{slot_id}/upload**

```
Content-Type: multipart/form-data
字段：
  file        - 文件内容
  uploaded_by - "ai" 或 "user"
  note        - 备注（可选）
```

Python 示例：
```python
with open("player_idle.png", "rb") as f:
    r = requests.post(
        f"{BASE}/api/slots/{slot_id}/upload",
        files={"file": ("player_idle.png", f, "image/png")},
        data={"uploaded_by": "ai", "note": "初稿，待审核"}
    )
```

---

## 6. 修改资源状态

**PUT /api/resources/{resource_id}/status**

```json
{ "status": "active" }
```

状态说明：
- `active` — 正在使用（绿）。设置后，同资源位其他资源自动变为 inactive
- `inactive` — 未使用（黄）
- `pending_delete` — 待删除（红）。执行 Sync 后从数据库和磁盘彻底删除

---

## 7. 读取 Manifest（游戏用）

获取所有资源位当前生效的资源，供游戏代码引用。

**GET /api/manifest**

```json
{
  "player_idle": {
    "game_key":     "player_idle",
    "slot_name":    "玩家站立动画",
    "asset_type":   "image",
    "category":     "角色",
    "url":          "http://服务器IP:8899/uploads/xxx/yyy.png",
    "is_placeholder": false,
    "resource_id":  "uuid",
    "original_name":"player_idle_v2.png",
    "metadata":     { "width": 64, "height": 64 }
  },
  "bg_music_main": {
    "game_key":     "bg_music_main",
    "url":          "https://upload.wikimedia.org/...Happy_Birthday.ogg",
    "is_placeholder": true,
    "asset_type":   "audio"
  }
}
```

`is_placeholder: true` 表示该资源位尚无激活资源，当前使用占位资源（爱因斯坦图/生日歌）。

**GET /api/manifest/{game_key}** — 获取单个资源

---

## 8. 执行 Sync

**POST /api/sync**

执行效果：
1. 彻底删除所有 `pending_delete` 状态的资源（数据库+磁盘文件）
2. 返回当前完整 manifest

建议先调用 GET /api/sync/preview 预览，确认无误再执行。

---

## 9. 统计信息

**GET /api/stats**

```json
{
  "total_slots": 12,
  "active":      8,
  "inactive":    5,
  "pending_delete": 2,
  "slots_no_active": 4
}
```

---

## 标准工作流程

```
1. AI 开发游戏基底代码（不含美术）
2. AI 调用 POST /api/slots 批量注册资源位（声明需要哪些资源）
3. AI 可调用 add-url 预填音乐资源候选（默认 inactive）
4. 用户打开 UI（http://服务器IP:8899）查看资源位
5. 用户上传图片资源，并将满意的资源设置为 active（绿色）
6. 用户通知 AI：「同步资源到游戏」
7. AI 调用 GET /api/manifest 获取最新资源清单，更新游戏引用
8. 可选：调用 POST /api/sync 清理待删除资源
```
