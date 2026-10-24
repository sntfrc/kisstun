# kissTUN

`kissTUN` connects your computer to Dire Wolf, so IPv4 traffic can travel over a KISS radio link. Choose the instructions for your computer below.

The bridge carries IPv4 unicast traffic. It filters out IPv6, broadcasts, multicast, and common local network discovery traffic.

## Before you start

Choose an IPv4 address and subnet for the tunnel, for example `10.73.0.1/16`. Use an address and subnet that fit your network plan and do not conflict with another device.

You will need to create a `direwolf.conf` file for your radio setup, see below section for an example.

## Linux

1. Clone the project and build and install it:

   ```sh
   git clone https://github.com/sntfrc/kisstun.git
   cd kisstun
   make
   sudo make install
   ```

2. Install Dire Wolf, for example with `sudo apt install direwolf` (or build it from source)
3. Create your Dire Wolf configuration at `~/direwolf.conf` and adjust it for your radio and KISS connection.
4. Start kissTUN with an address and subnet, for example:

   ```sh
   sudo kisstun --address 10.73.0.1/16
   ```

   If the installed command is not on your `PATH`, run the script directly from the project directory with `sudo python3 kisstun.py --address 10.73.0.1/16`.
5. To start kissTUN automatically at boot, configure it as a systemd service. The service must run as root to create the tunnel, and should include your chosen `--address` argument.

## macOS

There are two approaches: the first one is to just follow the Linux instructions, they work on macOS too - just ensure you have Dire Wolf installed, for example via `brew install direwolf`.

The second one is using the user-friendly packaged release, as follows:

1. Ensure [Homebrew](https://brew.sh) is installed and working.
2. Download the macOS `.dmg` from the project’s [Releases](https://github.com/sntfrc/kisstun/releases) page.
3. Open the disk image and drag the app into **Applications**.
4. Create `direwolf.conf` in your home directory and adjust it for your radio and KISS connection.
5. Open the app. If Dire Wolf isn't installed from homebrew, it will install it automatically. Then it will ask you for the tunnel’s IPv4 address and subnet.

To use a fixed address without being prompted, use Script Editor to edit the launch script inside the app bundle, and pass the `--address` argument to Python. You can also add the app to your login items if you want it to start when you sign in.

## Windows

There is a ready-made package which includes everything needed to run the tunnel, which is kissTUN + Python + Dire Wolf + Wintun DLL.

1. Download the Windows ZIP from the project’s [Releases](https://github.com/sntfrc/kisstun/releases) page and unzip it.
2. Open the `dist` folder and edit `direwolf.conf` inside it, for your radio and KISS connection.
3. Run the included `.bat` file as **Administrator**. Follow the prompt to enter the tunnel’s IPv4 address and subnet.

The ZIP includes everything needed; you do not need to install Python separately.

To use a fixed address without being prompted, edit the .bat file to pass the `--address` argument.

## Choosing the tunnel address

The address is written in IPv4 CIDR format: an address, a slash, and a prefix length. For example, `44.0.0.1/24`. Use the same tunnel network settings for the other devices in your radio network, assigning each device its own address.

## The Dire Wolf configuration file

A minimal `direwolf.conf` is required for kissTUN to run. Dire Wolf has many options, but only three are really needed to work with this script: ADEVICE, MODEM and PTT.

For example:

```
ADEVICE xxxx yyyy
MODEM 1200
PTT CM108
```

This will use audio device xxxx for input and yyyy for output, use 1200 baud packet modulation, and trigger the PTT via CM108 (you can also use serial port, or none at all for radio VOX which is however not recommended; refer to Dire Wolf documentation for the syntax).

Note on devices:
* on Windows they are numbers, you can see the numbered list by running the program and looking and the output;
* on Linux they are device names like `plughw:1,0` and similar, use `aplay -l` to see a list;
* on macOS you can match by name, for example `"MacBook Neo Microphone"`.

## If it does not connect

- Make sure `direwolf.conf` is in the location described for your operating system and contains the right settings for your radio.
- By default, kissTUN looks for Dire Wolf at `127.0.0.1:8001`. If it cannot connect, it tries to start Dire Wolf automatically. On Linux and macOS, it looks for Dire Wolf on your `PATH` or in the current directory. On Windows, use the supplied `.bat` package.
- The tunnel needs administrator/root privileges. On Windows, run the `.bat` file as Administrator; on Linux, use `sudo`; on macOS, grant the requested privileges.
- If you see a warning message that IPv6 could not be disabled, it probably means that it already is (this happens by default on macOS for example). No need to worry.

Stop a running session with `Ctrl+C` in its terminal.

## Acknowledgements

This project would never have been possible without the excellent work of:
* [Dire Wolf](https://github.com/wb2osz/direwolf)
* [Wintun](https://git.zx2c4.com/wintun)
