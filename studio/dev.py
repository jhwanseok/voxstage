"""Start the whole studio locally: Postgres (Docker), migrations, seed, backend, frontend.

    python studio/dev.py            # run until Ctrl+C
    python studio/dev.py --check    # bring everything up, probe it, shut the servers down, exit 0 or 1

Fixed ports: Postgres 5433, backend 8710, frontend 5710 (http://127.0.0.1:5710). Needs Docker, Python 3.10+, Node 20+.
"""

import os
import pathlib
import subprocess
import sys
import time
import urllib.request

STUDIO = pathlib.Path(__file__).resolve().parent
BACKEND = STUDIO / "backend"
FRONTEND = STUDIO / "frontend"
API_PORT, WEB_PORT = 8710, 5710
WIN = os.name == "nt"
VENV_PY = BACKEND / ".venv" / ("Scripts/python.exe" if WIN else "bin/python")
NPM = "npm.cmd" if WIN else "npm"


def run(cmd, cwd=None, **kw):
    print("+", " ".join(map(str, cmd)), flush=True)
    subprocess.run(cmd, cwd=cwd, check=True, **kw)


def wait_http(url: str, seconds: int = 90) -> bool:
    end = time.time() + seconds
    while time.time() < end:
        try:
            with urllib.request.urlopen(url, timeout=3) as r:
                if r.status < 500:
                    return True
        except Exception:
            time.sleep(1)
    return False


def wait_db(seconds: int = 60) -> None:
    code = ("import psycopg,sys\n"
            "psycopg.connect('postgresql://studio:studio@localhost:5433/studio', connect_timeout=2).close()")
    end = time.time() + seconds
    while time.time() < end:
        if subprocess.run([str(VENV_PY), "-c", code], capture_output=True).returncode == 0:
            return
        time.sleep(1)
    sys.exit("Postgres did not come up on localhost:5433")


def main() -> int:
    check = "--check" in sys.argv
    run(["docker", "compose", "-f", str(STUDIO / "docker-compose.yml"), "up", "-d"])
    if not VENV_PY.exists():
        run([sys.executable, "-m", "venv", str(BACKEND / ".venv")])
        run([str(VENV_PY), "-m", "pip", "install", "-q", "-e", str(STUDIO.parent), "-e", f"{BACKEND}[test]"])
    wait_db()
    run([str(VENV_PY), "-m", "alembic", "upgrade", "head"], cwd=BACKEND)
    run([str(VENV_PY), "-m", "studio_backend.seed"], cwd=BACKEND)
    if not (FRONTEND / "node_modules").exists():
        run([NPM, "install", "--no-audit", "--no-fund"], cwd=FRONTEND)

    env = {**os.environ, "STUDIO_API_PORT": str(API_PORT)}
    procs = [
        subprocess.Popen([str(VENV_PY), "-m", "uvicorn", "studio_backend.main:app", "--host", "127.0.0.1",
                          "--port", str(API_PORT)], cwd=BACKEND, env=env),
        subprocess.Popen([NPM, "run", "dev", "--", "--host", "127.0.0.1", "--port", str(WEB_PORT), "--strictPort"],
                         cwd=FRONTEND, env=env),
    ]
    ok = False
    try:
        api_up = wait_http(f"http://127.0.0.1:{API_PORT}/api/v1/bots")
        web_up = wait_http(f"http://127.0.0.1:{WEB_PORT}/")
        ok = api_up and web_up
        print(f"\nbackend  http://127.0.0.1:{API_PORT}/api/v1/bots  {'up' if api_up else 'DOWN'}")
        print(f"frontend http://127.0.0.1:{WEB_PORT}/               {'up' if web_up else 'DOWN'}\n", flush=True)
        if check:
            with urllib.request.urlopen(f"http://127.0.0.1:{WEB_PORT}/api/v1/bots", timeout=5) as r:   # via the proxy
                bots = r.read().decode()
            ok = ok and '"bank-en"' in bots
            print("proxy /api/v1/bots ->", "ok, bots seeded" if '"bank-en"' in bots else "no bots")
            return 0 if ok else 1
        print("Open the frontend URL. Ctrl+C stops the servers (Postgres keeps running).", flush=True)
        for p in procs:
            p.wait()
    except KeyboardInterrupt:
        pass
    finally:
        for p in procs:
            if p.poll() is None:
                if WIN:
                    subprocess.run(["taskkill", "/F", "/T", "/PID", str(p.pid)], capture_output=True)
                else:
                    p.terminate()
    return 0 if ok or not check else 1


if __name__ == "__main__":
    sys.exit(main())
