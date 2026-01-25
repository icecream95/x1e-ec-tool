#!/usr/bin/env python3

import os
import sys
import time
import tool

# "Fire" effect based on temperature
def kb_backlight_fire(zones, period=0.2):
    zones = tool.open_thermal_zones(zones)
    if not len(zones):
        print("No zones")
        return

    min_temp = 40
    blue_temp = 55
    temp_range = 30

    cur = [256, 256, 256]

    while True:
        temp = 0
        for fd in zones:
            temp = max(temp, int(os.pread(fd, 20, 0)) / 1000)

        frac = min(max((temp - min_temp) / temp_range, 0), 1)
        frac2 = min(max((temp - blue_temp) / temp_range, 0), 1)

        r = frac * 1.0
        g = frac * frac * 0.5
        b = frac2

        new = [round(r*255), round(g*255), round(b*255)]
        if new != cur:
            tool.set_keyboard_backlight(*new)
            cur = new

        time.sleep(period)

def usage():
    print("fire : temperature-based keyboard backlight effect")

if __name__ == "__main__":
    tool.init()

    args = sys.argv[1:]

    if not len(args):
        usage()
        exit()

    if args[0] == "fire":
        kb_backlight_fire(tool.THERMAL_ZONES)
    else:
        usage()
