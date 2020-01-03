#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Apple Photos Export - ApeMountPoint class

The ApeMountPoint class provides mount/unmount actions supporting Python's with statement.

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
"""

import subprocess, os, logging
from ape_errors import *

log = logging.getLogger("ape_mountpoint")

class ApeMountPoint:
    """Implements mount/umount for Python's with statement."""

    def __init__(self, smbfs_path, mount_point):
        self._mount_point = mount_point
        self._smbfs_path = smbfs_path

    def __enter__(self):
        if self._smbfs_path is not None:
            log.debug("Mounting %s to %s", self._smbfs_path, self._mount_point)
            os.makedirs(self._mount_point, exist_ok=True)
            with subprocess.Popen(['mount', '-t', 'smbfs', self._smbfs_path, self._mount_point], stdin=None) as proc:
                proc.wait()
                exit_code = proc.returncode
                if exit_code:
                    # Upper bits are not defined
                    exit_code = exit_code & 127
                    errors = []
                    return_strings = (
                        "incorrect invocation or permissions",
                        "system error (out of memory, cannot fork, no more loop devices)",
                        "internal mount bug",
                        "user interrupt",
                        "problems writing or locking /etc/mtab",
                        "mount failure",
                        "some mount succeeded"
                        )
                    bit = 0
                    while exit_code:
                        if exit_code & 1 == 1:
                            errors.append(return_strings[bit])
                        exit_code >>= 1
                        bit += 1
                    raise GenericExportError("Mount has failed: {0}".format(', '.join(errors)).rstrip(': '))
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._smbfs_path is not None:
            log.debug("Unmounting %s", self._mount_point)
            with subprocess.Popen(['umount', self._mount_point], stdin=None) as proc:
                pass
