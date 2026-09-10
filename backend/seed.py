"""生成演示数据：主人、宠物、疫苗、接种记录、抗体检测"""
import sqlite3
import random
from datetime import date, datetime, timedelta
from pathlib import Path
from db import DB_PATH, init_db

random.seed(42)

OWNERS = [
    ("张伟", "13800010001", "北京市朝阳区幸福小区3号楼"),
    ("李娜", "13800010002", "北京市海淀区中关村大街12号"),
    ("王芳", "13800010003", "上海市浦东新区世纪大道100号"),
    ("刘强", "13800010004", "广州市天河区体育西路88号"),
    ("陈静", "13800010005", "深圳市南山区科技园南区"),
    ("杨洋", "13800010006", "成都市武侯区桐梓林东路"),
    ("赵敏", "13800010007", "杭州市西湖区文三路200号"),
    ("孙磊", "13800010008", "武汉市洪山区珞瑜路72号"),
]

PETS = [
    # owner_idx, name, species, breed, gender, age_days, color, neutered
    (0, "豆豆", "犬", "金毛寻回犬", "公", 900, "金色", 1),
    (0, "咪咪", "猫", "英国短毛猫", "母", 700, "蓝灰", 1),
    (1, "旺财", "犬", "中华田园犬", "公", 1500, "黄色", 0),
    (1, "球球", "猫", "美国短毛猫", "公", 400, "银虎斑", 1),
    (2, "布丁", "猫", "布偶猫", "母", 600, "海豹双色", 0),
    (2, "巧克力", "犬", "拉布拉多", "母", 1200, "巧克力色", 1),
    (3, "大黄", "犬", "柴犬", "公", 800, "赤色", 1),
    (4, "雪球", "猫", "波斯猫", "母", 2000, "白色", 1),
    (5, "可乐", "犬", "柯基", "公", 500, "黄白", 0),
    (5, "奶茶", "猫", "暹罗猫", "母", 350, "重点色", 0),
    (6, "黑子", "犬", "边境牧羊犬", "公", 1100, "黑白", 1),
    (7, "橘子", "猫", "中华田园猫", "公", 2600, "橘色", 1),
    (3, "团子", "兔", "荷兰垂耳兔", "母", 300, "灰白", 0),
    (6, "闪电", "犬", "哈士奇", "公", 1300, "烟灰", 0),
]

VACCINES = [
    # name, species, interval_days, core
    ("犬四联疫苗", "犬", 365, 1),
    ("犬六联疫苗", "犬", 365, 1),
    ("狂犬疫苗", "通用", 365, 1),
    ("犬窝咳疫苗", "犬", 365, 0),
    ("猫三联疫苗", "猫", 365, 1),
    ("猫狂犬疫苗", "猫", 365, 1),
    ("猫白血病疫苗", "猫", 365, 0),
    ("兔病毒性出血症疫苗", "兔", 180, 1),
]

SITES = ["颈部皮下", "右前肢皮下", "左后肢肌肉", "臀部肌肉", "肩胛间皮下"]
DOCTORS = ["王医生", "李医生", "周医生"]
MANUFACTURERS = ["硕腾 Zoetis", "勃林格殷格翰", "默沙东 MSD", "中牧股份"]
MILD_REACTIONS = [
    "轻微：注射部位红肿，次日消退",
    "轻微：精神沉郁、食欲下降1天",
    "轻微：低热38.9℃，自行恢复",
]
SEVERE_REACTIONS = [
    "严重：面部肿胀、呕吐，经抗过敏治疗恢复",
    "严重：过敏性休克，急诊抢救后恢复",
]


def pick_reaction():
    r = random.random()
    if r < 0.92:
        return "无"
    if r < 0.985:
        return random.choice(MILD_REACTIONS)
    return random.choice(SEVERE_REACTIONS)
LABS = ["迪安宠医检验中心", "联宠检测", "瑞鹏中心实验室"]


