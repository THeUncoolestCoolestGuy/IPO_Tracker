# 🚀 IPO Tracker — Setup Guide for Any New Device

This tool automatically tracks Indian Mainboard IPOs on NSE & BSE every day and sends free alerts to your Telegram whenever the Grey Market Premium (**GMP**) is more than **10%**:
* **08:00 AM IST:** Morning alert with all high-GMP IPOs, prices, last filing dates, and direct **1-Click Kite App** launcher links.
* **02:30 PM IST:** Reminder alert highlighting high-GMP IPOs closing today before the 5:00 PM cut-off.

---

## 📱 1-Click Kite App Quick Apply (New Feature!)

Every alert for open IPOs includes a direct **1-Click Kite App** launcher:
```text
3. Deepa Jewellers
   • GMP: ₹28 (+15.8%)
   • Price: ₹177
   • Last Filing Date: 3 Sept ⚠️ (CLOSING TODAY!)
   • Status: OPEN
   👉 Open Kite App: https://play.google.com/store/apps/details?id=com.zerodha.kite3
```

### How to apply in 15 seconds:
1. Tap **`👉 Open Kite App`** right inside your Telegram message.
2. Tap the green **`[ Open ]`** button.
3. Your native **Kite app opens instantly** with your fingerprint / biometric unlock ready.
4. Tap **Bids** (at the bottom) ➔ **IPO** ➔ Tap **Apply** and submit your bid!
5. Approve the UPI mandate in Google Pay / PhonePe.

*(This keeps your Kite password 100% private, avoids any browser re-login, and takes under 20 seconds).*

---

## 💻 How to Set Up on a New Laptop / PC (Takes 3 Minutes)

Follow these 5 simple steps on your new device:

### Step 1: Copy the Folder
Copy the `IPO_Tracker` folder to your new computer (for example, at `D:\IPO_Tracker` or `C:\IPO_Tracker`).

---

### Step 2: Make Sure Python is Installed
1. If your new computer doesn't have Python, download and install it from [python.org](https://www.python.org/downloads/).
2. **Important:** During installation, check the box that says **"Add python.exe to PATH"**.

---

### Step 3: Install Required Packages
1. Open Command Prompt or PowerShell inside the `IPO_Tracker` folder.
2. Type this command and press Enter:
   ```cmd
   pip install -r requirements.txt
   ```

---

### Step 4: Link Your Telegram Phone(s)
1. Open Telegram on your phone and tap this link:
   👉 **[https://t.me/PaunwalaIpoAlert_bot](https://t.me/PaunwalaIpoAlert_bot)**
2. Tap **START** (or send any message like "Hi").
3. In your computer terminal, run:
   ```cmd
   python setup_telegram.py
   ```
   *Your phone is now connected! You will receive a confirmation welcome message on Telegram.*

*(Note: If a friend or family member also wants alerts on their phone, have them tap the same link and click START, then run the command again).*

---

### Step 5: Turn On Daily Automatic Runs (1-Click)
In the folder, simply **right-click and run**:
```text
setup_windows_tasks.bat
```
*(Select "Run as Administrator" if prompted)*

**That’s all!** Your computer will now automatically send the alerts to your phone every morning at **08:00 AM** and **02:30 PM IST**.

---

## 🧪 How to Test It Anytime

Want to test if messages are arriving or see live IPOs right now? Run any of these in your terminal:

* **Send live morning alert to your phone right now:**
  ```cmd
  python main.py --run-now
  ```

* **Send live 02:30 PM reminder to your phone right now:**
  ```cmd
  python main.py --run-reminder
  ```

* **See the list of all current IPOs & their GMP in terminal:**
  ```cmd
  python main.py --list
  ```

---

## ❓ Frequently Asked Questions

* **Does it work if my computer screen is locked?**
  Yes, 100%. As long as your computer is powered on, it runs in the background and sends the message.

* **What if my laptop was sleeping or closed at 8:00 AM?**
  The moment you open your laptop lid or wake it up, it automatically detects that the 8:00 AM run was missed and immediately sends the alert to your phone.

* **Is Telegram completely free?**
  Yes, 100% free forever with unlimited messages and no recharge needed.
