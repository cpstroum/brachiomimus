# carpaldactyl
Experiments with an SO-101 robotic arm using LeRobot

## Finding your serial port

**Windows (PowerShell):**
```powershell
[System.IO.Ports.SerialPort]::GetPortNames()
```
Plug in the arm, run it again, and the new entry is your port (e.g. `COM3`).

**Linux:**
```bash
ls /dev/ttyUSB* /dev/ttyACM*
```
Feetech-based arms typically appear as `/dev/ttyACM0`. Run `dmesg | tail -20` if unsure.

## Wave demo

```bash
# Linux
python wave.py --port /dev/ttyACM0 --reps 3

# Windows
python wave.py --port COM3 --reps 3
```
