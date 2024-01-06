#!/bin/bash

if [ $(id -u) -eq 0 ]; then
  echo "This should not be run with sudo. Try again without running with sudo."
elif [ "$BASH_SOURCE" != "" ]; then
  echo "This is intended to be run when pulled down by curl. Run setup.sh instead."
  echo "If you're getting a permission denied error, you may need to run"
  echo
  echo "chmod +x setup.sh"
  echo
  echo "to make the setup script executable."
else

  # Make sure git is installed
  echo "Making sure that git is installed..."
  ( sudo apt-get update -q && sudo apt-get install -y git ) || ( echo "Couldn't install git!"; exit 1 )

  # Pull down the repo
  echo -e "\nPulling down the repo..."
  cd ~
  git clone --branch dev https://github.com/Responseless/GaragePi.git garage_pi

  # Run the setup script
  echo -e "\nCalling the setup script..."
  cd ~/garage_pi
  chmod -v +x setup/setup.sh
  ./setup/setup.sh NO_APT_UPDATE

fi
