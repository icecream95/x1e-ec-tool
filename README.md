# x1e-ec-tool

Tool for working with the EC present on some Snapdragon X/X Plus/X Elite
systems.

## Supported devices:

So far:

- ASUS Vivobook S 15

But if the ACPI `dsdt.dsl` for your device has a block with the string
`"Temp to EC"` that mentions `\_SB.I2C6.FC20`, then it is very
possible that the device may work, if a model definition is added; see
"MODELS" in `tool.py`.

I would like to hear about any successes with other devices; patches
are welcome!

X2 devices might require more significant changes so are not yet
supported.

## Usage

Run `./tool.py` to see help.

## Installation

For systems using systemd, running `install.sh` as root will install
and start a service which sends the system temperature to the EC,
allowing the fans to work properly. It will also suspend the EC before
system suspend.

To uninstall, run `uninstall.sh` as root and then reboot.

Note that `x1e-ec-tool.service` uses `ConditionFirmware` so that it
only runs on supported systems.

## Note

There is no warranty!

That said, so long as you use a device with similar EC firmware (see
above), it is reasonably unlikely that you will damage anything from
trying to get it to work, other than tripping the EC watchdog and
causing a hard poweroff/reboot. At least ASUS devices have buggy
keyboard firmware and so you may need a USB keyboard to recover.

Spamming commands or using the effects in `effects.py` *might* cause
wear on EC flash memory; I think this is unlikely, but I am not
certain that configuration is only stored in SRAM.

Doing stupid things like using manual fan control to rapidly switch
fan speeds might cause some physical damage... I have a buzzing noise
from one fan which might be caused by this.
