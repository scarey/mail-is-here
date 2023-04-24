# MIT License (MIT)
# Copyright (c) 2023 Stephen Carey
# https://opensource.org/licenses/MIT

import json
from machine import RTC

rtc = RTC()


class JRAM():

    def get(self):
        try:
            return json.loads(rtc.memory().decode('ascii'))
        except:
            return {}

    def put(self, dic):
        rtc.memory(json.dumps(dic))

    def clear(self):
        self.put({})
        return self.get()
