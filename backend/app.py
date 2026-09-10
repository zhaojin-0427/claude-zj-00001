"""宠物疫苗接种档案与到期提醒平台 —— Flask API"""
from datetime import date, datetime, timedelta
from flask import Flask, g, jsonify, request
from flask_cors import CORS

from db import get_db, close_db, init_db

app = Flask(__name__)
CORS(app)
app.teardown_appcontext(close_db)

SOON_DAYS = 30        # 30 天内到期视为"即将到期"
FIRST_VAC_AGE = 60    # 超过 60 日龄纳入应接种统计

# 随访计划状态：pending 待确认 / confirmed 已确认 / completed 已完成 / cancelled 已取消
PLAN_STATUSES = ("pending", "confirmed", "completed", "cancelled")
OPEN_PLAN_STATUSES = ("pending", "confirmed")   # 未结束
CLOSED_PLAN_STATUSES = ("completed", "cancelled")


# ---------- 工具 ----------
def row_to_dict(row):
    return dict(row) if row is not None else None


def parse_date(s):
    return datetime.strptime(s, "%Y-%m-%d").date()


def today():
    return date.today()


def vac_status(next_due: str | None, has_record: bool, pet_birth: str):
    """返回接种状态：overdue 逾期 / due_soon 即将到期 / valid 有效 / none 未接种 / too_young"""
    if pet_birth and (today() - parse_date(pet_birth)).days < FIRST_VAC_AGE:
        return "too_young"
    if not has_record:
        return "none"
    due = parse_date(next_due)
    delta = (due - today()).days
    if delta < 0:
        return "overdue"
    if delta <= SOON_DAYS:
        return "due_soon"
    return "valid"


# ---------- 主人 ----------
@app.get("/api/owners")
def list_owners():
    db = get_db()
    q = request.args.get("q", "").strip()
    sql = ("SELECT o.*, COUNT(p.id) AS pet_count FROM owners o "
           "LEFT JOIN pets p ON p.owner_id = o.id WHERE 1=1")
    args = []
    if q:
        sql += " AND (o.name LIKE ? OR o.phone LIKE ?)"
        args += [f"%{q}%", f"%{q}%"]
    sql += " GROUP BY o.id ORDER BY o.id DESC"
    return jsonify([row_to_dict(r) for r in db.execute(sql, args)])


@app.post("/api/owners")
def create_owner():
    data = request.get_json(force=True)
    if not data.get("name") or not data.get("phone"):
        return jsonify({"error": "姓名和手机号必填"}), 400
    db = get_db()
    cur = db.execute(
        "INSERT INTO owners(name, phone, address) VALUES(?,?,?)",
        (data["name"], data["phone"], data.get("address", "")))
    db.commit()
    return jsonify({"id": cur.lastrowid}), 201


# ---------- 宠物 ----------
@app.get("/api/pets")
def list_pets():
    db = get_db()
    species = request.args.get("species", "").strip()
    q = request.args.get("q", "").strip()
    sql = """SELECT p.*, o.name AS owner_name, o.phone AS owner_phone
             FROM pets p JOIN owners o ON o.id = p.owner_id WHERE 1=1"""
    args = []
    if species:
        sql += " AND p.species = ?"
        args.append(species)
    if q:
        sql += " AND (p.name LIKE ? OR o.name LIKE ? OR o.phone LIKE ?)"
        args += [f"%{q}%", f"%{q}%", f"%{q}%"]
    sql += " ORDER BY p.id DESC"
    pets = [row_to_dict(r) for r in db.execute(sql, args)]
    return jsonify(pets)


