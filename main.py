#!/usr/bin/env kivy
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

# setup logging before proceeding further
import logging
import tempfile
logging.basicConfig(level=logging.DEBUG)
f, logfile = tempfile.mkstemp()

# get root logger
logger = logging.getLogger()
logger.info("logging to:  " + logfile)
fh = logging.FileHandler(logfile)
# Example of how to turn down logging in the future
# fh.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
fh.setFormatter(formatter)
logger.addHandler(fh)


import ConfigParser
from kivy.app import App
from kivy.clock import Clock
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.anchorlayout import AnchorLayout
from kivy.uix.label import Label
from kivy.uix.image import Image
from kivy.uix.button import Button
from kivy.uix.togglebutton import ToggleButton
from kivy.uix.textinput import TextInput
from kivy.uix.dropdown import DropDown
from kivy.uix.popup import Popup
from kivy.uix.checkbox import CheckBox
from kivy.core.clipboard import Clipboard
from docker import Client
from docker.utils import kwargs_from_env
import webbrowser
from urlparse import urlparse
import pprint
from utils import Utils
import json
import urllib2
import threading
import time
import subprocess
import os
import docker.errors
import requests.exceptions
from kivy.lang import Builder
from kivy.uix.settings import (SettingsWithSidebar,
                               SettingsWithSpinner,
                               SettingsWithTabbedPanel)
from kivy.uix.screenmanager import ScreenManager, Screen, FadeTransition
from kivy.properties import ObjectProperty
import dateutil.parser
import datetime
import ssl
import textwrap
from functools import partial

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
    gh_repo="geoffwilliams/pe_kit"

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


class DockerMachine():
    """
    DockerMachine

    Control the default docker-machine instance (boot2docker)
    """

    logger = logging.getLogger(__name__)
    
    # is a start/stop operation in progress?
    in_progress = False

    def __init__(self):
        self.logger.info("adjusted path for /usr/local/bin")
        os.environ['PATH'] = "/usr/local/bin/:" + os.environ['PATH']

    def run_cmd(self, *command, **options):
        return subprocess.check_output(env={
          'PATH': "/usr/local/bin/:" + os.environ['PATH']
        }, *command, **options)

    def status(self):
        status = subprocess.check_output(["docker-machine", "status"]).strip()
        self.logger.info("docker-machine status: " + status)
        return status

    def start(self):
        # start the daemon if its not already running
        started = False
        try:
            if not self.in_progress and self.status() != "Running":
                self.in_progress = True
                out = subprocess.check_output(["docker-machine", "start"])
                self.in_progress = False

                if self.status() == "Running":
                    self.logger.info("docker-machine started OK")
                    started = True
            else:
                started = True
                self.logger.info("docker-machine already running")

            # setup the docker environment variables if we managed to start the daemon
            if started:
                out = subprocess.check_output(["docker-machine", "env"]).split("\n")
                for line in out:
                    if not line.startswith('#') and line != "":
                        key = line.split("=")[0].replace('export ', '')
                        value = line.split("=")[1].replace('"','')

                        self.logger.info("export {key}={value}".format(key=key, value=value))
                        os.environ[key] = value
        except subprocess.CalledProcessError as e:
            self.logger.error("Error getting running docker-machine command, exception follows")
            self.logger.exception(e)

        return started

