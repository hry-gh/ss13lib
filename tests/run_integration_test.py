#!/usr/bin/env python3

import json
import os
import socket
import subprocess
import sys
import time
import urllib.request

GAME_PORT = 4587
HUB_PORT = 3000
TOPIC_POLL_INTERVAL = 5

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
HUB_DIR = os.environ.get("SS13HUB_DIR", os.path.join(PROJECT_DIR, "ss13hub"))
DATABASE_URL = os.environ.get("DATABASE_URL", "postgres://ss13hub:testpassword@localhost:5432/ss13hub")
DREAMSEEKER_EXE = os.environ.get("DREAMSEEKER_EXE")
CI = os.environ.get("CI") == "true"

processes: list[subprocess.Popen] = []
failed = False


def log(msg: str):
    print(f"  {msg}", flush=True)


def section(title: str):
    if CI:
        print(f"::group::{title}", flush=True)
    else:
        print(f"\n── {title} ──", flush=True)


def end_section():
    if CI:
        print("::endgroup::", flush=True)


def passed(msg: str):
    print(f"  PASS: {msg}", flush=True)


def fail(msg: str):
    global failed
    failed = True
    print(f"::error::{msg}" if CI else f"  FAIL: {msg}", file=sys.stderr, flush=True)


def cleanup():
    for proc in processes:
        try:
            proc.terminate()
            proc.wait(timeout=5)
        except Exception:
            proc.kill()


def psql(query: str) -> str:
    result = subprocess.run(
        ["psql", DATABASE_URL, "-t", "-A", "-c", query],
        capture_output=True, text=True, timeout=10,
    )
    return result.stdout.strip()


def wait_for(description: str, check, timeout: int = 30, interval: float = 1.0):
    for _ in range(int(timeout / interval)):
        result = check()
        if result:
            return result
        time.sleep(interval)
    fail(f"Timed out waiting for: {description}")
    return None


def read_log(path: str) -> str:
    try:
        with open(path) as f:
            return f.read()
    except FileNotFoundError:
        return ""


def port_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=1):
            return True
    except OSError:
        return False


def hub_api(method: str, path: str, body: dict | None = None, token: str | None = None) -> dict | None:
    url = f"http://127.0.0.1:{HUB_PORT}{path}"
    data = json.dumps(body).encode() if body else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"SS13Auth {token}"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        log(f"Hub API {method} {path} returned {e.code}: {e.read().decode()}")
        return None


def start_hub() -> subprocess.Popen:
    section("Starting SS13Hub")

    config_path = os.path.join(SCRIPT_DIR, ".test_hub_config.toml")
    with open(config_path, "w") as f:
        f.write(f"""\
[server]
host = "127.0.0.1"
port = {HUB_PORT}

[database]
url = "{DATABASE_URL}"

[auth]
require_email_confirmation = false

[email]
provider = "log"

[topic]
poll_interval_secs = {TOPIC_POLL_INTERVAL}
query_code = "ss13hub"

[background]
cleanup_interval_secs = 3600
heartbeat_timeout_secs = 120
ip_retention_days = 14
""")

    hub_log_path = os.path.join(SCRIPT_DIR, ".hub.log")
    hub_log = open(hub_log_path, "w")
    proc = subprocess.Popen(
        [os.path.join(HUB_DIR, "target", "debug", "ss13hub")],
        env={**os.environ, "SS13HUB_CONFIG": config_path, "RUST_LOG": "ss13hub=debug,tower_http=debug"},
        stdout=hub_log, stderr=subprocess.STDOUT,
    )
    processes.append(proc)
    log(f"Hub started (PID {proc.pid})")

    def hub_ready():
        if proc.poll() is not None:
            return None
        return port_open("127.0.0.1", HUB_PORT)

    if not wait_for("hub to be ready", hub_ready, timeout=15, interval=0.5):
        log("Hub logs:")
        log(read_log(hub_log_path))
        end_section()
        sys.exit(1)

    log("Hub is ready.")
    end_section()
    return proc


def compile_game():
    section("Compiling test game")
    result = subprocess.run(
        ["DreamMaker", "testgame.dme"],
        cwd=SCRIPT_DIR, capture_output=True, text=True, timeout=60,
    )
    if result.returncode != 0 or not os.path.exists(os.path.join(SCRIPT_DIR, "testgame.dmb")):
        log(result.stdout)
        log(result.stderr)
        fail("Compilation failed")
        end_section()
        sys.exit(1)
    passed("Compilation succeeded")
    end_section()


