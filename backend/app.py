"""宠物疫苗接种档案与到期提醒平台 —— Flask API"""
from datetime import date, datetime, timedelta

try:
    from flask import Flask, g, jsonify, request
    from flask_cors import CORS
except ImportError:  # 环境未安装 Flask 时使用标准库回退服务器，API 保持一致
    from stdlib_server import Flask, g, jsonify, request, CORS

from db import get_db, close_db, init_db

app = Flask(__name__)
CORS(app)
app.teardown_appcontext(close_db)

SOON_DAYS = 30        # 30 天内到期视为"即将到期"
FIRST_VAC_AGE = 60    # 超过 60 日龄纳入应接种统计
EXPIRE_SOON_DAYS = 30  # 库存批次 30 天内到期视为"临期"

# 随访计划状态：pending 待确认 / confirmed 已确认 / completed 已完成 / cancelled 已取消
PLAN_STATUSES = ("pending", "confirmed", "completed", "cancelled")
OPEN_PLAN_STATUSES = ("pending", "confirmed")   # 未结束
CLOSED_PLAN_STATUSES = ("completed", "cancelled")

# 库存流水类型：inbound 入库补充 / consume 接种消耗 / adjust 库存调整
STOCK_TXN_TYPES = ("inbound", "consume", "adjust")
# 库存批次实时状态：normal 正常 / low 低库存 / expiring 临期 / expired 已过期
BATCH_STATUSES = ("normal", "low", "expiring", "expired")


# ---------- 工具 ----------
def row_to_dict(row):
    return dict(row) if row is not None else None


def parse_date(s):
    return datetime.strptime(s, "%Y-%m-%d").date()


def today():
    return date.today()


def parse_positive_int(value, field, allow_zero=False):
    """解析正整数（allow_zero 时允许 0），失败抛出 ValueError(中文消息)"""
    if isinstance(value, bool) or isinstance(value, float) \
            or (isinstance(value, str)
                and not value.strip().lstrip("+").isdigit()):
        raise ValueError(f"{field}必须为{'非负' if allow_zero else '正'}整数")
    try:
        n = int(value)
    except (ValueError, TypeError):
        raise ValueError(f"{field}必须为{'非负' if allow_zero else '正'}整数")
    if n < 0 or (n == 0 and not allow_zero):
        raise ValueError(f"{field}必须为{'非负' if allow_zero else '正'}整数")
    return n


