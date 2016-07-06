#!/bin/sh
#
if [ -z $ANDROID_SERIAL ]; then
  echo "** ANDROID_SERIAL not set"
  exit 1
fi
# Check for emulator
EM=`echo $ANDROID_SERIAL | cut -f1 -d-`
if [ $EM == "emulator" ]; then
  echo emulator
  exit 0
fi
if [ -z "$DEVTAGS" ]; then
  echo "** DEVTAGS environment variable not set"
  exit 1
fi
TAG=`echo $DEVTAGS | tr " " "\n" | egrep "\:${ANDROID_SERIAL}"`
if [ -z $TAG ]; then
  echo "** unknown device serial number $ANDROID_SERIAL"
  exit 1
fi
echo $TAG |  cut -f1 -d:
