import subprocess
import threading


class Process:
    process = None
    data = ""

    def __init__(self, command, timeout=60, encoding="utf-8"):
        self.command = command
        self.timeout = timeout
        self.encoding = encoding

    def execute(self, input=None, callback=None):
        thread = threading.Thread(target=self.target, args=(input, callback))
        thread.start()

        thread.join(self.timeout)
        if thread.is_alive():
            self.process.kill()
            thread.join()

        return self

    def target(self, input, callback):
        self.process = subprocess.Popen(
            self.command, shell=True, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT
        )

        if callback:
            while self.process.poll() is None:
                for line in self.process.stdout:
                    line = line.decode(self.encoding)
                    line = line.strip()
                    self.data += line + "\n"
                    callback(line)
        else:
            (data, none) = self.process.communicate(input)

            self.data = data.decode(self.encoding)

        self.data = self.data.strip()

    def read_lines(self):
        lines = []
        for line in self.data.split("\n"):
            line = line.strip()
            lines.append(line)
        return lines

    def read(self):
        return "\n".join(self.read_lines()).strip()

    def return_code(self):
        return self.process.returncode
