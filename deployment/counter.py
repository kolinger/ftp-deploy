from multiprocessing import Lock


class Counter:
    total = None
    suffix = None
    suffixLength = None
    count = 1
    lock = Lock()

    def __init__(self):
        pass

    def counter(self):
        self.lock.acquire()
        count = self.count
        if count > self.total:
            count = self.total
        self.count += 1
        self.lock.release()
        return self.format(count)

    def format(self, number):
        string = str(number)
        length = len(string)
        if not self.suffix:
            self.suffix = str(self.total)
            self.suffixLength = len(self.suffix)
        return (" " * (self.suffixLength - length)) + string + " of " + self.suffix
