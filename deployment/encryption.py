import base64
import copy
from getpass import getpass
import json
import logging
import os
import re

from deployment.exceptions import MessageException

current_key_derivation_version = "A"
fallback_key_derivation_version = "A"


def encrypt_config_password(config, passphrase=None, verified=False):
    if passphrase is None:
        passphrase = getpass("Passphrase: ")

    verified = try_to_verify_shared_passphrase(config, passphrase, verified)

    password_encrypted, password_salt = encrypt(config.password, passphrase)
    config.password_encrypted = password_encrypted
    config.password_salt = password_salt

    if not verified:
        while True:
            passphrase = getpass("Passphrase (again): ")
            try:
                decrypt(config.password_encrypted, passphrase, config.password_salt)
                break
            except DecryptionFailedException:
                logging.warning("Verification failed. Wrong passphrase")

        encrypt_verification_material(config, passphrase)


def try_to_verify_shared_passphrase(config, passphrase, verified=False):
    shared_verify_file = config.shared_passphrase_verify_file
    if shared_verify_file:
        shared_material = load_shared_material(config)
        if shared_material:
            while True:
                try:
                    decrypt(shared_material["payload"], passphrase, shared_material["salt"])
                    verified = True
                    break
                except DecryptionFailedException:
                    logging.warning("Verification failed. Wrong passphrase?")
                    passphrase = getpass("Passphrase: ")

    return verified


def load_shared_material(config):
    shared_verify_file = config.shared_passphrase_verify_file
    if os.path.exists(shared_verify_file):
        with open(shared_verify_file, "r") as file:
            try:
                return json.load(file)
            except json.JSONDecodeError:
                return None


def encrypt_verification_material(config, passphrase):
    shared_verify_file = config.shared_passphrase_verify_file
    if shared_verify_file:
        payload, salt = encrypt("shared verification payload", passphrase)
        shared_material = {
            "payload": payload,
            "salt": salt,
        }
        save_shared_material(config, shared_material)


def save_shared_material(config, shared_material):
    shared_verify_file = config.shared_passphrase_verify_file
    directory = os.path.dirname(shared_verify_file)
    if directory and not os.path.exists(directory):
        os.makedirs(directory)
    with open(shared_verify_file, "w") as file:
        json.dump(shared_material, file, indent=True)


def save_encrypted_password(config):
    connection = {}
    data = copy.deepcopy(config.original_data)
    for name, value in data["connection"].items():
        if name == "password":
            connection[name] = None
            connection["password_encrypted"] = config.password_encrypted
            connection["password_salt"] = config.password_salt
        else:
            connection[name] = value

    data["connection"] = connection
    save_config(config, data)


def save_config(config, data):
    indent = True
    for line in config.original_contents.split("\n"):
        match = re.match(r"^(\s+)[^\s]+", line)
        if match:
            indent = match.group(1)
            break

    with open(config.file_path, "w") as file:
        json.dump(data, file, indent=indent, ensure_ascii=False)
        file.write("\n")


def decrypt_config_password(config, passphrase=None):
    while True:
        if passphrase is None:
            passphrase = getpass("Passphrase: ")
        try:
            config.password = decrypt(config.password_encrypted, passphrase, config.password_salt)
            break
        except DecryptionFailedException:
            logging.warning("Decryption failed. Wrong passphrase?")
            passphrase = None


def save_decrypted_password(config):
    data = copy.deepcopy(config.original_data)
    data["connection"]["password"] = config.password
    del data["connection"]["password_encrypted"]
    del data["connection"]["password_salt"]
    save_config(config, data)


