import requests
import subprocess
import json
import re

OLLAMA_URL = "http://172.16.18.128:11434"
MODEL = "qwen2.5:0.5b"

SYSTEM_PROMPT = """You are a DevOps agent running on a Linux machine. You help the user manage their system.

You can run shell commands by responding with:
<run>command here</run>

Rules:
- Always use <run> tags to execute commands
- Only run one command at a time
- After seeing command output, analyze it and respond helpfully
- Be concise and practical
- If a task needs multiple commands, do them one at a time
- NEVER use sudo or run commands as root
- NEVER delete files unless explicitly told to
- For sorting/organizing files, use ls, mv, mkdir — never rm
"""

BLOCKED_PATTERNS = [
    r"\bsudo\b",
    r"\brm\s+-rf\b",
    r"\brm\s+-r\b",
    r"\bdd\b",
    r"\bmkfs\b",
    r"\bshutdown\b",
    r"\breboot\b",
    r"\bchmod\s+777\b",
    r">\s*/dev/sd",
    r"\bkill\s+-9\b",
]

def is_safe_command(command):
    for pattern in BLOCKED_PATTERNS:
        if re.search(pattern, command, re.IGNORECASE):
            return False, pattern
    return True, None

def run_command(command):
    safe, reason = is_safe_command(command)
    if not safe:
        return f"⛔ Blocked: command matched safety rule '{reason}'"
    try:
        result = subprocess.run(
            command, shell=True, capture_output=True, text=True, timeout=30
        )
        output = result.stdout + result.stderr
        return output.strip() if output.strip() else "(no output)"
    except subprocess.TimeoutExpired:
        return "Command timed out after 30 seconds"
    except Exception as e:
        return f"Error: {str(e)}"

def chat(messages):
    response = requests.post(
        f"{OLLAMA_URL}/api/chat",
        json={
            "model": MODEL,
            "messages": messages,
            "stream": False,
        },
        timeout=300,
    )
    return response.json()["message"]["content"]

def extract_command(text):
    match = re.search(r"<run>(.*?)</run>", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return None

def main():
    print("🤖 DevOps Agent ready. Type your task or 'exit' to quit.\n")
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

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

        messages.append({"role": "user", "content": user_input})

        print("Agent: thinking...", end="\r")
        response = chat(messages)
        messages.append({"role": "assistant", "content": response})

        while True:
            command = extract_command(response)
            if not command:
                break

            display = re.sub(r"<run>.*?</run>", "", response, flags=re.DOTALL).strip()
            if display:
                print(f"Agent: {display}")
            print(f"$ {command}")
            output = run_command(command)
            print(f"{output}\n")

            messages.append({"role": "user", "content": f"Command output:\n{output}"})
            print("Agent: thinking...", end="\r")
            response = chat(messages)
            messages.append({"role": "assistant", "content": response})

        display = re.sub(r"<run>.*?</run>", "", response, flags=re.DOTALL).strip()
        if display:
            print(f"Agent: {display}\n")

if __name__ == "__main__":
    main()
