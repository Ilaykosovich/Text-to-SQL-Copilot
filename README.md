# LLM Orchestrator

Local LLM orchestration service built with **FastAPI**, **Ollama**, **Prometheus**, and **Grafana**.

The project provides:
- a FastAPI backend for chat and session-based history
- a simple web client (single-page)
- metrics collection via Prometheus
- dashboards and visualization via Grafana
- local LLM execution through Ollama (NOT containerized)

---

## 1. Overview

This service acts as an **LLM orchestrator**:
- manages chat sessions using `session_id`
- stores conversation history on the server
- exposes metrics for latency, throughput, and errors
- supports local development and Docker-based deployment

⚠️ **Important:**  
LLM models are executed locally via **Ollama** and **are not included in Docker**.

---

## 2. System Requirements

Required:
- **Windows / macOS / Linux**
- **Python 3.10+** (for local development)
- **Docker Desktop**
- **Internet access** (to download LLM models)

---

## 3. Ollama and LLM Setup (REQUIRED)

### 3.1 Install Ollama

Download and install Ollama from the official website:

