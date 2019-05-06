import os
import tarfile
import shutil
from collections import OrderedDict
from generate.http import request as web_request
from validate.file import exists as file_exists


class GeoLite:
    dbs = OrderedDict([("GeoLite2-City.mmdb",
                                "https://geolite.maxmind.com/download/geoip/database/GeoLite2-City.tar.gz"),
                               ("GeoLite2-Country.mmdb",
                                "https://geolite.maxmind.com/download/geoip/database/GeoLite2-Country.tar.gz")])

    def download_dbs(self, force_dl=False):
        db_files = []

        for db_file, db_url in self.dbs.items():
            if not force_dl:
                print('Looking for geolite db file', db_file)
                if file_exists(db_file):
                    print('Found geolite db file', db_file, '\n')
                    db_files.append(db_file)
                    continue

            if not file_exists(db_file):
                print('No', db_file, 'found')
            else:
                print('Forcing refresh of geolite db', db_file)
                os.remove(db_file)

            r = web_request(db_url)

            print('Downloading', db_url)

            db_tar = db_url.split('/')[-1]
            with open(db_tar, 'wb') as f:
                f.write(r.content)
            print('Finished downloading', db_tar)

            print('Extracting...')
            tf = tarfile.open(db_tar, 'r:gz')
            tf.extractall()

            print('Deleting', db_tar, 'file')
            os.remove(db_tar)

            target_dir = db_tar.split('.')[0]

            for root, dirs, files in os.walk('.'):
                for dir in dirs:
                    if dir.find(target_dir) != -1:
                        db_dir_path = os.path.join(root, dir)
                        print('Extracted contents into', db_dir_path)
                for fle in files:
                    if fle.find(db_file) != -1:
                        db_f_path = os.path.join(root, fle)
                        print('Moving', db_f_path, 'to current path')
                        shutil.move(db_f_path, '.')

            db_files.append(db_file)

            print('Deleting', db_dir_path, 'folder')
            shutil.rmtree(db_dir_path)
            print('DONE\n')

        return db_files