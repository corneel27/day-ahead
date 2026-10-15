"""Exercise native dependencies and a real debugger breakpoint on the selected Python."""

import argparse
import importlib
import json
import queue
import socket
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path


def verify_debugger():
    with tempfile.TemporaryDirectory(prefix="dao-debugger-") as directory:
        target = Path(directory) / "breakpoint_probe.py"
        target.write_text("value = 40\nvalue += 2\nprint(value, flush=True)\n")
        output_path = Path(directory) / "debugger.log"
        output_file = output_path.open("w")
        with socket.socket() as reservation:
            reservation.bind(("127.0.0.1", 0))
            port = reservation.getsockname()[1]
        process = subprocess.Popen(
            [sys.executable, "-m", "debugpy", "--listen", f"127.0.0.1:{port}",
             "--wait-for-client", str(target)],
            stdout=output_file, stderr=subprocess.STDOUT, text=True,
        )
        connection = None
        stream = None
        reader = None
        messages = queue.Queue()
        pending = []
        sequence = 0
        try:
            deadline = time.monotonic() + 30
            while connection is None:
                if process.poll() is not None:
                    raise AssertionError(output_path.read_text())
                try:
                    connection = socket.create_connection(("127.0.0.1", port), timeout=0.2)
                except OSError:
                    if time.monotonic() >= deadline:
                        raise TimeoutError("Debugger did not start") from None
                    time.sleep(0.1)
            connection.settimeout(None)
            stream = connection.makefile("rb")

            def receive():
                try:
                    while True:
                        headers = {}
                        while (line := stream.readline()) not in (b"\r\n", b""):
                            name, value = line.decode().split(":", 1)
                            headers[name.lower()] = value.strip()
                        if not headers:
                            return
                        messages.put(json.loads(stream.read(int(headers["content-length"]))))
                except (OSError, ValueError) as error:
                    messages.put({"reader_error": str(error)})

            reader = threading.Thread(target=receive, daemon=True)
            reader.start()

            def send(command, arguments):
                nonlocal sequence
                sequence += 1
                payload = json.dumps({"seq": sequence, "type": "request",
                                      "command": command, "arguments": arguments}).encode()
                connection.sendall(f"Content-Length: {len(payload)}\r\n\r\n".encode() + payload)
                return sequence

            def wait(predicate):
                for index, message in enumerate(pending):
                    if predicate(message):
                        return pending.pop(index)
                deadline = time.monotonic() + 30
                while True:
                    message = messages.get(timeout=max(0.01, deadline - time.monotonic()))
                    assert "reader_error" not in message, message
                    if predicate(message):
                        return message
                    pending.append(message)

            def response(identifier):
                result = wait(lambda message: message.get("request_seq") == identifier)
                assert result.get("success"), result
                return result.get("body", {})

            response(send("initialize", {"adapterID": "python", "pathFormat": "path",
                                         "linesStartAt1": True, "columnsStartAt1": True}))
            attached = send("attach", {"justMyCode": False})
            wait(lambda message: message.get("event") == "initialized")
            breakpoints = response(send("setBreakpoints", {"source": {"path": str(target)},
                                                         "breakpoints": [{"line": 2}]}))
            assert breakpoints["breakpoints"][0]["verified"], breakpoints
            response(send("configurationDone", {}))
            response(attached)
            stopped = wait(lambda message: message.get("event") == "stopped")["body"]
            assert stopped["reason"] == "breakpoint", stopped
            stack = response(send("stackTrace", {"threadId": stopped["threadId"]}))
            frame = stack["stackFrames"][0]
            assert frame["line"] == 2, frame
            value = response(send("evaluate", {"frameId": frame["id"],
                                               "expression": "value", "context": "watch"}))
            assert value["result"] == "40", value
            response(send("continue", {"threadId": stopped["threadId"]}))
            deadline = time.monotonic() + 30
            while "42" not in output_path.read_text().splitlines():
                if time.monotonic() >= deadline:
                    raise TimeoutError(f"Target did not resume: {pending}")
                time.sleep(0.1)
            response(send("disconnect", {"terminateDebuggee": False}))
            process.wait(timeout=30)
            output = output_path.read_text()
            assert process.returncode == 0 and "42" in output.splitlines(), output
            print("Debugger attach, breakpoint, variable inspection and resume passed.")
        finally:
            if process.poll() is None:
                process.kill()
            process.wait(timeout=10)
            if connection is not None:
                try:
                    connection.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                connection.close()
            if reader is not None:
                reader.join(timeout=2)
            if stream is not None:
                stream.close()
            output_file.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-python")
    arguments = parser.parse_args()
    actual = f"{sys.version_info.major}.{sys.version_info.minor}"
    if arguments.expected_python:
        assert actual == arguments.expected_python, (actual, arguments.expected_python)
    for name in ("numpy", "pandas", "pydantic", "pydantic_core", "mariadb", "MySQLdb",
                 "psycopg2", "mip", "scipy", "sklearn", "xgboost", "debugpy"):
        importlib.import_module(name)
    print(f"Native dependency imports passed on Python {actual}.")
    verify_debugger()


if __name__ == "__main__":
    main()