def start_dreamdaemon() -> subprocess.Popen:
    section(f"Starting DreamDaemon on port {GAME_PORT}")
    proc = subprocess.Popen(
        ["DreamDaemon", "testgame.dmb", str(GAME_PORT), "-ports", "1-65535", "-trusted", "-close", "-logself"],
        cwd=SCRIPT_DIR, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    processes.append(proc)
    log(f"DreamDaemon started (PID {proc.pid})")

    if wait_for("DreamDaemon to listen on port", lambda: port_open("127.0.0.1", GAME_PORT), timeout=15, interval=0.5):
        passed(f"DreamDaemon is listening on port {GAME_PORT}")
        result = subprocess.run(["ss", "-tlnp", f"sport = :{GAME_PORT}"], capture_output=True, text=True)
        log(f"Socket info:\n{result.stdout}")
    else:
        fail(f"DreamDaemon never started listening on port {GAME_PORT}")

    end_section()
    return proc

def test_handshake(dd: subprocess.Popen) -> str | None:
    section("Test: Handshake")

    def server_registered():
        if dd.poll() is not None:
            fail(f"DreamDaemon exited with code {dd.returncode}")
            log("Game log:")
            log(read_log(os.path.join(SCRIPT_DIR, "testgame.log")))
            return None
        row = psql(f"SELECT id, address, port, active FROM servers WHERE port = {GAME_PORT} LIMIT 1;")
        return row if row else None

    row = wait_for("server to register via handshake", server_registered, timeout=30)
    if not row:
        log("Hub logs:")
        log(read_log(os.path.join(SCRIPT_DIR, ".hub.log")))
        end_section()
        return None

    server_id, address, port, active = row.split("|")
    log(f"server_id: {server_id}")
    log(f"address:   {address}")
    log(f"port:      {port}")
    log(f"active:    {active}")

    if active != "t":
        fail("Server not marked active")
        end_section()
        return None

    passed("Server registered and active after handshake")
    end_section()
    return server_id


def test_heartbeat(server_id: str):
    section("Test: Heartbeat")

    recent = psql(
        f"SELECT COUNT(*) FROM servers WHERE id = '{server_id}' "
        f"AND last_heartbeat > NOW() - INTERVAL '30 seconds';"
    )
    if recent != "1":
        fail("Heartbeat timestamp not recent")
        end_section()
        return

    passed("Server heartbeat is recent")
    end_section()


def test_topic_poll(server_id: str):
    section("Test: Topic poll")

    def status_populated():
        row = psql(
            f"SELECT status, last_status_update FROM servers "
            f"WHERE id = '{server_id}' AND status IS NOT NULL;"
        )
        return row if row else None

    row = wait_for(
        "hub to poll game via BYOND Topic",
        status_populated,
        timeout=TOPIC_POLL_INTERVAL + 15,
    )

    if not row:
        log("Hub logs:")
        log(read_log(os.path.join(SCRIPT_DIR, ".hub.log")))
        end_section()
        return

    status_json, last_update = row.split("|")
    log(f"last_status_update: {last_update}")

    status = json.loads(status_json)
    log(f"status: {json.dumps(status, indent=2)}")

    required_fields = ["display_name", "pop", "language"]
    missing = [f for f in required_fields if f not in status]
    if missing:
        fail(f"Topic response missing required fields: {missing}")
    else:
        passed(f"Topic response contains required fields ({', '.join(required_fields)})")
    end_section()

def test_client_auth(server_id: str):
    if not DREAMSEEKER_EXE:
        log("DREAMSEEKER_EXE not set, skipping auth test")
        return

    section("Test: Client authentication")

    reg = hub_api("POST", "/api/auth/register", {
        "username": "testuser",
        "email": "test@example.com",
        "password": "testpassword123",
    })
    if not reg:
        fail("Failed to register test user")
        end_section()
        return
    log(f"Registered user: {reg['user_id']}")

    login = hub_api("POST", "/api/auth/login", {
        "username_or_email": "testuser",
        "password": "testpassword123",
    })
    if not login:
        fail("Failed to log in")
        end_section()
        return
    token = login["token"]
    log("Logged in, got session token")

    join = hub_api("POST", "/api/session/join", {
        "server_ip": "127.0.0.1",
        "server_port": GAME_PORT,
    }, token=token)
    if not join:
        fail("Failed to get auth ticket from /api/session/join")
        end_section()
        return
    auth_ticket = join["auth_ticket"]
    log("Got auth ticket")

    connect_url = f"byond://127.0.0.1:{GAME_PORT}?auth_ticket={auth_ticket}"
    ds_log_path = os.path.join(SCRIPT_DIR, ".dreamseeker.log")
    ds_log = open(ds_log_path, "w")
    ds_proc = subprocess.Popen(
        ["xvfb-run", "-a", "wine", DREAMSEEKER_EXE, connect_url],
        stdout=ds_log, stderr=subprocess.STDOUT,
    )
    processes.append(ds_proc)
    log(f"DreamSeeker launched (PID {ds_proc.pid})")

    def ticket_consumed():
        row = psql(
            "SELECT consumed FROM auth_tickets "
            f"WHERE ticket = '{auth_ticket}';"
        )
        return row == "t"

    if wait_for("auth ticket to be consumed", ticket_consumed, timeout=30):
        passed("Auth ticket was consumed — client authenticated successfully")
    else:
        log("DreamSeeker/Wine log:")
        log(read_log(ds_log_path))
        log("Game log:")
        log(read_log(os.path.join(SCRIPT_DIR, "testgame.log")))

    ds_proc.terminate()
    end_section()


def main():
    try:
        start_hub()
        compile_game()
        dd = start_dreamdaemon()

        server_id = test_handshake(dd)
        if server_id:
            test_heartbeat(server_id)
            test_topic_poll(server_id)
            test_client_auth(server_id)

        section("Game log")
        print(read_log(os.path.join(SCRIPT_DIR, "testgame.log")))
        end_section()

        if failed:
            section("Hub log")
            print(read_log(os.path.join(SCRIPT_DIR, ".hub.log")))
            end_section()
            print("::error::Some tests failed." if CI else "\n  Some tests failed.", file=sys.stderr)
            sys.exit(1)
        else:
            print("\n  All integration tests passed.")

    finally:
        cleanup()


if __name__ == "__main__":
    main()