class SettingsScreen(Screen):
    """
    Settings Screen

    Screen for saving settings and managing docker images
    """

    logger = logging.getLogger(__name__)
    master_image_management_layout  = ObjectProperty(None)
    agent_image_management_layout   = ObjectProperty(None)
    use_latest_images_checkbox      = ObjectProperty(None)
    start_automatically_checkbox    = ObjectProperty(None)
    kill_orphans_checkbox           = ObjectProperty(None)
    download_images_layout          = ObjectProperty(None)
    master_selected_image_button    = ObjectProperty(None)
    shutdown_on_exit_checkbox       = ObjectProperty(None)
    expose_ports_checkbox           = ObjectProperty(None)
    settings                        = Settings()


    def __init__(self, **kwargs):
        super(SettingsScreen, self).__init__(**kwargs)
        self.controller = Controller()

    def on_start(self):
        self.use_latest_images_checkbox.active    = self.settings.use_latest_image
        self.start_automatically_checkbox.active  = self.settings.start_automatically
        self.kill_orphans_checkbox.active         = self.settings.kill_orphans
        self.shutdown_on_exit_checkbox.active     = self.settings.shutdown_on_exit
        self.expose_ports_checkbox.active         = self.settings.expose_ports

        # periodically refresh the image managment grid if we need to
        Clock.schedule_interval(self.update_image_managment, 0.5)
        
        # scrollable image list for images (agent and master)
        self.master_image_management_layout.bind(
            minimum_height= self.master_image_management_layout.setter('height'))
        self.agent_image_management_layout.bind(
            minimum_height=self.agent_image_management_layout.setter('height'))

    def back(self):
        """save settings and go back"""
        self.settings.use_latest_image      = self.use_latest_images_checkbox.active
        self.settings.start_automatically   = self.start_automatically_checkbox.active
        self.settings.kill_orphans          = self.kill_orphans_checkbox.active
        self.settings.shutdown_on_exit      = self.shutdown_on_exit_checkbox.active
        self.settings.expose_ports          = self.expose_ports_checkbox.active
        self.settings.master_selected_image = App.get_running_app().get_master_selected_image()
        self.settings.agent_selected_image  = App.get_running_app().get_agent_selected_image()

        self.logger.info("save settings:" + str(self.settings))
        self.settings.save()
        App.get_running_app().root.current = 'main'

    def get_image_button(self, status):
        if status == "downloadable":
            icon = "icons/available.png"
        elif status == "local":
            icon = "icons/delete.png"
        else:
            # no idea, broken
            icon = "icons/error.png"

        button = Button()
        button.background_normal = icon
        button.border = (0, 0, 0, 0)
        button.width = "20dp"
        button.height = "20dp"

        return button
    
    
    def image_management_ui(self, layout, images, selected_image_name, selected_image_group):
        def image_action(button):
            self.logger.info(
              "image action: {image_name}, {status}".format(
                    image_name=button.image_name, status=button.status))
            if button.status == "downloadable":
                # start download in own thread
                button.background_normal = "icons/download.png"
                button.status = "downloading"
                threading.Thread(target=self.controller.download_image, args=[button.image_name]).start()
            elif button.image_name in self.controller.active_downloads:
                # currently downloading
                App.get_running_app().question(
                    "Image {image_name} is downloading, cancel?".format(
                        image_name=button.image_name
                    ),
                    yes_callback=partial(self.controller.stop_download, button.image_name)
                )
            elif button.status == "local":
                # delete
                App.get_running_app().question(
                    "really delete image {image_name}?".format(
                        image_name=button.image_name,
                    ), 
                    yes_callback=partial(self.controller.delete_image, button.image_name)
                )
                
                
        layout.clear_widgets()
        for image in images:
            name_label = Label(text=image["name"])
            name_label.bind(size=name_label.setter('text_size'))
            name_label.halign = "left"
            status_button = self.get_image_button(image["status"])
            status_button.image_name = image["name"]
            status_button.status = image["status"]
            status_button.bind(on_release=image_action)
            if self.use_latest_images_checkbox.active:
                # add a blank label as a spacer to avoid breaking the display
                selected_button = Label()
            else:
                if image["status"] == "local":
                    selected_button = ToggleButton()
                    selected_button.background_normal="icons/deselected_image.png"
                    selected_button.background_down="icons/selected_image.png"
                    selected_button.border = (0, 0, 0, 0)
                    selected_button.width = "20dp"
                    selected_button.height = "20dp"
                    selected_button.group = selected_image_group
                    selected_button.image_name = image["name"]
                    if image["name"] == selected_image_name:
                        selected_button.state = "down"
                else:
                    # use a blank label as a spacer
                    selected_button = Label()

            layout.add_widget(name_label)
            layout.add_widget(status_button)
            layout.add_widget(selected_button)        

    def update_image_managment(self, x=None, force_refresh=False, ):

            
        if self.controller.images_refreshed or force_refresh:
            self.image_management_ui(
                self.master_image_management_layout, 
                self.controller.container["master"]["images"], 
                self.settings.master_selected_image,
                "master_selected_image"
            )
            self.image_management_ui(
                self.agent_image_management_layout, 
                self.controller.container["agent"]["images"], 
                self.settings.agent_selected_image,
                "agent_selected_image"
            )
            self.controller.images_refreshed = False

