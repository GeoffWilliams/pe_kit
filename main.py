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
import platform
from settings import Settings
from requests.auth import HTTPBasicAuth

class DockerMachine():
    """
    DockerMachine

    Control the default docker-machine instance (boot2docker)
    """

    logger = logging.getLogger(__name__)
    
    # is a start/stop operation in progress?
    in_progress = False
    platform = platform.system()

    def __init__(self):
        self.logger.info("adjusted path for /usr/local/bin")
        os.environ['PATH'] = "/usr/local/bin/:" + os.environ['PATH']

    def boot2docker(self):
        """Everyone except Linux needs to use boot2docker/docker machine"""
        return not self.platform == "Linux"

    def status(self):
        try:
            if self.boot2docker():
                self.logger.debug("boot2docker mode")
                status = subprocess.check_output(["docker-machine", "status"]).strip()
            else:
                self.logger.debug("native mode")
                # we're good as long as we get exit status 0.  Non zero ends in exception
                subprocess.check_output(["docker", "version"])
                status = "Running"
        except subprocess.CalledProcessError as e:
                status = "Error"
        self.logger.info("docker (machine|daemon) status: " + status)
        return status

    def start(self):
        # start the daemon if its not already running
        started = False
        try:
            if not self.in_progress and self.status() != "Running":
                if self.boot2docker():
                    self.in_progress = True
                    self.logger.debug("starting docker-machine...")
                    out = subprocess.check_output(["docker-machine", "start"])
                    self.logger.debug("...done starting docker-machine")
                    self.in_progress = False

                    if self.status() == "Running":
                        self.logger.info("docker-machine started OK")
                        started = True
                else:
                    self.logger.error("Docker daemon needs to be started by super-user")
            else:
                started = True

            # setup the docker environment variables if we managed to start the daemon
            if started and self.boot2docker():
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

