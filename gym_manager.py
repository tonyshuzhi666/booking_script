from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, Optional


@dataclass
class GymSlot:
    gym_id: int
    gym_type: int
    start_time: str
    end_time: str

    def get_reserve_time(self) -> str:
        """根据场馆ID生成对应的预约时间字符串"""
        gym_slots = {
            69: {
                1:[296, 295, 297, 298, 299, 301, 134, 584, 300],
                2:[298, 299, 301, 296, 295, 297, 134, 584, 300],
                3:[134, 584, 300, 296, 295, 297, 298, 299, 301]
            },
            # 45: {
            #     1:[219,220,368] + list(range(369, 376)),
            #     2:[220,219,368] + list(range(369, 376)),
            #     3:[368,220,219] + list(range(369, 376))
            # },
            45: {
                1:[220, 219, 221, 217, 222, 223, 370, 371, 375, 376, 377, 368, 224, 369, 373, 374, 372],
                2:[368, 224, 369, 223, 370, 217, 222, 371, 375, 376, 377, 220, 219, 221, 373, 374, 372],
                3:[373, 374, 372, 371, 375, 223, 370, 217, 222, 376, 377, 368, 224, 369, 220, 219, 221]
            },
            117: {
                1:list(range(587, 596))
            },
            126: {
                1:[642, 643, 644]
            },
            124: {
                1:[625, 626, 627]
            }
        }

        if self.gym_id not in gym_slots:
            raise ValueError("Invalid gym ID")

        return ",".join(f"{slot}@{self.start_time}-{self.end_time}"
                        for slot in gym_slots[self.gym_id][self.gym_type])
