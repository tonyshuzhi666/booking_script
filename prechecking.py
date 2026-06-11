from appointment import Appointment
from config import AppConfig
from EmailSender import EmailSender
import logging

def main():
    logging.basicConfig(level=logging.DEBUG)
    config_file = "config.json"
    app_config = AppConfig.load_from_file(config_file)
    app = Appointment(app_config.username, app_config.password)
    email_sender = EmailSender(config_file)
    try:
        app.login()
        logging.info("登录成功")
    except Exception as e:
        logging.error(f"登录失败，错误信息：{e}")
        email_sender.send_email("登录失败", f"错误信息：{e}")
        exit(1)

    # 测试网站连通性

    try:
        app.get(url='https://pecg.hust.edu.cn/wescms')
    except Exception as e:
        logging.error(f"无法连接到网站，错误信息：{e}")
        email_sender.send_email("无法连接到网站", f"错误信息：{e}")
        exit(1)

    subject = '模块检查邮件'
    body = ('\n统一身份认证正常通过'
            '\n可正常连接场馆中心网站'
            f'\n场馆编号：{email_sender.selected_gym}'
            f'\n起始时间{email_sender.start_time}'
            f'\n结束时间{email_sender.end_time}'
            f'\n支付方式{app_config.paymethod}')
    email_sender.send_email(subject, body)

if __name__ == "__main__":
    main()