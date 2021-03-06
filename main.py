#!/usr/bin/env python2.7
#
# Copyright 2017 Geoff Williams for Declarative Systems PTY LTD
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
import calendar
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
logging.getLogger("requests").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)

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
import docker
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
from kivy.properties import ObjectProperty, BooleanProperty
import dateutil.parser
import datetime
import ssl
import textwrap
from functools import partial
import platform
from settings import Settings
from requests.auth import HTTPBasicAuth
import requests
import shutil
import argparse

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
    licence_file_textinput              = ObjectProperty(None)
    use_latest_images_checkbox          = ObjectProperty(None)
    start_automatically_checkbox        = ObjectProperty(None)
    provision_automatically_checkbox    = ObjectProperty(None)
    kill_orphans_checkbox               = ObjectProperty(None)
    download_images_layout              = ObjectProperty(None)
    master_selected_image_button        = ObjectProperty(None)
    shutdown_on_exit_checkbox           = ObjectProperty(None)
    expose_ports_checkbox               = ObjectProperty(None)
    shared_dir_textinput                = ObjectProperty(None)
    settings                            = Settings()


    def __init__(self, **kwargs):
        super(SettingsScreen, self).__init__(**kwargs)
        self.controller = Controller()

    def on_start(self):
        self.hub_username_textinput.text                = self.settings.hub_username
        self.hub_password_textinput.text                = self.settings.hub_password
        self.hub_address_textinput.text                 = self.settings.hub_address
        self.licence_file_textinput.text                = self.settings.licence_file
        self.use_latest_images_checkbox.active          = self.settings.use_latest_image
        self.start_automatically_checkbox.active        = self.settings.start_automatically
        self.provision_automatically_checkbox.active    = self.settings.provision_automatically
        self.kill_orphans_checkbox.active               = self.settings.kill_orphans
        self.shutdown_on_exit_checkbox.active           = self.settings.shutdown_on_exit
        self.expose_ports_checkbox.active               = self.settings.expose_ports
        self.shared_dir_textinput.text                  = self.settings.shared_dir if self.settings.shared_dir else ''

    def back(self):
        """save settings and go back"""
        self.settings.hub_username              = self.hub_username_textinput.text
        self.settings.hub_password              = self.hub_password_textinput.text
        self.settings.hub_address               = self.hub_address_textinput.text
        self.settings.licence_file              = self.licence_file_textinput.text
        self.settings.use_latest_image          = self.use_latest_images_checkbox.active
        self.settings.start_automatically       = self.start_automatically_checkbox.active
        self.settings.provision_automatically   = self.provision_automatically_checkbox.active
        self.settings.kill_orphans              = self.kill_orphans_checkbox.active
        self.settings.shutdown_on_exit          = self.shutdown_on_exit_checkbox.active
        self.settings.expose_ports              = self.expose_ports_checkbox.active
        self.settings.shared_dir                = self.shared_dir_textinput.text if  self.shared_dir_textinput.text else False

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

    MONITOR_THREAD_INTERVAL = 1

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

    # Status of PE last time we checked
    last_status = None

    def __init__(self):
        # CLI to overide settings - must be done before brain is sucked out!
        self.master_image = False
        self.agent_image = False
        self.provision_automatically = True
        self.onceover_dir = False
        self.__dict__ = self.__shared_state


    def pe_url(self):
        try:
            url = self.container["master"]["urls"]["443/tcp"]
        except KeyError:
            url = None
        return url

    def demo_url(self):
        return self.container["agent"]["urls"]["9090/tcp"]

    def bash_cmd(self, cmd):
        """docker exec commands must be wrapped in bash -c or they fail due
        to not being run from the shell"""

        # login to get a full bash shell due to puppet enterprise's insane paths
        return "bash --login -c \"{cmd}\"".format(cmd=cmd)

    def fix_hosts_cmd(self):
        return self.bash_cmd("grep {fqdn} /etc/hosts || echo '{pm_ip} {fqdn} {short_name}' >> /etc/hosts".format(
            pm_ip=self.pm_ip(),
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
            for line in self.ll_cli.pull(
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
            time.sleep(self.MONITOR_THREAD_INTERVAL)

    def pe_status(self):
        """return status of PE master: running, loading, stopped"""

        # turn off SSL cert verifcation since we're using puppets self-signed certs
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

        if self.pe_url():
            try:
                code = urllib2.urlopen(self.pe_url(), context=ctx, timeout=self.MONITOR_THREAD_INTERVAL * 0.2).getcode()
                if code == 200:
                    message = "puppet up and running :D"
                    status = "running"
                else:
                    message = "puppet loading..."
                    status = "loading"
            except urllib2.HTTPError as e:
                message = "puppet http server error: {message} code: {code}".format(
                  message=e.reason,
                  code=e.code
                )
                status = "loading"
            except urllib2.URLError as e:
                message = "puppet stopped/unreachable at {pe_url}:  {message}".format(
                  pe_url=self.pe_url(),
                  message=e.reason,
                )
                status = "loading"
            except ssl.SSLError as e:
                message = "puppet SSL timeout at {pe_url}:  {message}".format(
                  pe_url=self.pe_url(),
                  message=str(e),
                )
                status = "loading"
        else:
            status = "error"
            message = "error"

        if self.last_status != status:
            self.logger.debug("Status change: " + message)

        self.last_status = status
        return status

    def cleanup_container(self, container):
        """on-startup cleanup of orphaned containers (if requested)"""
        try:
            if self.ll_cli.inspect_container(container["name"]):
                if self.settings.kill_orphans:
                    self.logger.info("killing orphaned container: " + container["name"])
                    self.ll_cli.remove_container(container["name"], force=True)
                else:
                    self.logger.info("inspecting existing container")
                    container["instance"] = self.ll_cli.inspect_container(
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

    def pm_ip(self):
        """Get the IP address of the puppetmaster VM - only reachable from other docker containers"""
        inspection = self.ll_cli.inspect_container(Controller.container["master"]["name"])
        ip = inspection['NetworkSettings']['Networks']['bridge']['IPAddress']
        return ip

    def docker_init(self):
        self.cli = docker.DockerClient(base_url='unix://var/run/docker.sock')
        self.ll_cli = docker.APIClient(base_url='unix://var/run/docker.sock')
        self.docker_url = "https://{bridge_ip}".format(bridge_ip='localhost')
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
                    username=self.settings.hub_username,
                    password=self.settings.hub_password,
                    registry='https://index.docker.io/v1', #self.settings.hub_address,
                )
                self.logger.debug("LOGIN result " + str(login_result))
                if login_result:
                    if 'username' in login_result:
                      self.logger.info('already logged in...')
                      status = True
                    elif ('Status' in login_result and
                          login_result["Status"] == 'Login Succeeded'):
                      self.logger.info('logged in ok')
                      status = True
                    else:
                      self.logger.info('hub login failed')
                      status = False
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

            # Always fix /etc/hosts
            self.docker_exec(self.container["agent"], self.fix_hosts_cmd())

            # CLI + settings...
            if self.provision_automatically and self.settings.provision_automatically:
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
                inspection = self.ll_cli.inspect_container(container["name"])
                if inspection["State"]["Status"] == "running":
                    started = calendar.timegm(
                      dateutil.parser.parse(inspection["State"]["StartedAt"]).timetuple())
                    now = calendar.timegm(datetime.datetime.utcnow().timetuple())

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
            self.ll_cli.remove_container(container=container["instance"].get('Id'), force=True)

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
            8170: 8170 if self.settings.expose_ports else None,
            9000: None,
            61613: 61613 if self.settings.expose_ports else None,
            61616: None,
        }

    def agent_port_bindings(self):
        return {
            80: None,
            9090: None,
        }

    def start_agent(self):
        """ start agent container """
        if self.agent_image:
            self.logger.info("Using agent image: " + self.agent_image)
            self.container["agent"]["image_name"] = self.agent_image

        return self.start_container(
            self.container["agent"],
            self.agent_image or self.settings.agent_selected_image,
        )

    def start_pe(self):
        """ Start PE """
        status = self.start_container(
            self.container["master"],
            self.master_image or self.settings.master_selected_image,
        )

        if status and self.disable_puppet_on_master:
            self.disable_puppet(self.container["master"])

        if status and self.settings.licence_file:
            self.install_licence()

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

                volumes = [
                    '/sys/fs/cgroup',
                ]
                volume_map = {
                    '/sys/fs/cgroup': {
                        'bind': '/sys/fs/cgroup',
                        'mode': 'ro',
                    },
                }
                if self.settings.shared_dir:
                    shared_dir_path = os.path.abspath(
                        os.path.expanduser('~') + '/' + self.settings.shared_dir)
                    if not os.path.exists(shared_dir_path):
                        os.mkdir(shared_dir_path)
                    volume_map[os.path.abspath(shared_dir_path)] = {
                        'bind': '/shared',
                        'mode': 'rw',
                    }
                    volumes.append('/shared')

                if self.onceover_dir:

                    # /testcase
                    volume_map[os.path.abspath(onceover_dir)] = {
                        'bind': '/testcase',
                        'mode': 'ro',
                    }
                    volumes.append("/testcase")

                    # /etc/puppetlabs/code/environments/production/modules
                    volume_map[os.path.abspath(onceover_dir) + "/.onceover/etc/puppetlabs/code/environments/production/modules"] = {
                        'bind': '/etc/puppetlabs/code/environments/production/modules',
                        'mode': 'ro',
                    }
                    volumes.append("/etc/puppetlabs/code")

                    # /etc/puppetlabs/environments/production/manifests/site.pp (mock takes precidence)
                    volume_map[
                        Utils.first_existing_file([
                            os.path.abspath(onceover_dir) + "/spec/site.pp",
                            os.path.abspath(onceover_dir) + "/manifests/site.pp"]
                        )
                    ] = {
                        'bind': '/etc/puppetlabs/code/environments/production/manifests/site.pp',
                        'mode': 'ro',
                    }
                    volumes.append("/etc/puppetlabs/code/environments/production/manifests/site.pp")

                    # /etc/puppetlabs/environments/production/hiera.yaml
                    volume_map[
                        Utils.first_existing_file([
                            os.path.abspath(onceover_dir) + "/spec/hiera.yaml",
                            os.path.abspath(onceover_dir) + "/hiera.yaml"]
                        )
                    ] = {
                        'bind': '/etc/puppetlabs/code/environments/production/hiera.yaml',
                        'mode': 'ro',
                    }
                    volumes.append("/etc/puppetlabs/code/environments/production/hiera.yaml")

                    # /etc/puppetlabs/environments/production/environment.conf
                    volume_map[os.path.abspath(onceover_dir) + "/environment.conf"] = {
                        'bind': '/etc/puppetlabs/code/environments/production/environment.conf',
                        'mode': 'ro',
                    }
                    volumes.append("/etc/puppetlabs/code/environments/production/environment.conf")

                    # /etc/puppetlabs/environments/production/scripts
                    volume_map[os.path.abspath(onceover_dir) + "/scripts"] = {
                        'bind': '/etc/puppetlabs/code/environments/production/scripts',
                        'mode': 'ro',
                    }
                    volumes.append("/etc/puppetlabs/code/environments/production/scripts")


                    # /etc/puppetlabs/environments/production/data
                    volume_map[os.path.abspath(onceover_dir) + "/data"] = {
                        'bind': '/etc/puppetlabs/code/environments/production/data',
                        'mode': 'ro',
                    }
                    volumes.append("/etc/puppetlabs/code/environments/production/data")

                    # /etc/puppetlabs/environments/production/site
                    volume_map[os.path.abspath(onceover_dir) + "/site"] = {
                        'bind': '/etc/puppetlabs/code/environments/production/site',
                        'mode': 'ro',
                    }
                    volumes.append("/etc/puppetlabs/code/environments/production/site")

                # security_opt needed to be able to bind mount inside container: https://github.com/moby/moby/issues/16429
                host_config=self.ll_cli.create_host_config(
                    cap_add=['SYS_ADMIN', 'SYS_PTRACE', 'NET_ADMIN', 'NET_RAW'],
                    tmpfs={
                        '/tmp:exec': '',
                        '/run':'',
                        '/run/lock': '',
                    },
                    port_bindings=port_bindings,
                    binds=volume_map,
                    security_opt=["apparmor:unconfined"]
                )

                proceed = True
                try:
                    proceed = True
                    container["instance"] = self.ll_cli.create_container(
                      image=image_name,
                      name=container["name"],
                      hostname=container["host"],
                      detach=True,
                      volumes = volumes,
                      ports = port_bindings.keys(),
                      host_config=host_config,

                    )
                except docker.errors.APIError as e:
                    if e.response.status_code == 409:
                        self.logger.info(
                            "Container {name} already exists - starting it".format(
                                name=container["name"]))
                        container["instance"] = self.ll_cli.inspect_container(container["name"])
                    else:
                        proceed = False
                        self.logger.error("Unknown Docker error follows")
                        self.logger.exception(e)
                        self.app.error("Unknown Docker error:  " + str(e.explanation or e.message))
                if proceed:
                    id = container["instance"].get('Id')
                    self.logger.info("starting container " + id)
                    resp = self.ll_cli.start(container=id)
                    self.logger.info(container["instance"])
                    self.munge_urls(container)

                    status = True
            else:
                self.app.error("No image selected, check settings")

        return status

    def munge_urls(self, container):

        # inspect the container and get the port mapping
        container_info = self.ll_cli.inspect_container(container["instance"].get("Id"))
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
            docker_images = self.ll_cli.images()
            print(docker_images)
            for docker_image in docker_images:
                if docker_image["RepoTags"]:
                    # RepoTags contains all the names by which this image is known
                    for image_alias in docker_image["RepoTags"]:
                        if image_alias.startswith(container["image_name"]):
                            local_images.append(image_alias)
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


    def docker_hub_image_tags(self, username, password, repo):
        """Get the list of tags for a given image on docker hub """

        # token
        r = requests.post(
            self.settings.hub_address + '/v2/users/login/',
            json={'password': password, 'username': username},
            headers={
              'Accept': 'application/json',
              'Content-Type': 'application/json'},
            timeout=5)
        if r.status_code == requests.codes.ok:
            token = 'JWT ' + r.json()['token']
            r = requests.get(
                self.settings.hub_address + '/v2/repositories/' + repo + '/tags',
                headers={'Authorization': token},
                timeout=5)
            result = r.json()['results']
        else:
            result = []
            self.logger.error('docker hub login failed' + str(r))
            App.get_running_app().error("Unable to obtain Docker Hub token, check connectivity and username/password")

        return result


    # images available for download
    def update_downloadable_images(self, container):
        """
        re-create the list of image tags available for download.  Updates
        self.master_downloadable_images to be a list of the available tags (strings)
        """
        self.logger.debug("checking for remote images")
        downloadable_images = []
        if self.settings.hub_username and self.settings.hub_password:
            try:
                images = self.docker_hub_image_tags(
                self.settings.hub_username,
                self.settings.hub_password,
                container["image_name"])

                if images:
                    for tags in images:
                        # if image is already downloaded, don't list it as available for download
                        image_name = container["image_name"] + ":" + tags["name"]
                        self.logger.info("checking status of remote image " + image_name)
                        if not self.tag_exists_locally(image_name):
                            downloadable_images.append(image_name)
                else:
                    self.logger.error("Error from docker hub - image accessible and hub up?")
                downloadable_images.sort(reverse=True)
            except requests.exceptions.ConnectionError as e:
                self.logger.exception(e)
                self.logger.error("failed to reach docker hub - no internet?")

        else:
            App.get_running_app().error("Please enter your Docker Hub username and password on the settings screen")
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
        local_images = self.ll_cli.images()
        while not found and i < len(local_images):
            if local_images[i]["RepoTags"]:
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

    def disable_puppet(self, container):
        """Disable the Puppet Agent"""
        return self.docker_exec(container, "puppet agent --disable")

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

        # wait for cert to arrive in puppetserver
        time.sleep(5)
        self.logger.info("signing agent cert on master...")
        self.docker_exec(self.container["master"],
            self.bash_cmd(
                "puppet cert sign {host} || puppetserver ca sign --certname {host}".format(
                    host=self.container["agent"]["host"]
            )))
        self.logger.info("running puppet on agent...")
        self.run_puppet(self.container["agent"])
        self.logger.info("...provisioning complete! :D")

    def install_licence(self):
        """Install user-provided licence file on the puppet master"""

        self.logger.debug("Installing licence file...")

        if os.path.isfile(self.settings.licence_file):
            # first copy the licence file to make sure it ends up with the right name
            licence_filename = 'license.key'
            licence_tempfile = '/tmp/' + licence_filename
            shutil.copyfile(self.settings.licence_file, licence_tempfile)

            # upload file to container (via tarball)
            self.upload_file(
                self.container["master"],
                licence_tempfile,
                "/etc/puppetlabs"
            )

            # remove tempfile
            self.logger.debug("licence uploaded, deleting tempfile")
            os.unlink(licence_tempfile)
        else:
             App.get_running_app().error(
                "Specified licence key file %(licence_file)s does not exist"
                % {'licence_file': self.settings.licence_file})

    def upload_file(self, container, local_path, remote_path):
        # Python tarfile module has to create filesystem objects so might as
        # well just create a tar file on the system
        f, tar_tmp = tempfile.mkstemp()
        self.logger.debug(
            "creating tarfile at %(tar_tmp)s containing %(local_path)s" % locals())
        subprocess.call(
            [
                "tar",
                "cvf", tar_tmp,
                "-C", os.path.dirname(local_path),
                os.path.basename(local_path)
        ])

        # reopen file and read binary
        os.close(f)
        tar_bytes = open(tar_tmp, "rb").read()

        # docker python api seems to only provide a way to upload files via tarballs
        container_name = container["name"]
        self.logger.debug(
            "Uploading tarball bytes to %(container_name)s at %(remote_path)s" % locals())
        self.cli.put_archive(container_name, remote_path, tar_bytes)
        os.remove(tar_tmp)

    def agent_provision(self):
        """Install puppet on agent - you need to accept and run puppet manually"""

        # curl script
        return self.docker_exec(self.container["agent"], self.curl_command())

    def docker_exec(self, container, cmd):
        """run a docker command on a container and return the exit status"""
        container_name = container["name"]
        self.logger.debug("container {container_name} running: {cmd}...".format(
            container_name=container_name,
            cmd=cmd,
        ))
        exec_instance = self.ll_cli.exec_create(
            container=container_name,
            cmd=cmd,
        )
        for line in self.ll_cli.exec_start(exec_instance, stream=True):
            if self.running:
                self.logger.debug(line)
            else:
                raise Exception("Aborting command because quit/cancel!")
        exit_code = self.ll_cli.exec_inspect(exec_instance["Id"])['ExitCode']
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
                # run the older PE command and fallback to the newer one if it fails
                cmd = "puppet cert clean {host} || puppetserver ca clean --certname {host}"
            self.docker_exec(
                self.container["master"],
                self.bash_cmd(cmd.format(
                    host=self.container["agent"]["host"]
                ))
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
    __version__ = "v0.6.0"
    error_messages = []
    info_messages = []

    def outdated(self, this_version, upstream_version):
        this = this_version.replace('v', '').split('.')
        upstream = upstream_version.replace('v', '').split('.')

        major = 0
        minor = 1
        patch = 2

        if this_version == upstream_version:
            outdated = False
        elif int(this[major]) > int(upstream[major]):
            outdated = False
        elif int(this[minor]) > int(upstream[minor]):
            outdated = False
        elif int(this[patch]) > int(upstream[patch]):
            outdated = False
        else:
            outdated = True

        return outdated

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
            if self.outdated(self.__version__, latest_tag):
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
        self.controller.onceover_dir = self.onceover_dir
        self.controller.disable_puppet_on_master = self.disable_puppet_on_master
        self.controller.master_image = self.master_image
        self.controller.agent_image = self.agent_image
        self.controller.provision_automatically = self.provision_automatically
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
        Clock.schedule_interval(self.message_monitor, 5)

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
        self.error_messages.append(message)

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
        self.info_messages.append(message)


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

    def message_monitor(self, x):
        """
        Called every second and displays info or warning messages from the main thread to prevent painting errors
        no need to iterate the whole array here since we get called every second anyway...
        """
        if len(self.error_messages):
            self.popup(title='Error!', message=self.error_messages.pop(0))
        if len(self.info_messages):
            self.popup(title='Information', message=self.info_messages.pop(0))


    def daemon_monitor(self, x):
        screen = self.root.get_screen("main")
        pe_status = "stopped"
        agent_uptime = False
        daemon_up = False

        if self.controller.daemon_status == "running":
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

parser = argparse.ArgumentParser("PE_Kit - instant PE")
parser.add_argument("--onceover-dir", default=False, help="Path to a control repository configured with onceover")
parser.add_argument("--disable-puppet-on-master", default=False, action="store_true", help="Disable running puppet on the puppet master")
parser.add_argument("--master-image", default=False, help="Image to run puppet master with")
parser.add_argument("--agent-image", default=False, help="Image to run puppet agent node with")
parser.add_argument("--no-auto-provision", action="store_true", default=False, help="Do not install the puppet agent")


args = parser.parse_args()
onceover_dir = args.onceover_dir
disable_puppet_on_master = args.disable_puppet_on_master
if onceover_dir and not os.path.isdir(onceover_dir):
    logger.error("%s specified by --onceover-dir does not exist" % onceover_dir)


try:
    app = PeKitApp()
    app.onceover_dir = onceover_dir
    app.disable_puppet_on_master = disable_puppet_on_master
    app.master_image = args.master_image
    app.agent_image = args.agent_image
    app.provision_automatically = not args.no_auto_provision
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
    if hasattr(app, 'controller'):
        app.controller.running = False
    logger.exception(e)
    logger.error(
        "Unknown error (fatal) Error messages saved to logfile {logfile}".format(
            logfile=logfile
        )
    )
