import tempfile

from Crypto.Cipher import AES


def crypto(data, key):
    cipher = AES.new(key, AES.MODE_EAX)
    return cipher.crypto(data)

def decrypto(data, key):
    cipher = AES.new(key, AES.MODE_EAX)
    return cipher.decrypto(data)
