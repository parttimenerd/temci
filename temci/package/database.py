import os

import shutil

import subprocess

import time
import yaml
import typing as t

from temci.utils.settings import Settings
from temci.utils.typecheck import *
from temci.package.util import hashed_name_of_file, abspath
from temci.utils.util import does_command_succeed

Key = t.Union[str, 'Action']
KeySubKey = t.Tuple[Key, str]
FileId = str


class Database:
    """
    A database that can store files and other data and can be stored in a compressed archive.
    """

    entry_types = {
        "any": Dict(all_keys=False)
    }  # type: t.Dict[str, Dict]

    def __init__(self, data: t.Dict[str, t.Dict[str, Any]] = None, tmp_dir: str = None):
        self.tmp_dir = tmp_dir or os.path.join(Settings()["tmp_dir"], "package" + str(time.time()))
        if os.path.exists(self.tmp_dir):
            shutil.rmtree(self.tmp_dir)
        os.mkdir(self.tmp_dir)
        self.data_yaml_file_name = os.path.join(self.tmp_dir, "data.yaml")
        self.data = data or {}

    def __setitem__(self, key: t.Union[Key, KeySubKey], value: dict):
        key, subkey = self._key_subkey(key, normalize=False)
        key_n = self._normalize_key(key)
        if key_n not in self.data:
            #from temci.package.action import Action
            self.data[key_n] = {
                "value": {},
                "entry_type": "any"
            }
            if not isinstance(key, str):
                if key.name not in self.entry_types:
                    self.add_entry_type(key.name, key.db_entry_type)
                self.data[key_n]["entry_type"] = key.name
                if key.db_entry_type.has_default():
                    self.data[key_n]["value"] = key.db_entry_type.get_default()
        entry_type = self.entry_types[self.data[key_n]["entry_type"]]
        if subkey:
            typecheck_locals(value=entry_type[subkey])
            self.data[key_n]["value"][subkey] = value
        else:
            val = entry_type.get_default() if entry_type.has_default() else {}
            val.update(value)
            typecheck(val, entry_type)
            self.data[key_n]["value"] = val

    def __getitem__(self, key: t.Union[Key, KeySubKey]):
        key, subkey = self._key_subkey(key)
        if subkey:
            return self.data[key]["value"][subkey]
        return self.data[key]["value"]

    def store_file(self, key: Key, subkey: str, file_path: str):
        """
        Stores a file in the database and stores the files id under the passed key as an string.
        It uses the hashed (sha512 + md5) file contents as the id. A file can't be deleted by storing
        another file under the same key.
        :param key: passed key
        :param file_path: path of the file to store
        """
        file_path = abspath(file_path)
        typecheck_locals(file_path=FileName())
        file_id = hashed_name_of_file(file_path)
        shutil.copy(file_path, self._storage_filename(file_id))
        self[key, subkey] = file_id

    def retrieve_file(self, key: Key, subkey: str, destination: str):
        """
        Copies the stored file under the passed key to its new destination.
        """
        destination = abspath(destination)
        source = self._storage_filename(self[key, subkey])
        shutil.copy(source, destination)

    def _storage_filename(self, id: FileId) -> str:
        return os.path.join(self.tmp_dir, id)

    def _store_yaml(self):
        with open(self.data_yaml_file_name, "w") as f:
            yaml.dump(self.data, f)

    def _load_yaml(self):
        with open(self.data_yaml_file_name, "r") as f:
            self.data = yaml.load(f)

    def store(self, filename: str, compression_level: int = None):
        """
        Store the whole database as a compressed archive under the given file name.
        :param filename: passed file name
        :param compression_level: used compression level, from -1 (low) to -9 (high)
        """
        compression_level = compression_level or Settings()["package/compression/level"]
        self._store_yaml()
        filename = abspath(filename)
        used_prog = "gzip"
        av_programs = ["pixz", "xz"] if Settings()["package/compression/program"] == "xz" else ["pigz", "gzip"]
        for prog in av_programs:
            if does_command_succeed(prog + " --version"):
                used_prog = prog
                break
        cmd = "cd {dir}; XZ={l} GZIP={l} tar cf '{dest}' . --use-compress-program={prog}"\
            .format(l=compression_level, dest=filename, dir=self.tmp_dir, prog=used_prog)
        res = subprocess.check_output(["/bin/sh", "-c", cmd])

    def load(self, filename: str):
        """
        Load the database from the compressed achive.
        Cleans the database.
        :param filename: name of the compressed archive
        """
        os.system("tar xf '{file}' -C '{dest}'".format(file=abspath(filename), dest=self.tmp_dir))
        self.data = {}
        self._load_yaml()

    def clean(self):
        """
        Removes the used temporary directory.
        """
        shutil.rmtree(self.tmp_dir)

    @classmethod
    def _key_subkey(cls, key: KeySubKey, normalize: bool = True) -> t.Tuple[str, str]:
        def norm(key: Key):
            return cls._normalize_key(key) if normalize else key
        if isinstance(key, tuple):
            return norm(key[0]), key[1]
        return norm(key), None

    @classmethod
    def add_entry_type(cls, key: str, entry_type: Dict):
        typecheck_locals(entry_type=T(Dict))
        cls.entry_types[key] = entry_type

    @classmethod
    def _normalize_key(cls, key: Key) -> str:
        #from temci.package.action import Action
        if not isinstance(key, str):
            return key.id
        return key