USB FIX KIT — Traffic Deployer (work laptop)
=============================================

Copy this entire folder to the work laptop (USB stick, email, or inside TrafficDeployer zip).

FILES
  FIX_USB.bat         Double-click to run the fix (Administrator)
  fix_usb_ports.ps1   PowerShell engine (do not delete)
  USB_FIX_README.txt  This file

QUICK START
  1. Plug GPS or PicoCount USB into the BAD port (e.g. left side).
  2. Right-click FIX_USB.bat -> Run as administrator
     (or double-click — it will ask for admin).
  3. Say Y to remove ghost USB devices if prompted.
  4. Reboot when offered (recommended).
  5. After reboot, plug into the left port again and run FIX_USB.bat once more.
  6. Open Traffic Deployer -> Install tab -> Refresh.

CHECK ONLY (no changes)
  Open cmd in this folder:
    FIX_USB.bat diag
  Lists COM ports and USB errors without changing Windows.

WHAT IT FIXES
  - USB selective suspend (common cause of one bad port on 4 GB laptops)
  - AC power plan sleep while plugged in
  - Stale "Unknown USB Device" entries in Device Manager

WHAT IT CANNOT FIX
  - Physically broken USB port (bent pin, loose jack)
  - Missing laptop chipset drivers — download from HP/support for your model
  - Use the RIGHT USB port in the field if left still fails after reboot

LOG
  usb_fix_log_YYYYMMDD_HHMMSS.txt is created beside FIX_USB.bat.
  Copy newest log to home PC if Forge needs to review.

FROM HOME PC (optional zip)
  Double-click BUILD_USB_FIX_KIT.bat -> copy dist\USB-Fix-Kit.zip to work laptop.
