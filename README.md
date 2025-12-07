# Integration for PV inverters from KACO

This Home Assistant custom component allows you to integrate PV inverters from KACO via RS485.

# Installation

## HACS

The recommend way to install `kaco_inverter` is through [HACS](https://hacs.xyz/).

## Manual installation

Copy the `kaco_inverter` folder and all of its contents into your Home Assistant's `custom_components` folder. This folder is usually inside your `/config` folder. If you are running Hass.io, use SAMBA to copy the folder over. You may need to create the `custom_components` folder and then copy the `kaco_inverter` folder and all of its contents into it.

# Setup

1. Connect the inverters to a RS485 bus like described in the manual of the respective inverter.
2. Connect the device running Home Assistant to the RS485 bus. There are plenty of cheap and simple RS485 to USB modules available on eBay, that should work just fine.
3. Add the integration for a single inverter via the the Web UI.



# Trademark Legal Notices

All product names, trademarks and registered trademarks in the images in this
repository, are property of their respective owners.
