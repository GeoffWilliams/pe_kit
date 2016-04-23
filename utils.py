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

import sys
import subprocess
class Utils:

    @staticmethod
    def docker_terminal(command=''):
        print sys.platform
        p = sys.platform
        if p == "darwin":
            # http://stackoverflow.com/questions/989349/running-a-command-in-a-new-mac-os-x-terminal-window
            shell="osascript -e 'tell application \"Terminal\" to do script \"eval $(docker-machine env default) && {command}\"'".format(command=command)
        #elif p.startswith("linux"):
        #  print("linux support untested - this sux")
        #  shell="xterm"
        else:
            raise("unsupported os " + p)

        #l = [shell, command]
        #subprocess.Popen(filter(None,l))
        subprocess.Popen(shell, shell=True)