class ImagesScreen(Screen):
    """
    Images Screen
    
    Screen for managing images
    """
    
    logger = logging.getLogger(__name__)
    master_image_management_layout      = ObjectProperty(None)
    agent_image_management_layout       = ObjectProperty(None)
    settings                            = Settings()
    
    def __init__(self, **kwargs):
        super(ImagesScreen, self).__init__(**kwargs)
        self.controller = Controller()
        
    def on_start(self):
        # periodically refresh the image managment grid if we need to
        Clock.schedule_interval(self.update_image_managment, 1)
        
        # scrollable image list for images (agent and master)
        self.master_image_management_layout.bind(
            minimum_height= self.master_image_management_layout.setter('height'))
        self.agent_image_management_layout.bind(
            minimum_height=self.agent_image_management_layout.setter('height'))
        
    def on_enter(self):
        self.logger.debug("update image screen")
        self.update_image_managment(force_refresh=True)

    def back(self):
        """save settings and go back"""
        self.settings.master_selected_image     = App.get_running_app().get_master_selected_image()
        self.settings.agent_selected_image      = App.get_running_app().get_agent_selected_image()

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
            def delete_image_callback():
                try:
                    self.controller.delete_image(button.image_name)
                except docker.errors.APIError as e:
                    if e.response.status_code == 409:
                        message = "Cannot delete image while it is still in use"
                    else:
                        message = "Cannot delete image, please check log for info"
                    App.get_running_app().error(message)
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
                    "Image:\n\n {image_name}\n\n is downloading, cancel?".format(
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
                    yes_callback=delete_image_callback
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
            if self.settings.use_latest_image:
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

    def update_image_managment(self, x=None, force_refresh=False):
        """refresh the lists of images on the settings page.  The .kv file forces"""
        if self.controller.images_refreshed or force_refresh:
          
            # refresh selected agent in settings once GUI is ready
            if self.settings.use_latest_image:
                self.settings.master_selected_image = App.get_running_app().get_master_selected_image()
                self.settings.agent_selected_image = App.get_running_app().get_agent_selected_image()
            
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
            
            if self.controller.inital_setup_complete:
                self.logger.debug("marking GUI ready")
                self.controller.gui_ready = True


class SettingsScreen(Screen):
    """
    Settings Screen

    Screen for saving settings
    """

    logger = logging.getLogger(__name__)
    hub_address_textinput               = ObjectProperty(None)
    hub_password_textinput              = ObjectProperty(None)
    # hub_address_textinput               = ObjectProperty(None)
    use_latest_images_checkbox          = ObjectProperty(None)
    start_automatically_checkbox        = ObjectProperty(None)
    provision_automatically_checkbox    = ObjectProperty(None)
    kill_orphans_checkbox               = ObjectProperty(None)
    download_images_layout              = ObjectProperty(None)
    master_selected_image_button        = ObjectProperty(None)
    shutdown_on_exit_checkbox           = ObjectProperty(None)
    expose_ports_checkbox               = ObjectProperty(None)
    settings                            = Settings()


    def __init__(self, **kwargs):
        super(SettingsScreen, self).__init__(**kwargs)
        self.controller = Controller()

    def on_start(self):
        self.hub_username_textinput.text                = self.settings.hub_username
        self.hub_password_textinput.text                = self.settings.hub_password
        # self.hub_address_textinput.text                 = self.settings.hub_address
        self.use_latest_images_checkbox.active          = self.settings.use_latest_image
        self.start_automatically_checkbox.active        = self.settings.start_automatically
        self.provision_automatically_checkbox.active    = self.settings.provision_automatically
        self.kill_orphans_checkbox.active               = self.settings.kill_orphans
        self.shutdown_on_exit_checkbox.active           = self.settings.shutdown_on_exit
        self.expose_ports_checkbox.active               = self.settings.expose_ports
        
    def back(self):
        """save settings and go back"""
        self.settings.hub_username              = self.hub_username_textinput.text
        self.settings.hub_password              = self.hub_password_textinput.text
        # self.settings.hub_address               = self.hub_address_textinput.text
        self.settings.use_latest_image          = self.use_latest_images_checkbox.active
        self.settings.start_automatically       = self.start_automatically_checkbox.active
        self.settings.provision_automatically   = self.provision_automatically_checkbox.active
        self.settings.kill_orphans              = self.kill_orphans_checkbox.active
        self.settings.shutdown_on_exit          = self.shutdown_on_exit_checkbox.active
        self.settings.expose_ports              = self.expose_ports_checkbox.active

        # commit changes
        self.logger.info("save settings:" + str(self.settings))
        self.settings.save()
        
        App.get_running_app().root.current = 'main'



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
    clean_certs_button              = ObjectProperty(None)
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
            webbrowser.open_new(self.controller.dockerbuild_url())

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
            elif exit_status == -1:
                error = True
                message = "Puppet run on {location} FAILED, Puppet not installed yet"
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
                message="Agent provisioned OK.  Don't forget to accept the certificate!"
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
        
    def clean_certs(self):
        def clean():
            master_cleaned, agent_cleaned = self.controller.clean_certs()
            message = []
            if master_cleaned:
                message.append("Agent certificate purged from master")
            if agent_cleaned:
                message.append("SSL certificates purged from agent")

            if not message:
                message.append("No changes made, containers running?")

            App.get_running_app().info("\n".join(message))
            self.free_button(self.clean_certs_button)
            
        self.busy_button(self.clean_certs_button)
        threading.Thread(target=clean).start()


class MenuScreen(Screen):        
    """
    MenuScreen
    
    Simple menu of helpful links
    """
    settings = Settings()
    
    def __init__(self, **kwargs):
        super(MenuScreen, self).__init__(**kwargs)
       
    def help(self):
        webbrowser.open_new("https://github.com/{gh_repo}/blob/master/doc/help.md#pe_kit-help".format(
            gh_repo=self.settings.gh_repo))
    
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
        
class AboutScreen(Screen):
    """The about screen/dialogue"""
    license_label = ObjectProperty(None)
        
    def __init__(self, **kwargs):
        super(AboutScreen, self).__init__(**kwargs)
        
    def on_start(self):
        self.license_label.text = open(
            os.path.dirname(os.path.abspath(__file__)) + os.path.sep + "license_header.txt"
        ).read()

        
    
# borg class, see http://code.activestate.com/recipes/66531-singleton-we-dont-need-no-stinkin-singleton-the-bo/
class Controller:
    """
    Controller
    
    Separate off the control functions to remove dependency on kivy
    """
    __shared_state = {}

    logger = logging.getLogger(__name__)
    settings = Settings()
    
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
            "image_name": settings.master_image,
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
            "image_name": settings.agent_image,
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
    app = None
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
    
    # Flag to indicate inital image list and setup is complete
    inital_setup_complete = False
    
    # Flag to indicate the GUI is live an selections in the settings
    # object have been parsed in
    gui_ready = False
    
    # Docker hub token - store to access multiple repos
    #token = None

    def __init__(self):
        self.__dict__ = self.__shared_state
        
    def pe_url(self):
        try:
            url = self.container["master"]["urls"]["443/tcp"]
        except KeyError:
            url = None
        return url
    
    def dockerbuild_url(self):
        try:
            url = self.container["master"]["urls"]["9000/tcp"]
        except KeyError:
            url = None
        return url
    
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
                code = urllib2.urlopen(self.pe_url(), context=ctx, timeout=5).getcode()
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
                    self.logger.info("killing orphaned container: " + container["name"])
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

    def bridge_ip(self):
        """Get the IP address of the bridge if we are on linux"""
        networks = self.cli.networks(names=["bridge"])
        self.logger.debug(networks)
        ip = networks[0]["IPAM"]["Config"][0]["Gateway"]
        return ip

    def docker_init(self):
        #  boot2docker specific hacks in use - see:  http://docker-py.readthedocs.org/en/latest/boot2docker/

        self.dm = DockerMachine()
        if self.dm.start():
            if self.dm.boot2docker():
                kwargs = kwargs_from_env()
                if 'tls' not in kwargs:
                    # daemon not setup/running.  Sleep here to allow the render thread to catch up if
                    # we have just started otherwise there will be no app available to display the errors
                    time.sleep(1)
                    App.get_running_app().error("Docker could not be started, please check your system")
                else:
                    # docker ok
                    kwargs['tls'].assert_hostname = False

                    # save the boot2docker IP for use when we open browser windows
                    self.docker_url = kwargs['base_url']

                self.cli = Client(**kwargs)

            else:
                self.cli = Client(base_url='unix://var/run/docker.sock')
                self.docker_url = "https://{bridge_ip}".format(bridge_ip=self.bridge_ip())
            self.logger.info("Docker URL: " + self.docker_url)
 
            # stop any existing container (eg if we were killed)
            self.cleanup_container(self.container["agent"])
            self.cleanup_container(self.container["master"])

            # login to docker hub to get private image listings
            if not self.hub_login():
                self.app.error(
                    "Unable to login to registry at {hub_address}, please check details".format(
                        hub_address=self.settings.hub_address
                    )
                )

            # update downloadble and local images on the settings page
            self.refresh_images()
            
            # proceed to startup
            self.autostart_containers()

        else:
            # no docker machine
            self.app.error("Unable to start docker :*(")

    def hub_login(self):
        """
        Login to docker hub.  Return true on success otherwise false.
        This allows the CLI object to do stuff with the private hub images.  We still
        need to do our own separate authentication for docker hub API calls to get a 
        list of image tags since this isn't possible using the client
        """
        status = False
        if self.settings.hub_username and self.settings.hub_password and self.settings.hub_address:
            self.logger.info("Logging in to docker hub...(WARNING - this takes a while to fail)")
            try:
                login_result = self.cli.login(
                    self.settings.hub_username, 
                    password=self.settings.hub_password, 
                    registry=self.settings.hub_address,
                )
                self.logger.debug("LOGIN result " + str(login_result))
                if login_result and login_result["Status"] == 'Login Succeeded':
                    status = True
                else:
                    status = False
            except docker.errors.APIError as e:
                self.logger.exception(e)
                self.logger.error("Error logging in to hub - see previous error")

            self.logger.info("...login done! status={status}".format(status=status))
        else:
            self.logger.info("Not logging into docker hub - missing credentials in settings")
        return status

    def autostart_containers(self):
        if self.settings.start_automatically:
            self.logger.info("starting PE and agent containers automatically...")
            while self.running and (not self.inital_setup_complete or not self.gui_ready):
                self.logger.debug("waiting for inital_setup_complete...")
                time.sleep(1)
            self.logger.info("Finished waiting for GUI to start, booting containers...")
            self.start_pe()
            self.start_agent()
            if self.settings.provision_automatically:
                self.logger.debug("provisioning puppet agent automatically...")
                threading.Thread(target=self.auto_provision).start()


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
            except (requests.exceptions.ConnectionError, requests.exceptions.ReadTimeout):
                self.logger.error("requests (wrapped urllib3) error talking to docker daemon")
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

    def stop_all_docker_containers(self):
        for container in self.container:
            self.stop_docker_container(self.container[container])

    def stop_docker_container(self, container):
        # check we are still alive as this also gets called when we shut down
        if self.container_alive(container):
            self.logger.info("stopping container " + container["name"])
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
        """ start agent container """        
        return self.start_container(
            self.container["agent"], 
            self.settings.agent_selected_image)
    
    def start_pe(self):
        """ Start PE """
        return self.start_container(
            self.container["master"], 
            self.settings.master_selected_image)
        
    def start_container(self, container, image_name):
        status = False
        if self.container_alive(container):
            status = True
        else:
            if image_name:
                self.logger.info("Starting container {name} using {image}".format(
                    name=container["name"],
                    image=image_name
                ))
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
            downloadable_images, newest_downloadable = self.update_downloadable_images(container)

            # set flag here and pick it up in the render code
            if newest_downloadable > newest_local:
                self.update_available = True

            container["images"] = self.combine_image_list(container["local_images"], downloadable_images)
        self.logger.debug("marking initial_setup_complete")
        
        # flag to indicate we have been setup at least ONCE after startup
        self.inital_setup_complete = True
        
        # flag to indicate the GUI should be refreshed (gets set false after repaint)
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
            
            # move any 3.8x images to the end of the list otherwise they
            # will have been sorted to the start of the list
            i = 0
            while i < len(local_images):
                # move any images not starting with :201x to the end of the list
                # should be good for 4 years... 
                if ":201" not in local_images[0]:
                    local_images.append(local_images.pop(0))
                i += 1
            
        if len(local_images):
            newest_image = local_images[0]
        else:
            newest_image = None
        self.logger.info("Found {count} local images for {image_name}".format(
            count=len(local_images),
            image_name=container["image_name"]
        ))
        return local_images, newest_image

    
    # How to do authentication to/from the docker API borrowed from 
    # http://www.cakesolutions.net/teamblogs/docker-registry-api-calls-as-an-authenticated-user
    #
    # Can't for the life of me figure out how to use the V2 api to do this on the public 
    # forge against a private image.  Giving up for now, keeping code since might be useful...
    #
#    def hub_token(self, user, password, service, scope, realm):
#        if self.token:
#            token = self.token
#        else:
#            data = {
#                "scope": "repository:" + scope, 
#                "service":  service, 
#                "account": user, 
#                "client_id": "https://github.com/GeoffWilliams/pe_kit"
#            }
#            self.logger.debug("Auth_data: " + str(data))
#            r = requests.get(
#                "https://auth.docker.io/token", 
#                auth=HTTPBasicAuth(user, password), 
#                data=data, 
#                timeout=5
#            )
#
#            token=json.loads(str(r.content))["token"]
#            self.token = token
#
#        self.logger.debug("Obtained token: " + token)
#        return token
#    
#    def hub_request(self, api_url, token=None):
#        if token:
#            headers = {'Authorization':'Bearer ' + token}
#        else:
#            headers = {}
#        response = requests.get(api_url, headers=headers, timeout=5)
#        return response
#    
#    def hub_api(self, api_url, user, password, service, scope, realm):
#        # first make the request unuathenticated
#        self.logger.debug("making initial request for: " + api_url)
#        response = self.hub_request(api_url)
#        data = False
#        if response.status_code != 200:
#            self.logger.debug("non-successful status for: " + api_url)
#            print(">>>>>>>>>>>>>>" + str(response.content))
#            #{"errors":[{"code":"UNAUTHORIZED","message":"authentication required","detail":[{"Type":"repository","Name":"geoffwilliams/pe_master_public_lowmem_r10k_dockerbuild","Action":"pull"}]}]}
#            if 'Www-Authenticate' in response.headers:
#                # if we reach this, we need to authenticate...
#                self.logger.info("Hub says authentication required...")
#                #challenge = error.info()['Www-Authenticate']
#                #print "******************" + str(challenge)
#                
#                # authenticate and re-try
#                token = self.hub_token(user, password, service, scope, realm)
#                response = self.hub_request(api_url, token)
#                
#                if response.status_code == 200:
#                    self.logger.debug("200 OK - authenticated")
#                    data = json.loads(str(response.content))
#                else:
#                    self.logger.error("Invalid response from docker hub: " + str(response.content))
#                
#            else:
#                self.logger.info("HTTP error from docker hub: " + response.content)
#        else:
#            data = json.loads(str(response.content))
#        return data

    
    # images available for download
    def update_downloadable_images(self, container):
        """
        re-create the list of image tags available for download.  Updates
        self.master_downloadable_images to be a list of the available tags (strings)
        """
        self.logger.debug("checking for remote images")
        downloadable_images = []
        try:
            # V2 API doesn't seem to support looking up tags for private images, cannot 
            # find any documentation. Also note - trailing slash on v1 api is a 404
            response = requests.get(
                "https://registry.hub.docker.com/v1/repositories/{image_name}/tags".format(
                    image_name = container["image_name"]
                ), 
                auth=HTTPBasicAuth(self.settings.hub_username, self.settings.hub_password),
                timeout=5
            )
            if response.status_code == 200:
                images = json.loads(str(response.content))

                if images:
                    for tags in images: # <<<V1 | V2>>> images["results"]:
                        # if image is already downloaded, don't list it as available for download
                        image_name = container["image_name"] + ":" + tags["name"]
                        self.logger.info("checking status of remote image " + image_name)
                        if not self.tag_exists_locally(image_name):
                            downloadable_images.append(image_name)
            else:
                self.logger.error("Error from docker hub - image accessible and hub up?" + str(response))
        except requests.exceptions.ConnectionError as e:
            self.logger.exception(e)
            self.logger.error("failed to reach docker hub - no internet?")
        downloadable_images.sort(reverse=True)
        
        if len(downloadable_images):
            newest_image = downloadable_images[0]
        else:
            newest_image = None
            
        self.logger.debug("finished checking remote images")
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
    
    def auto_provision(self):
        self.logger.info("starting auto provision thread...")
        provisioned = False
        while not provisioned and self.running:
            if (self.container_alive(self.container["agent"]) and       
                    self.container_alive(self.container["master"]) and
                    self.pe_status() == "running"):
                    
                # can only provision when PE is running and agent is alive
                self.complete_provision()
                provisioned = True
            else:
                time.sleep(1)
        self.logger.info("...auto provisioning complete (or thread exiting...)!")

                
    def complete_provision(self):
        """Provision agent, sign cert, run puppet on agent - AIO"""
        self.logger.info("provisioning agent...")
        self.agent_provision()
        self.logger.info("signing agent cert on master...")
        self.docker_exec(self.container["master"],"puppet cert sign {host}".format(
            host=self.container["agent"]["host"]
            ))
        self.logger.info("running puppet on agent...")
        self.run_puppet(self.container["agent"])
        self.logger.info("...provisioning complete! :D")
        
        
    def agent_provision(self):
        """Install puppet on agent - you need to accept and run puppet manually"""
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

    def clean_certs(self):
        """Delete agent cert from master and all certs from agent to allow reprovisioning"""
        agent_cleaned = False
        master_cleaned = False
        
        # purge agent cert from master
        if self.container_alive(self.container["master"]):
            if self.pe_status() == "running":
                # can only purge from puppet console if master is running or we get
                # PDB error
                cmd = "puppet node purge {host}"
            else:
                # no PDB..? we can still make reprovision work by doing cert clean...
                cmd = "puppet cert clean {host}"
            self.docker_exec(
                self.container["master"], 
                cmd.format(
                    host=self.container["agent"]["host"]
                )
            )
            master_cleaned = True

        # agent
        if self.container_alive(self.container["agent"]):
            cmd = "rm -rf /etc/puppetlabs/puppet/ssl"
            self.docker_exec(self.container["agent"], cmd)
            agent_cleaned = True
            
        return master_cleaned, agent_cleaned
        
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
    __version__ = "v0.3.1"
    
    def check_update(self):
        """check for new release of the app"""
        try:
            r = json.loads(
                urllib2.urlopen(
                    "https://api.github.com/repos/{gh_repo}/releases".format(
                        gh_repo=self.settings.gh_repo,
                    ), 
                    timeout=5
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

        # setup the settings and about screens
        self.root.get_screen("images").on_start()        
        self.root.get_screen("settings").on_start()
        self.root.get_screen("about").on_start()

        # monitor the docker daemon and container
        Clock.schedule_interval(self.daemon_monitor, 1)
        
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
            self.info("stopping all docker containers")
            self.controller.stop_all_docker_containers()

            
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
                
                # handle nothing selected yet
                selected = None
                for member in group:
                    self.logger.debug("state is: " + member.state)
                    if member.state == 'down':
                        selected = member.image_name
            except IndexError as e:
                selected = None
        self.logger.debug("get_selected_image() returns {selected}".format(selected=selected))
        return selected

    def error(self, message):
        self.logger.error(message)
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
        self.logger.info(message)
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
        daemon_up = False

        if self.controller.daemon_status == "running":
            self.logger.debug("docker daemon ok :)")            
            daemon_icon = "icons/ok.png"
            daemon_up = True

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
            screen.clean_certs_button: False if pe_status == "running" or pe_status == "loading" or agent_uptime else True,
            screen.dockerbuild_button: False if pe_status == "running" or pe_status == "loading" else True,
            
            screen.agent_provision_button: False if pe_status == "running" and agent_uptime else True,
            screen.agent_run_puppet_button: False if pe_status == "running" and agent_uptime else True,
            screen.agent_terminal_button: False if agent_uptime else True,
            screen.agent_demo_button: False if agent_uptime else True,
            
            # FIXME more responsive here please
            screen.master_container_delete_button: False if daemon_up and self.controller.gui_ready else True,
            screen.agent_container_delete_button: False if daemon_up and self.controller.gui_ready else True,
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
