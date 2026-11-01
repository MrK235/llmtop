"""Ollama- und Linux-Sensorquellen fuer llmtop."""
import csv
import glob
import io
import os
import subprocess
from datetime import datetime
import urllib.request
import json

GPU_POWER_BOOST_W = 115.0
VENDOR_NAMES = {"0x10de": "NVIDIA", "0x1002": "AMD", "0x8086": "Intel"}
def http_json(host, path, timeout=2.0):
    with urllib.request.urlopen(host.rstrip("/") + path, timeout=timeout) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} liefert kein JSON-Objekt")
    return payload


def normalize_host(value):
    """Normalisiert OLLAMA_HOST und CLI-Werte auf eine API-Basisadresse."""
    host = value.strip()
    if host.startswith(":"):
        host = "localhost" + host
    if not host.startswith(("http://", "https://")):
        host = "http://" + host
    return host.rstrip("/")


def collect_ollama(host):
    st = {"ok": False, "version": None, "models": [], "error": None}
    try:
        st["version"] = http_json(host, "/api/version").get("version")
        st["ok"] = True
        models = http_json(host, "/api/ps").get("models", [])
        if not isinstance(models, list):
            raise ValueError("/api/ps liefert keine Modellliste")
        st["models"] = models
    except Exception as exc:
        st["error"] = f"{type(exc).__name__}: {exc}"
    return st
def read_cpu_totals():
    with open("/proc/stat") as fh:
        parts = [int(v) for v in fh.readline().split()[1:]]
    return sum(parts), parts[3] + parts[4]


def cpu_percent(prev, cur):
    dt = cur[0] - prev[0]
    di = cur[1] - prev[1]
    if dt <= 0:
        return None
    return max(0.0, min(100.0, 100.0 * (1.0 - di / dt)))


def loadavg():
    try:
        return open("/proc/loadavg").read().split()[:3]
    except OSError:
        return ["-", "-", "-"]


def _to_int(text):
    try:
        return int(text)
    except (TypeError, ValueError):
        return None


def cpu_temperature():
    """Liest die CPU-Temperatur aus bekannten Linux-hwmon-Treibern."""
    for hwmon in glob.glob("/sys/class/hwmon/hwmon*"):
        try:
            name = open(os.path.join(hwmon, "name")).read().strip().lower()
        except OSError:
            continue
        if name not in ("k10temp", "coretemp", "zenpower"):
            continue
        for path in sorted(glob.glob(os.path.join(hwmon, "temp*_input"))):
            try:
                value = float(open(path).read().strip()) / 1000.0
            except (OSError, ValueError):
                continue
            label_path = path.replace("_input", "_label")
            try:
                label = open(label_path).read().strip()
            except OSError:
                label = os.path.basename(path).replace("_input", "")
            return value, f"{name}/{label}"
    return None, "keine CPU-Temperaturquelle"


def get_ram_pct():
    """RAM % aus /proc/meminfo: (MemTotal - MemAvailable) / MemTotal * 100"""
    mem_total_kb = mem_available_kb = None
    try:
        with open("/proc/meminfo") as fh:
            for line in fh:
                if line.startswith("MemTotal:"):
                    mem_total_kb = int(line.split()[1])
                elif line.startswith("MemAvailable:"):
                    mem_available_kb = int(line.split()[1])
        if mem_total_kb and mem_available_kb:
            ram_pct = (mem_total_kb - mem_available_kb) / mem_total_kb * 100.0
            return ram_pct, mem_total_kb / 1024.0 / 1024.0, mem_available_kb / 1024.0 / 1024.0
    except (OSError, ValueError, IndexError):
        pass
    return None, None, None


def nvidia_gpus():
    cmd = ["nvidia-smi",
           "--query-gpu=name,utilization.gpu,memory.total,memory.used,power.draw,power.limit,enforced.power.limit,temperature.gpu",
           "--format=csv,noheader,nounits"]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=4)
    except (OSError, subprocess.TimeoutExpired):
        return []
    if res.returncode != 0:
        return []

    def number(text):
        try:
            return float(text) if text not in ("", "N/A", "[N/A]") else None
        except ValueError:
            return None

    gpus = []
    for row in csv.reader(io.StringIO(res.stdout)):
        f = [x.strip() for x in row]
        if len(f) != 8:
            continue
        mem_total, mem_used = _to_int(f[2]), _to_int(f[3])
        vram_pct = (max(0.0, min(100.0, 100.0 * mem_used / mem_total))
                    if mem_total and mem_used is not None else None)
        power_limit = number(f[5]) or number(f[6])
        util = _to_int(f[1])
        gpus.append({"name": f[0], "util": max(0, min(100, util)) if util is not None else None,
                     "mem_total": mem_total, "mem_used": mem_used,
                     "vram_pct": vram_pct, "power_watt": number(f[4]),
                     "power_limit": power_limit, "temp_c": number(f[7]),
                     "temp_source": "nvidia-smi", "source": "nvidia-smi"})
    return gpus