@app.get("/api/pets/<int:pet_id>")
def pet_detail(pet_id):
    db = get_db()
    pet = db.execute(
        """SELECT p.*, o.name AS owner_name, o.phone AS owner_phone,
                  o.address AS owner_address
           FROM pets p JOIN owners o ON o.id=p.owner_id WHERE p.id=?""",
        (pet_id,)).fetchone()
    if not pet:
        return jsonify({"error": "宠物不存在"}), 404
    pet = row_to_dict(pet)

    vacs = db.execute(
        """SELECT v.*, vac.vacc_date, vac.batch_no, vac.manufacturer,
                  vac.site, vac.doctor, vac.adverse_reaction, vac.next_due_date,
                  vac.note, vac.id AS vac_record_id,
                  va.name AS vaccine_name
           FROM vaccinations vac
           JOIN vaccines va ON va.id = vac.vaccine_id
           LEFT JOIN vaccines v ON v.id = vac.vaccine_id
           WHERE vac.pet_id=? ORDER BY vac.vacc_date DESC""",
        (pet_id,)).fetchall()
    vaccinations = []
    for r in vacs:
        d = row_to_dict(r)
        d["reaction_level"] = reaction_level(d.get("adverse_reaction"))
        vaccinations.append(d)

    antibodies = [row_to_dict(r) for r in db.execute(
        """SELECT a.*, va.name AS vaccine_name
           FROM antibody_tests a JOIN vaccines va ON va.id=a.vaccine_id
           WHERE a.pet_id=? ORDER BY a.test_date""", (pet_id,))]

    # 该宠物的随访计划历史
    followup_plans = [row_to_dict(r) for r in db.execute(
        """SELECT fp.*, v.name AS vaccine_name
           FROM followup_plans fp JOIN vaccines v ON v.id=fp.vaccine_id
           WHERE fp.pet_id=? ORDER BY fp.plan_date DESC, fp.id DESC""",
        (pet_id,))]

    # 每种适用疫苗的当前状态
    coverage = latest_status_for_pet(db, pet_id, pet["species"], pet["birth_date"])

    pet["vaccinations"] = vaccinations
    pet["antibodies"] = antibodies
    pet["followup_plans"] = followup_plans
    pet["vaccine_status"] = coverage
    return jsonify(pet)


def reaction_level(text):
    if not text or text == "无":
        return "none"
    if text.startswith("严重"):
        return "severe"
    return "mild"


def latest_status_for_pet(db, pet_id, species, birth):
    """该宠物各适用疫苗的最近一次接种与到期状态"""
    vaccines = db.execute(
        "SELECT * FROM vaccines WHERE species='通用' OR species=?",
        (species,)).fetchall()
    result = []
    for v in vaccines:
        last = db.execute(
            """SELECT * FROM vaccinations WHERE pet_id=? AND vaccine_id=?
               ORDER BY vacc_date DESC LIMIT 1""",
            (pet_id, v["id"])).fetchone()
        status = vac_status(last["next_due_date"] if last else None,
                            bool(last), birth)
        result.append({
            "vaccine_id": v["id"],
            "vaccine_name": v["name"],
            "interval_days": v["interval_days"],
            "status": status,
            "last_vacc_date": last["vacc_date"] if last else None,
            "next_due_date": last["next_due_date"] if last else None,
        })
    return result


@app.post("/api/pets")
def create_pet():
    d = request.get_json(force=True)
    required = ["owner_id", "name", "species"]
    for f in required:
        if not d.get(f):
            return jsonify({"error": f"缺少必填字段 {f}"}), 400
    db = get_db()
    if not db.execute("SELECT 1 FROM owners WHERE id=?", (d["owner_id"],)).fetchone():
        return jsonify({"error": "主人不存在"}), 400
    cur = db.execute(
        """INSERT INTO pets(owner_id,name,species,breed,gender,birth_date,
               color,microchip,neutered) VALUES(?,?,?,?,?,?,?,?,?)""",
        (d["owner_id"], d["name"], d["species"], d.get("breed", ""),
         d.get("gender", ""), d.get("birth_date"), d.get("color", ""),
         d.get("microchip", ""), 1 if d.get("neutered") else 0))
    db.commit()
    return jsonify({"id": cur.lastrowid}), 201


# ---------- 疫苗字典 ----------
@app.get("/api/vaccines")
def list_vaccines():
    db = get_db()
    species = request.args.get("species", "").strip()
    sql = "SELECT * FROM vaccines"
    args = []
    if species:
        sql += " WHERE species='通用' OR species=?"
        args.append(species)
    sql += " ORDER BY species, id"
    return jsonify([row_to_dict(r) for r in db.execute(sql, args)])


# ---------- 接种登记 ----------
@app.get("/api/vaccinations")
def list_vaccinations():
    db = get_db()
    pet_id = request.args.get("pet_id")
    sql = """SELECT vac.*, p.name AS pet_name, p.species,
                    o.name AS owner_name, o.phone AS owner_phone,
                    va.name AS vaccine_name
             FROM vaccinations vac
             JOIN pets p ON p.id=vac.pet_id
             JOIN owners o ON o.id=p.owner_id
             JOIN vaccines va ON va.id=vac.vaccine_id"""
    args = []
    if pet_id:
        sql += " WHERE vac.pet_id=?"
        args.append(pet_id)
    sql += " ORDER BY vac.vacc_date DESC, vac.id DESC LIMIT 500"
    rows = []
    for r in db.execute(sql, args):
        d = row_to_dict(r)
        d["reaction_level"] = reaction_level(d.get("adverse_reaction"))
        rows.append(d)
    return jsonify(rows)


