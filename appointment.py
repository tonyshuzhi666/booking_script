import hust_login

import requests
from bs4 import BeautifulSoup
from hust_login import HustPass
import json
import logging

class Appointment:
    def __init__(self, username, password):
        self.username = username
        self.password = password
        self.session = requests.Session()
        self.session.timeout = 10 
        self.user_agent = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                   'AppleWebKit/537.36 (KHTML, like Gecko) '
                   'Chrome/128.0.0.0 Safari/537.36')
        self.header ={
            'User-Agent': self.user_agent,
            'Host': 'pecg.hust.edu.cn',
        }

    def login(self):
        with HustPass(self.username, self.password) as s:
            s.Session.get('https://pecg.hust.edu.cn/cggl/index1')
            cookies = s.Session.cookies
            self.session.cookies = cookies

    def _log_response_status(self, response, url):
        """
        此方法现在仅用于记录日志，不再决定是否返回响应。
        """
        if response is None:
            return

        status_code = getattr(response, 'status_code', None)
        if status_code == 200:
            pass # 成功的请求无需记录
        elif status_code == 429:
            retry_after = response.headers.get("Retry-After", "N/A")
            logging.warning(f"请求触发限流(429 Too Many Requests): {url}, Retry-After: {retry_after}")
        elif status_code == 504:
            logging.warning(f"请求遭遇网关超时(504 Gateway Timeout): {url}")
        else:
            logging.error(f"请求失败{url}，状态码：{status_code}")

    def get(self, url, referer=None, x_requested_with=None, content_type=None, origin=None, proxies=None):
        if referer: self.header['Referer'] = referer
        if x_requested_with: self.header['x-requested-with'] = x_requested_with
        if content_type: self.header['Content-Type'] = content_type
        if origin: self.header['Origin'] = origin
        if proxies: self.header['Proxy-Connection']: proxies
        
        try:
            response = self.session.get(url, headers=self.header)
            self._log_response_status(response, url)
            return response # 关键修改：总是返回响应对象
        except requests.exceptions.RequestException as e:
            logging.error(f"GET请求网络异常: {url}, 错误: {e}")
        
        return None

    def post(self, url, data, referer=None, x_requested_with=None, content_type=None, origin=None, proxies=None, allow_redirects=True):
        if referer: self.header['Referer'] = referer
        if x_requested_with: self.header['x-requested-with'] = x_requested_with
        if content_type: self.header['Content-Type'] = content_type
        if origin: self.header['Origin'] = origin
        if proxies: self.header['Proxy-Connection']: proxies

        try:
            response = self.session.post(url, headers=self.header, data=data, allow_redirects=allow_redirects)
            self._log_response_status(response, url)
            return response # 关键修改：总是返回响应对象
        except requests.exceptions.RequestException as e:
            logging.error(f"POST请求网络异常: {url}, 错误: {e}")

        return None