def seed():
    init_db()
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # 已存在基础数据则跳过（库存批次仍幂等补充）
    if cur.execute("SELECT COUNT(*) FROM owners").fetchone()[0] > 0:
        print("基础数据已存在，跳过种子")
        vac_rows = cur.execute(
            "SELECT id, name, species, interval_days, core FROM vaccines"
        ).fetchall()
        seed_inventory(cur, [tuple(r) for r in vac_rows])
        conn.commit()
        conn.close()
        return

    today = date.today()

    for name, phone, addr in OWNERS:
        cur.execute("INSERT INTO owners(name, phone, address) VALUES(?,?,?)",
                    (name, phone, addr))

    pet_ids = []
    for oi, name, species, breed, gender, age, color, neut in PETS:
        birth = today - timedelta(days=age + random.randint(-30, 30))
        cur.execute(
            "INSERT INTO pets(owner_id,name,species,breed,gender,birth_date,color,neutered, microchip)"
            " VALUES(?,?,?,?,?,?,?,?,?)",
            (oi + 1, name, species, breed, gender, birth.isoformat(), color,
             neut, f"CN{random.randint(10**9, 10**10 - 1)}"))
        pet_ids.append((cur.lastrowid, species, birth))

    vac_ids = []
    for name, species, interval, core in VACCINES:
        cur.execute(
            "INSERT INTO vaccines(name,species,interval_days,core,description) VALUES(?,?,?,?,?)",
            (name, species, interval, core,
             f"{species}适用，建议每{interval}天加强免疫"))
        vac_ids.append((cur.lastrowid, name, species, interval, core))

    def applicable(species, vac_species):
        return vac_species == "通用" or vac_species == species

    # 为每只宠物生成 1~4 次接种史
    for pet_id, species, birth in pet_ids:
        vacs = [v for v in vac_ids if applicable(species, v[2])]
        first_vac_age = 70  # 首免日龄
        for v in vacs:
            vid, vname, _, interval, core = v
            # 非核心疫苗约 25% 漏种，核心疫苗约 5% 漏种
            skip_p = 0.25 if not core else 0.05
            if random.random() < skip_p:
                continue
            rounds = random.choices([1, 2, 3, 4], weights=[3, 4, 4, 2])[0]
            last_date = None
            for r in range(rounds):
                # 让部分记录到期/未接种：随机偏移下次时间
                offset = random.randint(-120, 60) if r == rounds - 1 else 0
                vd = birth + timedelta(days=first_vac_age + r * interval + offset)
                if vd > today:
                    break
                last_date = vd
                adv = pick_reaction()
                cur.execute(
                    "INSERT INTO vaccinations(pet_id,vaccine_id,vacc_date,batch_no,"
                    "manufacturer,site,doctor,adverse_reaction,next_due_date,note)"
                    " VALUES(?,?,?,?,?,?,?,?,?,?)",
                    (pet_id, vid, vd.isoformat(),
                     f"B{vd.year}{random.randint(1000,9999)}",
                     random.choice(MANUFACTURERS), random.choice(SITES),
                     random.choice(DOCTORS), adv,
                     (vd + timedelta(days=interval)).isoformat(),
                     "正常接种" if adv == "无" else "留观30分钟"))
        # 抗体检测：约 75% 的宠物有 1~3 次
        if random.random() < 0.75:
            tested_vacs = random.sample(vacs, k=min(len(vacs), random.randint(1, 2)))
            for v in tested_vacs:
                vid, vname, _, _, _ = v
                n = random.randint(1, 3)
                for k in range(n):
                    td = today - timedelta(days=random.randint(10, 700) + k * 200)
                    if td < birth + timedelta(days=100):
                        continue
                    result = random.choices(
                        ["阳性", "弱阳性", "阴性"], weights=[6, 2, 2])[0]
                    titer = round(random.uniform(0.2, 12.0), 2) if result != "阳性" \
                        else round(random.uniform(2.0, 15.0), 2)
                    cur.execute(
                        "INSERT INTO antibody_tests(pet_id,vaccine_id,test_date,result,titer,lab,note)"
                        " VALUES(?,?,?,?,?,?,?)",
                        (pet_id, vid, td.isoformat(), result, titer,
                         random.choice(LABS),
                         None if result == "阳性" else "建议加强免疫"))

    # 随访计划演示数据：每只被抽中的宠物最多 1 条，避免重复未结束计划
    PLAN_NOTES = ["电话随访提醒主人预约", "主人要求周末到店接种",
                  "接种后复查抗体", "上次接种有轻微反应，需重点观察", ""]
    for pet_id, species, birth in random.sample(pet_ids, k=8):
        vacs = [v for v in vac_ids if applicable(species, v[2])]
        if not vacs:
            continue
        vid = random.choice(vacs)[0]
        status = random.choices(
            ["pending", "confirmed", "completed", "cancelled"],
            weights=[4, 3, 2, 1])[0]
        if status in ("pending", "confirmed"):
            plan_date = today + timedelta(days=random.randint(0, 20))
        else:
            plan_date = today - timedelta(days=random.randint(5, 60))
        cur.execute(
            "INSERT INTO followup_plans(pet_id,vaccine_id,plan_date,assignee,note,status)"
            " VALUES(?,?,?,?,?,?)",
            (pet_id, vid, plan_date.isoformat(), random.choice(DOCTORS),
             random.choice(PLAN_NOTES), status))

    seed_inventory(cur, vac_ids)

    conn.commit()
    conn.close()
    print("演示数据生成完成")


