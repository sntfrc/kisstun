# kissTUN

`kissTUN` connects your computer to Dire Wolf, so IPv4 traffic can travel over a KISS radio link. Choose the instructions for your computer below.

The bridge carries IPv4 unicast traffic. It filters out IPv6, broadcasts, multicast, and common local network discovery traffic.

## Before you start

You will need a working Dire Wolf configuration file in your home directory, named `direwolf.conf`. Set it up for your radio and KISS connection before running kissTUN. The exact settings depend on your radio and station setup.

You will also need to choose an IPv4 address and subnet for the tunnel, for example `44.0.0.1/24`. Use an address and subnet that fit your network plan and do not conflict with another device.

## Linux

1. Clone the project and build and install it:

   ```sh
   git clone https://github.com/sntfrc/kisstun.git
   cd kisstun
   make
   sudo make install
   ```

2. Create your Dire Wolf configuration at `~/direwolf.conf` and adjust it for your radio and KISS connection.
3. Start kissTUN with an address and subnet, for example:

   ```sh
   sudo kisstun --address 44.0.0.1/24
   ```

   If the installed command is not on your `PATH`, run the script directly from the project directory with `sudo python3 kisstun.py --address 44.0.0.1/24`.
4. To start kissTUN automatically at boot, configure it as a systemd service. The service must run with the privileges needed to create the tunnel and should include your chosen `--address` argument.

## macOS

1. Ensure [Homebrew](https://brew.sh) is installed and working.
2. Download the macOS `.dmg` from the project’s [Releases](https://github.com/sntfrc/kisstun/releases) page.
3. Open the disk image and drag the app into **Applications**.
4. Create `~/direwolf.conf` and adjust it for your radio and KISS connection.
5. Open the app. If direwolf isn't installed from homebrew, it will install it automatically. Then it will ask you for the tunnel’s IPv4 address and subnet.

To use a fixed address without being prompted, edit the launch script inside the app bundle to pass the `--address` argument. You can also add the app to your login items if you want it to start when you sign in.

## Windows

1. Download the Windows ZIP from the project’s [Releases](https://github.com/sntfrc/kisstun/releases) page and unzip it.
2. Open the `dist` folder and edit `direwolf.conf` for your radio and KISS connection.
3. Run the included `.bat` file as **Administrator**. Follow the prompt to enter the tunnel’s IPv4 address and subnet.

The ZIP includes the files needed to run the app, including the Wintun component. You do not need to install Python separately.

To use a fixed address without being prompted, edit the .bat file to pass the `--address` argument.

## Choosing the tunnel address

The address is written in IPv4 CIDR format: an address, a slash, and a prefix length. For example, `44.0.0.1/24`. Use the same tunnel network settings for the other devices in your radio network, assigning each device its own address.

## If it does not connect

- Make sure `direwolf.conf` is in the location described for your operating system and contains the right settings for your radio.
- By default, kissTUN looks for Dire Wolf at `127.0.0.1:8001`. If it cannot connect, it tries to start Dire Wolf automatically. On Linux and macOS, it looks for Dire Wolf on your `PATH` or in the current directory. On Windows, use the supplied `.bat` package.
- The tunnel needs administrator/root privileges. On Windows, run the `.bat` file as Administrator; on Linux, use `sudo`; on macOS, grant the requested privileges.
- If you see a message that IPv6 could not be disabled, kissTUN will still filter out IPv6 traffic.

Stop a running session with `Ctrl+C` in its terminal. For the macOS app, close or stop the app using its provided interface.