class MainScreen(Screen):
    """
    MainScreen

    The main screen of the application
    """

    logger = logging.getLogger(__name__)
    settings = Settings()
    advanced_layout                 = ObjectProperty(None)
    advanced_layout_holder          = ObjectProperty(None)
    agent_status_label              = ObjectProperty(None)
    master_status_label             = ObjectProperty(None)
    master_container_delete_button  = ObjectProperty(None)
    docker_status_button            = ObjectProperty(None)
    pe_status_button                = ObjectProperty(None)
    console_button                  = ObjectProperty(None)
    terminal_button                 = ObjectProperty(None)
    master_run_puppet_button        = ObjectProperty(None)
    dockerbuild_button              = ObjectProperty(None)
    
    # Agent actions
    agent_provision_button          = ObjectProperty(None)
    agent_run_puppet_button         = ObjectProperty(None)
    agent_terminal_button           = ObjectProperty(None)
    agent_demo_button               = ObjectProperty(None)

    def __init__(self, **kwargs):
        super(MainScreen, self).__init__(**kwargs)
        self.controller = Controller()

    def pe_status_info(self):
        uptime = self.controller.container_alive(self.controller.container["master"])
        if uptime:
            pe_status = self.controller.pe_status()

            message = "PE Docker container is alive, up {uptime} seconds.  PE is {pe_status}.  ".format(
              uptime = uptime,
              pe_status = pe_status
            )
            if self.settings.expose_ports and pe_status == "running":
                command = self.controller.CURL_COMMAND
                Clipboard.copy(command)

                message += "You can install agent by running:" + textwrap.dedent(
                """
                {command}
                
                You must add the following to your /etc/hosts file before running:
                {docker_address} pe-puppet.localdomain pe-puppet
                """.format(command=command, docker_address=self.controller.docker_address))

            pe_status = self.controller.pe_status()
        else:
            message = "PE Docker container is not running"
        App.get_running_app().info(message)

    def docker_status_info(self):
        App.get_running_app().info(
            "Docker daemon is {alive}".format(
                alive=self.controller.daemon_alive()
            )
        )


    def toggle_advanced(self):
        self.logger.debug("clicked toggle_advanced()")
        if self.advanced_layout in self.advanced_layout_holder.children:
            # showing -> hide
            self.advanced_layout_holder.clear_widgets()
        else:
            # hidden -> show
            self.advanced_layout_holder.add_widget(self.advanced_layout)
        self.logger.debug("...exiting toggle_advanced()")


    def toggle_log(self, x):
        if self.log_textinput in self.advanced_layout.children:
            self.advanced_layout.remove_widget(self.log_textinput)
        else :
            self.advanced_layout.add_widget(self.log_textinput)


    def dockerbuild(self):
        App.get_running_app().info("Launching dockerbuild - have fun :)")

        def open_browser(dt):
            webbrowser.open_new(self.controller.container["master"]["urls"]["9000/tcp"])

        # call the named callback in 2 seconds (delay without freezing)
        Clock.schedule_once(open_browser, 2)

    def run_puppet(self, button, location):
        def run_puppet_real(location, callback, button):
            container = self.controller.container[location]
            exit_status=self.controller.run_puppet(container)
            if exit_status == 0:
                error = False
                message = "Puppet run on {location} OK (no changes)"
            elif exit_status == 1:
                error = True
                message = "Puppet run on {location} FAILED or already in progress"
            elif exit_status == 2:
                error = False
                message = "Puppet run on {location} OK (changes)"
            else:
                error = True
                message = "Puppet run on {location} OK (but resource errors)"
                
            app = App.get_running_app()
            message = message.format(location=location)
            if error:
                app.error(message)
            else:
                app.info(message)
            callback(button)
                
        self.busy_button(button)
        threading.Thread(
            target=run_puppet_real, args=[location, self.free_button, button]
        ).start()

    def log(self, message, level="[info]  "):
        current = self.log_textinput.text
        if message is not None:
            updated = current + level + message + "\n"
            self.log_textinput.text = updated

    def pe_console(self):

        App.get_running_app().info("Launching browser, please accept the certificate.\n"
                  "The username is 'admin' and the password is 'aaaaaaaa'")

        def open_browser(dt):
            webbrowser.open_new(self.controller.pe_url())

        # call the named callback in 2 seconds (delay without freezing)
        Clock.schedule_once(open_browser, 2)
     
    def pe_terminal(self):
        self.terminal(Controller.container["master"]["name"])
        
    def agent_terminal(self):
        self.terminal(Controller.container["agent"]["name"])
    
    def terminal(self, container_name):
        App.get_running_app().info("Launching terminal, please lookout for a new window")

        def terminal(dt):
            Utils.docker_terminal("docker exec -ti {name} bash".format(
              name=container_name,
            ))

        # call the named callback in 2 seconds (delay without freezing)
        Clock.schedule_once(terminal, 2)
        
    def busy_button(self, button):
        button.disabled=True
        button.busy=True
        button.text=button.busy_text
        
    def free_button(self, button):
        button.disabled=False
        button.busy=False
        button.text=button.free_text
        
    def agent_provision(self):
        def provision(callback, button):
            exit_status = self.controller.agent_provision()
            error = True
            if exit_status == 0:
                error = False
                message="Agent provisioned OK"
            elif exit_status == 7 or exit_status == 35:
                message="Agent provisioning FAILED, Puppet Master down/starting?"
            elif exit_status == 1:
                message="Agent provisioning FAILED, often a temporary failure, please try again later"
            else:
                message="Agent provisioning FAILED, check logs for more info"    
            
            app = App.get_running_app()
            if error:
                app.error(message)
            else:
                app.info(message)
            callback(button)    
        self.busy_button(self.agent_provision_button)
        threading.Thread(target=provision, args=[self.free_button, self.agent_provision_button]).start()

        
    def agent_demo(self):
        webbrowser.open_new(self.controller.demo_url())