def decrypt_passphrase_via_ssh_agent(config, ssh_key):
    from cryptography.fernet import Fernet, InvalidToken
    from paramiko import AgentKey
    from paramiko.ssh_exception import SSHException
    import paramiko.agent

    # these internal methods were extracted from paramiko.Agent and paramiko.agent.AgentSSH
    # we can't use paramiko public interface since paramiko.Agent.get_keys() doesn't include comment
    agent = paramiko.agent.AgentSSH()
    agent._conn = paramiko.agent.get_agent_connection()
    ptype, result = agent._send_message(paramiko.agent.cSSH2_AGENTC_REQUEST_IDENTITIES)
    if ptype != paramiko.agent.SSH2_AGENT_IDENTITIES_ANSWER:
        raise MessageException("ssh-agent: could not get keys, is your agent running?")

    keys = []
    matched = None
    found = []
    for i in range(result.get_int()):
        agent_key = AgentKey(agent, result.get_binary())
        agent_key.comment = result.get_string().decode("utf-8", errors="ignore")
        if ssh_key is not None and (ssh_key == agent_key.comment or ssh_key == agent_key.name):
            matched = agent_key
        found.append("name: %s, comment: %s" % (agent_key.name, agent_key.comment))
        keys.append(agent_key)
    agent_key = matched

    found.append("You can match your key either by name or comment")

    if not agent_key:
        if len(keys) == 0:
            raise MessageException("ssh-agent: no keys found, is your key loaded into your agent?")

        if ssh_key is not None:
            raise MessageException("ssh-agent: your key '%s' wasn't found, found following keys:\n%s" % (
                ssh_key, "\n".join(found)
            ))

        if len(keys) > 1:
            raise MessageException(
                "ssh-agent: you have multiple keys loaded in your agent, "
                "please specify what key to use with --ssh-key NAME_OR_COMMENT:\n%s" % "\n".join(found)
            )

        agent_key = keys[0]

    logging.info("Using your key from ssh-agent (name: %s, comment: %s)" % (agent_key.name, agent_key.comment))

    def initialize_ssh_fernet(agent_key, shared_material):
        try:
            intermediate_passphrase = base64_encode(agent_key.sign_ssh_data(shared_material["ssh_init_vector"]))
        except SSHException as e:
            raise MessageException(
                "ssh-agent: %s, wrong selected key? agent is not working properly? found following keys:\n%s" % (
                    e, "\n".join(found)
                ))

        key = derive_key(
            intermediate_passphrase, base64_decode(shared_material["ssh_init_vector"]), fallback_key_derivation_version
        )
        return Fernet(key)

    shared_material = load_shared_material(config)
    save = False
    if not shared_material or "ssh_token" not in shared_material:
        passphrase = getpass("Passphrase: ")
        verified = try_to_verify_shared_passphrase(config, passphrase)
        if not verified:
            encrypt_verification_material(config, passphrase)

        shared_material = load_shared_material(config)
        shared_material["ssh_init_vector"] = base64_encode(os.urandom(64))

        fernet = initialize_ssh_fernet(agent_key, shared_material)
        token = fernet.encrypt(passphrase.encode("utf-8"))
        shared_material["ssh_token"] = base64_encode(token)

        save = True

    fernet = initialize_ssh_fernet(agent_key, shared_material)
    try:
        passphrase = fernet.decrypt(base64_decode(shared_material["ssh_token"])).decode("utf-8")
    except InvalidToken:
        raise MessageException(
            "ssh-agent: decryption failed - unable to decrypt via ssh-agent, key changed? "
            "please select correct key or delete --shared-passphrase to create new configuration for new key, "
            "found following keys:\n%s" % (
                "\n".join(found)
            )
        )

    if save:
        save_shared_material(config, shared_material)

    return passphrase


def encrypt(payload, passphrase, salt=None):
    from cryptography.fernet import Fernet

    if salt is None:
        salt = os.urandom(16)
    key = derive_key(passphrase, salt, current_key_derivation_version)
    fernet = Fernet(key)
    token = fernet.encrypt(payload.encode("utf-8"))
    versioned_salt = "%s%s" % (current_key_derivation_version, base64_encode(salt))
    return base64_encode(token), versioned_salt


def decrypt(payload, passphrase, versioned_salt):
    from cryptography.fernet import Fernet, InvalidToken

    key_derivation_version = versioned_salt[0]
    salt = versioned_salt[1:]

    key = derive_key(passphrase, base64_decode(salt), key_derivation_version)
    fernet = Fernet(key)
    try:
        return fernet.decrypt(base64_decode(payload)).decode("utf-8")
    except InvalidToken:
        raise DecryptionFailedException("invalid token")


def derive_key(passphrase, salt, version):
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.primitives import hashes
    # derivation parameters taken from django:
    # https://github.com/django/django/blob/23e886886249ebe8f80a48b0d25fbb5308eeb06f/django/contrib/auth/hashers.py#L298
    # be careful about changing anything and make sure previous parameters are always preserved otherwise
    # all tokens will be broken
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=480000,
    )
    key = base64_encode(kdf.derive(passphrase.encode("utf-8")))
    return key


def base64_encode(payload):
    return base64.b64encode(payload).decode("utf-8")


def base64_decode(payload):
    return base64.b64decode(payload.encode("utf-8"))


class DecryptionFailedException(Exception):
    pass