@app.post("/api/vaccinations")
def create_vaccination():
    d = request.get_json(force=True)
    for f in ["pet_id", "vaccine_id", "vacc_date"]:
        if not d.get(f):
            return jsonify({"error": f"缺少必填字段 {f}"}), 400
    try:
        vacc_date = parse_date(d["vacc_date"])
    except (ValueError, TypeError):
        return jsonify({"error": "接种日期格式应为 YYYY-MM-DD"}), 400
    if vacc_date > today():
        return jsonify({"error": "接种日期不得晚于今天"}), 400
    db = get_db()
    vac = db.execute("SELECT * FROM vaccines WHERE id=?",
                     (d["vaccine_id"],)).fetchone()
    pet = db.execute("SELECT * FROM pets WHERE id=?",
                     (d["pet_id"],)).fetchone()
    if not vac or not pet:
        return jsonify({"error": "宠物或疫苗不存在"}), 400

    # 自动计算下次到期日：接种日 + 疫苗标准间隔（也允许前端传入覆盖）
    next_due = d.get("next_due_date")
    if not next_due:
        next_due = (vacc_date + timedelta(days=vac["interval_days"])).isoformat()
    else:
        try:
            next_due_date = parse_date(next_due)
        except (ValueError, TypeError):
            return jsonify({"error": "下次接种日期格式应为 YYYY-MM-DD"}), 400
        if next_due_date < vacc_date:
            return jsonify({"error": "下次接种日期不得早于本次接种日期"}), 400

    reaction = d.get("adverse_reaction", "无") or "无"
    cur = db.execute(
        """INSERT INTO vaccinations(pet_id,vaccine_id,vacc_date,batch_no,
               manufacturer,site,doctor,adverse_reaction,next_due_date,note)
           VALUES(?,?,?,?,?,?,?,?,?,?)""",
        (d["pet_id"], d["vaccine_id"], d["vacc_date"],
         d.get("batch_no", ""), d.get("manufacturer", ""),
         d.get("site", ""), d.get("doctor", ""), reaction,
         next_due, d.get("note", "")))

    # 自动完成该宠物+疫苗最近一条未结束的随访计划（同事务提交）
    open_plan = db.execute(
        """SELECT id FROM followup_plans
           WHERE pet_id=? AND vaccine_id=? AND status IN ('pending','confirmed')
           ORDER BY id DESC LIMIT 1""",
        (d["pet_id"], d["vaccine_id"])).fetchone()
    completed_plan_id = None
    if open_plan:
        db.execute(
            """UPDATE followup_plans SET status='completed',
                   updated_at=datetime('now','localtime') WHERE id=?""",
            (open_plan["id"],))
        completed_plan_id = open_plan["id"]

    db.commit()
    return jsonify({"id": cur.lastrowid, "next_due_date": next_due,
                    "completed_plan_id": completed_plan_id}), 201


# ---------- 抗体检测 ----------
@app.get("/api/antibodies")
def list_antibodies():
    db = get_db()
    pet_id = request.args.get("pet_id")
    sql = """SELECT a.*, p.name AS pet_name, va.name AS vaccine_name
             FROM antibody_tests a
             JOIN pets p ON p.id=a.pet_id
             JOIN vaccines va ON va.id=a.vaccine_id"""
    args = []
    if pet_id:
        sql += " WHERE a.pet_id=?"
        args.append(pet_id)
    sql += " ORDER BY a.test_date DESC LIMIT 500"
    return jsonify([row_to_dict(r) for r in db.execute(sql, args)])