class MenuScreen(Screen):        
    """
    MenuScreen
    
    Simple menu of helpful links
    """
    settings = Settings()
    
    def __init__(self, **kwargs):
        super(MenuScreen, self).__init__(**kwargs)
    
    def about(self):
        App.get_running_app().info("PE_Kit {version}".format(version = PeKitApp.__version__))
        
    def help(self):
        webbrowser.open_new("https://github.com/{gh_repo}#help".format(self.settings.gh_repo))
    
    def report_bug(self):
        def report_bug(x):
            webbrowser.open_new(
                'https://github.com/{gh_repo}/issues/new'.format(gh_repo=self.settings.gh_repo))
        App.get_running_app().info("Please also try to copy and paste the logs if reporting a bug")
        Clock.schedule_once(report_bug, 2)


    def copy_log_clipboard(self):
        log = open(logfile).read()
        Clipboard.copy(log)
        App.get_running_app().info("Logfile copied to clipboard")

    
# borg class, see http://code.activestate.com/recipes/66531-singleton-we-dont-need-no-stinkin-singleton-the-bo/
class Controller:
    """
    Controller
    
    Separate off the control functions to remove dependency on kivy
    """
    __shared_state = {}

    logger = logging.getLogger(__name__)
    
    # container names, image info and urls for each image.
    #   * name - the name of the started container in docker
    #   * host - the hostname for the started container
    #   * image_name - the name of the image used for this container
    #   * local_images - the name+tags for this image that are available locally
    #   * images - the name+tags for this image that are downloadable or local
    #   * instance - object representing the running container, if started
    #   * urls - URLs accessible in the started container
    #   * status - current status of the container, updated every second by a thread
    #   * port_bindings_func - name of function to run to obtain port mappings 
    #     to preserve liveness of settings
    #   * ports - dict of docker to local ports we will use to build URLs in the GUI
    container = {
        "master": {
            "name": "pe_kit_master__",
            "host": "pe-puppet.localdomain",
            "image_name": "geoffwilliams/pe_master_public_lowmem_r10k_dockerbuild",
            "local_images": [],
            "images": [],
            "instance": None,
            "urls": {},
            "status": False,
            "port_bindings_func": "master_port_bindings",
            "ports": {
                "443/tcp": None, 
                "9000/tcp": None,
            }
        },
        "agent": {
            "name": "pe_kit_agent__",
            "host": "agent.localdomain",
            "image_name": "picoded/centos-systemd",
            "local_images": [],
            "images": [],
            "instance": None,
            "urls": {},
            "status": False,
            "port_bindings_func": "agent_port_bindings",
            "ports": {
                "9090/tcp": None,
            }
        }
    }

    # Puppet.com suggested curl installation command (swallows exit status)
    CURL_COMMAND="curl -k https://pe-puppet.localdomain:8140/packages/current/install.bash | bash"
    
    # Save to intermediate file to prevent streaming errors and preserve exit status
    CURL_COMMAND_SAFE="curl -k https://pe-puppet.localdomain:8140/packages/current/install.bash > /tmp/pe_installer && bash < /tmp/pe_installer"
    
    cli = None
    
    docker_url = None
    docker_address = "unknown"
    pe_url = None
    dockerbuild_url = None
    pe_console_port = 0
    dockerbuild_port = 0
    app = None
    settings = Settings()
    daemon_status = "stopped"
    update_available = False
    dm = None
    active_downloads = []

    # app/program is running - threads use this to see if they should
    # continue executing
    running = True

    # When new images are loaded, this flag is set true to flag the GUI
    # to refresh.  We must use a variable to communicate with the GUI thread
    # because since the update takes place in its own thread, we can't let
    # it interact with the GUI thread or we'll get segfaults
    images_refreshed = False

    def __init__(self):
        self.__dict__ = self.__shared_state
        
    def pe_url(self):
        return self.container["master"]["urls"]["443/tcp"]
    
    def dockerbuild_url(self):
        return self.container["master"]["urls"]["9000/tcp"]
    
    def demo_url(self):
        return self.container["agent"]["urls"]["9090/tcp"]
    
    def bash_cmd(self, cmd):
        """docker exec commands must be wrapped in bash -c or they fail due
        to not being run from the shell"""
        return "bash -c \"{cmd}\"".format(cmd=cmd)
    
    def fix_hosts_cmd(self):
        return self.bash_cmd("grep {fqdn} /etc/hosts || echo '{docker_address} {fqdn} {short_name}' >> /etc/hosts".format(
            docker_address=self.docker_address,
            fqdn=self.container["master"]["host"],
            short_name=self.container["master"]["host"].split()[-1],
        ))
    
    def curl_command(self):
        return self.bash_cmd(self.CURL_COMMAND_SAFE)
        
    def delete_image(self, image_name):
        self.cli.remove_image(image_name)
        self.refresh_images()

    def download_image(self, image_name):
        if image_name in self.active_downloads:
            self.logger.info(
                "Already downloading {image_name}, refusing duplicate download".format(
                    image_name=image_name
            ))
        else:
            self.logger.info("starting download of:  " + image_name)
            self.active_downloads.append(image_name)
            image_name_split = image_name.split(":")
            for line in self.cli.pull(
              repository = image_name_split[0],
              tag = image_name_split[1],
              stream = True,
            ):
                if self.running and image_name in self.active_downloads:
                    self.logger.debug(line)
                else:
                    raise Exception("Aborting download because quit/cancel!")
            
            # mark as completed
            self.stop_download(image_name)
            self.refresh_images()
        
    def stop_download(self, image_name):
        """abort a download by removing it from the list of active downloads"""
        if image_name in self.active_downloads:
            self.active_downloads.remove(image_name)
        self.refresh_images()

    def update_status(self):
        """daemon thread to check if docker and container are alive"""
        while (self.running):
            self.daemon_status = self.daemon_alive()

            if self.daemon_status == "running":
                self.container["master"]["status"] = self.container_alive(self.container["master"])
                self.container["agent"]["status"] = self.container_alive(self.container["agent"])
            else:
                self.container_status = False
            time.sleep(1)

    def pe_status(self):
        """return status of PE master: running, loading, stopped"""

        # turn off SSL cert verifcation since we're using puppets self-signed certs
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

        if self.pe_url():
            try:
                code = urllib2.urlopen(self.pe_url(), context=ctx).getcode()
                if code == 200:
                    self.logger.debug("puppet up and running :D")
                    status = "running"
                else:
                    self.logger.debug("puppet loading...")
                    status = "loading"
            except urllib2.HTTPError as e:
                self.logger.debug("puppet http server error: {message} code: {code}".format(
                  message = e.reason,
                  code = e.code
                ))
                status = "loading"
            except urllib2.URLError as e:
                self.logger.debug("puppet stopped/unreachable at {pe_url}:  {message}".format(
                  pe_url = self.pe_url(),
                  message = e.reason,
                ))
                status = "loading"
        else:
            status = "error"

        return status

    def cleanup_container(self, container):
        """on-startup cleanup of orphaned containers (if requested)"""
        try:
            if self.cli.inspect_container(container["name"]):
                if self.settings.kill_orphans:
                    self.logger.info("killing orphaned container")
                    self.cli.remove_container(container["name"], force=True)
                else:
                    self.logger.info("inspecting existing container")
                    container["instance"] = self.cli.inspect_container(
                        container["name"])
                    if container["instance"]["State"]["Running"]:
                        self.munge_urls(container)
                    # else container exists but has not yet been started, leave it
                    # alone until its started by the start_automatically flag or 
                    # a user manually pressing the play button
        except docker.errors.NotFound:
            self.logger.info(
                "container {container} not running, OK to start new one".format(
                    container=container["name"]))

        
    def docker_init(self):
        #  boot2docker specific hacks in use - see:  http://docker-py.readthedocs.org/en/latest/boot2docker/

        self.dm = DockerMachine()
        if self.dm.start():
            kwargs = kwargs_from_env()

            if 'tls' not in kwargs:
                # daemon not setup/running
                self.app.error("Docker could not be started, please check your system")
            else:
                # docker ok
                kwargs['tls'].assert_hostname = False

                # save the boot2docker IP for use when we open browser windows
                self.docker_url = kwargs['base_url']

                self.cli = Client(**kwargs)

                # stop any existing container (eg if we were killed)
                self.cleanup_container(self.container["agent"])
                self.cleanup_container(self.container["master"])

                # update downloadble and local images on the settings page
                self.refresh_images()

                if self.settings.start_automatically:
                    self.start_pe()

        else:
            # no docker machine
            self.app.error("Unable to start docker :*(")

    def daemon_alive(self):
        """
        Return 'running' if docker daemon is alive, 'loading' if starting, 'stopped' otherwise
        """
        if self.cli:
            try:
                version_info = self.cli.version()
                if "Version" in version_info:
                    alive = "running"
                else:
                    alive = "stopped"
            except requests.exceptions.ConnectionError:
                self.logger.error("urllib3 error talking to docker daemon")
                alive = "stopped"
        elif self.dm and self.dm.in_progress:
            alive = "loading"
        else:
            alive = "stopped"
        return alive

    def container_alive(self, container):
        """
        Return container uptime or false if its dead
        """
        alive = False
        if self.cli:
            try:
                inspection = self.cli.inspect_container(container["name"])
                if inspection["State"]["Status"] == "running":
                    started = time.mktime(
                      dateutil.parser.parse(inspection["State"]["StartedAt"]).timetuple())
                    now = time.mktime(datetime.datetime.utcnow().timetuple())

                    alive = now - started
            except requests.exceptions.ConnectionError:
                self.logger.error("urllib3 error talking to docker daemon")
            except docker.errors.NotFound:
                pass
        return alive

    def toggle_docker_container(self, container_key):
        self.logger.debug("toggle_docker_container clicked")
        container = self.container[container_key]
        if self.container_alive(container):
            self.stop_docker_container(container)
        else:
            if container_key == "master":
                self.start_pe()
            elif container_key == "agent":
                self.start_agent()
            else:
                self.logger.error("requested unknown container start: " + container_key)

    def stop_docker_container(self, container):
        # check we are still alive as this also gets called when we shut down
        if self.container_alive(container):
            self.cli.remove_container(container=container["instance"].get('Id'), force=True)

    def start_docker_daemon(self):
        # docker startup in own thread
        self.logger.info("starting docker_init in own thread")
        threading.Thread(target=self.docker_init).start()

        # self-monitoring/status in own thread
        self.logger.info("starting update_status in own thread")
        threading.Thread(target=self.update_status).start()

    def master_port_bindings(self):
        return {
            22: None,
            443: None,
            8140: 8140 if self.settings.expose_ports else None,
            8142: 8142 if self.settings.expose_ports else None, 
            9000: None,
            61613: 61613 if self.settings.expose_ports else None,
            61616: None,
        }
    
    def agent_port_bindings(self):
        return { 
            9090: None,
        }

    def start_agent(self):
        image_name = self.app.get_agent_selected_image()
        return self.start_container(self.container["agent"], image_name)
    
    def start_pe(self):
        image_name = self.app.get_master_selected_image()
        return self.start_container(self.container["master"], image_name)
        
    def start_container(self, container, image_name):
        status = False

        if self.container_alive(container):
            status = True
        else:
            if image_name:
                port_bindings_func = getattr(self, container["port_bindings_func"])
                port_bindings = port_bindings_func()
                proceed = True
                try:
                    proceed = True
                    container["instance"] = self.cli.create_container(
                      image=image_name,
                      name=container["name"],
                      hostname=container["host"],
                      detach=True,
                      volumes = [
                          "/sys/fs/cgroup",
                      ],
                      ports = port_bindings.keys(),
                      host_config=self.cli.create_host_config(port_bindings=port_bindings)
                    )
                except docker.errors.APIError as e:
                    if e.response.status_code == 409:
                        self.logger.info(
                            "Container {name} already exists - starting it".format(
                                name=container["name"]))
                        container["instance"] = self.cli.inspect_container(container["name"])
                    else:
                        proceed = False
                        self.logger.error("Unknown Docker error follows")
                        self.logger.exception(e)
                        self.app.error("Unknown Docker error:  " + str(e.explanation or e.message))
                if proceed:
                    id = container["instance"].get('Id')
                    self.logger.info("starting container " + id)
                    resp = self.cli.start(
                      container=id,
                      privileged=True,
                      port_bindings=port_bindings

                    )
                    self.logger.info(container["instance"])
                    self.munge_urls(container)

                    status = True
            else:
                self.app.error("No image selected, check settings")

        return status

    def munge_urls(self, container):

        # inspect the container and get the port mapping
        container_info = self.cli.inspect_container(container["instance"].get("Id"))
        pp = pprint.PrettyPrinter()
        pp.pprint(container_info)

        parsed = urlparse(self.docker_url)
        self.docker_address = parsed.netloc.split(":")[0]        
        
        for port in container["ports"]:
            scheme = "https" if port == "443/tcp" else "http"
  
            container["ports"][port] = container_info["NetworkSettings"]["Ports"][port][0]["HostPort"]
            container["urls"][port] = parsed._replace(
                scheme=scheme,
                netloc="{}:{}".format(parsed.hostname, container["ports"][port])
            ).geturl()        
        self.logger.info("port mapping: {ports}".format(ports=container["ports"]))
        
    def refresh_images(self):
        """Update the lists of downloadable and locally available images,
        then de-duplicate the list and produce a map combining both lists
        so that the image managment grid can be built"""
        
        self.update_available = False
        for container_key in ["agent", "master"]:
            container = self.container[container_key]
            container["local_images"], newest_local = self.update_local_images(container)
            downloadable_images, newest_downloadable =self.update_downloadable_images(container)

            # set flag here and pick it up in the render code
            if newest_downloadable > newest_local:
                self.update_available = True

            container["images"] = self.combine_image_list(container["local_images"], downloadable_images)

        self.images_refreshed = True
        
    def combine_image_list(self, local_images, downloadable_images):
        # now combine into an array of hashes
        images = []
        for image_name in downloadable_images:
            images.append({
              "name": image_name,
              "status": "downloadable",
              "selected": False
            })

        for image_name in local_images:
            images.append({
              "name": image_name,
              "status": "local",
              "selected": False
            })
        return images
        

    def update_local_images(self, container):
        """
        re-create the list of locally downloaded images that are ready to
        run.  Updates the self.local_images array to be a list of tags
        present locally
        """
        local_images = []
        if self.cli is not None:
            docker_images = self.cli.images()

            for docker_image in docker_images:
                image_name = docker_image["RepoTags"][0]
                if image_name.startswith(container["image_name"]):
                    local_images.append(image_name)
            local_images.sort(reverse=True)
            
        if len(local_images):
            newest_image = local_images[0]
        else:
            newest_image = None
        return local_images, newest_image

    # images available for download
    def update_downloadable_images(self, container):
        """
        re-create the list of image tags available for download.  Updates
        self.master_downloadable_images to be a list of the available tags (strings)
        """
        downloadable_images = []
        try:
            images = json.load(
              urllib2.urlopen(
                "https://registry.hub.docker.com/v2/repositories/%s/tags/" %
                container["image_name"]
              )
            )
            for tags in images["results"]:
                # if image is already downloaded, don't list it as available for download
                image_name = container["image_name"] + ":" + tags["name"]
                if not self.tag_exists_locally(image_name):
                    downloadable_images.append(image_name)
        except urllib2.URLError:
            self.logger.error("failed to reach docker hub - no internet?")
        downloadable_images.sort(reverse=True)
        
        if len(downloadable_images):
            newest_image = downloadable_images[0]
        else:
            newest_image = None
            
        return downloadable_images, newest_image

    # test if a tag has already been downloaded
    def tag_exists_locally(self, image_name):
        """determine if a pattern and tag exists locallay"""        
        found = False
        i = 0
        local_images = self.cli.images()
        while not found and i < len(local_images):
            local_image = local_images[i]["RepoTags"][0]
            self.logger.debug(local_image + "==" + image_name)
            if local_image == image_name:
                found = True
            i += 1

        self.logger.debug("image {image_name} local={found}".format(
                image_name=image_name,found=found)
        )

        return found

    def run_puppet(self, container):
        """Run puppet on the master or agent"""
        return self.docker_exec(container, "puppet agent --detailed-exitcodes -t")
        
    def agent_provision(self):
        """Install puppet on agent"""
        # fix /etc/hosts
        fix_hosts_cmd = self.fix_hosts_cmd()
        self.docker_exec(self.container["agent"], fix_hosts_cmd)
        self.logger.info("hosts file updated on agent: " + fix_hosts_cmd)

        # curl script
        return self.docker_exec(self.container["agent"], self.curl_command())

    def docker_exec(self, container, cmd):
        """run a docker command on a container and return the exit status"""
        container_name = container["name"]
        self.logger.debug("container {container_name} running: {cmd}...".format(
            container_name=container_name,
            cmd=cmd,
        ))
        exec_instance = self.cli.exec_create(
            container=container_name,
            cmd=cmd,
        )
        for line in self.cli.exec_start(exec_instance, stream=True):
            if self.running:
                self.logger.debug(line)
            else:
                raise Exception("Aborting command because quit/cancel!")
        exit_code = self.cli.exec_inspect(exec_instance["Id"])['ExitCode']
        self.logger.debug("...done! result: {exit_code}".format(
            exit_code=exit_code))
        return exit_code  
        
        
