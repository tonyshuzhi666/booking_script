import logging
from datetime import datetime, timedelta
import re
import time
from typing import Any, Optional, Tuple
from captcha_handler import CaptchaHandler
from gym_manager import GymSlot
from config import AppConfig
import json
import uuid
from urllib.parse import urlparse, parse_qs
import random
from bs4 import BeautifulSoup
from email.utils import parsedate_to_datetime

TOKEN_RE = re.compile(
    r'<input[^>]*name\s*=\s*\\?["\']token\\?["\'][^>]*value\s*=\s*\\?["\']([^"\'\\]+)\\?["\']',
    re.IGNORECASE
)


class BookingManager:
    LOGIN_TIME = "07:55:00"
    BOOKING_TIME = "07:59:58"
    BOOKING_DEADLINE_TIME = "08:06:00"
    WAIT_END_TIME = "18:00:00"
    ACCESS_GYM_MAX_RETRIES = 30
    GUIDE_TOKEN_MAX_RETRIES = 20
    FIND_SLOT_MAX_RETRIES = 25
    STEP2_MAX_RETRIES = 5
    STEP3_MAX_RETRIES = 5
    CAPTCHA_MAX_RETRIES = 3
    GYM_OPEN_TIME = "08:00:00"

    GYM_PAGE_URL = "https://pecg.hust.edu.cn/cggl/front/syqk?cdbh={gym_id}"
    BOOKING_GUIDE_URL = "https://pecg.hust.edu.cn/cggl/front/yuyuexz"
    FIND_SLOT_URL = "https://pecg.hust.edu.cn/cggl/front/ajax/getsyzt"
    STEP2_URL = "https://pecg.hust.edu.cn/cggl/front/step2"
    STEP3_URL = "https://pecg.hust.edu.cn/cggl/front/repay"
    CAPTCHA_GET_URL = "http://pecg.hust.edu.cn/cggl/api/open/captcha/get"
    CAPTCHA_CHECK_URL = "https://pecg.hust.edu.cn/cggl/api/open/captcha/check"

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
        self.debug = False

    def execute_booking(self):
        """
        执行预约主流程
        """
        try:
            self._wait_for_login_time()
            self._login()

            self._init_booking_dates()

            token = self._get_token()   # 在预约开始前获取初始 token，失败则直接放弃预约流程
            if not token:
                return None

            self._wait_for_booking_time()

            return self._run_booking_loop(token)

        except Exception as e:
            logging.error(f"执行预约时发生意外错误: {e}", exc_info=True)
            return None

    def _init_booking_dates(self):
        self.now_day = datetime.now().date()
        self.mid_day = (self.now_day + timedelta(days=1)).strftime('%Y-%m-%d')
        self.book_day = (self.now_day + timedelta(days=2)).strftime('%Y-%m-%d')
        logging.info(f"目标预约日期: {self.book_day}")

    def _get_token(self) -> Optional[str]:
        token = self._fetch_token_from_booking_guide()
        if token:
            return token

        logging.error("BOOKING_TIME 前未能从预约须知页提取 token，终止预约流程")
        return None

    def _run_booking_loop(self, token: str) -> Optional[str]:
        booking_deadline = self._booking_deadline()
        gym_page_response = None
        # current_token = token

        while datetime.now() < booking_deadline or self.debug:
            if not gym_page_response:
                gym_page_response = self._access_gym_page()
                if not gym_page_response:
                    logging.warning("访问场馆页面失败或未开放，间歇重试...")
                    sleep_time = self._pre_open_probe_delay() if self._is_before_gym_open() else random.uniform(0.8, 1.6)
                    time.sleep(sleep_time)
                    continue

            # available_site, booking_token = self._find_available_slot(token)
            available_site = self._find_available_slot(token)

            if available_site in (0, None):
                logging.info("无可用场地或请求失败，间歇重试。")
                time.sleep(random.uniform(0.3, 1.0))  # 避免过于频繁的请求
                continue

            logging.info(f"成功找到可用场地: {available_site}")
            captcha_token, reserve_id, order_id = self._process_step2(
                available_site=available_site,
                token=token
            )
            if not captcha_token:
                logging.warning("处理Step2或验证码失败，立即重试...")
                continue

            final_url = self._process_step3(
                captcha_token=captcha_token,
                token=token,
                reserve_id=reserve_id,
                order_id=order_id
            )
            if final_url:
                logging.info("--- 预约流程成功完成 ---")
                return final_url

            logging.warning("最终提交(Step3)失败，立即重试...")

        logging.error("预约失败")
        return None

    def _booking_deadline(self) -> datetime:
        deadline_time = datetime.strptime(self.BOOKING_DEADLINE_TIME, "%H:%M:%S").time()
        return datetime.now().replace(
            hour=deadline_time.hour,
            minute=deadline_time.minute,
            second=deadline_time.second,
            microsecond=0,
        )

    def _wait_for_login_time(self):
        self._wait_until_time(self.LOGIN_TIME)

    def _wait_for_booking_time(self):
        self._wait_until_time(self.BOOKING_TIME)

    @staticmethod
    def _wait_until_time(target_time: str):
        """
        等待直到指定时间点
        params:
            target_time(str): 目标时间字符串，格式 "HH:MM:SS"
        """
        target = datetime.strptime(target_time, "%H:%M:%S").time()
        endtime = datetime.strptime(BookingManager.WAIT_END_TIME, "%H:%M:%S").time()

        while True:
            now = datetime.now().time()
            if target <= now <= endtime:
                break
            
            # 计算距离目标时间的秒数
            time_diff = (datetime.combine(datetime.today(), target) - datetime.combine(datetime.today(), now)).total_seconds()
            
            # 等待本质上是“少唤醒 + 到点别迟到”，不是做高精度计时器。
            # 所以前面睡粗一点，最后10秒再细化轮询。
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

    @staticmethod
    def _response_status(response) -> Any:
        return response.status_code if response is not None else "N/A"

    @staticmethod
    def _is_response_ok(response, expected_status: int = 200) -> bool:
        return bool(response and response.status_code == expected_status)

    @staticmethod
    def _safe_json(response) -> Optional[Any]:
        try:
            return response.json()
        except (json.JSONDecodeError, ValueError, TypeError):
            return None

    @staticmethod
    def _retry_after_seconds(response) -> float:
        if response is None:
            return 0.0

        retry_after = response.headers.get("Retry-After")
        if not retry_after:
            return 0.0

        try:
            return max(float(retry_after), 0.0)
        except ValueError:
            try:
                dt = parsedate_to_datetime(retry_after)
                if dt is None:
                    return 0.0
                now = datetime.now(dt.tzinfo) if dt.tzinfo else datetime.now()
                return max((dt - now).total_seconds(), 0.0)
            except Exception:
                return 0.0

    @staticmethod
    def _is_before_gym_open() -> bool:
        open_time = datetime.strptime(BookingManager.GYM_OPEN_TIME, "%H:%M:%S").time()
        return datetime.now().time() < open_time

    @staticmethod
    def _pre_open_probe_delay() -> float:
        now = datetime.now()
        open_dt = datetime.combine(
            now.date(),
            datetime.strptime(BookingManager.GYM_OPEN_TIME, "%H:%M:%S").time()
        )
        seconds_to_open = (open_dt - now).total_seconds()

        if seconds_to_open > 180:
            return random.uniform(8.0, 12.0)
        if seconds_to_open > 60:
            return random.uniform(4.0, 7.0)
        if seconds_to_open > 15:
            return random.uniform(2.0, 3.5)
        if seconds_to_open > 0:
            return random.uniform(1.0, 1.8)
        return random.uniform(0.25, 0.6)

    def _login(self):
        self.appointment.login()
        logging.info("登录成功")

    def _gym_status_referer(self) -> str:
        return f'https://pecg.hust.edu.cn/cggl/front/syqk?date={self.mid_day}&type=1&cdbh={self.gym_id}'

    def _fetch_token_from_booking_guide(self) -> Optional[str]:
        """
        在 BOOKING_TIME 前，从预约须知页提取初始 token。
        """
        booking_time = datetime.strptime(self.BOOKING_TIME, "%H:%M:%S").time()

        for attempt in range(self.GUIDE_TOKEN_MAX_RETRIES):
            # 过了 BOOKING_TIME 再来这里拿初始 token 已经没有意义，直接交给主流程。
            if datetime.now().time() >= booking_time:
                break

            response = self.appointment.get(
                self.BOOKING_GUIDE_URL,
                referer=self.BOOKING_GUIDE_URL
            )
            if self._is_response_ok(response):
                token = self._extract_token(response.text)
                if token:
                    logging.info(f"成功从预约须知页提取 token (尝试 {attempt + 1} 次)")
                    return token

                logging.warning(
                    f"预约须知页访问成功但未提取到 token，继续重试... "
                    f"(第 {attempt + 1} 次尝试)"
                )
            else:
                status = self._response_status(response)
                logging.warning(
                    f"访问预约须知页失败，状态码: {status}，继续重试... "
                    f"(第 {attempt + 1} 次尝试)"
                )

            sleep_time = self._pre_open_probe_delay() if self._is_before_gym_open() else random.uniform(1.0, 2.0)
            time.sleep(sleep_time)

        return None

    def _access_gym_page(self) -> Optional[Any]:
        url = self.GYM_PAGE_URL.format(gym_id=self.gym_id)
        referer = self.BOOKING_GUIDE_URL
        consecutive_429 = 0
        
        for attempt in range(self.ACCESS_GYM_MAX_RETRIES):
            response = self.appointment.get(url, referer=referer)
            
            # 情况1: 请求返回200，判断是否进入了真实场馆页面
            if self._is_response_ok(response):
                consecutive_429 = 0
                if response.url == url:
                    logging.info(f"成功访问场馆页面 (尝试 {attempt + 1} 次)")
                    return response

                # 200 但 URL 被回退，说明入口还没放开；这时继续猛打只会更快撞限流。
                fallback_sleep = self._pre_open_probe_delay() if self._is_before_gym_open() else random.uniform(0.25, 0.6)
                logging.info(
                    f"场馆可能尚未开放，页面回退到: {response.url}，继续重试... "
                    f"(第 {attempt + 1} 次尝试)"
                )
                time.sleep(fallback_sleep)
                continue

            # 情况2: 服务器繁忙，收到504，进行重试
            if response and response.status_code == 504:
                consecutive_429 = 0
                logging.warning(f"访问场馆页面遭遇504，正在重试... (第 {attempt + 1} 次尝试)")
                time.sleep(random.uniform(0.3, 0.8))
                continue

            # 情况3: 触发限流429，优先遵循Retry-After，否则指数退避
            if response and response.status_code == 429:
                consecutive_429 += 1
                retry_after = self._retry_after_seconds(response)
                exp_backoff = min(1.2 * (2 ** min(consecutive_429, 5)), 12.0)
                cooldown = max(retry_after, exp_backoff) + random.uniform(0.2, 0.7)
                if self._is_before_gym_open():
                    # 开放前抢不到任何资源，优先恢复“可访问资格”，别把自己封死在429里。
                    cooldown = max(cooldown, self._pre_open_probe_delay() + random.uniform(1.0, 2.5))
                logging.warning(
                    f"访问场馆页面触发429限流，冷却 {cooldown:.2f}s 后重试 "
                    f"(第 {attempt + 1} 次尝试)"
                )
                time.sleep(cooldown)
                continue

            consecutive_429 = 0
            # 情况4: 其他错误 (网络错误, 其他状态码), 继续重试
            status = self._response_status(response)
            logging.warning(
                f"访问场馆页面失败，状态码: {status}，继续重试... "
                f"(第 {attempt + 1} 次尝试)"
            )
            time.sleep(random.uniform(0.3, 0.8))
        
        logging.error("在内部重试次数内未能成功访问场馆页面")
        return None

    @staticmethod
    def _extract_token(page_text: str) -> Optional[str]:
        """
        提取页面中的 token（匹配 name="token"）。
        """
        match = TOKEN_RE.search(page_text)
        if not match:
            return None

        token = match.group(1)
        logging.info(f"成功提取 token: {token}")
        return token

    def _find_available_slot(self, token: str) -> int | None:
        """
        查找可预约场地编号
        returns:
            - 场地编号(int) 和 token(str) : 找到可预约场地
            - 0 和 token(str) : 无可预约场地
            - None, None 如果请求失败或遭遇504错误
        """
        url = self.FIND_SLOT_URL
        data = {
            "changdibh": self.gym_id,
            "data": self.gym_slot.get_reserve_time(),
            "date": self.book_day,
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "token": token
        }

        for attempt in range(self.FIND_SLOT_MAX_RETRIES):
            response = self.appointment.post(url,
                                             data=data,
                                             referer=self._gym_status_referer(),
                                             x_requested_with='XMLHttpRequest')
            
            # 成功路径：仅在请求成功时进入
            if self._is_response_ok(response):
                response_data = self._safe_json(response)
                if not isinstance(response_data, list) or not response_data:
                    logging.error(f"解析getsyzt响应失败: 返回结构异常 (尝试 {attempt + 1}/{self.FIND_SLOT_MAX_RETRIES})")
                    continue

                try:
                    # 确保数据结构符合预期
                    msgs = response_data[0].get('message', [])
                    # new_booking_token = response_data[0].get('token')

                    # 查找可用场地
                    choosetime = next((m.get('pian') for m in msgs if m.get('zt') == 1), 0)

                    if choosetime == 0:
                        logging.info("查询成功，当前无可预约场地")
                    else:
                        logging.info(f"成功找到可用场地: {choosetime}")

                    # return choosetime, new_booking_token
                    return choosetime

                except (IndexError, KeyError, AttributeError, TypeError) as e:
                    # 成功返回200，但响应内容不是预期的JSON格式
                    logging.error(f"解析getsyzt响应失败: {e} (尝试 {attempt + 1}/{self.FIND_SLOT_MAX_RETRIES})")
            
            # 失败路径：处理所有非200或网络错误的情况
            else:
                status = self._response_status(response)
                logging.warning(
                    f"查找可用场地请求失败，状态码: {status} "
                    f"(尝试 {attempt + 1}/{self.FIND_SLOT_MAX_RETRIES})"
                )
                time.sleep(random.uniform(0.3, 0.9))  # 避免过于频繁的请求

        # 如果循环正常结束，说明所有尝试都失败了
        logging.error(f"查找可用场地在{self.FIND_SLOT_MAX_RETRIES}次重试后仍然失败。")
        # return None None
        return None

    def _process_step2(self, available_site: int, token: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        if not token:
            logging.error("Step2参数无效: token为空")
            return None, None, None

        payloads = {
            'starttime': self.start_time,
            'endtime': self.end_time,
            'partnerCardtype': '1',
            'choosetime': available_site,
            'changdibh': self.gym_id,
            'date': self.book_day,
            'token': token,
        }

        response = None
        for attempt in range(self.STEP2_MAX_RETRIES):
            response = self.appointment.post(url=self.STEP2_URL,
                                referer=self._gym_status_referer(),
                                content_type="application/x-www-form-urlencoded",
                                origin="https://pecg.hust.edu.cn",
                                data=payloads)
            if self._is_response_ok(response):
                break
            logging.warning(f"锁定场地(Step2)请求失败，正在重试... (第 {attempt + 1} 次尝试)")

        if not self._is_response_ok(response):
            logging.error("锁定场地(Step2)请求失败")
            return None, None, None

        logging.info("锁定场地成功")

        reserve_id = order_id = ''
        # 解析Step2响应的跳转URL，提取 reserveId 和 orderId
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

    def _process_step3(self, captcha_token, token, reserve_id, order_id) -> Optional[str]:
        data_step3 = {
            'orderId': order_id,
            'reserveId': reserve_id,
            'data': '',
            'id': '',
            'select_pay_type': self.pay_method,
            'captchatoken': captcha_token,
            # 'cg_csrf_token': csrf_token,
            'token': token
        }
        step3_response = None
        for attempt in range(self.STEP3_MAX_RETRIES):
            step3_response = self.appointment.post(self.STEP3_URL,
                                      data=data_step3,
                                      referer=f'https://pecg.hust.edu.cn/cggl/front/toPay?reserveId={reserve_id}&orderId={order_id}',
                                      content_type='application/x-www-form-urlencoded',
                                      origin='https://pecg.hust.edu.cn',
                                      allow_redirects=False  # 禁用自动重定向
                                      )
            # 302 表示重定向到支付页面，即预约成功
            if step3_response and step3_response.status_code in [200, 302]:
                break
            logging.warning(f"最终提交(Step3)请求失败，正在重试... (第 {attempt + 1} 次尝试)")

        if not step3_response:
            logging.error("最终提交(Step3)请求失败: 未获取有效响应")
            return None

        if step3_response.status_code == 302:
            pay_url = step3_response.headers.get('Location', '')
            logging.info(f"预约成功，支付链接: {pay_url}")
            return pay_url
        elif step3_response.status_code == 200:
            logging.info("预约成功")
            return step3_response.url
        else:
            return None

    def _solve_captcha(self, json_data, point) -> Optional[str]:
        for attempt in range(self.CAPTCHA_MAX_RETRIES):
            response = self.appointment.post(
                url=self.CAPTCHA_GET_URL,
                referer="https://pecg.hust.edu.cn/cggl/front/step2",
                content_type="application/json;charset=UTF-8",
                proxies="keep-alive",
                origin="https://pecg.hust.edu.cn",
                data=json_data
            )
            if not self._is_response_ok(response):
                logging.error(
                    f"验证码获取失败，状态码: {self._response_status(response)} "
                    f"(尝试 {attempt + 1}/{self.CAPTCHA_MAX_RETRIES})"
                )
                continue

            # 将 JSON 响应内容转换为 Python 字典
            response_data = self._safe_json(response)
            if not isinstance(response_data, dict):
                logging.error(
                    f"验证码获取响应解析失败 (尝试 {attempt + 1}/{self.CAPTCHA_MAX_RETRIES})"
                )
                continue

            # 超级鹰识别验证码
            point_json, token = self.captcha_handler.process_captcha(response_data)

            data_check = {
                "captchaType": "clickWord",
                'clientUid': point,
                'pointJson': point_json,
                'token': token,
                'ts': int(time.time() * 1000)
            }

            check_json_data = json.dumps(data_check)
            response_check = self.appointment.post(
                self.CAPTCHA_CHECK_URL,
                data=check_json_data,
                origin='https://pecg.hust.edu.cn',
                content_type='application/json;charset=UTF-8',
                referer='https://pecg.hust.edu.cn/cggl/front/step2',
                proxies='keep-alive'
            )
            if not self._is_response_ok(response_check):
                logging.error(
                    f"验证码校验请求失败，状态码: {self._response_status(response_check)} "
                    f"(尝试 {attempt + 1}/{self.CAPTCHA_MAX_RETRIES})"
                )
                continue

            response_data = self._safe_json(response_check)
            if not isinstance(response_data, dict):
                logging.error(
                    f"验证码校验响应解析失败 (尝试 {attempt + 1}/{self.CAPTCHA_MAX_RETRIES})"
                )
                continue

            success = response_data.get('success')
            if success is True:
                logging.info("验证码验证成功")
                return self.captcha_handler.process_captcha_token()

            logging.error(f"验证码验证失败 (尝试 {attempt + 1}/{self.CAPTCHA_MAX_RETRIES})")
            self.retry = attempt + 1

        return None
        
    def _check_booking_result(self):
        
        # 等待10分钟
        time.sleep(600)
        
        # 检查预约结果
        response = self.appointment.get(
            url = "https://pecg.hust.edu.cn/cggl/front/gerenzx"
        )

        soup = BeautifulSoup(response.text, "html.parser")
        booking_rows = soup.select('tr')
        for row in booking_rows[1:]:
            cells = row.select('td')
            if len(cells) < 4:
                continue
            field_info = cells[1].get_text(strip=True)
            time_info = cells[2].get_text(strip=True)
            status = cells[3].get_text(strip=True)

            # 预约成功，返回预约结果
            if status == "已缴费" and time_info == f"{self.book_day}{self.start_time}—{self.end_time}":
                booking_result = f"场地信息: {field_info}, 时间: {time_info}, 状态: {status}"
                return booking_result
        
        # 获取最近一条记录
        if len(booking_rows) > 1:
            latest_cells = booking_rows[1].select('td')
            if len(latest_cells) >= 4:
                booking_result = f"场地信息: {latest_cells[1].get_text(strip=True)}, 时间: {latest_cells[2].get_text(strip=True)}, 状态: {latest_cells[3].get_text(strip=True)}"
                return f"未查询到预约成功结果\n最近一条预约记录如下:\n{booking_result}"
        return "未查询到任何预约记录"
