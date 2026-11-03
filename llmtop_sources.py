"""Ollama- und Linux-Sensorquellen fuer llmtop."""
import csv
import glob
import io
import math
import os
import re
import shlex
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime
import urllib.request
import json

GPU_POWER_DISPLAY_SCALE_W = 115.0
# Reine Darstellungsskala, keine gemeldete CPU-Leistungsgrenze.
CPU_POWER_DISPLAY_SCALE_W = 65.0
VENDOR_NAMES = {
    "0x10de": "NVIDIA", "0x1002": "AMD", "0x8086": "Intel",
    "0x15ad": "VMware", "0x1af4": "Virtio",
}
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
def _read_text(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read().strip()
    except (OSError, UnicodeError):
        return None


def _read_float(path, scale=1.0):
    value = _read_text(path)
    if value is None:
        return None
    try:
        return float(value) * scale
    except ValueError:
        return None


def read_cpu_totals():
    try:
        parts = [int(v) for v in _read_text("/proc/stat").splitlines()[0].split()[1:]]
        if len(parts) < 5:
            raise ValueError("/proc/stat ohne CPU-Werte")
        return sum(parts), parts[3] + parts[4]
    except (AttributeError, IndexError, OSError, ValueError):
        return 0, 0


def cpu_percent(prev, cur):
    if not prev or not cur:
        return None
    dt = cur[0] - prev[0]
    di = cur[1] - prev[1]
    if dt <= 0:
        return None
    return max(0.0, min(100.0, 100.0 * (1.0 - di / dt)))


def loadavg():
    try:
        values = _read_text("/proc/loadavg").split()[:3]
        if len(values) == 3:
            return values
    except AttributeError:
        pass
    try:
        return [f"{value:.2f}" for value in os.getloadavg()]
    except OSError:
        return ["-", "-", "-"]


def cpu_count():
    """Liefert die für den Prozess nutzbare logische CPU-Anzahl."""
    try:
        return len(os.sched_getaffinity(0))
    except (AttributeError, OSError):
        return os.cpu_count() or 1


def cpu_name():
    """Liest den vom Kernel gemeldeten CPU-Modellnamen."""
    keys = ("model name", "Model name", "Hardware", "Processor", "cpu model")
    try:
        with open("/proc/cpuinfo", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                key, separator, value = line.partition(":")
                if separator and key.strip() in keys and value.strip():
                    name = " ".join(value.split())
                    return re.sub(r"\s+(?:w/|with)\s+Radeon\b.*$", "", name,
                                  flags=re.IGNORECASE).rstrip()
    except OSError:
        pass
    return "unbekannte CPU"


def _to_int(text):
    try:
        return int(text)
    except (TypeError, ValueError):
        return None


def _temperature_value(path):
    value = _read_float(path, 0.001)
    return value if value is not None and -100.0 <= value <= 200.0 else None


def _temperature_score(name, label):
    text = f"{name} {label}".lower()
    if name in ("k10temp", "coretemp", "zenpower", "zenpower3"):
        return 100
    if any(token in text for token in ("package", "tctl", "tdie", "cpu", "core")):
        return 80
    if any(token in text for token in ("x86_pkg", "soc_thermal", "cpu_thermal")):
        return 70
    if name in ("acpitz", "acpi_thermal_rel"):
        return 10
    return 0


def _power_value(path):
    """Liest einen hwmon-/powercap-Wert und verwirft ungültige Werte."""
    value = _read_float(path)
    return value if value is not None and value >= 0 else None


def _power_limit_watt(directory):
    """Liest die erste plausible Leistungsgrenze eines Sensorverzeichnisses."""
    paths = []
    for pattern in ("constraint*_power_limit_uw", "power*_cap", "power*_max",
                    "power*_rated_max", "power_limit_uw"):
        paths.extend(sorted(glob.glob(os.path.join(directory, pattern))))
    for path in paths:
        value = _power_value(path)
        if value is not None and value > 0:
            return value * 1e-6
    return None


def _powercap_zones():
    """Findet powercap-Zonen ohne eine feste Intel-Verzeichnisstruktur."""
    zones = []
    seen = set()
    for root in ("/sys/class/powercap", "/sys/devices/virtual/powercap"):
        if not os.path.isdir(root):
            continue
        for directory, subdirs, files in os.walk(root):
            if "energy_uj" not in files and "power_uw" not in files:
                continue
            real = os.path.realpath(directory)
            if real in seen:
                continue
            seen.add(real)
            name = _read_text(os.path.join(directory, "name")) or os.path.basename(directory)
            zones.append((directory, name))
    def priority(item):
        name = item[1].lower()
        if name == "package-0":
            return (0, name)
        if re.search(r"(?:package|socket)(?:[-_]?[0-9]+)?$", name):
            return (1, name)
        if "package" in name or "socket" in name:
            return (2, name)
        return (3, name)
    return sorted(zones, key=priority)


_CPU_POWER_SAMPLES = {}


def _counter_power(energy, timestamp, prior, maximum):
    """Berechnet Watt aus zwei monotonen Energiezählerständen."""
    if prior is None:
        return None
    old_energy, old_timestamp = prior
    elapsed = timestamp - old_timestamp
    if elapsed <= 0 or energy < 0 or old_energy < 0:
        return None
    delta = energy - old_energy
    if delta < 0:
        if maximum is None or maximum <= 0 or old_energy > maximum or energy > maximum:
            return None
        delta = (maximum - old_energy) + energy
    if delta < 0:
        return None
    watt = delta / elapsed / 1_000_000.0
    return watt if math.isfinite(watt) and watt <= 10000.0 else None


class PrivilegedRaplReader:
    """Liest RAPL-Zähler über einen ausdrücklich gestarteten Root-Helper."""

    def __init__(self, process):
        self.process = process
        self._lock = threading.Lock()
        self._latest = None
        self._sequence = 0
        self._last_sequence = 0
        self._prior = None
        self._thread = threading.Thread(target=self._read_output,
                                        name="llmtop-rapl-helper", daemon=True)

    @classmethod
    def start(cls, script_path):
        script_path = os.path.abspath(script_path)
        command = [sys.executable, script_path, "--rapl-helper"]
        if os.geteuid() != 0:
            sudo = shutil.which("sudo")
            if not sudo:
                raise OSError("sudo nicht gefunden")
            command.insert(0, sudo)
            command.insert(1, "-n")
        process = subprocess.Popen(
            command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, bufsize=1, close_fds=True)
        time.sleep(0.05)
        if process.poll() is not None:
            raise OSError("privilegierter RAPL-Helper konnte nicht gestartet werden")
        reader = cls(process)
        reader._thread.start()
        return reader

    def _read_output(self):
        try:
            for line in self.process.stdout:
                try:
                    item = json.loads(line)
                except (TypeError, ValueError):
                    continue
                if not isinstance(item, dict):
                    continue
                energy = item.get("energy_uj")
                timestamp = item.get("timestamp")
                try:
                    energy = float(energy)
                    timestamp = float(timestamp)
                except (TypeError, ValueError):
                    continue
                if not math.isfinite(energy) or not math.isfinite(timestamp) or energy < 0:
                    continue
                maximum = item.get("max_energy_range_uj")
                limit = item.get("limit_watt")
                try:
                    maximum = float(maximum) if maximum is not None else None
                    limit = float(limit) if limit is not None else None
                except (TypeError, ValueError):
                    continue
                if (maximum is not None and (not math.isfinite(maximum) or maximum <= 0) or
                        limit is not None and (not math.isfinite(limit) or limit <= 0)):
                    continue
                name = str(item.get("name") or "package-0")[:80]
                with self._lock:
                    self._sequence += 1
                    self._latest = (self._sequence, energy, timestamp, maximum, limit, name)
        except (OSError, ValueError, TypeError):
            pass

    def sample(self):
        with self._lock:
            item = self._latest
        if item is None:
            return None
        sequence, energy, timestamp, maximum, limit, name = item
        source = f"RAPL (sudo) {name}"
        if sequence == self._last_sequence:
            return {"watt": None, "limit": limit, "source": source}
        self._last_sequence = sequence
        watt = _counter_power(energy, timestamp, self._prior, maximum)
        self._prior = (energy, timestamp)
        return {"watt": watt, "limit": limit, "source": source}

    def stop(self):
        process = self.process
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=0.5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=0.5)
        try:
            process.stdout.close()
        except (AttributeError, OSError):
            pass


def run_rapl_helper(interval=0.5):
    """Gibt privilegierte RAPL-Messpunkte als JSONL aus."""
    try:
        while True:
            zones = _powercap_zones()
            record = None
            for directory, name in zones:
                energy = _power_value(os.path.join(directory, "energy_uj"))
                if energy is None:
                    continue
                maximum = _power_value(os.path.join(directory, "max_energy_range_uj"))
                record = {"timestamp": time.monotonic(), "name": name,
                          "energy_uj": energy, "max_energy_range_uj": maximum,
                          "limit_watt": _power_limit_watt(directory)}
                break
            if record is not None:
                sys.stdout.write(json.dumps(record, separators=(",", ":")) + "\n")
                sys.stdout.flush()
            time.sleep(max(0.2, float(interval)))
    except (BrokenPipeError, KeyboardInterrupt):
        return 0
    return 0


def _rapl_cpu_power():
    """Liest CPU-Package-Leistung direkt aus powercap/RAPL."""
    zones = _powercap_zones()
    for directory, name in zones:
        direct = _power_value(os.path.join(directory, "power_uw"))
        limit = _power_limit_watt(directory)
        source = f"RAPL {name}"
        if direct is not None:
            return {"watt": direct * 1e-6, "limit": limit, "source": source}
        energy = _power_value(os.path.join(directory, "energy_uj"))
        if energy is None:
            continue
        now = time.monotonic()
        key = os.path.realpath(directory)
        prior = _CPU_POWER_SAMPLES.get(key)
        _CPU_POWER_SAMPLES[key] = (energy, now)
        if prior is None:
            return {"watt": None, "limit": limit, "source": source}
        maximum = _power_value(os.path.join(directory, "max_energy_range_uj"))
        watt = _counter_power(energy, now, prior, maximum)
        return {"watt": watt, "limit": limit, "source": source}
    return None


def _hwmon_cpu_power():
    """Liest CPU-nahe hwmon-Leistung, ohne GPU-hwmon zu übernehmen."""
    gpu_words = ("amdgpu", "nvidia", "nouveau", "radeon", "gpu", "drm", "i915", "xe")
    cpu_names = ("coretemp", "k10temp", "zenpower", "zenpower3", "cpu", "package", "soc")
    candidates = []
    for hwmon in sorted(glob.glob("/sys/class/hwmon/hwmon*")):
        real = os.path.realpath(hwmon).lower()
        name = (_read_text(os.path.join(hwmon, "name")) or "").lower()
        labels = []
        for label_path in sorted(glob.glob(os.path.join(hwmon, "power*_label"))):
            label = _read_text(label_path)
            if label:
                labels.append(label.lower())
        text = " ".join((real, name, *labels))
        if any(word in text for word in gpu_words):
            continue
        explicit_cpu = (name in cpu_names or any(word in text for word in
                        ("cpu", "package", "socket", "core", "soc")))
        if not explicit_cpu:
            continue
        for pattern in ("power*_input", "power*_average"):
            for path in sorted(glob.glob(os.path.join(hwmon, pattern))):
                value = _power_value(path)
                if value is None:
                    continue
                number = re.search(r"power(\d+)_", os.path.basename(path))
                label = (_read_text(path.replace("_input", "_label").replace("_average", "_label"))
                         or (f"power{number.group(1)}" if number else "power"))
                score = 2 if name in cpu_names else 1
                candidates.append((score, value * 1e-6, _power_limit_watt(hwmon),
                                   f"hwmon {name or 'cpu'}/{label}"))
    if candidates:
        _score, watt, limit, source = max(candidates, key=lambda item: item[0])
        return {"watt": watt, "limit": limit, "source": source}
    return None


def _tcc_json_output(output):
    """Extrahiert das JSON-String-Ergebnis von busctl oder dbus-send."""
    try:
        values = shlex.split(output.strip())
    except ValueError:
        values = []
    candidates = values + [output.strip()]
    for value in candidates:
        if value.startswith("{"):
            try:
                parsed = json.loads(value)
            except (TypeError, ValueError):
                continue
            if isinstance(parsed, dict):
                return parsed
    return None


def _tcc_cpu_power():
    """Optionaler, rein lesender TUXEDO-Control-Center-Fallback."""
    service = "com.tuxedocomputers.tccd"
    path = "/com/tuxedocomputers/tccd"
    interface = service
    busctl = shutil.which("busctl")
    dbus_send = shutil.which("dbus-send")
    if not busctl and not dbus_send:
        return None
    try:
        if busctl:
            status = subprocess.run([busctl, "--system", "--no-pager", "status", service],
                                    capture_output=True, text=True, timeout=1.0)
            if status.returncode != 0:
                return None
            command = [busctl, "--system", "--no-pager", "call", service, path,
                       interface, "GetCpuPowerValuesJSON"]
        else:
            command = [dbus_send, "--system", "--print-reply", "--dest=" + service,
                       path, interface + ".GetCpuPowerValuesJSON"]
        result = subprocess.run(command, capture_output=True, text=True, timeout=1.0)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    values = _tcc_json_output(result.stdout)
    if not values:
        return None
    watt = values.get("powerDraw")
    limit = values.get("maxPowerLimit")
    try:
        watt = float(watt)
        limit = float(limit) if limit is not None else None
    except (TypeError, ValueError):
        return None
    if (not math.isfinite(watt) or watt < 0 or watt > 10000 or
            (limit is not None and (not math.isfinite(limit) or limit <= 0 or limit > 10000))):
        return None
    return {"watt": watt, "limit": limit, "source": "TCC D-Bus"}


def collect_cpu_power(privileged_reader=None):
    """Liefert CPU-Package-Power und Quelle über die definierte Fallback-Kette."""
    for reader in (_rapl_cpu_power,):
        result = reader()
        if result is not None:
            return {"watt": result.get("watt"), "limit": result.get("limit"),
                    "source": result.get("source") or "CPU-Power"}
    result = _hwmon_cpu_power()
    if result is not None:
        return {"watt": result.get("watt"), "limit": result.get("limit"),
                "source": result.get("source") or "CPU-hwmon"}
    result = _tcc_cpu_power()
    if result is not None:
        return {"watt": result.get("watt"), "limit": result.get("limit"),
                "source": result.get("source") or "TCC D-Bus"}
    if privileged_reader is not None:
        result = privileged_reader.sample()
        if result is not None:
            return {"watt": result.get("watt"), "limit": result.get("limit"),
                    "source": result.get("source") or "RAPL (sudo)"}
    return {"watt": None, "limit": None, "source": "keine CPU-Powerquelle"}


def cpu_temperature():
    """Liest CPU-Temperatur über hwmon und generische Thermal-Zones."""
    candidates = []
    for hwmon in sorted(glob.glob("/sys/class/hwmon/hwmon*")):
        name = (_read_text(os.path.join(hwmon, "name")) or "").lower()
        for path in sorted(glob.glob(os.path.join(hwmon, "temp*_input"))):
            value = _temperature_value(path)
            if value is None:
                continue
            label = _read_text(path.replace("_input", "_label"))
            label = label or os.path.basename(path).replace("_input", "")
            score = _temperature_score(name, label)
            if score:
                candidates.append((score, value, f"{name or 'hwmon'}/{label}"))
    if candidates:
        _score, value, source = max(candidates, key=lambda item: item[0])
        return value, source

    zones = []
    for zone in sorted(glob.glob("/sys/class/thermal/thermal_zone*")):
        zone_type = (_read_text(os.path.join(zone, "type")) or "").lower()
        value = _temperature_value(os.path.join(zone, "temp"))
        if value is None:
            continue
        score = _temperature_score(zone_type, "")
        if score:
            zones.append((score, value, f"thermal/{zone_type}"))
    if zones:
        _score, value, source = max(zones, key=lambda item: item[0])
        return value, source
    return None, "keine CPU-Temperaturquelle"


def _mountinfo_unescape(value):
    return re.sub(r"\\([0-7]{3})",
                  lambda match: chr(int(match.group(1), 8)), value)


def _cgroup_mounts():
    """Ermittelt cgroup-Mounts und den relativen Pfad des aktuellen Prozesses."""
    relative = {}
    for line in (_read_text("/proc/self/cgroup") or "").splitlines():
        fields = line.split(":", 2)
        if len(fields) == 3:
            controllers, path = fields[1], fields[2].lstrip("/")
            relative["v2" if not controllers else "memory"] = path
    mounts = []
    mountinfo = _read_text("/proc/self/mountinfo") or ""
    for line in mountinfo.splitlines():
        fields = line.split(" - ", 1)
        if len(fields) != 2:
            continue
        left, right = fields
        left_fields = left.split()
        right_fields = right.split()
        if len(left_fields) < 6 or len(right_fields) < 3:
            continue
        mount_point = _mountinfo_unescape(left_fields[4])
        filesystem = right_fields[0]
        options = set(left_fields[5].split(",")) | set(right_fields[2].split(","))
        kind = "v2" if filesystem == "cgroup2" else "memory" if (
            filesystem == "cgroup" and "memory" in options) else None
        if kind is not None:
            mounts.append(os.path.join(mount_point, relative.get(kind, "")))
    mounts.extend(("/sys/fs/cgroup", "/sys/fs/cgroup/memory"))
    return list(dict.fromkeys(mounts))


def _cgroup_memory(total_kb):
    """Liest eine endliche Speichergrenze des aktuellen cgroups."""
    host_bytes = total_kb * 1024
    for path in _cgroup_mounts():
        current = _read_float(os.path.join(path, "memory.current"))
        limit = _read_float(os.path.join(path, "memory.max"))
        if current is None or limit is None:
            current = _read_float(os.path.join(path, "memory.usage_in_bytes"))
            limit = _read_float(os.path.join(path, "memory.limit_in_bytes"))
        if current is None or limit is None or limit <= 0 or limit >= host_bytes * 1.5:
            continue
        current = max(0.0, min(current, limit))
        return limit / 1024.0, max(0.0, limit - current) / 1024.0
    return None


def get_ram_pct():
    """RAM % aus meminfo, bei endlichem cgroup-Limit aus dem cgroup."""
    mem = {}
    try:
        with open("/proc/meminfo", encoding="utf-8") as fh:
            for line in fh:
                key, _, rest = line.partition(":")
                parts = rest.split()
                if parts:
                    mem[key] = int(parts[0])
    except (OSError, ValueError, IndexError):
        return None, None, None
    mem_total_kb = mem.get("MemTotal")
    if not mem_total_kb:
        return None, None, None
    cgroup = _cgroup_memory(mem_total_kb)
    if cgroup:
        total_kb, available_kb = cgroup
    else:
        available_kb = mem.get("MemAvailable")
        if available_kb is None:
            available_kb = (mem.get("MemFree", 0) + mem.get("Buffers", 0) +
                            mem.get("Cached", 0) + mem.get("SReclaimable", 0) -
                            mem.get("Shmem", 0))
        available_kb = max(0.0, min(float(mem_total_kb), available_kb))
        total_kb = float(mem_total_kb)
    ram_pct = 100.0 * (total_kb - available_kb) / total_kb if total_kb else None
    return ram_pct, total_kb / 1024.0 / 1024.0, available_kb / 1024.0 / 1024.0


def _number(text):
    if text is None or text.strip() in ("", "N/A", "[N/A]"):
        return None
    try:
        return float(text.strip())
    except ValueError:
        return None


def _normalize_pci_id(value):
    value = (value or "").strip().lower()
    match = re.match(r"^(?:0x)?([0-9a-f]{4,8}):([0-9a-f]{2}):([0-9a-f]{2})\.([0-7])$", value)
    if not match:
        return value or None
    domain = int(match.group(1), 16)
    return f"{domain:04x}:{match.group(2)}:{match.group(3)}.{match.group(4)}"


def _pci_short_id(value):
    value = (value or "").strip().lower()
    if value.startswith("0x"):
        value = value[2:]
    return value.zfill(4) if re.fullmatch(r"[0-9a-f]{1,4}", value) else None


def _pci_device_name(device):
    vendor_id = _pci_short_id(_read_text(os.path.join(device, "vendor")))
    device_id = _pci_short_id(_read_text(os.path.join(device, "device")))
    if not vendor_id or not device_id:
        return None
    for database in ("/usr/share/hwdata/pci.ids", "/usr/share/misc/pci.ids",
                     "/usr/share/pci.ids"):
        try:
            with open(database, encoding="utf-8", errors="replace") as fh:
                vendor_match = False
                for line in fh:
                    if line.startswith(vendor_id + " "):
                        vendor_match = True
                    elif not line.startswith("\t") and line.strip() and not line.startswith("#"):
                        vendor_match = False
                    elif vendor_match and line.startswith("\t" + device_id + " "):
                        return line.split(None, 1)[1].strip()
        except OSError:
            continue
    return None


def _nvidia_command():
    command = shutil.which("nvidia-smi")
    if command:
        return command
    for path in ("/usr/bin/nvidia-smi", "/usr/local/bin/nvidia-smi",
                 "/opt/nvidia/bin/nvidia-smi", "/usr/lib/wsl/lib/nvidia-smi",
                 "/run/opengl-driver/bin/nvidia-smi",
                 "/run/current-system/sw/bin/nvidia-smi"):
        if os.path.isfile(path) and os.access(path, os.X_OK):
            return path
    return None


def nvidia_gpus():
    command = _nvidia_command()
    if not command:
        return []
    queries = (
        "index,name,pci.bus_id,utilization.gpu,memory.total,memory.used,power.draw,power.limit,enforced.power.limit,temperature.gpu",
        "name,utilization.gpu,memory.total,memory.used,power.draw,power.limit,enforced.power.limit,temperature.gpu",
    )
    result = None
    fields = None
    for query in queries:
        cmd = [command, f"--query-gpu={query}", "--format=csv,noheader,nounits"]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=4)
        except (OSError, subprocess.TimeoutExpired):
            return []
        if result.returncode == 0:
            fields = query.split(",")
            break
    if result is None or result.returncode != 0:
        return []

    gpus = []
    for row in csv.reader(io.StringIO(result.stdout)):
        values = [item.strip() for item in row]
        if len(values) != len(fields):
            continue
        item = dict(zip(fields, values))
        mem_total, mem_used = _to_int(item.get("memory.total")), _to_int(item.get("memory.used"))
        vram_pct = (max(0.0, min(100.0, 100.0 * mem_used / mem_total))
                    if mem_total and mem_used is not None else None)
        power_limit = _number(item.get("power.limit")) or _number(item.get("enforced.power.limit"))
        util = _to_int(item.get("utilization.gpu"))
        gpus.append({
            "name": item.get("name", "NVIDIA GPU"),
            "util": max(0, min(100, util)) if util is not None else None,
            "mem_total": mem_total, "mem_used": mem_used, "vram_pct": vram_pct,
            "power_watt": _number(item.get("power.draw")), "power_limit": power_limit,
            "temp_c": _number(item.get("temperature.gpu")),
            "temp_source": "nvidia-smi", "source": "nvidia-smi",
            "pci_id": _normalize_pci_id(item.get("pci.bus_id")), "vendor": "NVIDIA",
        })
    return gpus


