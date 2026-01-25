#!/usr/bin/env python3

import ctypes
import fcntl
import math
import os
import re
import sys
import time

BUSADDR = "b94000.i2c"

class Model:
    def __init__(self, profiles=("Lowest",), fans=("Fan",), fan_blades=None, rpm_models=None):
        self.profiles = profiles
        self.fans = fans
        self.fan_blades = fan_blades
        self.rpm_models = rpm_models

    def blades(self, fan_id):
        if self.fan_blades is None:
            raise RuntimeError("No fan blade count defined")
        return self.fan_blades[fan_id]

MODELS = {
    "ASUS Vivobook S 15": Model(
        profiles=["Whisper",
                  "Standard",
                  "Performance",
                  "Full speed"],
        fans=["Left Fan", "Right Fan"],
        fan_blades=[97, 97],
        rpm_models=[
            ("-0.06309x^2 +48.64x -174.4", 17, 22, 8340),
            ("-0.07043x^2 +56.12x -2255", 55, 59, 8400),
        ],
    ),
}

# Use the maximum of a selection of thermal zones, since
# there can be a delta of about 10°C across the chip.
# TODO: Do not try to use the core cluster 2 for Purwa.
THERMAL_ZONES = [
    "cpu0-0-top-thermal",
    "cpu1-0-top-thermal",
    "cpu2-0-top-thermal",
    "gpuss-0-thermal",
]

def get_model_info():
    with open("/sys/firmware/devicetree/base/model") as f:
        model = f.read().strip(" \n\0")

    try:
        return MODELS[model]
    except KeyError:
        print(f"Error: Device '{model}' unrecognized")
        return None

def open_i2c(addr):
    buspath = f"/sys/bus/platform/devices/{addr}"

    devs = [x for x in os.listdir(buspath) if x.startswith("i2c-")]

    if len(devs) != 1:
        print(f"Cannot find device in {buspath}")
        exit(1)

    bus = int(devs[0].split("-")[1])

    try:
        return os.open(f"/dev/i2c-{bus}", os.O_RDWR)
    except FileNotFoundError:
        try:
            return os.open(f"/dev/i2c/{bus}", os.O_RDWR)
        except FileNotFoundError:
            raise RuntimeError("Try: modprobe i2c-dev")

info = None
i2c_fd = None

I2C_SLAVE = 0x0703
I2C_RDWR = 0x0707

# The EC handles both, so the distinction isn't precise
EC_ADDR = 0x5b
FAN_ADDR = 0x76

def init():
    global info
    global i2c_fd
    info = get_model_info()
    i2c_fd = open_i2c(BUSADDR)

    # Check that there is no kernel driver for the I2C devices
    fcntl.ioctl(i2c_fd, I2C_SLAVE, FAN_ADDR)
    fcntl.ioctl(i2c_fd, I2C_SLAVE, EC_ADDR)

I2C_M_RD = 0x0001

class I2c_msg(ctypes.Structure):
    _fields_ = [("addr", ctypes.c_uint16),
                ("flags", ctypes.c_uint16),
                ("len", ctypes.c_uint16),
                ("buf", ctypes.POINTER(ctypes.c_char))]

    def __repr__(self):
        flg = "I2C_M_RD" if (self.flags & I2C_M_RD) != 0 else "0"
        buf = " ".join([f"{self.buf[i][0]:02x}" for i in range(self.len)])
        return f"I2c_msg(addr={self.addr}, flags={flg}, len={self.len}, buf='{buf}')"

class I2c_rdwr_ioctl_data(ctypes.Structure):
    _fields_ = [("msgs", ctypes.POINTER(I2c_msg)),
                ("nmsgs", ctypes.c_uint32)]

class Buffer:
    def __init__(self, len):
        self.buf = ctypes.create_string_buffer(len)
    def __len__(self):
        return len(self.buf)
    def array(self):
        return list(self.buf.raw)

class Request:
    def __init__(self, addr):
        self.addr = addr
        self.msgs = []

    def write(self, *data):
        data = bytes(data)
        # Adds a trailing NUL, oh well...
        buf = ctypes.create_string_buffer(data)
        self.msgs.append(I2c_msg(addr=self.addr, flags=0,
                                 len=len(data), buf=buf))
        return self

    def read(self, buf):
        self.msgs.append(I2c_msg(addr=self.addr, flags=I2C_M_RD,
                                 len=len(buf), buf=buf.buf))
        return self

    def send(self):
        #print(self.msgs)
        nmsgs = len(self.msgs)
        arr = (I2c_msg * nmsgs)(*self.msgs)
        msg = I2c_rdwr_ioctl_data(arr, nmsgs)
        fcntl.ioctl(i2c_fd, I2C_RDWR, msg)

######## EC basic commands (defined in DSDT)

def ecrb(maj, min):
    res = Buffer(1)
    Request(EC_ADDR).write(0x10, maj, min).write(0x11).read(res).send()
    return res.array()[0]

