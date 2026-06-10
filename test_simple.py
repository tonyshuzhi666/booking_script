# 极简测试脚本：仅测试 华科预约系统验证码 + 超级鹰识别
import requests
from chaojiying import Chaojiying_Client
import json

# 自动读取你的配置文件
with open("config.json", "r", encoding="utf-8") as f:
    config = json.load(f)

# 从配置提取信息
USER = config["Uname"]
PWD = config["Upass"]
CJY_USER = config["Chaojiying"]["username"]
CJY_PWD = config["Chaojiying"]["passwd"]
CJY_SOFTID = config["Chaojiying"]["softid"]

# 初始化
session = requests.Session()
session.headers = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
}

print("=" * 50)
print("测试开始：获取华科预约系统验证码")
print("=" * 50)

# ✅ 正确的华科体育预约官网！！！
BASE_URL = "https://tyyp.hust.edu.cn"

try:
    session.get(BASE_URL, timeout=10)
    print("✅ 成功访问华科体育预约系统！")
except Exception as e:
    print("❌ 访问失败：", e)
    exit()

# 获取验证码
try:
    captcha_img = session.get(f"{BASE_URL}/captcha").content
    with open("captcha.png", "wb") as f:
        f.write(captcha_img)
    print("✅ 验证码图片已保存！")
except Exception as e:
    print("❌ 获取验证码失败：", e)
    exit()

# 超级鹰识别
print("\n===== 超级鹰开始识别 =====")
try:
    cjy = Chaojiying_Client(CJY_USER, CJY_PWD, CJY_SOFTID)
    result = cjy.PostPic(captcha_img, 1004)
    
    print("识别结果：", result)
    if result["err_no"] == 0:
        print(f"\n✅ 超级鹰识别成功！验证码：{result['pic_str']}")
        print("✅ 超级鹰正常扣费！")
    else:
        print(f"\n❌ 识别失败：{result['err_str']}")
        
except Exception as e:
    print("\n❌ 超级鹰调用失败：", e)

print("\n===== 测试完成 =====")