def _gpu_util(device):
    direct = (os.path.join(device, "gpu_busy_percent"),
              os.path.join(device, "gt_busy_percent"),
              os.path.join(device, "busy_percent"))
    for path in direct:
        value = _to_int(_read_text(path))
        if value is not None:
            return max(0, min(100, value))
    paths = []
    for relative in ("gt/gt*/gt_busy_percent", "gt/gt*/busy_percent",
                     "gt*/gt_busy_percent", "gt*/busy_percent"):
        paths.extend(glob.glob(os.path.join(device, relative)))
    values = [_to_int(_read_text(path)) for path in sorted(set(paths))]
    values = [value for value in values if value is not None]
    if values:
        return max(0, min(100, round(sum(values) / len(values))))
    return None


def _gpu_hwmon_dirs(device):
    device_real = os.path.realpath(device)
    candidates = glob.glob("/sys/class/hwmon/hwmon*")
    candidates += glob.glob(os.path.join(device, "hwmon", "hwmon*"))
    result = []
    for path in candidates:
        real = os.path.realpath(path)
        if real == device_real or real.startswith(device_real + os.sep):
            if path not in result:
                result.append(path)
    return sorted(result)


def _gpu_hwmon_values(device):
    temp_c = temp_source = power_watt = power_limit = None
    for hwmon in _gpu_hwmon_dirs(device):
        name = _read_text(os.path.join(hwmon, "name")) or "hwmon"
        if temp_c is None:
            for path in sorted(glob.glob(os.path.join(hwmon, "temp*_input"))):
                value = _temperature_value(path)
                if value is None:
                    continue
                label = _read_text(path.replace("_input", "_label"))
                label = label or os.path.basename(path).replace("_input", "")
                temp_c, temp_source = value, f"sysfs/{name}/{label}"
                break
        power_paths = sorted(glob.glob(os.path.join(hwmon, "power*_input")))
        power_paths += sorted(glob.glob(os.path.join(hwmon, "power*_average")))
        for path in power_paths:
            value = _read_float(path, 1e-6)
            if value is None:
                continue
            power_watt = value
            number = re.search(r"power(\d+)_", os.path.basename(path))
            if number:
                prefix = os.path.join(hwmon, f"power{number.group(1)}")
                for suffix in ("_cap", "_max", "_rated_max"):
                    power_limit = _read_float(prefix + suffix, 1e-6)
                    if power_limit is not None:
                        break
            break
        if temp_c is not None and power_watt is not None:
            break
    return temp_c, temp_source, power_watt, power_limit