def ecwb(maj, min, value):
    Request(EC_ADDR).write(0x10, maj, min).write(0x11, value).send()
    
def ec_settle():
    while True:
        if ecrb(0xc4, 0x30) == 0:
            return
        time.sleep(0.05)

def eccr(a1, a2):
    ec_settle()
    ecwb(0xc4, 0x31, a2)
    ecwb(0xc4, 0x30, a1)
    ec_settle()

    res = ecrb(0xc4, 0x32)
    ecwb(0xc4, 0x32, 0x00)
    return res
    
def eccw(a1, a2, val):
    ec_settle()
    ecwb(0xc4, 0x31, a2)
    ecwb(0xc4, 0x32, val)
    ecwb(0xc4, 0x30, a1)
    ec_settle()

######## EC control functions

def get_fan_rpm(fan_id):
    if fan_id >= len(info.fans):
        print("Trying to get RPM of invalid fan id")
    res = Buffer(3)
    Request(FAN_ADDR).write(0x22, fan_id + 1).read(res).send()
    arr = res.array()
    return arr[1] + arr[2] * 256

FAN_MODE_AUTO = 0
FAN_MODE_MANUAL = 2

def set_fan_mode(mode):
    eccw(0x01, 0x82, mode)

def set_fan_profile(profile):
    if profile >= len(info.profiles):
        print("Trying to switch to invalid profile")
    Request(FAN_ADDR).write(0x24, profile).send()

# Speed is 0-255. Only works in manual fan mode
def set_fan_speed(fan_id, speed):
    if fan_id >= len(info.fans):
        print("Trying to set speed of invalid fan id")

    eccw(0x01, 0x8c, fan_id)
    eccw(0x01, 0x8a, speed)

# Temperature is degrees Celsius
def send_soc_temp(temp):
    # TODO: I'm not entirely sure the units really are deci-Celsius
    temp = min(max(round(temp * 10), 0), 2000)

    lo = temp & 0xff
    hi = temp >> 8

    Request(FAN_ADDR).write(0x20, 0x01, 0x02, lo, hi).send()

def set_suspend_mode(mode):
    Request(FAN_ADDR).write(0x23, mode).send()

# Backlight control is probably specific to ASUS Vivobook S15.
# Note that brightness is also controlled by keyboard HID reports.

BACKLIGHT_SOLID = 0x01
BACKLIGHT_BREATHE = 0x02
BACKLIGHT_RAINBOW = 0x03
BACKLIGHT_STROBE = 0x04

def set_keyboard_backlight(r, g, b, mode=BACKLIGHT_SOLID, period=7):
    # TODO: What does this do?
    unk = 0x55

    Request(FAN_ADDR).write(0x51, 0x07, 0x66, 0x00, 0x10, 0x00, 0xb3, mode,
                            r, g, b, unk, period, *([0] * 9)).send()

########

def measure_fan_model(fan_ids, step=1):
    import numpy as np

    print("Switching to manual mode")
    set_fan_mode(FAN_MODE_MANUAL)

    print("Spinning up fans...")
    for j in fan_ids:
        set_fan_speed(j, 255)
    time.sleep(3)

    max_speeds = {j: get_fan_rpm(j) for j in fan_ids}

    print("Collecting RPM information:")

    data = {j: [] for j in fan_ids}
    for i in range(254, 0, -1 * step):
        for j in fan_ids:
            set_fan_speed(j, i)
        time.sleep(0.5)
        for j in fan_ids:
            rpm = get_fan_rpm(j)
            print(j, i, rpm)
            data[j].append([i, rpm])

    # Filter out speeds where the fan doesn't spin
    data = {j: np.array([x for x in data[j] if x[1]]) for j in fan_ids}

    for j in fan_ids:
        if not len(data):
            print(f"Error: Could not read RPM for fan {j}")

    firsts = {j: data[j][:, 0].min() for j in fan_ids}
    first_spins = {j: 255 for j in fan_ids}

    print("Searching for lowest speed where fans spin up")

    for i in range(min(firsts.values()), 255, step):
        for j in fan_ids:
            set_fan_speed(j, i)
        time.sleep(0.5)
        for j in fan_ids:
            if first_spins[j] == 255 and get_fan_rpm(j):
                first_spins[j] = i
        print(i, first_spins)
        if 255 not in first_spins.values():
            break

    print("Fan model data:")

    for j in fan_ids:
        a, b, c = np.polyfit(data[j][:, 0], data[j][:, 1], 2)
        poly = f"{a:.4g}x^2 {b:+.4g}x {c:+.4g}"

        print(f"{j}: ({poly}, {firsts[j]}, {first_spins[j]}, {max_speeds[j]}),")

    print("Switching back to automatic mode")
    set_fan_mode(FAN_MODE_AUTO)

