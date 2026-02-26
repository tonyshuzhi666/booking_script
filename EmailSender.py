import json
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import Header


class EmailSender:
    def __init__(self, config_path: str):
        """
        初始化邮件发送器，加载配置文件
        :param config_path: 配置文件路径
        """
        self.load_config(config_path)

    def load_config(self, config_path: str):
        """
        加载配置文件
        :param config_path: 配置文件路径
        """
        with open(config_path, 'r', encoding='utf-8') as file:
            config = json.load(file)
        self.smtp_server = config['Email']['smtp_server']
        self.smtp_port = config['Email']['smtp_port']
        self.username = config['Email']['username']
        self.password = config['Email']['password']
        self.sender = config['Email']['sender']
        self.recipients = config['Email'].get('recipients', [])  # 收件人列表
        self.selected_gym = config['Gym']
        self.start_time = config['Time']['start']
        self.end_time = config['Time']['end']

    def send_email(self, subject: str, body: str):
        """
        发送邮件给配置文件中的所有收件人
        :param subject: 邮件主题
        :param body: 邮件正文
        """
        if not self.recipients:
            print("收件人列表为空，邮件未发送。")
            return

        # 创建邮件对象
        message = MIMEMultipart()
        message['From'] = Header(self.sender)  # 发件人
        message['To'] = Header(", ".join(self.recipients))  # 收件人
        message['Subject'] = Header(subject, 'utf-8')  # 邮件主题
        message.attach(MIMEText(body, 'plain', 'utf-8'))  # 添加正文

        try:
            # 连接SMTP服务器
            with smtplib.SMTP_SSL(self.smtp_server, self.smtp_port) as server:
                print("连接SMTP服务器成功！")
                server.login(self.username, self.password)  # 登录
                print("登录成功！")
                server.sendmail(self.sender, self.recipients, message.as_string())  # 发送邮件
                server.quit()
            print("邮件发送成功！")
        except Exception as e:
            print(f"邮件发送失败：{e}")


# 测试代码
if __name__ == '__main__':
    config_path = 'config.json'  # 配置文件路径
    email_sender = EmailSender(config_path)  # 创建邮件发送器实例


    # 发送邮件
    subject = '测试邮件'
    body = ('这是通过 Python 类发送的测试邮件，支持多个收件人！'
            f'\n场馆编号：{email_sender.selected_gym}'
            f'\n起始时间{email_sender.start_time}'
            f'\n结束时间{email_sender.end_time}')
    email_sender.send_email(subject, body)