def _read_vram(device):
    used = _to_int(_read_text(os.path.join(device, "mem_info_vram_used")))
    total = _to_int(_read_text(os.path.join(device, "mem_info_vram_total")))
    if total is not None and total <= 0:
        total = None
    if used is not None:
        used /= 1024 * 1024
    if total is not None:
        total /= 1024 * 1024
    pct = (max(0.0, min(100.0, 100.0 * used / total))
           if total and used is not None else None)
    return used, total, pct


def sysfs_gpus():
    gpus = []
    cards = [path for path in glob.glob("/sys/class/drm/card[0-9]*")
             if re.search(r"card(\d+)$", path)]
    cards.sort(key=lambda path: int(re.search(r"card(\d+)$", path).group(1)))
    for card in cards:
        device = os.path.join(card, "device")
        if not os.path.exists(device):
            continue
        vendor_id = (_read_text(os.path.join(device, "vendor")) or "").lower()
        vendor = VENDOR_NAMES.get(vendor_id, "GPU")
        driver_path = os.path.realpath(os.path.join(device, "driver"))
        driver = os.path.basename(driver_path) if driver_path else None
        busy = _gpu_util(device)
        mem_used, mem_total, vram_pct = _read_vram(device)
        temp_c, temp_source, power_watt, power_limit = _gpu_hwmon_values(device)
        pci_id = _normalize_pci_id(os.path.basename(os.path.realpath(device)))
        pci_name = _pci_device_name(device)
        vendor_short = vendor_id[2:] if vendor_id.startswith("0x") else vendor_id
        fallback_id = ":".join(filter(None, (vendor_short,
                                                _pci_short_id(_read_text(os.path.join(device, "device"))))))
        name = (_read_text(os.path.join(device, "product_name")) or
                (f"{vendor} {pci_name}" if pci_name else None) or
                (f"{vendor} GPU ({fallback_id})" if fallback_id else f"{vendor} GPU"))
        gpus.append({
            "name": name, "util": busy, "mem_used": mem_used, "mem_total": mem_total,
            "vram_pct": vram_pct, "power_watt": power_watt, "power_limit": power_limit,
            "temp_c": temp_c, "temp_source": temp_source, "source": "sysfs",
            "pci_id": pci_id, "vendor": vendor, "driver": driver,
        })
    return gpus


def _merge_gpu(primary, fallback):
    merged = dict(fallback)
    for key, value in primary.items():
        if value is not None:
            merged[key] = value
    merged["source"] = primary.get("source") or fallback.get("source")
    return merged


def collect_gpus(use_nvidia):
    sysfs = sysfs_gpus()
    external = nvidia_gpus() if use_nvidia else []
    remaining = list(sysfs)
    gpus = []
    for item in external:
        match = None
        if item.get("pci_id"):
            match = next((candidate for candidate in remaining
                          if candidate.get("pci_id") == item["pci_id"]), None)
        if match is None:
            match = next((candidate for candidate in remaining
                          if candidate.get("vendor") == "NVIDIA"), None)
        if match is not None:
            remaining.remove(match)
            gpus.append(_merge_gpu(item, match))
        else:
            gpus.append(item)
    gpus.extend(remaining)
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


BAR_FILL_CHAR = "█"


def bar(pct, width):
    if pct is None:
        return "[" + " " * width + "]"
    n = max(0, min(width, int(round(pct * width / 100.0))))
    return "[" + BAR_FILL_CHAR * n + " " * (width - n) + "]"
