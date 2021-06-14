#!/usr/bin/env bash

# Make sure we're not running at root to start
if [ $(id -u) -eq 0 ]; then
  echo "This should not be run with sudo. It will be called for the"
  echo "commands that require it. Try again without sudo."
else

sudo ./uninstall.sh
curl -s "https://raw.githubusercontent.com/Responseless/GaragePi/master/setup/online_install.sh" | bash