def speed_for_rpm(fan_id, rpm):
    model = None if info.rpm_models is None else info.rpm_models[fan_id]
    if model is None:
        raise RuntimeError("No fan RPM model defined")

    if rpm == 0:
        return 0

    quadratic_regex = r"([-+0-9.e]+)x\^2 ([-+0-9.e]+)x ([-+0-9.e]+)"
    m = re.fullmatch(quadratic_regex, model[0])

    a, b, c = [float(m.group(i)) for i in (1, 2, 3)]
    if a >= 0:
        # I think this might just be flipping the sign
        # in the quadratic equation?
        raise RuntimeError("Convex model unimplemented")

    try:
        val = (-b + math.sqrt(b*b - 4*a*(c - rpm))) / (2*a)
    except ValueError: # sqrt of negative value
        val = 256

    if val < model[1] or val > 254:
        print(f"Warning: Speed for RPM {rpm} is out of domain")

    return min(max(round(val), 0), 255)

def open_thermal_zones(zones):
    zones = set(zones)
    files = []
    for zone in os.listdir("/sys/class/thermal"):
        if not zone.startswith("thermal_zone"):
            continue
        with open(f"/sys/class/thermal/{zone}/type") as f:
            zone_type = f.read().strip(" \n\0")
        if zone_type in zones:
            fd = os.open(f"/sys/class/thermal/{zone}/temp", os.O_RDONLY)
            files.append(fd)

    if len(files) != len(zones):
        print("Warning: Could not open all specified thermal zones")

    return files

def temperature_report_loop(zones, period=2, display=True):
    # Infinite loop, so don't bother closing file handles...
    zones = open_thermal_zones(zones)
    if not len(zones):
        print("No zones")
        return

    print("Warning: If temperature reporting is ever stopped (including")
    print("suspend) for more than a couple of minutes, then the EC may")
    print("hard poweroff the system.")

    while True:
        temp = 0
        for fd in zones:
            temp = max(temp, int(os.pread(fd, 20, 0)) / 1000)

        if display:
            print(f"\r{temp} °C", end="", flush=True)
        send_soc_temp(temp)
        time.sleep(period)

########

def rpm_for_freq(fan_id, hz):
    return hz / info.blades(fan_id) * 60
def freq_for_rpm(fan_id, rpm):
    return rpm * info.blades(fan_id) / 60

def print_fan_speeds():
    for i, fan in enumerate(info.fans):
        rpm = get_fan_rpm(i)
        if info.fan_blades is not None:
            print(f"{fan}: {rpm} RPM ({round(freq_for_rpm(i, rpm))} Hz)")
        else:
            print(f"{fan}: {get_fan_rpm(i)} RPM")

########

def usage():
    print("get-speed : get fan speeds")
    print("set-speed : set fan speed (RPM if available), only works in manual mode")
    print("mode : set mode to 'manual' or 'auto'")
    print("temp-loop : send temps to EC (required for auto mode to work)")
    print("profile : set profile (takes integer index starting at 0)")
    print("suspend : set suspend mode to 1 or 0 (DISABLES KEYBOARD while active!)")
    print("measure-rpm : measure RPM at different fan speeds (takes three minutes)")
    print("kb : set ASUS keyboard backlight to #rgb or rrggbb")

def main(args):
    if not len(args):
        usage()
        return 0

    if info is None or i2c_fd is None:
        sys.exit(1)

    if args[0] == "get-speed":
        print_fan_speeds()
    elif args[0] == "set-speed":
        speed = int(args[1])
        if info.rpm_models is not None:
            print(f"Setting speed to about {speed} RPM")
            for i in range(len(info.fans)):
                set_fan_speed(i, speed_for_rpm(i, speed))
        else:
            print(f"Setting speed to {speed}/255")
            for i in range(len(info.fans)):
                set_fan_speed(i, speed)
    elif args[0] == "mode":
        if args[1] == "auto":
            set_fan_mode(FAN_MODE_AUTO)
        elif args[1] == "manual":
            set_fan_mode(FAN_MODE_MANUAL)
        else:
            print("Invalid fan mode {args[1]}")
    elif args[0] == "profile":
        profile = int(args[1])
        if profile < len(info.profiles):
            print(f"Setting profile to {info.profiles[profile]}")
        set_fan_profile(profile)
    elif args[0] == "temp-loop":
        temperature_report_loop(THERMAL_ZONES)
    elif args[0] == "suspend":
        set_suspend_mode(int(args[1]))
    elif args[0] == "measure-rpm":
        measure_fan_model(range(len(info.fans)))
    elif args[0] == "kb":
        colour = args[1].strip("#")
        if re.fullmatch('[0-9a-fA-F]{3}', colour):
            fac = 17
        elif re.fullmatch('[0-9a-fA-F]{6}', colour):
            colour = [colour[:2], colour[2:4], colour[4:]]
            fac = 1
        else:
            print("#rgb or #rrggbb")
            return 1

        colour = [int(x, 16) * fac for x in colour]
        set_keyboard_backlight(*colour)
    else:
        usage()
    return 1

if __name__ == "__main__":
    init()
    sys.exit(main(sys.argv[1:]))