def batch_status(remaining, warning_threshold, expiry_d):
    """按剩余数量与有效期实时计算批次状态。

    优先级：已过期 > 临期（30 天内到期）> 低库存（剩余 ≤ 预警阈值）> 正常。
    """
    if expiry_d < today():
        return "expired"
    if (expiry_d - today()).days <= EXPIRE_SOON_DAYS:
        return "expiring"
    if remaining <= warning_threshold:
        return "low"
    return "normal"


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
    for f in ["pet_id", "vaccine_id", "vacc_date", "batch_id"]:
        if not d.get(f):
            return jsonify({"error": f"缺少必填字段 {f}"}), 400
    try:
        vacc_date = parse_date(d["vacc_date"])
    except (ValueError, TypeError):
        return jsonify({"error": "接种日期格式应为 YYYY-MM-DD"}), 400
    if vacc_date > today():
        return jsonify({"error": "接种日期不得晚于今天"}), 400
    try:
        batch_id = parse_positive_int(d["batch_id"], "库存批次")
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    db = get_db()
    vac = db.execute("SELECT * FROM vaccines WHERE id=?",
                     (d["vaccine_id"],)).fetchone()
    pet = db.execute("SELECT * FROM pets WHERE id=?",
                     (d["pet_id"],)).fetchone()
    if not vac or not pet:
        return jsonify({"error": "宠物或疫苗不存在"}), 400
    # 批次必须与宠物物种匹配（通用疫苗批次对所有物种适用）
    batch = db.execute(
        "SELECT * FROM vaccine_batches WHERE id=?", (batch_id,)).fetchone()
    if not batch:
        return jsonify({"error": "库存批次不存在"}), 400
    if batch["vaccine_id"] != vac["id"]:
        return jsonify({"error": "所选批次与疫苗不匹配"}), 400
    if vac["species"] != "通用" and vac["species"] != pet["species"]:
        return jsonify({"error": f"该疫苗不适用于物种：{pet['species']}"}), 400
    expiry = parse_date(batch["expiry_date"])
    if expiry < today():
        return jsonify({"error": f"批次 {batch['batch_no']} 已过期，不能接种"}), 400
    if batch["remaining"] <= 0:
        return jsonify({"error": f"批次 {batch['batch_no']} 库存不足"}), 400

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

    # 接种记录创建、库存扣减、流水写入在同一 SQLite 事务中完成，
    # 任一步失败全部回滚，不产生负库存，也不会重复扣减
    db.execute("BEGIN")
    try:
        cur = db.execute(
            """INSERT INTO vaccinations(pet_id,vaccine_id,vacc_date,batch_no,
                   manufacturer,site,doctor,adverse_reaction,next_due_date,note,
                   batch_id)
               VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
            (d["pet_id"], d["vaccine_id"], d["vacc_date"],
             # 批号、厂家以库存批次登记信息为准，避免前端篡改
             batch["batch_no"], batch["manufacturer"],
             d.get("site", ""), d.get("doctor", ""), reaction,
             next_due, d.get("note", ""), batch_id))
        vac_id = cur.lastrowid
        new_remaining = batch["remaining"] - 1

        # 条件更新：仅当剩余数量仍 > 0 时扣减成功，数据库层面杜绝负库存
        upd = db.execute(
            "UPDATE vaccine_batches SET remaining = remaining - 1 "
            "WHERE id=? AND remaining > 0", (batch_id,))
        if upd.rowcount != 1:
            db.rollback()
            return jsonify({"error": f"批次 {batch['batch_no']} 库存不足"}), 400

        # 唯一索引 uq_txn_vaccination 保证同一接种记录不会重复写消耗流水
        db.execute(
            """INSERT INTO inventory_transactions(batch_id,vaccination_id,type,
                   quantity,delta,remaining_after,reason,operator)
               VALUES(?,?,'consume',1,-1,?,?,?)""",
            (batch_id, vac_id, new_remaining,
             f"接种消耗：{pet['name']} / {vac['name']}",
             (d.get("doctor") or "").strip() or "接种医生"))

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
    except Exception as e:
        db.rollback()
        # 唯一索引冲突等（如重复扣减）
        return jsonify({"error": f"接种登记失败，已全部回滚：{e}"}), 400
    return jsonify({"id": vac_id, "next_due_date": next_due,
                    "batch_no": batch["batch_no"],
                    "manufacturer": batch["manufacturer"],
                    "remaining": new_remaining,
                    "completed_plan_id": completed_plan_id}), 201


# ---------- 疫苗库存批次 ----------
def serialize_batch(r, today_s=None):
    d = row_to_dict(r)
    expiry = parse_date(d["expiry_date"])
    days_left = (expiry - today()).days
    d["days_left"] = days_left
    d["status"] = batch_status(d["remaining"], d["warning_threshold"], expiry)
    d["usable"] = d["remaining"] > 0 and days_left >= 0
    # 兼容旧调用（未关联流水列时即时计算累计入库量）
    if "total_inbound" not in d:
        db = get_db()
        d["total_inbound"] = db.execute(
            "SELECT COALESCE(SUM(quantity),0) AS q FROM inventory_transactions "
            "WHERE batch_id=? AND type='inbound'", (d["id"],)).fetchone()["q"]
    return d


BATCH_LIST_SQL = """
    SELECT b.*, v.name AS vaccine_name, v.species AS vaccine_species,
           v.interval_days,
           (SELECT COALESCE(SUM(quantity),0) FROM inventory_transactions t
             WHERE t.batch_id = b.id AND t.type = 'inbound') AS total_inbound
    FROM vaccine_batches b
    JOIN vaccines v ON v.id = b.vaccine_id
"""


@app.get("/api/inventory/batches")
def list_inventory_batches():
    """库存批次列表：按疫苗 / 批号 / 状态检索，可只取可用批次"""
    db = get_db()
    vaccine_id = request.args.get("vaccine_id", "").strip()
    batch_no = request.args.get("batch_no", "").strip()
    status = request.args.get("status", "").strip()
    species = request.args.get("species", "").strip()
    usable = request.args.get("usable", "").strip()

    if status and status not in BATCH_STATUSES:
        return jsonify({"error": "无效的批次状态"}), 400

    sql = BATCH_LIST_SQL + " WHERE 1=1"
    args = []
    if vaccine_id:
        sql += " AND b.vaccine_id = ?"
        args.append(vaccine_id)
    if batch_no:
        sql += " AND b.batch_no LIKE ?"
        args.append(f"%{batch_no}%")
    if species:
        sql += " AND (v.species='通用' OR v.species=?)"
        args.append(species)

    rows = [serialize_batch(r) for r in db.execute(sql, args)]
    if usable in ("1", "true", "yes"):
        rows = [r for r in rows if r["usable"]]
    if status:
        rows = [r for r in rows if r["status"] == status]

    # 默认排序：已过期沉底，临期/低库存优先，再按有效期升序
    order = {"expired": 3, "expiring": 0, "low": 1, "normal": 2}
    rows.sort(key=lambda r: (order.get(r["status"], 9), r["expiry_date"], r["id"]))
    return jsonify(rows)


def validate_batch_fields(d):
    """校验登记/入库字段，返回 (values_dict, error)"""
    result = {}
    for f in ("vaccine_id", "batch_no", "manufacturer",
              "production_date", "expiry_date", "operator"):
        val = d.get(f)
        if val is None or (isinstance(val, str) and not val.strip()):
            return None, f"缺少必填字段 {f}"
        result[f] = str(val).strip() if isinstance(val, str) else val
    try:
        result["vaccine_id"] = parse_positive_int(result["vaccine_id"], "疫苗")
    except ValueError as e:
        return None, str(e)
    try:
        prod = parse_date(result["production_date"])
        exp = parse_date(result["expiry_date"])
    except (ValueError, TypeError):
        return None, "生产日期与有效期格式应为 YYYY-MM-DD"
    if exp < prod:
        return None, "有效期不得早于生产日期"
    result["production_date"] = prod.isoformat()
    result["expiry_date"] = exp.isoformat()
    result["threshold"] = parse_nonneg(
        d.get("warning_threshold", 10), "预警阈值")
    result["note"] = (d.get("note") or "").strip()
    return result, None


def parse_nonneg(value, field):
    n = parse_positive_int(value, field, allow_zero=True)
    return n


@app.post("/api/inventory/batches")
def create_inventory_batch():
    """登记新的疫苗库存批次（首次入库）"""
    d = request.get_json(force=True) or {}
    v, err = validate_batch_fields(d)
    if err:
        return jsonify({"error": err}), 400
    try:
        quantity = parse_positive_int(d.get("quantity"), "入库数量")
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    db = get_db()
    if not db.execute("SELECT 1 FROM vaccines WHERE id=?",
                      (v["vaccine_id"],)).fetchone():
        return jsonify({"error": "疫苗不存在"}), 400
    dup = db.execute(
        "SELECT id FROM vaccine_batches WHERE vaccine_id=? AND lower(batch_no)=?",
        (v["vaccine_id"], v["batch_no"].lower())).fetchone()
    if dup:
        return jsonify({"error": "该疫苗已存在相同批号的批次，不能重复登记"}), 400

    db.execute("BEGIN")
    try:
        cur = db.execute(
            """INSERT INTO vaccine_batches(vaccine_id,batch_no,manufacturer,
                   production_date,expiry_date,initial_quantity,remaining,
                   warning_threshold,operator,note)
               VALUES(?,?,?,?,?,?,?,?,?,?)""",
            (v["vaccine_id"], v["batch_no"], v["manufacturer"],
             v["production_date"], v["expiry_date"], quantity, quantity,
             v["threshold"], v["operator"], v["note"]))
        batch_id = cur.lastrowid
        db.execute(
            """INSERT INTO inventory_transactions(batch_id,type,quantity,delta,
                   remaining_after,reason,operator)
               VALUES(?,'inbound',?,?,?,?,?)""",
            (batch_id, quantity, quantity, quantity,
             v["note"] or "首次入库", v["operator"]))
        db.commit()
    except Exception as e:
        db.rollback()
        return jsonify({"error": f"登记失败，已回滚：{e}"}), 400
    return jsonify({"id": batch_id, "remaining": quantity}), 201


def _load_batch(db, batch_id):
    return db.execute(BATCH_LIST_SQL + " WHERE b.id=?",
                      (batch_id,)).fetchone()


@app.post("/api/inventory/batches/<int:batch_id>/restock")
def restock_batch(batch_id):
    """入库补充：数量为正整数，必须填写原因"""
    d = request.get_json(force=True) or {}
    try:
        quantity = parse_positive_int(d.get("quantity"), "入库数量")
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    reason = (d.get("reason") or "").strip()
    operator = (d.get("operator") or "").strip()
    if not reason:
        return jsonify({"error": "请填写入库原因"}), 400
    if not operator:
        return jsonify({"error": "缺少必填字段 operator"}), 400

    db = get_db()
    batch = _load_batch(db, batch_id)
    if not batch:
        return jsonify({"error": "库存批次不存在"}), 404
    if parse_date(batch["expiry_date"]) < today():
        return jsonify({"error": "批次已过期，不能继续入库补充"}), 400

    db.execute("BEGIN")
    try:
        upd = db.execute(
            "UPDATE vaccine_batches SET remaining = remaining + ? WHERE id=?",
            (quantity, batch_id))
        if upd.rowcount != 1:
            raise RuntimeError("更新批次失败")
        row = db.execute("SELECT remaining FROM vaccine_batches WHERE id=?",
                         (batch_id,)).fetchone()
        db.execute(
            """INSERT INTO inventory_transactions(batch_id,type,quantity,delta,
                   remaining_after,reason,operator)
               VALUES(?,'inbound',?,?,?,?,?)""",
            (batch_id, quantity, quantity, row["remaining"], reason, operator))
        db.commit()
    except Exception as e:
        db.rollback()
        return jsonify({"error": f"入库失败，已回滚：{e}"}), 400
    return jsonify({"id": batch_id, "remaining": row["remaining"]})


@app.post("/api/inventory/batches/<int:batch_id>/adjust")
def adjust_batch(batch_id):
    """库存调整（盘盈/盘耗等）：change 为带符号整数，不得调出负库存，必须填写原因"""
    d = request.get_json(force=True) or {}
    if d.get("change") is None:
        return jsonify({"error": "缺少必填字段 change"}), 400
    try:
        change = int(d["change"])
    except (ValueError, TypeError):
        return jsonify({"error": "调整数量必须为整数"}), 400
    if change == 0:
        return jsonify({"error": "调整数量不能为 0"}), 400
    reason = (d.get("reason") or "").strip()
    operator = (d.get("operator") or "").strip()
    if not reason:
        return jsonify({"error": "请填写调整原因"}), 400
    if not operator:
        return jsonify({"error": "缺少必填字段 operator"}), 400

    db = get_db()
    batch = _load_batch(db, batch_id)
    if not batch:
        return jsonify({"error": "库存批次不存在"}), 404
    if batch["remaining"] + change < 0:
        return jsonify({"error":
                        f"调整后库存为负（当前剩余 {batch['remaining']}），"
                        "已拒绝调整"}), 400

    db.execute("BEGIN")
    try:
        # 条件更新兜底，数据库层面禁止负库存
        if change > 0:
            upd = db.execute(
                "UPDATE vaccine_batches SET remaining = remaining + ? WHERE id=?",
                (change, batch_id))
        else:
            upd = db.execute(
                "UPDATE vaccine_batches SET remaining = remaining - ? "
                "WHERE id=? AND remaining >= ?",
                (-change, batch_id, -change))
        if upd.rowcount != 1:
            db.rollback()
            return jsonify({"error": "库存不足，调整后将出现负库存，已拒绝"}), 400
        row = db.execute("SELECT remaining FROM vaccine_batches WHERE id=?",
                         (batch_id,)).fetchone()
        db.execute(
            """INSERT INTO inventory_transactions(batch_id,type,quantity,delta,
                   remaining_after,reason,operator)
               VALUES(?,'adjust',?,?,?,?,?)""",
            (batch_id, abs(change), change, row["remaining"], reason, operator))
        db.commit()
    except Exception as e:
        db.rollback()
        return jsonify({"error": f"调整失败，已回滚：{e}"}), 400
    return jsonify({"id": batch_id, "remaining": row["remaining"]})


@app.get("/api/inventory/transactions")
def list_inventory_transactions():
    """库存流水：可按批次 / 类型过滤，最新在前"""
    db = get_db()
    batch_id = request.args.get("batch_id", "").strip()
    ttype = request.args.get("type", "").strip()
    sql = """SELECT t.*, b.batch_no, b.manufacturer, v.name AS vaccine_name,
                    v.species AS vaccine_species,
                    p.name AS pet_name
             FROM inventory_transactions t
             JOIN vaccine_batches b ON b.id = t.batch_id
             JOIN vaccines v ON v.id = b.vaccine_id
             LEFT JOIN vaccinations vac ON vac.id = t.vaccination_id
             LEFT JOIN pets p ON p.id = vac.pet_id
             WHERE 1=1"""
    args = []
    if batch_id:
        sql += " AND t.batch_id = ?"
        args.append(batch_id)
    if ttype:
        if ttype not in STOCK_TXN_TYPES:
            return jsonify({"error": "无效的流水类型"}), 400
        sql += " AND t.type = ?"
        args.append(ttype)
    sql += " ORDER BY t.id DESC LIMIT 500"
    return jsonify([row_to_dict(r) for r in db.execute(sql, args)])


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
def inventory_stats(db):
    """库存统计：总量 / 临期数量 / 低库存批次数 / 本月消耗量（状态实时计算）"""
    batches = db.execute(
        "SELECT remaining, warning_threshold, expiry_date FROM vaccine_batches"
    ).fetchall()
    stock_total = stock_valid = expiring_soon_qty = 0
    low_count = expiring_count = expired_count = batch_count = 0
    in30 = today() + timedelta(days=EXPIRE_SOON_DAYS)
    for b in batches:
        batch_count += 1
        expiry = parse_date(b["expiry_date"])
        remaining = b["remaining"]
        stock_total += remaining
        if expiry < today():
            expired_count += 1
            continue  # 已过期批次不计入可用库存与临期数量
        stock_valid += remaining
        st = batch_status(remaining, b["warning_threshold"], expiry)
        if st == "expiring":
            expiring_count += 1
            expiring_soon_qty += remaining
        elif st == "low":
            low_count += 1

    # 本月消耗量：本月接种消耗流水数量合计（不含调整盘亏）
    month_prefix = today().isoformat()[:7]
    consumed_row = db.execute(
        """SELECT COALESCE(SUM(quantity),0) AS qty, COUNT(*) AS times
           FROM inventory_transactions
           WHERE type='consume' AND substr(created_at,1,7)=?""",
        (month_prefix,)).fetchone()
    return {
        "batch_count": batch_count,
        "stock_total": stock_total,          # 当前库存总量（含已过期批次剩余）
        "stock_valid": stock_valid,          # 未过期批次可用库存
        "expiring_soon_qty": expiring_soon_qty,   # 30 天内临期数量（剩余支数）
        "expiring_soon_batches": expiring_count,  # 临期批次数
        "low_batch_count": low_count,             # 低库存批次数
        "expired_batch_count": expired_count,     # 已过期批次数
        "month_consumed": consumed_row["qty"],    # 本月消耗量（支）
        "month_consume_times": consumed_row["times"],
    }


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

    # 7) 疫苗库存指标：当前库存总量 / 30 天内临期数量 / 低库存批次数 / 本月消耗量
    inventory = inventory_stats(db)

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
        "inventory": inventory,
    })


@app.get("/api/health")
def health():
    return jsonify({"status": "ok", "time": datetime.now().isoformat()})


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5000, debug=True)
