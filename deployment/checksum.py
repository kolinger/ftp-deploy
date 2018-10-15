import hashlib


def sha256_checksum(file, block_size=10485760):
    hash = hashlib.sha256()
    with open(file, "rb") as file:
        for block in iter(lambda: file.read(block_size), b''):
            hash.update(block)
    return hash.hexdigest()