# ---------- 疫苗库存演示数据 ----------
# 每个疫苗生成多个批次，覆盖 正常 / 低库存 / 临期 / 已过期 四种状态
def seed_inventory(cur, vac_ids):
    if cur.execute("SELECT COUNT(*) FROM vaccine_batches").fetchone()[0] > 0:
        return

    today = date.today()
    batch_seq = 1000
    # 本月已消耗（支）：写入 consume 流水，使"本月消耗量"有演示数据
    CONSUMED_PER_VAC = [2, 1, 3, 2, 1, 2, 1, 2]

    for idx, (vid, vname, vspecies, interval, core) in enumerate(vac_ids):
        manufacturer = random.choice(MANUFACTURERS)

        def add_batch(remain, prod_offset, exp_offset, threshold, note,
                      consumed=0):
            """remain=当前剩余；consumed=本批次本月已消耗（会同时写消耗流水）"""
            nonlocal batch_seq
            batch_seq += 1
            prod = today - timedelta(days=prod_offset)
            exp = today + timedelta(days=exp_offset)
            received = remain + consumed
            cur.execute(
                "INSERT INTO vaccine_batches(vaccine_id,batch_no,manufacturer,"
                "production_date,expiry_date,initial_quantity,remaining,"
                "warning_threshold,operator,note)"
                " VALUES(?,?,?,?,?,?,?,?,?,?)",
                (vid, f"B{prod.year}{batch_seq}", manufacturer,
                 prod.isoformat(), exp.isoformat(), received, remain,
                 threshold, "库管小陈", note))
            bid = cur.lastrowid
            cur.execute(
                "INSERT INTO inventory_transactions(batch_id,type,quantity,delta,"
                "remaining_after,reason,operator,created_at)"
                " VALUES(?,'inbound',?,?,?,?,?,?)",
                (bid, received, received, received, "首次入库",
                 "库管小陈",
                 datetime.combine(prod, datetime.min.time()).strftime(
                     "%Y-%m-%d %H:%M:%S")))
            # 本月消耗流水：时间从前到后，结余逐条递减
            after = received
            used_days = sorted((random.randint(0, 27) for _ in range(consumed)),
                               reverse=True)
            for offset_day in used_days:
                day = today - timedelta(days=offset_day)
                created = datetime.combine(day, datetime.min.time()).replace(
                    hour=random.randint(9, 17)).strftime("%Y-%m-%d %H:%M:%S")
                after -= 1
                cur.execute(
                    "INSERT INTO inventory_transactions(batch_id,type,quantity,"
                    "delta,remaining_after,reason,operator,created_at)"
                    " VALUES(?,'consume',1,-1,?,?,?,?)",
                    (bid, after, f"接种消耗：{vname}",
                     random.choice(DOCTORS), created))
            return bid

        # 1) 正常批次（库存充足、效期充足，挂本月消耗流水）
        add_batch(random.choice([60, 80, 100]),
                  random.randint(120, 200), random.randint(200, 400),
                  20, "常规备货批次",
                  consumed=CONSUMED_PER_VAC[idx % len(CONSUMED_PER_VAC)])
        # 2) 低库存批次（剩余 ≤ 预警阈值、效期正常）
        add_batch(random.choice([3, 6, 8]),
                  random.randint(60, 150), random.randint(120, 300),
                  20, "库存低于预警阈值，待补货")
        # 3) 临期批次（30 天内到期）
        add_batch(random.choice([10, 15, 25]),
                  random.randint(300, 360), random.randint(3, 28),
                  20, "临近有效期，请优先使用")
        # 4) 已过期批次
        add_batch(random.choice([2, 5]),
                  random.randint(500, 700), -random.randint(5, 90),
                  20, "已过期，禁止接种，待报损")


if __name__ == "__main__":
    seed()