@app.post("/api/antibodies")
def create_antibody():
    d = request.get_json(force=True)
    for f in ["pet_id", "vaccine_id", "test_date", "result"]:
        if not d.get(f):
            return jsonify({"error": f"缺少必填字段 {f}"}), 400
    if d["result"] not in ("阳性", "弱阳性", "阴性"):
        return jsonify({"error": "检测结果必须为 阳性/弱阳性/阴性"}), 400
    try:
        test_date = parse_date(d["test_date"])
    except (ValueError, TypeError):
        return jsonify({"error": "检测日期格式应为 YYYY-MM-DD"}), 400
    if test_date > today():
        return jsonify({"error": "检测日期不得晚于今天"}), 400
    db = get_db()
    cur = db.execute(
        """INSERT INTO antibody_tests(pet_id,vaccine_id,test_date,result,titer,lab,note)
           VALUES(?,?,?,?,?,?,?)""",
        (d["pet_id"], d["vaccine_id"], d["test_date"], d["result"],
         d.get("titer"), d.get("lab", ""), d.get("note", "")))
    db.commit()
    return jsonify({"id": cur.lastrowid}), 201


# ---------- 随访计划 ----------
def get_plan(db, plan_id):
    return db.execute("SELECT * FROM followup_plans WHERE id=?",
                      (plan_id,)).fetchone()


@app.get("/api/followup-plans")
def list_followup_plans():
    """随访计划列表：按状态 / 计划日期区间 / 宠物或主人检索"""
    db = get_db()
    status = request.args.get("status", "").strip()
    date_from = request.args.get("date_from", "").strip()
    date_to = request.args.get("date_to", "").strip()
    q = request.args.get("q", "").strip()
    pet_id = request.args.get("pet_id", "").strip()

    sql = """SELECT fp.*, p.name AS pet_name, p.species,
                    o.name AS owner_name, o.phone AS owner_phone,
                    v.name AS vaccine_name
             FROM followup_plans fp
             JOIN pets p ON p.id = fp.pet_id
             JOIN owners o ON o.id = p.owner_id
             JOIN vaccines v ON v.id = fp.vaccine_id
             WHERE 1=1"""
    args = []
    if status:
        if status not in PLAN_STATUSES:
            return jsonify({"error": "无效的随访计划状态"}), 400
        sql += " AND fp.status = ?"
        args.append(status)
    if date_from:
        sql += " AND fp.plan_date >= ?"
        args.append(date_from)
    if date_to:
        sql += " AND fp.plan_date <= ?"
        args.append(date_to)
    if pet_id:
        sql += " AND fp.pet_id = ?"
        args.append(pet_id)
    if q:
        sql += " AND (p.name LIKE ? OR o.name LIKE ? OR o.phone LIKE ?)"
        args += [f"%{q}%", f"%{q}%", f"%{q}%"]
    # 未结束的排在前面，按计划日期升序
    sql += """ ORDER BY CASE WHEN fp.status IN ('pending','confirmed')
                        THEN 0 ELSE 1 END,
                        fp.plan_date ASC, fp.id ASC"""
    return jsonify([row_to_dict(r) for r in db.execute(sql, args)])


def validate_plan_item(db, item, idx, seen_pairs):
    """校验单条批量创建项，返回错误消息（None 表示通过）"""
    label = f"第{idx}条"
    for f in ("pet_id", "vaccine_id", "plan_date"):
        if not item.get(f):
            return f"{label}：缺少必填字段 {f}"
    if not (item.get("assignee") or "").strip():
        return f"{label}：负责人不能为空"
    try:
        plan_date = parse_date(item["plan_date"])
    except (ValueError, TypeError):
        return f"{label}：计划日期格式应为 YYYY-MM-DD"
    if plan_date < today():
        return f"{label}：计划日期不得早于今天"
    pet = db.execute("SELECT name FROM pets WHERE id=?",
                     (item["pet_id"],)).fetchone()
    if not pet:
        return f"{label}：宠物不存在"
    vac = db.execute("SELECT name FROM vaccines WHERE id=?",
                     (item["vaccine_id"],)).fetchone()
    if not vac:
        return f"{label}：疫苗不存在"
    pair = (item["pet_id"], item["vaccine_id"])
    if pair in seen_pairs:
        return (f"{label}：同一批次中 {pet['name']} 的 "
                f"{vac['name']} 重复")
    seen_pairs.add(pair)
    dup = db.execute(
        """SELECT id FROM followup_plans
           WHERE pet_id=? AND vaccine_id=? AND status IN ('pending','confirmed')""",
        pair).fetchone()
    if dup:
        return (f"{label}：{pet['name']} 的 {vac['name']} "
                f"已存在未结束的随访计划（#{dup['id']}）")
    return None


