import os


class InstanceLock:
    """OS releases this lock on crash; do not delete a lockfile while a process owns it."""
    def __init__(self, path):
        self.file = open(path, "a+b")
        self.file.seek(0, os.SEEK_END)
        if self.file.tell() == 0:
            self.file.write(b"0")
            self.file.flush()
        self.file.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.file.close()
            raise RuntimeError("This simulation data directory already has an active controller") from None

    def close(self):
        self.file.close()
