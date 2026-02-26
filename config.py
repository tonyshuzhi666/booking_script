import json
from dataclasses import dataclass
from typing import Dict


@dataclass
class ChaojiyingConfig:
    username: str
    passwd: str
    softid: str


@dataclass
class TimeConfig:
    start: str
    end: str

@dataclass
class EmailConfig:
    username: str
    sender: str
    password: str
    smtp_server: str
    smtp_port: int
    receiver: str


@dataclass
class AppConfig:
    username: str
    password: str
    chaojiying: ChaojiyingConfig
    gym_id: int
    gym_type: int
    time: TimeConfig
    email: EmailConfig
    paymethod: int

    @classmethod
    def load_from_file(cls, filepath: str) -> 'AppConfig':
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
            return cls(
                username=data["Uname"],
                password=data["Upass"],
                chaojiying=ChaojiyingConfig(
                    username=data["Chaojiying"]["username"],
                    passwd=data["Chaojiying"]["passwd"],
                    softid=data["Chaojiying"]["softid"]
                ),
                gym_id=int(data["Gym"]),
                gym_type=int(data["GymType"]),
                time=TimeConfig(
                    start=data["Time"]["start"],
                    end=data["Time"]["end"]
                ),
                email=EmailConfig(
                    username=data["Email"]["username"],
                    sender=data["Email"]["sender"],
                    password=data["Email"]["password"],
                    smtp_server=data["Email"]["smtp_server"],
                    smtp_port=data["Email"]["smtp_port"],
                    receiver=data["Email"]["recipients"]
                ),
                paymethod=int(data["Payment"]["method"]) * -1
            )