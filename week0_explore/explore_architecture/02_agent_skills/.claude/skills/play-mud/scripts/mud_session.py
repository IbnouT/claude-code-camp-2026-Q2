#!/usr/bin/env python3
"""Persistent MUD session manager.

Owns a single telnet connection to the MUD and exposes it through a small
control socket, so every `cmd` call talks to the SAME live game session
instead of opening a new connection per command.

Usage:
    mud_session.py start              # connect + log in, then daemonize
    mud_session.py cmd "look"         # send one command, print the response
    mud_session.py recv [--wait N]    # drain async output (combat, chat...)
    mud_session.py status             # is the session alive? last prompt?
    mud_session.py log [-n N]         # tail the full session transcript
    mud_session.py stop               # quit the game and shut down

Connection settings can be overridden with env vars:
    MUD_HOST, MUD_PORT, MUD_USER, MUD_PASS, MUD_SESSION_DIR
"""
import argparse
import codecs
import json
import os
import re
import select
import socket
import sys
import time

HOST = os.environ.get("MUD_HOST", "localhost")
PORT = int(os.environ.get("MUD_PORT", "4000"))
USER = os.environ.get("MUD_USER", "dummy")
PASSWORD = os.environ.get("MUD_PASS", "helloworld")

SESSION_DIR = os.path.expanduser(
    os.environ.get("MUD_SESSION_DIR", "~/.play_mud/%s_%d" % (HOST, PORT)))
SOCK_PATH = os.path.join(SESSION_DIR, "control.sock")
TRANSCRIPT = os.path.join(SESSION_DIR, "transcript.log")
PIDFILE = os.path.join(SESSION_DIR, "daemon.pid")
DAEMON_LOG = os.path.join(SESSION_DIR, "daemon.log")

# --- telnet protocol bytes ---
IAC, DONT, DO, WONT, WILL, SB, SE = 255, 254, 253, 252, 251, 250, 240

ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]|\x1b[()][0-9A-B]|\x1b[=>]")
# In-game prompt, e.g. "90H 100M 92V (news) > ". Fallback: buffer ends "> ".
GAME_PROMPT_RE = re.compile(r"\d+H \d+M \d+V[^\n]*>\s?$")
# CircleMUD/tbaMUD pager prompts for long output.
PAGER_RE = re.compile(
    r"(\*\*\* Press return \*\*\*|\[ Return to continue[^\]\n]*\])\s*$",
    re.IGNORECASE)


class SessionError(Exception):
    pass


