# DevOps CLI Agent

A local DevOps assistant powered by Ollama + qwen2.5 that runs system commands and explains the output in plain English.

## Features
- Check Docker containers, disk usage, memory, CPU, open ports and more
- Plain English interface — no need to remember commands
- LLM-powered explanations of command output
- Runs fully locally with Ollama

## Setup
```bash
python3 -m venv venv
source venv/bin/activate
pip install requests
python3 devops_cli.py
```

## Requirements
- Python 3.x
- Ollama running locally with qwen2.5:0.5b pulled
