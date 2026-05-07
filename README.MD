# AtiumSync

AtiumSync is a tool for syncing and controlling dumbphones via a PC.

## Features:

* Sync contacts
* Sync call logs

## Dumb phones supporting

Tested mainly with this phones, but intended to work with all PBAP-compatible phones.

| Device | OS | Tested By | Working Properly | Notes |
|--------|----|-----------|------------------|-------|
| Navi C1       | XXXXXX   | AshiVered         | Yes (Channel: 6)                |       |
| FirstPhone PRO30       | Mocor 20A   | AshiVered         | Yes (Channel: 7)                |       |
| KosherMobile K46       | Mocor 20A   | [@dfhzrhree](https://mitmachim.top/user/dfhzrhree?_=1778145388054)         | Yes (Channel: 6)                |       |
| Nokia 225 4G 2020       | Mocor 20A   | AshiVered         | No                | Doesn't support PBAP      |
| Nokia 3210 4G 2024       | Mocor 20A   | AshiVered         | No                | Doesn't support PBAP      |
| Nokia 215 4G 2024       | Mocor 20A   | AshiVered         | No                | Doesn't support PBAP      |
| Xiaomi Qin 1S+       | MocorDroid 5 (Android KitKat)   | AshiVered         | No                | Supports PBAP, but connection is refused (likely Android security limitation)      |
| Xiaomi Qin K25       | Android 14   | AshiVered         | No                | Supports PBAP, but connection is refused (likely Android security limitation)      |
| Nokia C5 (RM 645)      | Symbian 9.3   | AshiVered         | No                | Supports PBAP, but an unknown error occurs      |


#### Devices expected to work but not yet tested

According to the information I gathered, there is a high chance that these devices will work with the software.
But it's not certain, and of course it doesn't mean that other phones won't fit. I would be very happy to receive information about any phone that you think should work, or even better - if you have tested it and it works.

| Device | OS |
|--------|----|
| QLYX Q7 | Mocor 20A |
| QLYX Q8 | Mocor 20A |
| Escolls 4*4 | Mocor 20A |
| Escolls 5*5 | Mocor 20A |
| Escolls Flip 2 | Mocor 20A |

#### Adding support for a new device

This should be very easy.

1. Power on Bluetooth in phone&PC.
2. Run AtiumSync and press scan.
3. When devices list appear, find your phone (by name) and copy MAC address.
4. Run this command to scan supported protocols for your phone:

```
sdptool browse MAC
```

5. If you see output like this:

```
Service RecHandle: 0x10006
Service Class ID List:
  "Phonebook Access - PSE" (0x112f)
Protocol Descriptor List:
  "L2CAP" (0x0100)
  "RFCOMM" (0x0003)
    Channel: 6
  "OBEX" (0x0008)
Profile Descriptor List:
  "Phonebook Access" (0x1130)
    Version: 0x0102
```

Your phone must be supported. but, if your channel isn't 6, you need modify this line in code:

```
subprocess.run(["obexftp", "--bluetooth", mac, "--channel", "6", "-g", remote_path])
```

(line 122)

if work good, please update me, to add your device to the list :)

## To do list

1. Support controling media
2. Support calls
3. Support SMS (Need phone that supported MAP)
4. Clean folder when opening software
5. Add option to export contacts as VCF file and call log as Excel file.

## Will never happen

1. Devices without PBAP support.
2. Old devices (like Nokia C5), if they do not work properly in the standard way.

## Highly unlikely features
1. Solve Android security problems.
2. Supporting Windows. (Currently, software has based on Linux BlueZ)

## Donation

If you like my work, please buy me coffe :)

https://ko-fi.com/ashivered
