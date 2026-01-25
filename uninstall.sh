#!/bin/bash

set -ex

# Do not stop the service, because of the watchdog...
systemctl disable x1e-ec-tool.service

rm /usr/local/bin/x1e-ec-tool
rm /usr/local/lib/modules-load.d/x1e-ec-tool.conf
rm /usr/local/lib/systemd/system/x1e-ec-tool.service
