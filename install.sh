#!/bin/bash

set -ex

install -Dm755 tool.py /usr/local/bin/x1e-ec-tool
install -Dm644 x1e-ec-tool.conf /usr/local/lib/modules-load.d/x1e-ec-tool.conf
install -Dm644 x1e-ec-tool.service /usr/local/lib/systemd/system/x1e-ec-tool.service

modprobe i2c-dev

systemctl daemon-reload
systemctl enable x1e-ec-tool.service
systemctl start x1e-ec-tool.service
sleep 1
systemctl status x1e-ec-tool.service
