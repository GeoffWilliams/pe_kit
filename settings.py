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
    DEFAULTS_FILE           = os.path.dirname(os.path.realpath(__file__)) + "/defaults.cfg"
    CONFIG_FILE             = os.path.expanduser('~') + "/.pe_kit.cfg"
    __shared_state          = {}
    start_automatically     = True
    kill_orphans            = True
    use_latest_image        = True
    shutdown_on_exit        = True
    expose_ports            = True
    master_selected_image   = None
    agent_selected_image    = None
    gh_repo                 = None
    master_image            = None
    agent_image             = None
    terminal_program        = None
    provision_automatically = True
    hub_username            = None
    hub_password            = None
    hub_address             = None
    licence_file            = None
    shared_dir              = False


    def __init__(self):
        self.__dict__ = self.__shared_state
        self.load()

    def save(self):
        # reset the selected image names if we are configued to use the latest image
        if self.use_latest_image:
            # If we use None here we end up with literal 'None' in the file ;-)
            master_selected_image = ''
            agent_selected_image = ''
        else:
            master_selected_image = self.master_selected_image
            agent_selected_image = self.agent_selected_image
        self.config.set("main", "start_automatically", self.start_automatically)
        self.config.set("main", "provision_automatically", self.provision_automatically)
        self.config.set("main", "kill_orphans", self.kill_orphans)
        self.config.set("main", "use_latest_image", self.use_latest_image)
        self.config.set("main", "shutdown_on_exit", self.shutdown_on_exit)
        self.config.set("main", "expose_ports", self.expose_ports)
        self.config.set("main", "master_selected_image", master_selected_image)
        self.config.set("main", "agent_selected_image", agent_selected_image)
        self.config.set("main", "gh_repo", self.gh_repo)
        self.config.set("main", "hub_username", self.hub_username)
        self.config.set("main", "hub_password", self.hub_password)
        self.config.set("main", "hub_address", self.hub_address)
        self.config.set("main", "licence_file", self.licence_file)
        self.config.set("main", "shared_dir", self.shared_dir)
        self.config.write(open(self.CONFIG_FILE, 'w'))

    def load(self):
        self.config = ConfigParser.RawConfigParser()
        self.config.readfp(open(self.DEFAULTS_FILE))
        self.config.read(self.CONFIG_FILE)
        self.start_automatically        = self.config.getboolean("main","start_automatically")
        self.provision_automatically    = self.config.getboolean("main","provision_automatically")
        self.kill_orphans               = self.config.getboolean("main","kill_orphans")
        self.use_latest_image           = self.config.getboolean("main","use_latest_image")
        self.shutdown_on_exit           = self.config.getboolean("main", "shutdown_on_exit")
        self.expose_ports               = self.config.getboolean("main", "expose_ports")
        self.gh_repo                    = self.config.get("main", "gh_repo")
        self.master_image               = self.config.get("main", "master_image")
        self.agent_image                = self.config.get("main", "agent_image")
        self.terminal_program           = self.config.get("main", "terminal_program")
        self.hub_username               = self.config.get("main", "hub_username")
        self.hub_password               = self.config.get("main", "hub_password")
        self.hub_address                = self.config.get("main", "hub_address")
        self.licence_file               = self.config.get("main", "licence_file")

        shared_dir_raw = self.config.get("main", "shared_dir")
        self.shared_dir = shared_dir_raw if shared_dir_raw.lower() != "false" else False

        # skip loading image selections if using latest images
        if not self.use_latest_image:
          self.master_selected_image    = self.config.get("main", "master_selected_image")
          self.agent_selected_image     = self.config.get("main", "agent_selected_image")
