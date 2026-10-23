# Keypad — Keyboard to Controller

Use your keyboard to control games that support an Xbox 360 controller. For example, you can make the **B** key press **RT** at **70% strength**.

## Get started

### 1. Download the app

Download and open [ControllerMapper.exe](./dist/ControllerMapper.exe). 

### 2. Install controller support

The app needs the **ViGEmBus** virtual controller driver to send Xbox controller inputs to games. Install [ViGEmBus](https://github.com/nefarius/ViGEmBus/releases), then open the app.

### 3. Add keys

1. Click **Add binding**.
2. Click **Press key…**, then press a key on your keyboard (for example, `B` or an arrow key).
3. Choose the controller button or movement you want that key to control.
4. For **LT** or **RT**, choose how strong the trigger should be. For example, `70%` is a partial press.
5. Click **Save** and hold your key to use the controller input.

Your bindings are saved automatically, so they will still be there next time you open the app.

## Pause or resume your bindings

- Click **Disable bindings** to pause all your keys. Click **Enable bindings** to turn them back on.
- You can also add a binding with the **Toggle bindings** action. Press its assigned key to switch your bindings on or off. This shortcut still works when bindings are paused.

## Keep the app running in the background

Clicking the window's **X** hides the app in the system tray. The app stays running and your keys continue to work.

- Double-click the gamepad icon in the tray to reopen the app.
- Right-click the icon and choose **Quit** to close the app completely.

## If something does not work

- **The game does not respond:** Make sure ViGEmBus is installed and your bindings are enabled. Some games only detect controllers when started after the virtual controller is available.
- **The app says the controller is unavailable:** Install or repair ViGEmBus, then close and reopen the app.
- **The app is still running after clicking X:** This is expected. Find its gamepad icon in the system tray, then choose **Quit** to exit.

## Optional: run or build from source

These steps are only for people who want to work on the app. Most users should use `dist/ControllerMapper.exe` instead.

You will need Windows 10 or later, Python 3.10 or later, and ViGEmBus. Open PowerShell in the project folder and run:

```powershell
py -m pip install -r requirements.txt
py main.py
```

To rebuild the one-file app:

```powershell
py -m pip install -r requirements.txt pyinstaller
py -m PyInstaller --noconfirm --clean ControllerMapper.spec
```

The rebuilt app will be in `dist/ControllerMapper.exe`.
