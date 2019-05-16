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
            tar_db_folder = None
            tar_db_file = None

            if not force_dl:
                print('Looking for geolite db file', db_file)
                if file_exists(db_file):
                    print('Found geolite db file', db_file, '\n')
                    db_files.append(os.path.abspath(db_file))
                    continue

            if not file_exists(db_file):
                print('No', db_file, 'found')
            else:
                print('Forcing refresh of geolite db', db_file)
                os.remove(db_file)

            db_tar = db_url.split('/')[-1]

            print('Downloading', db_url)
            r = web_request(db_url)
            with open(db_tar, 'wb') as f:
                f.write(r.content)
            print('Finished downloading', db_tar)

            tf = tarfile.open(db_tar, 'r:gz')

            tar_file_members = tf.getmembers()
            for member in tar_file_members:
                if member.name.endswith('.mmdb'):
                    tar_db_folder= member.name.split('/', 1)[0]
                    tar_db_file = member.name.rsplit('/', 1)[-1]

            print('Extracting into', tar_db_folder)
            tf.extractall()

            print('Deleting', db_tar, 'file')
            os.remove(db_tar)

            db_file_path = os.path.join(tar_db_folder, tar_db_file)

            print('Moving', db_file_path, 'into', os.getcwd())
            shutil.move(db_file_path, os.getcwd())

            db_files.append(os.path.abspath(db_file))

            print('Deleting', tar_db_folder, 'folder')
            shutil.rmtree(tar_db_folder)
            print('DONE\n')

        return db_files
