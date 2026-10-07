#!/usr/bin/env python3
"""Prepara o instala una tarea diaria. No se activa sin --instalar."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import os
import platform
import plistlib
import subprocess
import sys
import xml.etree.ElementTree as ET
from src.data.backup import ROOT, DEFAULT_BACKUP_DIR

LABEL = "com.dashboard-finance.backup"
TASK = "DashboardFinanceRespaldoDiario"


def mac_definition(python, script, logs, hour, minute):
    return {"Label": LABEL, "ProgramArguments": [python, script], "WorkingDirectory": str(ROOT), "RunAtLoad": True,
            "StartCalendarInterval": {"Hour": hour, "Minute": minute},
            "StandardOutPath": str(logs / "backup-daily.log"),
            "StandardErrorPath": str(logs / "backup-daily-errors.log")}


def windows_definition(python, script, hour, minute, username=None):
    ns = "http://schemas.microsoft.com/windows/2004/02/mit/task"
    ET.register_namespace("", ns)
    def node(parent, name, value=None):
        element = ET.SubElement(parent, "{" + ns + "}" + name)
        if value is not None:
            element.text = value
        return element
    task = ET.Element("{" + ns + "}Task", version="1.2")
    triggers = node(task, "Triggers")
    calendar = node(triggers, "CalendarTrigger")
    node(calendar, "StartBoundary", datetime.now().strftime("%Y-%m-%d") + f"T{hour:02d}:{minute:02d}:00")
    node(calendar, "Enabled", "true")
    node(node(calendar, "ScheduleByDay"), "DaysInterval", "1")
    principals = node(task, "Principals")
    principal = node(principals, "Principal")
    principal.set("id", "Author")
    account = username or (os.environ.get("USERDOMAIN", "") + "\\" + os.environ.get("USERNAME", "")).strip("\\")
    node(principal, "UserId", account)
    node(principal, "LogonType", "InteractiveToken")
    node(principal, "RunLevel", "LeastPrivilege")
    settings = node(task, "Settings")
    node(settings, "MultipleInstancesPolicy", "IgnoreNew")
    node(settings, "DisallowStartIfOnBatteries", "false")
    node(settings, "StopIfGoingOnBatteries", "false")
    node(settings, "StartWhenAvailable", "true")
    node(settings, "Enabled", "true")
    node(settings, "ExecutionTimeLimit", "PT1H")
    actions = node(task, "Actions")
    actions.set("Context", "Author")
    execution = node(actions, "Exec")
    node(execution, "Command", python)
    node(execution, "Arguments", '"' + script + '"')
    node(execution, "WorkingDirectory", str(ROOT))
    return ET.tostring(task, encoding="utf-16", xml_declaration=True)


def scheduled_arguments(hour, minute, zone, activation):
    return ["--scheduled", "--hora", f"{hour:02d}:{minute:02d}", "--zona", zone, "--activated-at", activation]


def daily_mac_definition(python, script, logs, hour, minute, zone, activation):
    definition = mac_definition(python, script, logs, hour, minute)
    definition.pop("StartCalendarInterval")
    definition["StartInterval"] = 60
    definition["ProgramArguments"] += scheduled_arguments(hour, minute, zone, activation)
    return definition


def daily_windows_definition(python, script, hour, minute, zone, activation, username=None):
    ns = "http://schemas.microsoft.com/windows/2004/02/mit/task"
    task = ET.fromstring(windows_definition(python, script, hour, minute, username))
    triggers = task.find("{" + ns + "}Triggers")
    triggers.clear()
    trigger = ET.SubElement(triggers, "{" + ns + "}TimeTrigger")
    repetition = ET.SubElement(trigger, "{" + ns + "}Repetition")
    ET.SubElement(repetition, "{" + ns + "}Interval").text = "PT1M"
    ET.SubElement(repetition, "{" + ns + "}StopAtDurationEnd").text = "false"
    ET.SubElement(trigger, "{" + ns + "}StartBoundary").text = activation
    ET.SubElement(trigger, "{" + ns + "}Enabled").text = "true"
    arguments = task.find(".//{" + ns + "}Arguments")
    arguments.text = subprocess.list2cmdline([script] + scheduled_arguments(hour, minute, zone, activation))
    return ET.tostring(task, encoding="utf-16", xml_declaration=True)


def main():
    parser = argparse.ArgumentParser(description="Preparar copia diaria en Mac o Windows; solo instalar en la máquina elegida.")
    parser.add_argument("--hora", default="21:15", help="Hora de la zona elegida (por defecto Buenos Aires)")
    parser.add_argument("--zona", default="America/Argentina/Buenos_Aires", help="Zona horaria real del horario diario")
    parser.add_argument("--instalar", action="store_true", help="Activar la tarea en ESTA máquina")
    args = parser.parse_args()
    try:
        hour, minute = [int(v) for v in args.hora.split(":")]
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise ValueError()
    except ValueError:
        parser.error("La hora debe ser HH:MM, por ejemplo 21:15.")
    directory = DEFAULT_BACKUP_DIR / "schedule"
    logs = DEFAULT_BACKUP_DIR / "logs"
    directory.mkdir(parents=True, exist_ok=True)
    logs.mkdir(parents=True, exist_ok=True)
    python = os.path.abspath(sys.executable)  # No resolver el enlace: conserva el entorno .venv.
    script = str(ROOT / "daily_run.py")  # respaldo + update + run_calc + foto del tablero
    activation = datetime.now(timezone.utc).isoformat(timespec="seconds")
    system = platform.system()
    try:
        if system == "Darwin":
            file = directory / (LABEL + ".plist")
            file.write_bytes(plistlib.dumps(daily_mac_definition(python, script, logs, hour, minute, args.zona, activation)))
            if args.instalar:
                agent = Path.home() / "Library/LaunchAgents" / file.name
                agent.parent.mkdir(parents=True, exist_ok=True)
                subprocess.run(["launchctl", "bootout", f"gui/{os.getuid()}", str(agent)], capture_output=True)
                agent.write_bytes(file.read_bytes())
                subprocess.run(["launchctl", "bootstrap", f"gui/{os.getuid()}", str(agent)], check=True, capture_output=True)
        elif system == "Windows":
            file = directory / "daily-backup.xml"
            file.write_bytes(daily_windows_definition(python, script, hour, minute, args.zona, activation))
            if args.instalar:
                subprocess.run(["schtasks", "/Create", "/TN", TASK, "/XML", str(file), "/F"], check=True)
        else:
            print("Este instalador es para Mac y Windows. Podés ejecutar backup_data.py con el programador de tu sistema.")
            return 1
    except Exception as exc:
        print(f"❌ No se pudo preparar/instalar la tarea: {exc}")
        return 1
    print(f"✅ Tarea {'instalada' if args.instalar else 'preparada, NO activada'}: {hour:02d}:{minute:02d} {args.zona}.")
    print(f"   Archivo de configuración: {file}")
    print("   La tarea corre daily_run.py: respaldo + descarga + cálculos + foto del tablero.")
    print("   Comprueba cada minuto si venció la hora diaria; solo entonces actualiza una vez. Al volver del apagado toma una foto real tardía, sin inventar las perdidas.")
    print("   Funciona sin abrir Streamlit; requiere equipo encendido y sesión de usuario iniciada.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
