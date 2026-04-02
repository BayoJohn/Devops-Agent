#!/usr/bin/env python3
import requests
import subprocess
import sys
import re

OLLAMA_URL = "http://172.16.18.128:11434"
MODEL = "qwen2.5:0.5b"

# Intent map: keyword patterns → shell commands
INTENTS = [
    (r"docker|container", "docker ps -a --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'"),
    (r"disk|storage|space",  "df -h --output=source,size,used,avail,pcent,target | head -20"),
    (r"memory|ram",          "free -h"),
    (r"cpu|process|top",     "ps aux --sort=-%cpu | head -15"),
    (r"port|listen|network", "ss -tlnp"),
    (r"uptime|load",         "uptime && echo '' && cat /proc/loadavg"),
    (r"system|info|os",      "uname -a && cat /etc/os-release | head -5"),
    (r"log.*docker|docker.*log", "docker ps --format '{{.Names}}' | head -5 | xargs -I{} docker logs --tail 20 {}"),
    (r"ip|address",          "ip addr show | grep 'inet '"),
    (r"service|running",     "systemctl list-units --type=service --state=running | head -20"),
    (r"temperature|temp",    "cat /sys/class/thermal/thermal_zone*/temp 2>/dev/null | awk '{print $1/1000\"°C\"}' || echo 'No temp sensor found'"),
    (r"who|user|login",      "w && echo '' && last | head -5"),
    (r"file|dir|folder|ls",  "ls -lah ."),
    (r"env|variable",        "env | sort"),
    (r"cron|schedule",       "crontab -l 2>/dev/null || echo 'No crontab'"),
]

HELP_TEXT = """
🤖 DevOps CLI — Commands you can ask:

  docker / containers     → show running containers
  disk / space / storage  → disk usage
  memory / ram            → RAM usage
  cpu / processes / top   → top processes
  ports / network         → open ports
  uptime / load           → system load
  system / info / os      → OS info
  docker logs             → recent container logs
  ip / address            → network interfaces
  services / running      → systemd services
  temperature / temp      → CPU temperature
  who / users / login     → logged in users
  files / ls              → list current directory
  env / variables         → environment variables
  cron / schedule         → crontab

Type 'exit' to quit.
"""

def run_command(cmd):
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=15
        )
        output = result.stdout + result.stderr
        return output.strip() if output.strip() else "(no output)"
    except subprocess.TimeoutExpired:
        return "Command timed out"
    except Exception as e:
        return f"Error: {e}"

def match_intent(user_input):
    text = user_input.lower()
    for pattern, command in INTENTS:
        if re.search(pattern, text):
            return command
    return None

def explain(user_input, command, output):
    prompt = f"""The user asked: "{user_input}"
We ran: {command}
Output:
{output[:1000]}

Give a short, clear summary of what this output means. Be concise - 2-3 sentences max."""

    try:
        resp = requests.post(
            f"{OLLAMA_URL}/api/chat",
            json={
                "model": MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
            },
            timeout=60,
        )
        return resp.json()["message"]["content"].strip()
    except Exception as e:
        return f"(could not get explanation: {e})"

def main():
    print("🤖 DevOps CLI ready. Type 'help' for commands or 'exit' to quit.\n")

    while True:
        try:
            user_input = input("You: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nBye!")
            break

        if not user_input:
            continue
        if user_input.lower() in ("exit", "quit"):
            print("Bye!")
            break
        if user_input.lower() in ("help", "?"):
            print(HELP_TEXT)
            continue

        command = match_intent(user_input)
        if not command:
            print("🤷 I don't know how to handle that yet. Type 'help' for a list of commands.\n")
            continue

        print(f"$ {command}")
        output = run_command(command)
        print(f"\n{output}\n")
        print("Explaining...", end="\r")
        explanation = explain(user_input, command, output)
        print(f"💡 {explanation}\n")

if __name__ == "__main__":
    main()
