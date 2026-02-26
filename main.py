import argparse
from chaojiying import Chaojiying_Client
from config import AppConfig
from captcha_handler import CaptchaHandler
from appointment import Appointment
from booking_manager import BookingManager
from gym_manager import GymSlot
from EmailSender import EmailSender
import requests
import logging


def main():
    # 初始化config,预约类，验证码类
    # 使用 argparse 获取命令行参数
    parser = argparse.ArgumentParser(description="预约脚本")
    parser.add_argument("config_file", type=str, help="配置文件路径，例如 config1.json")
    args = parser.parse_args()

    config_file = args.config_file
    
    print(f'using config file : {config_file}')
    logging.basicConfig(level=logging.INFO)
    email = EmailSender(config_file)
    app_config = AppConfig.load_from_file(config_file)
    chaojiying = Chaojiying_Client(app_config.chaojiying.username, app_config.chaojiying.passwd,
                                   app_config.chaojiying.softid)
    captcha_handler = CaptchaHandler(chaojiying)
    app = Appointment(app_config.username, app_config.password)
    gym_manager = GymSlot(gym_id=app_config.gym_id,gym_type=app_config.gym_type, start_time=app_config.time.start, end_time=app_config.time.end)
    booking_manager = BookingManager(app, gym_manager, captcha_handler, app_config)

    response = booking_manager.execute_booking()


    if response:
        if app_config.paymethod == -2:
            subject = "预约成功"
            body = f'付款链接: {response} \n ,预约场馆编号:{app_config.gym_id},时间段:{app_config.time.start}-{app_config.time.end},用户:{app_config.username}'
            email.send_email(subject, body)
            booking_result = booking_manager._check_booking_result()
            subject = "预约结果"
            email.send_email(subject, booking_result)
        else:
            subject = "预约成功"
            body = '如电子账户余额充足，将自动扣款，否则本次预约失败'
            email.send_email(subject, body)
            booking_result = booking_manager._check_booking_result()
            subject = "预约结果"
            email.send_email(subject, booking_result)
            
        # logging.info("预约成功")
        
    else:
        subject = "预约失败"
        body = "请手动预约"
        email.send_email(subject, body)
        logging.error("预约失败")


if __name__ == "__main__":
    main()
