#!/usr/bin/env python3
import requests
import subprocess
import re

OLLAMA_URL = "http://172.16.18.128:11434"
MODEL = "qwen2.5:0.5b"

ALERT_CPU_PERCENT = 80
ALERT_MEM_PERCENT = 85
ALERT_DISK_PERCENT = 90

RED    = "\033[91m"
GREEN  = "\033[92m"
YELLOW = "\033[93m"
BLUE   = "\033[94m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

INTENTS = [
    (r"docker|container",        "docker ps -a --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'"),
    (r"disk|storage|space",      "df -h --output=source,size,used,avail,pcent,target | head -20"),
    (r"memory|ram",              "free -h"),
    (r"cpu|process|top",         "ps aux --sort=-%cpu | head -15"),
    (r"port|listen|network",     "ss -tlnp"),
    (r"uptime|load",             "uptime && echo '' && cat /proc/loadavg"),
    (r"system|info|os",          "uname -a && cat /etc/os-release | head -5"),
    (r"log.*docker|docker.*log", "docker ps --format '{{.Names}}' | xargs -I{} sh -c 'echo \"=== {} ===\"; docker logs --tail 10 {}'"),
    (r"ip|address",              "ip addr show | grep 'inet '"),
    (r"service|running",         "systemctl list-units --type=service --state=running | head -20"),
    (r"temp",                    "cat /sys/class/thermal/thermal_zone*/temp 2>/dev/null | awk '{print \$1/1000\"°C\"}' || echo 'No sensor'"),
    (r"who|user|login",          "w && echo '' && last | head -5"),
    (r"file|dir|folder|ls",      "ls -lah ."),
    (r"env|variable",            "env | sort"),
    (r"cron|schedule",           "crontab -l 2>/dev/null || echo 'No crontab'"),
    (r"pod|pods",                "kubectl get pods -A"),
    (r"node|nodes",              "kubectl get nodes -o wide"),
    (r"namespace",               "kubectl get namespaces"),
    (r"deployment|deploy",       "kubectl get deployments -A"),
    (r"svc|service.*k8s|k8s.*service", "kubectl get svc -A"),
    (r"ingress",                 "kubectl get ingress -A"),
    (r"event|events",            "kubectl get events -A --sort-by='.lastTimestamp' | tail -20"),
    (r"pvc|volume",              "kubectl get pvc -A"),
    (r"cluster|k3s|k8s",        "kubectl cluster-info && echo '' && kubectl get nodes"),
    (r"log.*pod|pod.*log",       "kubectl get pods -A --no-headers | awk '{print \$1, \$2}' | head -5 | xargs -n2 sh -c 'echo \"=== \$0/\$1 ===\"; kubectl logs --tail=10 -n \$0 \$1 2>/dev/null'"),
]

def run_command(cmd):
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=20)
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
    prompt = f"""User asked: "{user_input}"
Command run: {command}
Output:
{output[:800]}
Summarize what this output means in 2-3 sentences."""
    try:
        resp = requests.post(
            f"{OLLAMA_URL}/api/chat",
            json={"model": MODEL, "messages": [{"role": "user", "content": prompt}], "stream": False},
            timeout=60,
        )
        return resp.json()["message"]["content"].strip()
    except Exception as e:
        return f"(explanation unavailable: {e})"

