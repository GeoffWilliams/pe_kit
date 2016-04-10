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