class ScreenManagement(ScreenManager):
    """Screen management binding class"""
    pass

class PeKitApp(App):
    """
    PeKitApp
    The main application
    """
    logger = logging.getLogger(__name__)
    settings = Settings()
    __version__ = "v0.1.8"
    
    def check_update(self):
        """check for new release of the app"""
        try:
            r = json.loads(
                urllib2.urlopen(
                    "https://api.github.com/repos/{gh_repo}/releases".format(
                        gh_repo=self.settings.gh_repo, timeout=5
                    )
                ).read()
            )
            latest_tag = r[0]["tag_name"]
            if latest_tag != self.__version__:
                self.info(
                    "A new version of PE_Kit is available ({latest_tag}), you are running {version}\n" "please go to https://github.com/{gh_repo}/releases to download the\n"
                    "new version".format(
                        gh_repo=self.settings.gh_repo,
                        latest_tag=latest_tag, 
                        version=self.__version__))
        except (TypeError, urllib2.URLError) as e:
            self.error("failed to check for new releases, please check your internet connection")
            self.logger.exception(e)
            


    def build(self):
        self.controller = Controller()
        self.controller.start_docker_daemon()
        self.controller.app = self
        self.icon = "icons/logo.png"

        return Builder.load_file("main.kv")

    def on_start(self):
        # hide advanced by default
        self.root.get_screen("main").toggle_advanced()

        # setup the settings screen
        self.root.get_screen("settings").on_start()

        # monitor the docker daemon and container
        Clock.schedule_interval(self.daemon_monitor, 3)
        
        # disclaimer message
        self.info(
            "Warning:  This tool is for test and evaulation use only\n"
            "and is not supported by Puppet.  The images used are NOT\n"
            "secure and must not be used for production use.")

        # check for newer version
        self.check_update()        
        
    def on_stop(self):
        self.controller.running = False
        if self.settings.shutdown_on_exit:
            self.controller.stop_docker_container(self.container["master"])
            self.controller.stop_docker_container(self.container["agent"])

            
    def get_master_selected_image(self):
        return self.get_selected_image(
            self.controller.container["master"]["local_images"], "master_selected_image")
    
    def get_agent_selected_image(self):
        return self.get_selected_image(
             self.controller.container["agent"]["local_images"], "agent_selected_image")
    
    def get_selected_image(self, local_images, widget_group):
        if len(local_images) == 0:
            # error loading local images or none available
            self.logger.error("no local images available!")
            selected = None
        elif self.settings.use_latest_image:
            selected = local_images[0]
            self.logger.debug("using latest image {selected}".format(selected=selected))
        else:
            self.logger.debug(
                "trying to find selection from {widget_group}".format(widget_group=widget_group))
            try:
                group = ToggleButton.get_widgets(widget_group)
                self.logger.debug("found items in list: " + str(len(group)))
                for member in group:
                    self.logger.debug("state is: " + member.state)
                    if member.state == 'down':
                        selected = member.image_name
            except IndexError as e:
                selected = None
        self.logger.debug("get_selected_image() returns {selected}".format(selected=selected))
        return selected

    def error(self, message):
        return self.popup(title='Error!', message=message)

    def popup(self, title, message, question=False, yes_callback=None, no_callback=None):
        def close(button):
            text = button.text
            popup.dismiss()
            if text == "Yes" and yes_callback:
                yes_callback()
            elif text == "No" and no_callback:
                no_callback()

            popup.dismiss()

        popup_content = BoxLayout(orientation="vertical")
        popup_content.add_widget(Label(text=message))
        button_layout = BoxLayout()
        if question:
            button_layout.add_widget(Button(text="Yes", on_press=close))
            button_layout.add_widget(Button(text="No", on_press=close))
        else:
            button_layout.add_widget(Button(text="OK", on_press=close))
        popup_content.add_widget(button_layout)
        popup = Popup(
          title=title,
          content=popup_content,
          size_hint=(0.8,0.5),
          text_size=16
        )
        popup.open()
        return popup

    def question(self, message, yes_callback=None, no_callback=None):
        """Ask a yes/no question with an optional callback attached to each choice"""
        self.popup(
            title="Question", 
            message=message, 
            question=True, 
            yes_callback=yes_callback,
            no_callback=no_callback
        )
    
    def info(self, message):
        return self.popup(title='Information', message=message)
        
    def container_monitor(self, container, button, label):
        uptime = container["status"]
        if uptime:
            status = "up {uptime} seconds".format(uptime=uptime)
            icon = "icons/delete.png"
        else:
            status = ""
            icon = "icons/play.png"
        button.background_normal = icon
        label.text = status
        
        return uptime

    def daemon_monitor(self, x):
        screen = self.root.get_screen("main")
        pe_status = "stopped"
        agent_uptime = False

        if self.controller.daemon_status == "running":
            self.logger.debug("docker daemon ok :)")            
            daemon_icon = "icons/ok.png"

            # docker is alive, lets check the containers too
            master_uptime = self.container_monitor(
                self.controller.container["master"],
                screen.master_container_delete_button,
                screen.master_status_label
            )
            agent_uptime = self.container_monitor(
                self.controller.container["agent"],
                screen.agent_container_delete_button,
                screen.agent_status_label            
            )
            
            if master_uptime:
                pe_status = self.controller.pe_status()
    
        elif self.controller.daemon_status == "loading":
            self.logger.error("docker daemon starting!")
            daemon_icon = "icons/wait.png"                   
        else:
            self.logger.error("docker daemon dead!")
            daemon_icon = "icons/error.png"

        actions_disabled = {
            screen.console_button: False if pe_status == "running" else True,
            screen.terminal_button: False if pe_status == "running" or pe_status == "loading" else True,
            screen.master_run_puppet_button: False if pe_status == "running" else True,
            screen.dockerbuild_button: False if pe_status == "running" or pe_status == "loading" else True,
            
            screen.agent_provision_button: False if pe_status == "running" and agent_uptime else True,
            screen.agent_run_puppet_button: False if pe_status == "running" and agent_uptime else True,
            screen.agent_terminal_button: False if agent_uptime else True,
            screen.agent_demo_button: False if agent_uptime else True,
        }    
        if pe_status == "running":
            pe_status_icon = "icons/puppet.png"
        elif pe_status == "loading":
            pe_status_icon = "icons/wait.png"
        else:
            pe_status_icon = "icons/disabled.png"

        # buttons
        for key in actions_disabled:
            if not hasattr(key, 'busy') or not key.busy:
                # protect us from altering buttons that are busy doing something
                key.disabled = actions_disabled[key]
        
        # docker daemon
        screen.docker_status_button.background_normal = daemon_icon

        # pe status
        screen.pe_status_button.background_normal = pe_status_icon


# non-class logger
logger = logging.getLogger(__name__)
try:
    app = PeKitApp()
    app.run()
    
    # delete the logfile on succesful exit
    os.unlink(logfile)
except KeyboardInterrupt:
    # signal all treads to stop
    logger.error("someone pressed ctrl+c - exit")
    app.controller.running = False
    
    # delete the logfile on succesful exit
    os.unlink(logfile)    
except Exception as e:
    app.controller.running = False
    logger.exception(e)
    logger.error(
        "Unknown error (fatal) Error messages saved to logfile {logfile}".format(
            logfile=logfile
        )
    )
