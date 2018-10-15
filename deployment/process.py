import subprocess
import threading


class Process:
    process = None
    data = ""

    def __init__(self, command, timeout=60, encoding="utf-8"):
        self.command = command
        self.timeout = timeout
        self.encoding = encoding

    def testing(self):
        pass

    def execute(self, input=None):
        thread = threading.Thread(target=self.target, args=(input,))
        thread.start()

        thread.join(self.timeout)
        if thread.is_alive():
            self.process.kill()
            thread.join()

        return self

    def target(self, input):
        self.process = subprocess.Popen(
            self.command, shell=True, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT
        )
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