@app.post("/api/followup-plans/batch")
def batch_create_followup_plans():
    """批量生成随访计划：整体事务，任一记录校验失败则全部回滚"""
    data = request.get_json(force=True) or {}
    items = data.get("items")
    if not isinstance(items, list) or not items:
        return jsonify({"error": "items 必须是非空数组"}), 400

    db = get_db()
    db.execute("BEGIN")  # 显式开启事务
    try:
        seen_pairs = set()
        errors = []
        for i, item in enumerate(items, 1):
            err = validate_plan_item(db, item, i, seen_pairs)
            if err:
                errors.append(err)
        if errors:
            db.rollback()
            return jsonify({"error": f"校验失败，已取消全部创建：{errors[0]}",
                            "errors": errors}), 400

        ids = []
        for item in items:
            cur = db.execute(
                """INSERT INTO followup_plans(pet_id,vaccine_id,plan_date,
                       assignee,note,status)
                   VALUES(?,?,?,?,?,'pending')""",
                (item["pet_id"], item["vaccine_id"], item["plan_date"],
                 item["assignee"].strip(), item.get("note", "")))
            ids.append(cur.lastrowid)
        db.commit()
    except Exception as e:
        db.rollback()
        return jsonify({"error": f"批量创建失败，已全部回滚：{e}"}), 500
    return jsonify({"created": len(ids), "ids": ids}), 201


def ensure_plan_open(plan):
    """已完成/已取消的计划不得再次修改"""
    if plan["status"] in CLOSED_PLAN_STATUSES:
        label = "完成" if plan["status"] == "completed" else "取消"
        return jsonify({"error": f"该计划已{label}，不能再次修改"}), 400
    return None


@app.post("/api/followup-plans/<int:plan_id>/confirm")
def confirm_followup_plan(plan_id):
    db = get_db()
    plan = get_plan(db, plan_id)
    if not plan:
        return jsonify({"error": "随访计划不存在"}), 404
    err = ensure_plan_open(plan)
    if err:
        return err
    if plan["status"] != "pending":
        return jsonify({"error": "仅待确认的计划可以确认"}), 400
    db.execute(
        """UPDATE followup_plans SET status='confirmed',
               updated_at=datetime('now','localtime') WHERE id=?""",
        (plan_id,))
    db.commit()
    return jsonify({"id": plan_id, "status": "confirmed"})


@app.post("/api/followup-plans/<int:plan_id>/reschedule")
def reschedule_followup_plan(plan_id):
    d = request.get_json(force=True) or {}
    if not d.get("plan_date"):
        return jsonify({"error": "缺少必填字段 plan_date"}), 400
    try:
        plan_date = parse_date(d["plan_date"])
    except (ValueError, TypeError):
        return jsonify({"error": "计划日期格式应为 YYYY-MM-DD"}), 400
    if plan_date < today():
        return jsonify({"error": "计划日期不得早于今天"}), 400
    db = get_db()
    plan = get_plan(db, plan_id)
    if not plan:
        return jsonify({"error": "随访计划不存在"}), 404
    err = ensure_plan_open(plan)
    if err:
        return err
    assignee = (d.get("assignee") or plan["assignee"]).strip()
    if not assignee:
        return jsonify({"error": "负责人不能为空"}), 400
    note = d["note"] if "note" in d else plan["note"]
    db.execute(
        """UPDATE followup_plans SET plan_date=?, assignee=?, note=?,
               updated_at=datetime('now','localtime') WHERE id=?""",
        (d["plan_date"], assignee, note, plan_id))
    db.commit()
    return jsonify({"id": plan_id, "plan_date": d["plan_date"]})


@app.post("/api/followup-plans/<int:plan_id>/cancel")
def cancel_followup_plan(plan_id):
    db = get_db()
    plan = get_plan(db, plan_id)
    if not plan:
        return jsonify({"error": "随访计划不存在"}), 404
    err = ensure_plan_open(plan)
    if err:
        return err
    db.execute(
        """UPDATE followup_plans SET status='cancelled',
               updated_at=datetime('now','localtime') WHERE id=?""",
        (plan_id,))
    db.commit()
    return jsonify({"id": plan_id, "status": "cancelled"})


