import os
import re
import signal
import subprocess
import sys
import threading

os_win = os.name == "nt"


def hidden_startupinfo():
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags = subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = subprocess.SW_HIDE
    return startupinfo


class Process:
    encoding = "utf-8"
    encoding_errors = "strict"
    process = None
    thread = None
    data = None
    data_raw = None
    raw_lines = []
    shell = True
    hidden = True
    exception = None

    def __init__(self, command, timeout=3600, block=True, encoding=None, popen_override=None):
        self.command = command
        self.popen_override = popen_override
        self.timeout = timeout
        self.block = block
        if encoding is not None:
            self.encoding = encoding

    def execute(self, input=None, callback=None):
        self.thread = threading.Thread(target=self.target, args=(input, callback), daemon=True)
        self.thread.start()

        if self.timeout > 0:
            threading.Thread(target=self.killer, daemon=True).start()

        if self.block:
            while self.thread.is_alive():
                self.thread.join(1)
        else:
            while self.process is None and self.exception is None:
                pass

        if self.exception:
            raise self.exception

        return self

    def target(self, input, callback):
        try:
            parameters = {
                "args": self.command,
                "stdin": subprocess.PIPE,
                "stdout": subprocess.PIPE,
                "stderr": subprocess.STDOUT,
                "shell": self.shell,
            }

            if os_win:
                if self.hidden and "startupinfo" not in parameters:
                    parameters["startupinfo"] = hidden_startupinfo()
            else:
                parameters["preexec_fn"] = os.setsid

            if self.popen_override:
                if "shell" in self.popen_override:
                    self.shell = self.popen_override["shell"]
                parameters.update(self.popen_override)

            self.process = subprocess.Popen(**parameters)

            if self.block:
                if self.data is None:
                    self.data = ""

                if callback:
                    while self.process.poll() is None:
                        for line in self.process.stdout:
                            if self.encoding:
                                line = line.decode(self.encoding, errors=self.encoding_errors)
                                line = line.rstrip("\r\n")
                                self.data += line + "\n"
                                callback(line)
                            else:
                                self.data_raw += line
                                self.raw_lines.append(line)
                                callback(line)
                else:
                    (data, none) = self.process.communicate(input)
                    if data is not None:
                        if self.encoding:
                            self.data = data.decode(self.encoding, errors=self.encoding_errors)
                        else:
                            self.data_raw = data

                self.data = self.data.rstrip("\r\n")
            else:
                self.process.wait()

        except:
            self.exception = sys.exc_info()[1]

    def killer(self):
        self.thread.join(self.timeout)
        if self.thread.is_alive():
            self.kill()

    def read_lines(self):
        if self.encoding:
            if self.data is None and self.block is False:
                source = self.process.stdout.read()
                source = source.decode(self.encoding, errors=self.encoding_errors)
            else:
                source = self.data

            lines = []
            for line in source.split("\n"):
                line = line.rstrip("\r")
                lines.append(line)
            return lines

        else:
            return self.raw_lines

    def read(self):
        if self.encoding:
            return "\n".join(self.read_lines()).rstrip("\r\n")
        else:
            return self.data_raw

    def return_code(self):
        if not self.process:
            return None
        return self.process.returncode

    def pid(self):
        if not self.process:
            return None
        return self.process.pid

    def kill(self, block=True):
        if not self.process:
            return

        if self.shell:
            if os_win:
                subprocess.check_output(
                    "taskkill /t /f /pid " + str(self.process.pid), startupinfo=hidden_startupinfo()
                )
            else:
                os.killpg(os.getpgid(self.process.pid), signal.SIGKILL)
        else:
            self.process.kill()

        if block:
            self.thread.join()


_detected_encoding = None


def detect_encoding():
    global _detected_encoding

    if _detected_encoding is None:
        if os_win:
            output = subprocess.check_output("C:\\Windows\\System32\\chcp.com", startupinfo=hidden_startupinfo())
            output = output.decode("ascii", errors="ignore").strip()

            match = re.search(r":\s*([0-9]+)$", output, flags=re.I | re.M)
            if not match:
                raise ProcessException("unexpected response from chcp while detecting encoding: " + output)

            _detected_encoding = "cp" + match.group(1)
        else:
            _detected_encoding = "utf-8"

    return _detected_encoding


def execute_command(command, timeout=60, valid_codes=0):
    process = Process(command, timeout=timeout, encoding=detect_encoding()).execute()

    if not isinstance(valid_codes, list):
        valid_codes = [valid_codes]

    if process.return_code() not in valid_codes:
        raise ProcessException(
            "command " + command + " failed with code " + str(process.return_code()) +
            ", output: " + process.read()
        )

    return process


class ProcessException(Exception):
    pass