class Mud:
    """One live telnet connection + cleaned-text buffer."""

    def __init__(self):
        self.sock = socket.create_connection((HOST, PORT), timeout=15)
        self.sock.setblocking(False)
        self._telnet_pending = b""
        self._decoder = codecs.getincrementaldecoder("utf-8")("replace")
        self.text = ""            # cleaned, not-yet-consumed output
        self._pager_pos = 0       # how far pager auto-continue has scanned
        self.last_prompt = ""
        self.started_at = time.time()
        self.alive = True
        self._transcript = open(TRANSCRIPT, "a")

    # -- low level ---------------------------------------------------------
    def _strip_telnet(self, data):
        """Remove telnet IAC sequences, politely refusing all options."""
        data = self._telnet_pending + data
        self._telnet_pending = b""
        out = bytearray()
        i = 0
        while i < len(data):
            b = data[i]
            if b != IAC:
                out.append(b)
                i += 1
                continue
            if i + 1 >= len(data):          # incomplete sequence: keep for later
                self._telnet_pending = data[i:]
                break
            cmd = data[i + 1]
            if cmd == IAC:                   # escaped 0xff data byte
                out.append(IAC)
                i += 2
            elif cmd in (DO, DONT, WILL, WONT):
                if i + 2 >= len(data):
                    self._telnet_pending = data[i:]
                    break
                opt = data[i + 2]
                try:
                    if cmd == DO:
                        self.sock.sendall(bytes([IAC, WONT, opt]))
                    elif cmd == WILL:
                        self.sock.sendall(bytes([IAC, DONT, opt]))
                except OSError:
                    pass
                i += 3
            elif cmd == SB:                  # subnegotiation: skip to IAC SE
                end = data.find(bytes([IAC, SE]), i + 2)
                if end == -1:
                    self._telnet_pending = data[i:]
                    break
                i = end + 2
            else:
                i += 2
        return bytes(out)

    def _clean(self, data):
        text = self._decoder.decode(self._strip_telnet(data))
        return ANSI_RE.sub("", text).replace("\r", "")

    def pump(self, wait=0.0):
        """Read whatever the MUD has sent (within `wait`s); buffer it cleaned."""
        r, _, _ = select.select([self.sock], [], [], wait)
        if not r:
            return False
        try:
            data = self.sock.recv(65536)
        except (BlockingIOError, InterruptedError):
            return False
        except OSError:
            self.alive = False
            return False
        if not data:
            self.alive = False
            return False
        cleaned = self._clean(data)
        if cleaned:
            self.text += cleaned
            self._transcript.write(cleaned)
            self._transcript.flush()
        return True

    def send_line(self, line):
        self.sock.sendall(line.encode() + b"\n")
        self._transcript.write("\n[SENT] %s\n" % line)
        self._transcript.flush()

    def consume(self):
        out, self.text = self.text, ""
        self._pager_pos = 0
        m = re.search(r"(\d+H \d+M \d+V[^\n]*>)\s?$", out)
        if m:
            self.last_prompt = m.group(1)
        return out

    # -- prompt-driven reading ---------------------------------------------
    def _auto_page(self):
        """If the pager is asking 'Press return', press it (once per prompt)."""
        m = PAGER_RE.search(self.text, self._pager_pos)
        if m:
            self._pager_pos = len(self.text)
            self.sock.sendall(b"\n")     # continue, without a [SENT] entry
            return True
        return False

    def wait_prompt(self, timeout=8.0):
        """Read until the in-game prompt is at the end of the buffer."""
        end = time.time() + timeout
        while time.time() < end:
            if GAME_PROMPT_RE.search(self.text) or self.text.endswith("> "):
                return True
            if not self.alive:
                return False
            self._auto_page()
            self.pump(0.1)
        return False

    def expect(self, pattern, timeout=15.0, label=""):
        """Read until `pattern` appears anywhere in the buffer."""
        rx = re.compile(pattern)
        end = time.time() + timeout
        while time.time() < end:
            m = rx.search(self.text)
            if m:
                return m
            if not self.alive:
                raise SessionError(
                    "Server closed the connection while waiting for %s.\n"
                    "Last output:\n%s" % (label or pattern, self.text[-500:]))
            self.pump(0.1)
        raise SessionError(
            "Timed out waiting for %s.\nLast output:\n%s"
            % (label or pattern, self.text[-500:]))

    # -- login --------------------------------------------------------------
    def login(self):
        """Drive the tbaMUD login sequence end to end; return the game intro."""
        self.expect(r"By what name", label="the name prompt")
        self.send_line(USER)
        m = self.expect(r"Password:|Did I get that right|Wrong password",
                        label="the password prompt")
        if "Did I get that right" in m.group(0):
            self.send_line("N")   # don't create a new character by accident
            raise SessionError(
                "Character %r does not exist on this server "
                "(it offered to create it; refused)." % USER)
        self.send_line(PASSWORD)
        m = self.expect(
            r"\*\*\* PRESS RETURN:|Make your choice:|Wrong password",
            label="the post-password screen")
        if "Wrong password" in m.group(0):
            raise SessionError("Wrong password for %r." % USER)
        if "PRESS RETURN" in m.group(0):
            self.send_line("")
            self.expect(r"Make your choice:", label="the main menu")
        self.send_line("1")       # menu option 1: enter the game
        if not self.wait_prompt(15):
            raise SessionError(
                "Logged in but never saw the game prompt.\nLast output:\n%s"
                % self.text[-500:])
        return self.consume()

    def close(self):
        self.alive = False
        try:
            self.sock.close()
        except OSError:
            pass
        self._transcript.write("\n[SESSION CLOSED]\n")
        self._transcript.close()


