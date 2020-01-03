#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Apple Photos Export

This Python script is exporting photos from Apple Photos application and placing copies in a directory
structure according to the album folders you have created inside the Photos.

--- License ---

This program is free software: you can redistribute it and/or modify it under
the terms of the GNU General Public License as published by the Free Software
Foundation, either version 3 of the License, or (at your option) any later
version.

This program is distributed in the hope that it will be useful, but WITHOUT
ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.

You should have received a copy of the GNU General Public License along with
this program. If not, see <http://www.gnu.org/licenses/>.

--- Sample configuration ---

[MAIN]
originals-subdir-name=Originals

[JOB]
output-path=Export
smbfs=//root@AirPort-Time-Capsule.local./Data
photos-library-path=~/Pictures/Photos Library.photoslibrary
"""

import sqlite3, subprocess, logging, os, codecs, sys, unicodedata, tempfile, shutil, argparse, configparser
from ape_mountpoint import ApeMountPoint
from ape_exporter import ApeExporter
from ape_photos import ApePhotos
from ape_errors import *

__author__ = "Ladislav Čapka"
__copyright__ = "Copyright 2019, Ladislav Čapka"
__license__ = "GPLv3"
__version__ = "1.0.0"

def main():
    script_name = os.path.splitext(os.path.basename(__file__))[0]
    logfile_filename = script_name + '.log'

    config = configparser.ConfigParser()
    try:
        config.read(script_name + '.config', encoding='utf-8')
    except FileNotFoundError:
        # The configuration file is not required.
        pass

    # Load pre-configured values
    smbfs_path = config.get('JOB', 'smbfs', fallback=None)
    destination_path = config.get('JOB', 'output-path', fallback=None)
    photos_library_path = config.get('JOB', 'photos-library-path', fallback=None)
    originals_subdir_name = config.get('MAIN', 'originals-subdir-name', fallback='Originals')
    update_exif = config.get('MAIN', 'update_exif', fallback=None)

    # Try to parse run arguments, pre-configured value will be overriden.
    parser = argparse.ArgumentParser(description='Export script for Apple Photos application library.')
    parser.add_argument('--smbfs',
                        help='a URL to a samba share, if not set the photos are exported directly to the directory specified in the --output-path argument')
    parser.add_argument('--output-path', required=not destination_path,
                        help='a path where the photos will be exported; if --smbfs is set then it specifies a relative path on the mounted share')
    parser.add_argument('--photos-library-path',
                        help='a path to a photos library; the path shall has the .photoslibrary extension')
    parser.add_argument('--update_exif', action='store_const', const=True,
                        help='enables EXIF updating; current photos (not originals) EXIFs are updated (GPS location, keywords as tags)')
    parser.add_argument('--logfile', default=logfile_filename,
                        help='a filename where the logs will be saved')
    parser.add_argument('--verbose', action='store_const', const=True,
                        help='enables debug information')
    args = parser.parse_args()

    # Get run arguments
    smbfs_path = args.smbfs or smbfs_path
    destination_path = args.output_path or destination_path
    photos_library_path = args.photos_library_path or photos_library_path
    update_exif = args.update_exif or update_exif
    logfile_filename = args.logfile or logfile_filename
    verbose = not not args.verbose

    # Input validation
    if smbfs_path and (os.path.isabs(destination_path) or destination_path.startswith('~')):
        ArgumentParser.error("When the --smbfs argument is set, the --output-path must NOT be rooted. It's a sub-directory created on the mounted smbfs.")

    if not photos_library_path:
        pictures_directory = os.path.expanduser('~/Pictures')
        options = [p for p in os.listdir(pictures_directory) if p.endswith('.photoslibrary')]
        if len(options) != 1:
            ArgumentParser.error("The Photos library couldn't be found automatically. Please set the path manually using the --photos-library-path argument.")

        photos_library_path = os.path.join(pictures_directory, options[0])

    if not originals_subdir_name:
        log.critical("The sub-directory name for original photos must be set.")
        sys.exit(1)

    # Finish logger setup
    if verbose:
        screen_handler.setLevel(logging.DEBUG)

    if logfile_filename:
        log.addHandler(logging.FileHandler(logfile_filename, encoding='utf-8'))

    # Expand home dirs if needed
    if destination_path.startswith('~'):
        destination_path = os.path.expanduser(destination_path)

    if photos_library_path.startswith('~'):
        photos_library_path = os.path.expanduser(photos_library_path)

    # Let's prevent system from falling asleep while running this export
    subprocess.Popen(['caffeinate', '-i', '-w', str(os.getpid())])

    # Do the export
    with tempfile.TemporaryDirectory() as temp_export:
        temp_mount_point = os.path.expanduser('~/.photos_export_mountpoint')

        log.info("Photos library:    %s", photos_library_path)
        if smbfs_path:
            log.info("Samba URL:         %s", smbfs_path)
            log.info("Samba mount point: %s", temp_mount_point)
            log.info("Destination path:  %s", os.path.join(smbfs_path, destination_path))
        else:
            log.info("Destination path:  %s", destination_path)

        # Mount/unmount Samba share (if set)
        with ApeMountPoint(smbfs_path, temp_mount_point):
            export_path = os.path.join(temp_mount_point, destination_path) if smbfs_path else destination_path

            # Fetch album tree
            photos = ApePhotos(photos_library_path)
            album_tree = photos.fetch_albums()

            # Export album tree
            exporter = ApeExporter(photos_library_path, temp_export, originals_subdir_name=originals_subdir_name, update_exif=update_exif)
            exporter.export_photos(album_tree, export_path)

if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG, handlers=[logging.NullHandler()])
    log = logging.getLogger()

    screen_handler = logging.StreamHandler(sys.stdout)
    screen_handler.setLevel(logging.INFO)
    log.addHandler(screen_handler)

    if sys.platform != 'darwin':
        log.critical("This script can run on macOS operating system only.")
        sys.exit(1)

    try:
        main()
    except GenericExportError as e:
        log.critical(str(e))
        sys.exit(1)
    except Exception as e:
        log.exception("Fatal error has occured.", exc_info=e)
        sys.exit(1)
