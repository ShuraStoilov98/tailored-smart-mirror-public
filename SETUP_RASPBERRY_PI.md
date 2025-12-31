# Raspberry Pi 4 – Setup & Development Guide (VS Code + SSH)

This guide explains how to set up a Raspberry Pi 4 for development using **SSH**, **VS Code Remote**, **Python virtual environments**, and **GitHub**.  

Purpouse is to ensure smooth collaborative work during Xmas fun build-athon.

---

## 1. Flashing the OS (one-time)

1. Install **Raspberry Pi Imager**
2. Select:
   - **OS**: Raspberry Pi OS (64-bit)
   - **Storage**: your SD card
3. Open **Advanced Options (⚙️)**:
   - Enable SSH
   - Set hostname (e.g. `raspberrypi`)
   - Set username and password
   - Configure Wi-Fi (SSID + password)
   - (Optional) Enable Raspberry Pi Connect
4. Flash the SD card, insert it into the Pi, and power it on

## NOTE: Only need to do ONCE at start OR if major issues and full reboot req.
Last done on [30/12/2025] for buildathon.

---

## 2. Find the Raspberry Pi IP address

### Option A – Router admin panel (recommended)
Locate a device named `raspberrypi` and note its IPv4 address, for example:
192.0.2.10

### NOTE: This is actual IP adress 192.0.2.10 for buildathon

### Option B – From another machine
```bash
ping raspberrypi.local
```

## 3. SSH into the Raspberry Pi (sanity check)
From your PC terminal / PowerShell:

```bash
ssh <username>@192.0.2.10
```

Example:
```bash
ssh YOUR_PI_USER@192.0.2.10
```
### Note: One above is actual credentials to be used for buildathon.

If prompted about host authenticity:

```text
Are you sure you want to continue connecting? → yes
```

## 4. VS Code Remote SSH setup
1. Install Visual Studio Code (If not already intsalled :D)
2. Install the extension Remote – SSH

Open Command Palette:

```css
Ctrl + Shift + P
```
Select:

```pgsql
Remote-SSH: Connect to Host
```
Enter:

```css
YOUR_PI_USER@192.0.2.10
Platform: Linux
```

Enter your password
### NOTE: Ask Shura for the password

➡️ A new VS Code window opens — this window runs directly on the Raspberry Pi.

## 5. System preparation (recommended)
Run once on the Raspberry Pi:
### NOTE: Do once for each new flash of the RP4 SD card - already done for buildathon 

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y git python3 python3-pip python3-venv
```

Verify:

```bash
python3 --version
git --version
```

## 6. Clone the GitHub repository
Create a workspace:
### NOTE: Do once for each new flash of the RP4 SD card - already done for buildathon 
### DO ALL OF THESE

```bash
mkdir -p ~/Desktop/projects
cd ~/Desktop/projects
```

Clone the repo:

```bash
git clone https://github.com/ShuraStoilov98/tailored-smart-mirror.git
cd tailored-smart-mirror
```

## 7. Python virtual environment (.venv)
Create the virtual environment
### NOTE: Do once for each new flash of the RP4 SD card - already done for buildathon 
```bash
python3 -m venv .venv
```

Activate (.venv) – Raspberry Pi / Linux
### NOTE: Do once at every new init of IDE to work and make changes
```bash
source .venv/bin/activate
```

Expected prompt:

```text
(.venv) username@raspberrypi:...
```

Deactivate
```bash
deactivate
```

## 8. Install Python dependencies
Upgrade pip:
### NOTE: Do once for each new flash of the RP4 SD card - already done for buildathon 

```bash
pip install --upgrade pip
```

Install project dependencies:
### NOTE: Add to requirements.txt file for traceability 

```bash
pip install -r requirements.txt
```

Freeze current environment (when needed - for now Optional - IGNORE):

```bash
pip freeze > requirements.txt
```

## 9. VS Code Python interpreter selection
Inside the SSH VS Code window:
Open Command Palette:

```css
Ctrl + Shift + P
```

Select:

```vbnet
Python: Select Interpreter
```

Choose:

```bash
.venv/bin/python
```
This ensures all scripts run inside the virtual environment.

## 10. Running scripts
Examples:

```bash
python src/camera_test.py
python src/led_test.py
```
Stop execution:

```mathematica
Copy code
Ctrl + C
```

## 11. GPIO access (hardware control)
For GPIO access without sudo, ensure your user is in the gpio group:

```bash
groups
```

If needed:

```bash
sudo usermod -aG gpio $USER
sudo reboot
```

## 12. Common troubleshooting
1. SSH host key mismatch
```bash
ssh-keygen -R 192.0.2.10
```

2. Permission denied on SSH
Verify username (not always pi)

Verify password

Ensure SSH was enabled in Raspberry Pi Imager

3. OpenCV GUI errors (cv2.imshow)
When connected via SSH, use headless capture (no GUI windows).
Save frames to disk instead of displaying them.

## 13. Recommended project structure
```css
project-root/
├── .venv/
├── requirements.txt
├── README.md
├── src/
│   ├── camera_test.py
│   ├── led_test.py
│   └── main.py
└── docs/
    └── SETUP_RASPBERRY_PI.md
```
