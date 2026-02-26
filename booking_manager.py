import logging
import sys
from datetime import datetime, timedelta
from selectolax.parser import HTMLParser
import re
import time
from typing import Dict, Optional
from captcha_handler import CaptchaHandler
from gym_manager import GymSlot
from config import AppConfig
import json
import uuid
from urllib.parse import urlparse, parse_qs
import random

CSRF_RE = re.compile(r'name="cg_csrf_token"\s+value="([^"]+)"')
INLINE_SCRIPT_WITH_VALUE_RE = re.compile(
    r'<script[^>]*>.*?value\s*=\s*["\'][^"\']+["\'].*?</script>', re.DOTALL
)
TOKEN_VALUE_IN_SCRIPT_RE = re.compile(r'value\s*=\s*["\']([^"\']+)["\']')


class BookingManager:
    def __init__(self, appointment, gym_slot: GymSlot, captcha_handler: CaptchaHandler, AppConfig: AppConfig):
        self.appointment = appointment
        self.gym_slot = gym_slot
        self.captcha_handler = captcha_handler
        self.start_time = AppConfig.time.start
        self.end_time = AppConfig.time.end
        self.gym_id = self.gym_slot.gym_id
        self.pay_method = AppConfig.paymethod
        self.now_day = None
        self.mid_day = None
        self.book_day = None
        self.retry = 0
        self.debug = True

    def execute_booking(self):
        """
        执行预约主流程
        """
        try:
            self._wait_for_login_time()
            self._login()
            
            self.now_day = datetime.now().date()
            self.mid_day = (self.now_day + timedelta(days=1)).strftime('%Y-%m-%d')
            self.book_day = (self.now_day + timedelta(days=2)).strftime('%Y-%m-%d')
            logging.info(f"目标预约日期: {self.book_day}")

            self._wait_for_booking_time()

            booking_deadline = datetime.now().replace(hour=8, minute=9, second=0, microsecond=0)
            # logging.info(f"抢票主循环启动，将持续尝试直到 {booking_deadline.strftime('%H:%M:%S')}")
            
            gym_page_response, csrf_token= self._access_gym_page()
            if not gym_page_response:
                logging.warning("访问场馆页面失败，立即重试...")
                return None
            
            while datetime.now() < booking_deadline or self.debug:
                available_site, booking_token = self._find_available_slot(csrf_token)
                
                if available_site == 0 or available_site == None:
                    logging.info("无可用场地或请求失败，间歇重试。")
                    time.sleep(random.uniform(0.3, 1.0)) # 避免过于频繁的请求
                    continue

                logging.info(f"成功找到可用场地: {available_site}")

                captcha_token, reserve_id, order_id = self._process_step2(
                    available_site=available_site,
                    csrf_token=csrf_token,
                    booking_token=booking_token
                )
                if not captcha_token:
                    logging.warning("处理Step2或验证码失败，立即重试...")
                    continue
                
                final_url = self._process_step3(
                    captcha_token=captcha_token,
                    csrf_token=csrf_token,
                    booking_token=booking_token,
                    reserve_id=reserve_id,
                    order_id=order_id
                )
                if final_url:
                    logging.info("--- 预约流程成功完成 ---")
                    return final_url
                else:
                    logging.warning("最终提交(Step3)失败，立即重试...")
            
            logging.error("预约失败")
            return None

        except Exception as e:
            logging.error(f"执行预约时发生意外错误: {e}", exc_info=True)
            return None

    def _wait_for_login_time(self):
        self._wait_until_time("07:55:00")

    def _wait_for_booking_time(self):
        self._wait_until_time("07:59:55")

    @staticmethod
    def _wait_until_time(target_time: str):
        """
        等待直到指定时间点
        params:
            target_time(str): 目标时间字符串，格式 "HH:MM:SS"
        """
        target = datetime.strptime(target_time, "%H:%M:%S").time()
        endtime = datetime.strptime("18:00:00","%H:%M:%S").time()

        while True:
            now = datetime.now().time()
            if now >= target and now <= endtime:
                break
            
            # 计算距离目标时间的秒数
            time_diff = (datetime.combine(datetime.today(), target) - datetime.combine(datetime.today(), now)).total_seconds()
            
            # 智能睡眠策略：根据距离目标时间的远近动态调整
            if time_diff > 300:  # 距离目标时间超过5分钟
                sleep_time = random.uniform(25, 35)  # 睡眠25-35秒
            elif time_diff > 60:  # 距离目标时间超过1分钟
                sleep_time = random.uniform(8, 12)   # 睡眠8-12秒
            elif time_diff > 30:  # 距离目标时间超过30秒
                sleep_time = random.uniform(3, 5)    # 睡眠3-5秒
            elif time_diff > 10:  # 距离目标时间超过10秒
                sleep_time = random.uniform(1, 2)    # 睡眠1-2秒
            else:  # 最后10秒，精确控制
                sleep_time = random.uniform(0.05, 0.15)  # 睡眠0.05-0.15秒
                
            time.sleep(sleep_time)
                
        logging.info(f"到达目标时间 {target_time}，开始执行")

    def _login(self):
        self.appointment.login()
        logging.info("登录成功")

    def _access_gym_page(self):
        url = f"https://pecg.hust.edu.cn/cggl/front/syqk?cdbh={self.gym_id}"
        referer = "https://pecg.hust.edu.cn/cggl/front/yuyuexz"
        
        for attempt in range(30):
            response = self.appointment.get(url, referer=referer)
            
            # 情况1: 成功
            if response and response.status_code == 200 and response.url == url:
                logging.info(f"成功访问场馆页面 (尝试 {attempt + 1} 次)")
                csrf_token= self._extract_tokens(response.text)
                return response, csrf_token
            
            # 情况2: 服务器繁忙，收到504，进行重试
            if response.status_code == 504:
                logging.warning(f"访问场馆页面遭遇504，正在重试... (第 {attempt + 1} 次尝试)")
                time.sleep(random.uniform(0.1, 0.3))
                continue

            # 情况3: 其他错误 (网络错误, 其他状态码), 立即失败
            logging.error("访问场馆页面失败，非504错误或网络异常，停止重试。")
            return None, None # 快速失败
        
        logging.error("在内部重试次数内未能成功访问场馆页面 (均为504超时)")
        return None, None

    @staticmethod
    def _extract_tokens(page_text: str):
        """
        提取页面中的 csrf_token 和 token
        returns: csrf_token(str), token(str) or None, None if not found
        """
        csrf_token = None

        CSRF_RE.search(page_text)
        match_csrf = CSRF_RE.search(page_text)
        if match_csrf:
            csrf_token = match_csrf.group(1)
            logging.info(f"成功提取 csrf_token: {csrf_token}")

        # matches_script = INLINE_SCRIPT_WITH_VALUE_RE.findall(page_text)
        # if matches_script:
        #     m = TOKEN_VALUE_IN_SCRIPT_RE.search(matches_script[0])
        #     if m:
        #         token = m.group(1)
        #         logging.info(f"成功提取 token: {token}")  

        return csrf_token

    def _find_available_slot(self, booking_token: str):
        """
        查找可预约场地编号
        returns:
            - 场地编号(int) 和  booking_token(str) : 找到可预约场地
            - 0 和  booking_token(str) : 无可预约场地
            - None, None 如果请求失败或遭遇504错误
        """
        url = "https://pecg.hust.edu.cn/cggl/front/ajax/getsyzt"
        data = {
            "changdibh": self.gym_id,
            "data": self.gym_slot.get_reserve_time(),
            "date": self.book_day,
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "token": booking_token
        }

        for attempt in range(25):
            response = self.appointment.post(url,
                                             data=data,
                                             referer=f'https://pecg.hust.edu.cn/cggl/front/syqk?date={self.mid_day}&type=1&cdbh={self.gym_id}',
                                             x_requested_with='XMLHttpRequest')
            
            # 成功路径：仅在请求成功时进入
            if response and response.status_code == 200:
                try:
                    response_data = response.json()
                    # 确保数据结构符合预期
                    msgs = response_data[0].get('message', [])
                    new_booking_token = response_data[0].get('token')
                    
                    # 查找可用场地
                    choosetime = next((m.get('pian') for m in msgs if m.get('zt') == 1), 0)
                    
                    if choosetime == 0:
                        logging.info("查询成功，当前无可预约场地")
                    else:
                        logging.info(f"成功找到可用场地: {choosetime}")

                    return choosetime, new_booking_token
                
                except (json.JSONDecodeError, IndexError, KeyError, AttributeError) as e:
                    # 成功返回200，但响应内容不是预期的JSON格式
                    logging.error(f"解析getsyzt响应失败: {e} (尝试 {attempt + 1}/25)")
            
            # 失败路径：处理所有非200或网络错误的情况
            else:
                status = response.status_code if response else "N/A"
                logging.warning(f"查找可用场地请求失败，状态码: {status} (尝试 {attempt + 1}/25)")
                time.sleep(random.uniform(0.1, 0.3))  # 避免过于频繁的请求

        # 如果循环正常结束，说明所有尝试都失败了
        logging.error("查找可用场地在25次重试后仍然失败。")
        return None, None

    def _process_step2(self, available_site: int, csrf_token: str, booking_token: str):
        payloads = {
            'starttime': self.start_time,
            'endtime': self.end_time,
            'partnerCardtype': '1',
            'choosetime': available_site,
            'changdibh': self.gym_id,
            'date': self.book_day,
            'cg_csrf_token': csrf_token,
            'token': booking_token,
        }

        for attempt in range(5):
            response = self.appointment.post(url="https://pecg.hust.edu.cn/cggl/front/step2",
                                referer=f"https://pecg.hust.edu.cn/cggl/front/syqk?date={self.mid_day}&type=1&cdbh={self.gym_id}",
                                content_type="application/x-www-form-urlencoded",
                                origin="https://pecg.hust.edu.cn",
                                data=payloads)
            if response and response.status_code == 200:
                break
            logging.warning(f"锁定场地(Step2)请求失败，正在重试... (第 {attempt + 1} 次尝试)")

        if not response or response.status_code != 200:
            logging.error("锁定场地(Step2)请求失败")
            return None, None, None

        logging.info(f'锁定场地成功')

        reserve_id = order_id = ''
        try:
            qs = parse_qs(urlparse(response.url).query)
            reserve_id = (qs.get('reserveId') or [''])[0]
            order_id = (qs.get('orderId') or [''])[0]
            if not reserve_id or not order_id:
                logging.error("未能从Step2的跳转URL中解析出reserveId或orderId")
                return None, None, None
            logging.info(f"reserveId: {reserve_id}, orderId: {order_id}")
        except Exception as e:
            logging.error(f"解析reserveId和orderId时出错: {e}")
            return None, None, None

        ts = int(time.time() * 1000)
        point = 'point-' + str(uuid.uuid4())
        data_get_pic = {
            "captchaType": "clickWord",
            'clientUid': point,
            'ts': ts
        }

        json_data = json.dumps(data_get_pic)
        self.retry = 0  # 重置重试计数器
        captcha_token = self._solve_captcha(json_data, point)
        
        if captcha_token is None:
            logging.error("验证码识别失败")
            return None, None, None

        return captcha_token, reserve_id, order_id

    def _process_step3(self, captcha_token ,csrf_token, booking_token, reserve_id, order_id):
        data_step3 = {
            'orderId': order_id,
            'reserveId': reserve_id,
            'data': '',
            'id': '',
            'select_pay_type': self.pay_method,
            'captchatoken': captcha_token,
            'cg_csrf_token': csrf_token,
            'token': booking_token
        }
        step3_url = 'https://pecg.hust.edu.cn/cggl/front/repay'
        for attempt in range(5):
            step3_response = self.appointment.post(step3_url,
                                      data=data_step3,
                                      referer=f'https://pecg.hust.edu.cn/cggl/front/toPay?reserveId={reserve_id}&orderId={order_id}',
                                      content_type='application/x-www-form-urlencoded',
                                      origin='https://pecg.hust.edu.cn',
                                      allow_redirects=False  # 禁用自动重定向
                                      )
            # 302 表示重定向到支付页面，即预约成功
            if step3_response.status_code in [200, 302]:
                break
            logging.warning(f"最终提交(Step3)请求失败，正在重试... (第 {attempt + 1} 次尝试)")
        
        if step3_response.status_code == 302:
            # 从 Location header 获取支付链接
            pay_url = step3_response.headers.get('Location', '')
            logging.info(f"预约成功，支付链接: {pay_url}")
            return pay_url
        elif step3_response.status_code == 200:
            logging.info("预约成功")
            return step3_response.url
        else:
            return None

    def _solve_captcha(self, json_data, point) -> Optional[str]:

        response = self.appointment.post(url="http://pecg.hust.edu.cn/cggl/api/open/captcha/get",
                            referer=f"https://pecg.hust.edu.cn/cggl/front/step2",
                            content_type="application/json;charset=UTF-8",
                            proxies="keep-alive",
                            origin="https://pecg.hust.edu.cn",
                            data=json_data)

        # 将 JSON 响应内容转换为 Python 字典
        response_data = response.json()

        # 超级鹰识别验证码
        point_json, token = self.captcha_handler.process_captcha(response_data)

        data_check = {
            "captchaType": "clickWord",
            'clientUid': point,
            'pointJson': point_json,
            'token': token,
            'ts': int(time.time() * 1000)
        }

        json_data = json.dumps(data_check)
        response_check = self.appointment.post('https://pecg.hust.edu.cn/cggl/api/open/captcha/check',
                                  data=json_data,
                                  origin='https://pecg.hust.edu.cn',
                                  content_type='application/json;charset=UTF-8',
                                  referer='https://pecg.hust.edu.cn/cggl/front/step2',
                                  proxies='keep-alive')
        if response_check.status_code == 200:
            # 将 JSON 响应内容转换为 Python 字典
            response_data = response_check.json()
            logging.info("请求成功")
        else:
            logging.error("请求失败，状态码:", response_check.status_code)

        success = response_data['success']
        if success is True:
            logging.info("验证码验证成功")
            return self.captcha_handler.process_captcha_token()
        else:
            logging.error("验证码验证失败")
            self.retry += 1
            if self.retry >= 3:
                return None
            return self._solve_captcha(json_data, point)
        
    def _check_booking_result(self):
        
        # 等待五分钟
        time.sleep(300)
        
        # 检查预约结果
        response = self.appointment.get(
            url = "https://pecg.hust.edu.cn/cggl/front/gerenzx"
        )

        tree = HTMLParser(response.text)
        booking_rows = tree.css('tr')
        for row in booking_rows[1:]:
            cells = row.css('td')
            if len(cells) < 4:
                continue
            field_info = cells[1].text(strip=True)
            time_info = cells[2].text(strip=True)
            status = cells[3].text(strip=True)

            # 预约成功，返回预约结果
            if status == "已缴费" and time_info == f"{self.book_day}{self.start_time}—{self.end_time}":
                booking_result = f"场地信息: {field_info}, 时间: {time_info}, 状态: {status}"
                return booking_result
        
        # 获取最近一条记录
        if len(booking_rows) > 1:
            latest_cells = booking_rows[1].css('td')
            if len(latest_cells) >= 4:
                booking_result = f"场地信息: {latest_cells[1].text(strip=True)}, 时间: {latest_cells[2].text(strip=True)}, 状态: {latest_cells[3].text(strip=True)}"
                return f"未查询到预约成功结果\n最近一条预约记录如下:\n{booking_result}"
        return "未查询到任何预约记录"


