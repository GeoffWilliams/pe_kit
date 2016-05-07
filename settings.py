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

import os
import ConfigParser

class Settings:
    DEFAULTS_FILE = os.path.dirname(os.path.realpath(__file__)) + "/defaults.cfg"
    CONFIG_FILE = os.path.expanduser('~') + "/.pe_kit.cfg"
    __shared_state = {}
    start_automatically = True
    kill_orphans = True
    use_latest_image = True
    shutdown_on_exit = True
    expose_ports = True
    master_selected_image = None
    agent_selected_image = None
    gh_repo = None
    master_image = None
    agent_image = None
    terminal_program = None
    
    def __init__(self):
        self.__dict__ = self.__shared_state
        self.load()

    def save(self):
        self.config.set("main", "start_automatically", self.start_automatically)
        self.config.set("main", "kill_orphans", self.kill_orphans)
        self.config.set("main", "use_latest_image", self.use_latest_image)
        self.config.set("main", "shutdown_on_exit", self.shutdown_on_exit)
        self.config.set("main", "expose_ports", self.expose_ports)
        self.config.set("main", "master_selected_image", self.master_selected_image)
        self.config.set("main", "agent_selected_image", self.agent_selected_image)
        self.config.set("main", "gh_repo", self.gh_repo)
        
        self.config.write(open(self.CONFIG_FILE, 'w'))

    def load(self):
        self.config = ConfigParser.RawConfigParser()
        self.config.readfp(open(self.DEFAULTS_FILE))
        self.config.read(self.CONFIG_FILE)
        self.start_automatically = self.config.getboolean("main","start_automatically")
        self.kill_orphans = self.config.getboolean("main","kill_orphans")
        self.use_latest_image = self.config.getboolean("main","use_latest_image")
        self.shutdown_on_exit = self.config.getboolean("main", "shutdown_on_exit")
        self.expose_ports = self.config.getboolean("main", "expose_ports")
        self.master_selected_image = self.config.get("main", "master_selected_image")
        self.agent_selected_image = self.config.get("main", "agent_selected_image")
        self.gh_repo = self.config.get("main", "gh_repo")
        self.master_image = self.config.get("main", "master_image")
        self.agent_image = self.config.get("main", "agent_image")
        self.terminal_program = self.config.get("main", "terminal_program")