# --- daemon side ------------------------------------------------------------

def serve(mud):
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    listener.bind(SOCK_PATH)
    listener.listen(4)
    with open(PIDFILE, "w") as f:
        f.write(str(os.getpid()))
    try:
        while mud.alive:
            r, _, _ = select.select([listener, mud.sock], [], [], 1.0)
            if mud.sock in r:
                mud.pump(0)          # buffer async output (combat, chat, ...)
                mud._auto_page()
            if listener in r:
                conn, _ = listener.accept()
                try:
                    if handle(conn, mud):   # True => stop requested
                        break
                except Exception as e:      # keep the session alive on bad requests
                    try:
                        conn.sendall((json.dumps(
                            {"ok": False, "error": str(e)}) + "\n").encode())
                    except OSError:
                        pass
                finally:
                    conn.close()
    finally:
        mud.close()
        for p in (SOCK_PATH, PIDFILE):
            try:
                os.unlink(p)
            except OSError:
                pass


def handle(conn, mud):
    conn.settimeout(30)
    buf = b""
    while not buf.endswith(b"\n"):
        d = conn.recv(65536)
        if not d:
            return False
        buf += d
    req = json.loads(buf)
    op = req.get("op")

    if op == "send":
        pre = mud.consume()                       # async output queued earlier
        mud.send_line(req["line"])
        got_prompt = mud.wait_prompt(float(req.get("timeout", 8)))
        body = mud.consume()
        reply = {"ok": True, "text": pre + body, "prompt": mud.last_prompt,
                 "saw_prompt": got_prompt, "alive": mud.alive}
    elif op == "recv":
        deadline = time.time() + float(req.get("wait", 1.0))
        while time.time() < deadline and mud.alive:
            mud.pump(0.1)
            mud._auto_page()
        reply = {"ok": True, "text": mud.consume(), "prompt": mud.last_prompt,
                 "alive": mud.alive}
    elif op == "status":
        reply = {"ok": True, "alive": mud.alive, "host": HOST, "port": PORT,
                 "user": USER, "prompt": mud.last_prompt,
                 "uptime_s": round(time.time() - mud.started_at, 1),
                 "transcript": TRANSCRIPT}
    elif op == "stop":
        mud.send_line("quit")               # in-game quit drops to the menu...
        deadline = time.time() + 3
        while time.time() < deadline and mud.alive:
            mud.pump(0.1)
            if "Make your choice:" in mud.text:
                mud.send_line("0")          # ...menu option 0 disconnects cleanly
                deadline = time.time() + 2
                mud.text = mud.text.replace("Make your choice:", "", 1)
        reply = {"ok": True, "text": mud.consume()}
        conn.sendall((json.dumps(reply) + "\n").encode())
        return True
    else:
        reply = {"ok": False, "error": "unknown op %r" % op}

    conn.sendall((json.dumps(reply) + "\n").encode())
    return False


def daemonize():
    """Detach into the background; stdio goes to daemon.log."""
    if os.fork() > 0:
        return False                              # parent: keep running CLI
    os.setsid()
    devnull = os.open(os.devnull, os.O_RDONLY)
    logfd = os.open(DAEMON_LOG, os.O_WRONLY | os.O_CREAT | os.O_APPEND)
    os.dup2(devnull, 0)
    os.dup2(logfd, 1)
    os.dup2(logfd, 2)
    return True                                   # child: become the daemon


# --- client side --------------------------------------------------------------

