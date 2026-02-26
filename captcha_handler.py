import base64
import json
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad
from typing import List, Dict, Tuple
import logging

class CaptchaHandler:
    def __init__(self, chaojiying_client):
        self.chaojiying = chaojiying_client
        self.secret_key = ''
        self.click_data = []
        self.token = ''
        self.click_data = []

    def process_captcha(self, response_data: Dict) -> Tuple[str, str]:
        """处理验证码识别流程"""
        self.secret_key = response_data['repData']['secretKey']
        image_base64 = response_data['repData']['originalImageBase64']
        word_list = response_data['repData']['wordList']
        self.token = response_data['repData']['token']

        result = self.chaojiying.PostPic_base64(image_base64, 9501)
        word_box = result['pic_str']

        self.click_data = self._process_word_box(word_box=word_box, word_list=word_list)
        point_json = self._generate_point_json(click_data=self.click_data, secret_key=self.secret_key)
        # captcha_token = self._generate_captcha_token(click_data, token, secret_key)
        logging.info("验证码识别成功")

        return point_json, self.token

    def process_captcha_token(self) -> str:
        """处理验证码token"""
        return self._generate_captcha_token(self.click_data, self.token, self.secret_key)

    def _process_word_box(self, word_box: str, word_list: List[str]) -> List[Dict]:
        """处理验证码识别结果"""
        items = word_box.split('|')
        matched_data = {}

        for item in items:
            word, x, y = item.split(',')
            if word in word_list:
                matched_data[word] = (int(x), int(y))

        return [{"x": matched_data[word][0], "y": matched_data[word][1]}
                for word in word_list]

    def _generate_captcha_token(self, click_data: List[Dict], token,
                                secret_key: str) -> str:
        """生成加密的验证码token"""
        json_data = token + '---' + (json.dumps(click_data))
        json_token = json_data.replace(' ', '')
        return self._aes_encrypt(json_token, secret_key)

    def _generate_point_json(self, click_data: List[Dict], secret_key) -> str:
        """生成点击坐标的json字符串"""
        json_click_data = json.dumps(click_data)
        json_click_data = json_click_data.replace(' ', '')
        return self._aes_encrypt(json_click_data, secret_key)

    @staticmethod
    def _aes_encrypt(text: str, key: str) -> str:
        """AES加密"""
        cipher = AES.new(key.encode('utf-8'), AES.MODE_ECB)
        padded_data = pad(text.encode('utf-8'), AES.block_size)
        encrypted = cipher.encrypt(padded_data)
        return base64.b64encode(encrypted).decode('utf-8')