def sysfs_gpus():
    gpus = []
    for card in sorted(glob.glob("/sys/class/drm/card[0-9]*")):
        busy_path = os.path.join(card, "device", "gpu_busy_percent")
        if not os.path.exists(busy_path):
            continue
        try:
            busy = int(open(busy_path).read().strip())
        except (OSError, ValueError):
            continue
        vendor = "GPU"
        vfile = os.path.join(card, "device", "vendor")
        try:
            vendor = VENDOR_NAMES.get(open(vfile).read().strip().lower(), vendor)
        except OSError:
            pass

        # sysfs VRAM (MiB)
        mem_info_used = None
        mem_info_total = None
        mem_path = os.path.join(card, "device", "mem_info_vram_used")
        total_path = os.path.join(card, "device", "mem_info_vram_total")
        if os.path.exists(mem_path):
            try:
                mem_info_used = int(open(mem_path).read().strip())
            except (OSError, ValueError):
                pass
        if os.path.exists(total_path):
            try:
                mem_info_total = int(open(total_path).read().strip())
            except (OSError, ValueError):
                pass

        vram_pct = None
        if mem_info_total:
            vram_pct = (max(0.0, min(100.0, 100.0 * mem_info_used / mem_info_total))
                    if mem_info_used is not None else None)
        # sysfs liefert Bytes, die restliche Anzeige verwendet MiB.
        if mem_info_used is not None:
            mem_info_used /= 1024 * 1024
        if mem_info_total is not None:
            mem_info_total /= 1024 * 1024

        # hwmon Power für AMD/NVIDIA (sysfs unter card/*/device/hwmon*)
        power_watt = None
        power_limit = None
        temp_c = None
        temp_source = None
        hwmon_path = os.path.join(card, "device", "hwmon")
        if not hwmon_path or not os.path.isdir(hwmon_path):
            pass
        else:
            for hwmon_dir in sorted(glob.glob(os.path.join(hwmon_path, "hwmon*")), reverse=True):
                name_file = os.path.join(hwmon_dir, "name")
                if not os.path.exists(name_file):
                    continue
                try:
                    name = open(name_file).read().strip()
                except (OSError, ValueError):
                    pass
                if temp_c is None:
                    for temp_path in sorted(glob.glob(os.path.join(hwmon_dir, "temp*_input"))):
                        try:
                            temp_c = float(open(temp_path).read().strip()) / 1000.0
                        except (OSError, ValueError):
                            continue
                        label_path = temp_path.replace("_input", "_label")
                        try:
                            label = open(label_path).read().strip()
                        except OSError:
                            label = os.path.basename(temp_path).replace("_input", "")
                        temp_source = f"sysfs/{label}"
                        break
                # Suche Power-Input in diesem hwmon-Verzeichnis
                for num in range(1, 6):
                    inp_path = os.path.join(hwmon_dir, f"power{num}_input")
                    try:
                        content = open(inp_path).read().strip()
                        watt = float(content) / 1e6  # µW -> W
                        power_watt = watt
                        cap_path = os.path.join(hwmon_dir, f"power{num}_cap")
                        try:
                            power_limit = float(open(cap_path).read().strip()) / 1e6
                        except (OSError, ValueError):
                            pass
                        break
                    except (OSError, ValueError):
                        pass

        gpus.append({
            "name": f"{vendor} {os.path.basename(card)}",
            "util": max(0, min(100, busy)),
            "mem_used": mem_info_used,
            "mem_total": mem_info_total,
            "vram_pct": vram_pct,
            "power_watt": power_watt,
            "power_limit": power_limit,
            "temp_c": temp_c,
            "temp_source": temp_source,
            "source": "sysfs"
        })
    return gpus


def collect_gpus(use_nvidia):
    gpus = nvidia_gpus() if use_nvidia else []
    if not gpus:
        gpus = sysfs_gpus()
    if not gpus:
        return [], "keine GPU-Quelle gefunden"
    return gpus, None


def fmt_bytes(n):
    if n is None:
        return "-"
    step = float(n)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if step < 1024 or unit == "TiB":
            return f"{step:.1f} {unit}"
        step /= 1024.0


def model_lines(model):
    d = model.get("details") or {}
    size = max(0, model.get("size") or 0)
    vram = max(0, min(size, model.get("size_vram") or 0)) if size else 0
    offload = (100.0 * vram / size) if size else 0.0
    unload = "unload ?"
    exp = model.get("expires_at")
    if exp:
        try:
            dt = datetime.fromisoformat(exp.replace("Z", "+00:00"))
            secs = int((dt - datetime.now(dt.tzinfo)).total_seconds())
            unload = f"unload in {secs // 60}:{secs % 60:02d}" if secs >= 0 else "unload jetzt"
        except ValueError:
            pass
    line1 = (f"{model.get('name', '?')}  {d.get('parameter_size', '-')} "
             f"{d.get('quantization_level', '-')}  ctx {model.get('context_length', '-')}  "
             f"{model.get('runner', '-')}  {unload}")
    line2 = (f"Speicher {fmt_bytes(vram)} VRAM / {fmt_bytes(size)} gesamt  "
             f"GPU {offload:.0f}%  CPU {100 - offload:.0f}%")
    return [line1, line2]


def bar(pct, width):
    if pct is None:
        return "[" + " " * width + "]"
    n = max(0, min(width, int(round(pct * width / 100.0))))
    return "[" + "#" * n + " " * (width - n) + "]"
