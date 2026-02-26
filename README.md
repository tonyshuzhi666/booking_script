# Gym Booking Script (场馆预约脚本)

这是一个用于自动化预约场馆的 Python 脚本。它支持自动登录、验证码识别（使用超级鹰服务）、指定时间段预约以及邮件通知功能。

## 功能特点

- **自动登录**：使用配置的账号密码自动登录预约系统。
- **验证码识别**：集成超级鹰（Chaojiying）API，自动处理登录或预约过程中的验证码。
- **定时预约**：支持配置预约的具体时间段。
- **邮件通知**：预约成功或失败后，通过 SMTP 发送邮件通知结果。
- **多配置支持**：可以通过命令行参数指定不同的配置文件，方便管理多个账号或不同的预约策略。

## 环境要求

- Python 3.7+
- 需要安装以下 Python 依赖库：
    1. `hust_login`：用于华科统一认证登录[GitHub repo](https://github.com/MarvinTerry/HustLogin)
       - 需要额外安装[tesseract-ocr](https://blog.csdn.net/qq_38463737/article/details/109679007)，安装完成后将安装目录添加到环境变量Path中。
    2. requests 和 beautifulsoup4：用于HTTP请求和HTML解析
    3. pycryptodome：用于加密

```bash
pip install hust_login   # 华科统一认证登录库
pip install requests beautifulsoup4 # HTTP请求和HTML解析库
pip install pycryptodome      # 加密库
```
或者直接使用 `requirements.txt` 安装所有依赖：

```bash
pip install -r requirements.txt
```

## 目录结构

```
.
├── main.py                 # 程序入口
├── config.py               # 配置类定义及加载逻辑
├── booking_manager.py      # 核心预约逻辑管理
├── appointment.py          # 处理网络请求和会话
├── captcha_handler.py      # 验证码处理逻辑
├── chaojiying.py           # 超级鹰 API 接口
├── gym_manager.py          # 场馆信息管理
├── EmailSender.py          # 邮件发送模块
├── log.py                  # 日志模块
├── prechecking.py          # 预检查模块
└── ...
```

## 配置文件说明

脚本运行需要一个 JSON 格式的配置文件。请创建一个 JSON 文件（例如 `config.json`），并包含以下字段：

```json
{
  "Uname": "",          // 华科账号(学号)
  "Upass": "",          // 华科密码(统一认证的)
  "Chaojiying": {
    "username": "",     // 超级鹰账号
    "passwd": "",       // 超级鹰密码
    "softid": "968707"  // 图形验证码的ID
  },
  "?Gym": {
    "光体": 45,
    "西体": 69,
    "韵苑乒乓球馆": 126,
    "游泳馆": 117
    },
  "Gym": "45",         // 预约场馆ID, 对应上面的"?Gym"字段
  "GymType":1,
  "?Time": {
    "08:00 - 10:00": ["08:00:00", "10:00:00"],
    "10:00 - 12:00": ["10:00:00", "12:00:00"],
    "12:00 - 14:00": ["12:00:00", "14:00:00"],
    "14:00 - 16:00": ["14:00:00", "16:00:00"],
    "16:00 - 18:00": ["16:00:00", "18:00:00"],
    "18:00 - 20:00": ["18:00:00", "20:00:00"],
    "20:00 - 22:00": ["20:00:00", "22:00:00"]
},
  "Time": {
    "start": "18:00:00",        // 预约开始时间
    "end": "20:00:00",          // 预约结束时间
    "notion": "only allow one time slot to be selected"
  },
  "Payment": {
    "method": "2",              // 付款方式(1-电子卡, 2-在线支付)，电子卡没实现
    "notion": "1 for ecard, 2 for online payment"
  },
  "Email": {
    "smtp_server": "smtp.qq.com",     // SMTP 服务器地址(QQ/163等)
    "smtp_port": 465,
    "username": "",                   // 发件人邮箱地址      
    "password": "",                   // 发件人邮箱密码或授权码   
    "sender": "",                     // 发件人名称(与邮箱地址相同)
    "recipients": [                   // 收件人列表,填写收件人邮箱地址
          "example1@qq.com",
          "example2@qq.com"
      ]
  }
}
```

## 使用方法

### 超级鹰账号注册
1. 在 [超级鹰官网](http://www.chaojiying.com/) 注册得到账号和密码。
2. 识别验证码需要积分（充钱），十块钱能用挺久的

### SMTP 邮箱设置
1. 推荐使用 QQ 邮箱或 163 邮箱，注册并登录邮箱。
2. 在邮箱设置中开启 SMTP 服务，并获取授权码（通常不是登录密码）。

### 脚本运行
在`config.json`中填写相关字段后，可以先运行 `prechecking.py` 来检查配置文件和环境是否正确：

```bash
python prechecking.py config.json
```

没问题且能收到邮件后，可以在终端中运行 `main.py`，并指定配置文件路径：

```bash
python main.py config.json
```

#### 相关工具

Linux环境下可以用`tmux`或`screen`等工具在后台运行脚本，也方便多开好几个账号一起抢。

### 结果查看
预约结果会通过邮件发送到配置文件中指定的收件人邮箱。
在收件邮箱里面查看预约成功或失败的通知邮件。预约成功的邮件内还有支付链接，5min内要完成支付。
支付完成后约5min会发送具体的预约信息邮件（有时候因为场馆预约服务器的问题，得自己手动登录账号查看）。

## 注意事项

1.  **超级鹰账号**：请确保你的超级鹰账号有足够的积分用于验证码识别。
2.  **网络环境**：脚本依赖网络请求，请确保网络连接稳定。
3.  **邮件设置**：如果使用 QQ 邮箱等，`password` 字段通常需要填写 SMTP 授权码而不是邮箱登录密码。