# ---------- 到期提醒看板 ----------
@app.get("/api/reminders")
def reminders():
    """每只宠物 × 每种适用疫苗 的到期状态"""
    db = get_db()
    status = request.args.get("status", "").strip()
    q = request.args.get("q", "").strip()

    pets = db.execute(
        """SELECT p.*, o.name AS owner_name, o.phone AS owner_phone
           FROM pets p JOIN owners o ON o.id=p.owner_id
           WHERE (?='' OR p.species=?)""",
        (request.args.get("species", "").strip(),
         request.args.get("species", "").strip())).fetchall()

    items = []
    for p in pets:
        if q and not (q in p["name"] or q in p["owner_name"]
                      or q in (p["owner_phone"] or "")):
            continue
        for s in latest_status_for_pet(db, p["id"], p["species"],
                                      p["birth_date"]):
            if s["status"] == "too_young":
                continue
            if status and s["status"] != status:
                continue
            days_left = None
            if s["next_due_date"]:
                days_left = (parse_date(s["next_due_date"]) - today()).days
            items.append({
                "pet_id": p["id"],
                "pet_name": p["name"],
                "species": p["species"],
                "owner_name": p["owner_name"],
                "owner_phone": p["owner_phone"],
                **s,
                "days_left": days_left,
            })
    # 排序：逾期最久优先，然后即将到期
    order = {"overdue": 0, "due_soon": 1, "none": 2, "valid": 3}
    items.sort(key=lambda x: (order.get(x["status"], 9),
                              x["days_left"] if x["days_left"] is not None
                              else -99999))
    return jsonify(items)