def rpc(payload):
    c = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        c.connect(SOCK_PATH)
    except (FileNotFoundError, ConnectionRefusedError):
        sys.exit("No active MUD session. Start one with:\n"
                 "  %s start" % sys.argv[0])
    c.settimeout(float(payload.get("timeout", 8)) + 25)
    c.sendall((json.dumps(payload) + "\n").encode())
    buf = b""
    while not buf.endswith(b"\n"):
        d = c.recv(65536)
        if not d:
            break
        buf += d
    c.close()
    if not buf:
        sys.exit("Session daemon did not answer (it may have just shut down).")
    return json.loads(buf)


def session_running():
    if not os.path.exists(SOCK_PATH):
        return False
    c = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        c.connect(SOCK_PATH)
        c.close()
        return True
    except (ConnectionRefusedError, FileNotFoundError, OSError):
        os.unlink(SOCK_PATH)                      # stale socket from a dead daemon
        return False


# --- CLI ----------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="op", required=True)
    sub.add_parser("start", help="connect, log in, run session in background")
    p = sub.add_parser("cmd", help="send one game command, print the response")
    p.add_argument("words", nargs="+", help="the command, e.g.: look")
    p.add_argument("--timeout", type=float, default=8)
    p = sub.add_parser("recv", help="collect async output without sending anything")
    p.add_argument("--wait", type=float, default=1.5)
    sub.add_parser("status", help="show session state")
    p = sub.add_parser("log", help="tail the session transcript")
    p.add_argument("-n", type=int, default=40)
    sub.add_parser("stop", help="quit the game and stop the session")
    args = ap.parse_args()

    if args.op == "start":
        os.makedirs(SESSION_DIR, exist_ok=True)
        if session_running():
            sys.exit("A session is already running (use `status`, or `stop` first).")
        try:
            mud = Mud()
        except OSError as e:
            sys.exit("Cannot reach the MUD at %s:%d — is the server up? (%s)"
                     % (HOST, PORT, e))
        try:
            intro = mud.login()
        except SessionError as e:
            mud.close()
            sys.exit("Login failed: %s" % e)
        if daemonize():
            serve(mud)                            # child never returns here
            sys.exit(0)
        print(intro.rstrip())
        print("\n[session started: %s@%s:%d — transcript: %s]"
              % (USER, HOST, PORT, TRANSCRIPT))

    elif args.op == "cmd":
        r = rpc({"op": "send", "line": " ".join(args.words),
                 "timeout": args.timeout})
        print(r["text"].rstrip())
        if not r.get("saw_prompt"):
            print("[warning: no prompt within %.0fs — output may be partial; "
                  "use `recv` to collect the rest]" % args.timeout,
                  file=sys.stderr)
        if not r.get("alive"):
            print("[session ended — the server closed the connection]",
                  file=sys.stderr)

    elif args.op == "recv":
        r = rpc({"op": "recv", "wait": args.wait})
        out = r["text"].rstrip()
        print(out if out else "[no new output]")

    elif args.op == "status":
        if not session_running():
            print("No active session.")
            return
        r = rpc({"op": "status"})
        print("Session: %s@%s:%d  alive=%s  uptime=%.0fs"
              % (r["user"], r["host"], r["port"], r["alive"], r["uptime_s"]))
        print("Last prompt: %s" % (r["prompt"] or "(none yet)"))
        print("Transcript:  %s" % r["transcript"])

    elif args.op == "log":
        if not os.path.exists(TRANSCRIPT):
            sys.exit("No transcript at %s" % TRANSCRIPT)
        with open(TRANSCRIPT) as f:
            lines = f.readlines()
        sys.stdout.write("".join(lines[-args.n:]))

    elif args.op == "stop":
        r = rpc({"op": "stop", "timeout": 5})
        out = r.get("text", "").rstrip()
        if out:
            print(out)
        print("[session stopped]")


if __name__ == "__main__":
    main()
