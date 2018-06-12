#
# Copyright 2016 Geoff Williams for Puppet Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import platform
import subprocess
import os
from settings import Settings

class Utils:

    @staticmethod
    def docker_terminal(command=''):
        settings = Settings()
        # use terminal provided in settings file, otherwise detect
        if settings.terminal_program:
            shell = settings.terminal_program + " -e \"{command}\""
        else:
            p = platform.system()
            if p == "Darwin":
                # http://stackoverflow.com/questions/989349/running-a-command-in-a-new-mac-os-x-terminal-window
                shell="osascript -e 'tell application \"Terminal\" to do script \"{command}\"'"
            elif p == "Linux":
                shell="xterm -e \"{command}\""
            else:
                raise("unsupported os " + p)

        subprocess.Popen(shell.format(command=command), shell=True)

    @staticmethod
    def first_existing_file(files):
        """Return the name of the first file that exists in `files` or `False` if none can be Found"""
        found = False
        i = 0
        while not found and i < len(files):
            if os.path.isfile(files[i]):
                found = files[i]
            i += 1

        return found