# ---------- 统计页 ----------
@app.get("/api/stats")
def stats():
    db = get_db()

    # 1) 各疫苗接种覆盖率
    pets = db.execute("SELECT id, species, birth_date FROM pets").fetchall()
    vaccines = db.execute("SELECT * FROM vaccines ORDER BY id").fetchall()
    coverage = []
    total_applicable = total_valid = total_ever = total_overdue = 0
    for v in vaccines:
        applicable = [p for p in pets
                      if (v["species"] == "通用" or v["species"] == p["species"])
                      and p["birth_date"]
                      and (today() - parse_date(p["birth_date"])).days >= FIRST_VAC_AGE]
        ever = valid = overdue = 0
        for p in applicable:
            last = db.execute(
                "SELECT next_due_date FROM vaccinations WHERE pet_id=? AND vaccine_id=?"
                " ORDER BY vacc_date DESC LIMIT 1",
                (p["id"], v["id"])).fetchone()
            if last:
                ever += 1
                if parse_date(last["next_due_date"]) >= today():
                    valid += 1
                else:
                    overdue += 1
        n = len(applicable)
        total_applicable += n
        total_valid += valid
        total_ever += ever
        total_overdue += overdue
        coverage.append({
            "vaccine_id": v["id"],
            "vaccine_name": v["name"],
            "species": v["species"],
            "applicable": n,
            "ever_vaccinated": ever,
            "valid": valid,
            "overdue": overdue,
            "coverage_rate": round(valid / n * 100, 1) if n else 0.0,
            "ever_rate": round(ever / n * 100, 1) if n else 0.0,
        })

    # 2) 不良反应率
    all_vacs = db.execute(
        "SELECT adverse_reaction FROM vaccinations").fetchall()
    vac_total = len(all_vacs)
    mild = sum(1 for r in all_vacs
               if reaction_level(r["adverse_reaction"]) == "mild")
    severe = sum(1 for r in all_vacs
                 if reaction_level(r["adverse_reaction"]) == "severe")
    adverse = mild + severe

    # 3) 到期未接种比例（应种组合中 逾期 + 从未接种）
    never = total_applicable - total_ever
    overdue_unvac = total_overdue + never
    overdue_rate = round(overdue_unvac / total_applicable * 100, 1) \
        if total_applicable else 0.0

    # 4) 抗体阳性率（总体 + 分疫苗）
    ab_rows = db.execute(
        """SELECT va.name AS vaccine_name, a.result, COUNT(*) AS cnt
           FROM antibody_tests a JOIN vaccines va ON va.id=a.vaccine_id
           GROUP BY va.id, a.result""").fetchall()
    ab_map = {}
    for r in ab_rows:
        m = ab_map.setdefault(r["vaccine_name"],
                              {"阳性": 0, "弱阳性": 0, "阴性": 0})
        m[r["result"]] = r["cnt"]
    antibody = []
    g_pos = g_weak = g_neg = 0
    for name, m in ab_map.items():
        tot = m["阳性"] + m["弱阳性"] + m["阴性"]
        g_pos += m["阳性"]; g_weak += m["弱阳性"]; g_neg += m["阴性"]
        antibody.append({
            "vaccine_name": name, "total": tot,
            "positive": m["阳性"], "weak": m["弱阳性"], "negative": m["阴性"],
            "positive_rate": round(m["阳性"] / tot * 100, 1) if tot else 0.0,
        })
    antibody.sort(key=lambda x: -x["total"])
    g_tot = g_pos + g_weak + g_neg

    # 5) 月度接种趋势 & 物种分布（辅助图表）
    # 最近 12 个自然月（含当月），无记录的月份补 0
    month_counts = {r["month"]: r["cnt"] for r in db.execute(
        """SELECT substr(vacc_date,1,7) AS month, COUNT(*) AS cnt
           FROM vaccinations GROUP BY month""")}
    monthly = []
    cursor = today().replace(day=1)
    for _ in range(12):
        key = cursor.isoformat()[:7]
        monthly.insert(0, {"month": key, "cnt": month_counts.get(key, 0)})
        cursor = (cursor - timedelta(days=1)).replace(day=1)
    species_dist = [row_to_dict(r) for r in db.execute(
        "SELECT species, COUNT(*) AS cnt FROM pets GROUP BY species")]
    recent_reactions = [row_to_dict(r) for r in db.execute(
        """SELECT vac.vacc_date, p.name AS pet_name, va.name AS vaccine_name,
                  vac.adverse_reaction, vac.doctor
           FROM vaccinations vac JOIN pets p ON p.id=vac.pet_id
           JOIN vaccines va ON va.id=vac.vaccine_id
           WHERE vac.adverse_reaction != '无' AND vac.adverse_reaction != ''
           ORDER BY vac.vacc_date DESC LIMIT 10""")]

    # 6) 随访计划统计：总数 / 七日内待执行 / 完成率
    plan_rows = db.execute(
        "SELECT status, plan_date FROM followup_plans").fetchall()
    plan_total = len(plan_rows)
    plan_by_status = {s: sum(1 for r in plan_rows if r["status"] == s)
                      for s in PLAN_STATUSES}
    today_s = today().isoformat()
    in7_s = (today() + timedelta(days=7)).isoformat()
    due_in_7_days = sum(
        1 for r in plan_rows
        if r["status"] in OPEN_PLAN_STATUSES
        and today_s <= r["plan_date"] <= in7_s)
    followup = {
        "total": plan_total,
        "due_in_7_days": due_in_7_days,
        "completed": plan_by_status["completed"],
        "pending": plan_by_status["pending"],
        "confirmed": plan_by_status["confirmed"],
        "cancelled": plan_by_status["cancelled"],
        "completion_rate": round(plan_by_status["completed"] / plan_total * 100, 1)
        if plan_total else 0.0,
    }

    return jsonify({
        "pet_count": db.execute("SELECT COUNT(*) c FROM pets").fetchone()["c"],
        "owner_count": db.execute("SELECT COUNT(*) c FROM owners").fetchone()["c"],
        "vaccination_count": vac_total,
        "antibody_test_count":
            db.execute("SELECT COUNT(*) c FROM antibody_tests").fetchone()["c"],
        "coverage": coverage,
        "overall_coverage_rate":
            round(total_valid / total_applicable * 100, 1) if total_applicable else 0,
        "adverse": {
            "total": vac_total, "mild": mild, "severe": severe,
            "reaction_count": adverse,
            "rate": round(adverse / vac_total * 100, 1) if vac_total else 0.0,
            "severe_rate": round(severe / vac_total * 100, 1) if vac_total else 0.0,
        },
        "overdue": {
            "applicable": total_applicable,
            "overdue": total_overdue,
            "never": never,
            "unvaccinated": overdue_unvac,
            "rate": overdue_rate,
        },
        "antibody": {
            "items": antibody, "total": g_tot, "positive": g_pos,
            "weak": g_weak, "negative": g_neg,
            "positive_rate": round(g_pos / g_tot * 100, 1) if g_tot else 0.0,
        },
        "monthly": monthly,
        "species_dist": species_dist,
        "recent_reactions": recent_reactions,
        "followup": followup,
    })


@app.get("/api/health")
def health():
    return jsonify({"status": "ok", "time": datetime.now().isoformat()})


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5000, debug=True)
