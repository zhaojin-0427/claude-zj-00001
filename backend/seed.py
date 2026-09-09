"""生成演示数据：主人、宠物、疫苗、接种记录、抗体检测"""
import sqlite3
import random
from datetime import date, timedelta
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

    # 已存在数据则跳过
    if cur.execute("SELECT COUNT(*) FROM owners").fetchone()[0] > 0:
        print("数据已存在，跳过种子")
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

    conn.commit()
    conn.close()
    print("演示数据生成完成")


if __name__ == "__main__":
    seed()