def health_check():
    print(f"\n{BOLD}{'='*52}{RESET}")
    print(f"{BOLD}   🏥 System + Cluster Health Check{RESET}")
    print(f"{BOLD}{'='*52}{RESET}\n")
    alerts = []
    score = 100

    cpu_out = run_command("top -bn1 | grep 'Cpu(s)'")
    cpu_match = re.search(r"(\d+\.?\d*)\s*id", cpu_out)
    if cpu_match:
        cpu_used = round(100 - float(cpu_match.group(1)), 1)
        color = RED if cpu_used > ALERT_CPU_PERCENT else YELLOW if cpu_used > 60 else GREEN
        status = "⚠️  HIGH" if cpu_used > ALERT_CPU_PERCENT else "✅ OK"
        print(f"  CPU Usage:      {color}{cpu_used}%{RESET}  {status}")
        if cpu_used > ALERT_CPU_PERCENT:
            alerts.append(f"CPU is high: {cpu_used}%")
            score -= 20
    else:
        print(f"  CPU Usage:      {YELLOW}unknown{RESET}")

    mem_out = run_command("free | grep Mem")
    mem_match = re.search(r"Mem:\s+(\d+)\s+(\d+)", mem_out)
    if mem_match:
        mem_pct = round(int(mem_match.group(2)) / int(mem_match.group(1)) * 100, 1)
        color = RED if mem_pct > ALERT_MEM_PERCENT else YELLOW if mem_pct > 70 else GREEN
        status = "⚠️  HIGH" if mem_pct > ALERT_MEM_PERCENT else "✅ OK"
        print(f"  Memory Usage:   {color}{mem_pct}%{RESET}  {status}")
        if mem_pct > ALERT_MEM_PERCENT:
            alerts.append(f"Memory is high: {mem_pct}%")
            score -= 20

    disk_out = run_command("df / --output=pcent | tail -1")
    disk_match = re.search(r"(\d+)", disk_out)
    if disk_match:
        disk_pct = int(disk_match.group(1))
        color = RED if disk_pct > ALERT_DISK_PERCENT else YELLOW if disk_pct > 75 else GREEN
        status = "⚠️  HIGH" if disk_pct > ALERT_DISK_PERCENT else "✅ OK"
        print(f"  Disk Usage:     {color}{disk_pct}%{RESET}  {status}")
        if disk_pct > ALERT_DISK_PERCENT:
            alerts.append(f"Disk is critical: {disk_pct}%")
            score -= 20

    running = run_command("docker ps -q | wc -l").strip()
    total = run_command("docker ps -aq | wc -l").strip()
    print(f"  Docker:         {GREEN}{running} running{RESET} / {total} total  ✅")

    print(f"\n  {BOLD}Kubernetes:{RESET}")
    nodes_out = run_command("kubectl get nodes --no-headers 2>/dev/null")
    if not nodes_out or "error" in nodes_out.lower():
        print(f"  Nodes:          {YELLOW}unreachable{RESET}")
    elif "NotReady" in nodes_out:
        print(f"  Nodes:          {RED}⚠️  Some nodes NotReady{RESET}")
        alerts.append("Kubernetes node(s) NotReady")
        score -= 25
    else:
        count = len(nodes_out.strip().split("\n"))
        print(f"  Nodes:          {GREEN}✅ {count} Ready{RESET}")

    pods_out = run_command("kubectl get pods -A --no-headers 2>/dev/null")
    if pods_out and "error" not in pods_out.lower():
        all_pods = pods_out.strip().split("\n")
        bad = [l for l in all_pods if l and not re.search(r"Running|Completed", l)]
        if bad:
            print(f"  Pods:           {YELLOW}⚠️  {len(bad)} not Running{RESET}")
            for p in bad[:3]:
                print(f"                  {YELLOW}{p.strip()}{RESET}")
            alerts.append(f"{len(bad)} pods not Running")
            score -= 15
        else:
            print(f"  Pods:           {GREEN}✅ {len(all_pods)} Running{RESET}")
    else:
        print(f"  Pods:           {YELLOW}unreachable{RESET}")

    score = max(0, score)
    color = GREEN if score >= 80 else YELLOW if score >= 50 else RED
    label = "HEALTHY" if score >= 80 else "DEGRADED" if score >= 50 else "CRITICAL"
    print(f"\n{BOLD}{'='*52}{RESET}")
    print(f"  Health Score:   {color}{BOLD}{score}/100 — {label}{RESET}")
    if alerts:
        print(f"\n  {RED}{BOLD}🚨 Alerts:{RESET}")
        for a in alerts:
            print(f"  {RED}• {a}{RESET}")
    else:
        print(f"\n  {GREEN}✅ All clear!{RESET}")
    print(f"{BOLD}{'='*52}{RESET}\n")

def main():
    print(f"{BOLD}🤖 DevOps CLI v2{RESET} — Type 'help' or 'health' to start.\n")
    while True:
        try:
            user_input = input(f"{BOLD}You:{RESET} ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nBye!")
            break
        if not user_input:
            continue
        if user_input.lower() in ("exit", "quit"):
            print("Bye!")
            break
        if user_input.lower() in ("help", "?"):
            print("\nType: health, pods, nodes, docker, disk, memory, cpu, ports, uptime, events\n")
            continue
        if re.search(r"health|status", user_input.lower()):
            health_check()
            continue
        command = match_intent(user_input)
        if not command:
            print(f"{YELLOW}🤷 Unknown. Type 'help' for options.{RESET}\n")
            continue
        print(f"{BLUE}$ {command}{RESET}")
        output = run_command(command)
        print(f"\n{output}\n")
        print(f"{YELLOW}Explaining...{RESET}", end="\r")
        explanation = explain(user_input, command, output)
        print(f"{GREEN}💡 {explanation}{RESET}\n")

if __name__ == "__main__":
    main()