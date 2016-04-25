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
#import requests.packages.urllib3 as urllib3
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
    selected_image = None

    def __init__(self):
        self.__dict__ = self.__shared_state
        self.load()

    def save(self):
        self.config.set("main", "start_automatically", self.start_automatically)
        self.config.set("main", "kill_orphans", self.kill_orphans)
        self.config.set("main", "use_latest_image", self.use_latest_image)
        self.config.set("main", "shutdown_on_exit", self.shutdown_on_exit)
        self.config.set("main", "expose_ports", self.expose_ports)
        self.config.set("main", "selected_image", self.selected_image)

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
        self.selected_image = self.config.get("main", "selected_image")

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
    image_management_layout       = ObjectProperty(None)
    use_latest_image_checkbox     = ObjectProperty(None)
    start_automatically_checkbox  = ObjectProperty(None)
    kill_orphans_checkbox         = ObjectProperty(None)
    download_images_layout        = ObjectProperty(None)
    selected_image_button         = ObjectProperty(None)
    shutdown_on_exit_checkbox     = ObjectProperty(None)
    expose_ports_checkbox         = ObjectProperty(None)
    settings                      = Settings()


    def __init__(self, **kwargs):
        super(SettingsScreen, self).__init__(**kwargs)
        self.controller = Controller()

    def on_start(self):
        self.use_latest_image_checkbox.active     = self.settings.use_latest_image
        self.start_automatically_checkbox.active  = self.settings.start_automatically
        self.kill_orphans_checkbox.active         = self.settings.kill_orphans
        self.shutdown_on_exit_checkbox.active     = self.settings.shutdown_on_exit
        self.expose_ports_checkbox.active         = self.settings.expose_ports

        # periodically refresh the image managment grid if we need to
        Clock.schedule_interval(self.update_image_managment, 0.5)

    def back(self):
        """save settings and go back"""
        self.settings.use_latest_image    = self.use_latest_image_checkbox.active
        self.settings.start_automatically = self.start_automatically_checkbox.active
        self.settings.kill_orphans        = self.kill_orphans_checkbox.active
        self.settings.shutdown_on_exit    = self.shutdown_on_exit_checkbox.active
        self.settings.expose_ports        = self.expose_ports_checkbox.active
        self.settings.selected_image      = App.get_running_app().get_selected_image()

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

    def update_image_managment(self, x=None, force_refresh=False, ):
        def image_action(button):
            self.logger.info(
              "image action: {tag}, {status}".format(tag=button.tag, status=button.status))
            if button.status == "downloadable":
                # start download in own thread
                button.background_normal = "icons/download.png"
                threading.Thread(target=self.controller.download_image, args=[button.tag]).start()
            elif button.tag in self.controller.active_downloads:
                # currently downloading
                App.get_running_app().question(
                    "Image {tag} is downloading, cancel?".format(tag=button.tag),
                    yes_callback=partial(self.controller.stop_download, button.tag)
                )
            elif button.status == "local":
                # delete
                App.get_running_app().question(
                    "really delete image {tag}?".format(tag=button.tag), 
                    yes_callback=partial(self.controller.delete_image, button.tag)
                )
            
        if self.controller.images_refreshed or force_refresh:
            self.image_management_layout.clear_widgets()
            for image in self.controller.images:
                name_label = Label(text=image["name"])
                name_label.bind(size=name_label.setter('text_size'))
                name_label.halign = "left"
                status_button = self.get_image_button(image["status"])
                status_button.tag = image["name"]
                status_button.status = image["status"]
                status_button.bind(on_release=image_action)
                if self.use_latest_image_checkbox.active:
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
                        selected_button.group = "selected_image"
                        
                        selected_image = image["name"]
                        selected_button.image_name = selected_image
                        if selected_image == self.settings.selected_image:
                            selected_button.state = "down"
                    else:
                        # use a blank label as a spacer
                        selected_button = Label()

                self.image_management_layout.add_widget(name_label)
                self.image_management_layout.add_widget(status_button)
                self.image_management_layout.add_widget(selected_button)
            self.controller.images_refreshed = False

class MainScreen(Screen):
    """
    MainScreen

    The main screen of the application
    """

    logger = logging.getLogger(__name__)
    advanced_layout         = ObjectProperty(None)
    advanced_layout_holder  = ObjectProperty(None)
    app_status_label        = ObjectProperty(None)
    container_status_label  = ObjectProperty(None)
    container_delete_button = ObjectProperty(None)
    docker_status_button    = ObjectProperty(None)
    action_layout_holder    = ObjectProperty(None)
    action_layout           = ObjectProperty(None)
    pe_status_button        = ObjectProperty(None)
    console_button          = ObjectProperty(None)
    terminal_button         = ObjectProperty(None)
    run_puppet_button       = ObjectProperty(None)
    dockerbuild_button      = ObjectProperty(None)
    settings                = Settings()

    def __init__(self, **kwargs):
        super(MainScreen, self).__init__(**kwargs)
        self.controller = Controller()

    def pe_status_info(self):
        uptime = self.controller.container_alive()
        if uptime:
            pe_status = self.controller.pe_status()

            message = "Docker container is alive, up {uptime} seconds.  PE is {pe_status}.  ".format(
              uptime = uptime,
              pe_status = pe_status
            )
            if self.settings.expose_ports and pe_status == "running":
                command = "curl -k https://pe-puppet.localdomain:8140/packages/current/install.bash | sudo bash"
                Clipboard.copy(command)

                message += "You can install agent by running:" + textwrap.dedent(
                """
                {command}
                
                You must add the following to your /etc/hosts file before running:
                {docker_address} pe-puppet.localdomain pe-puppet
                """.format(command=command, docker_address=self.controller.docker_address))

            pe_status = self.controller.pe_status()
        else:
            message = "Docker container is not running"
        App.get_running_app().info(message)

    def docker_status_info(self):
        App.get_running_app().info(
            "Docker daemon is {alive}".format(alive=self.controller.daemon_alive())
        )

    def toggle_action_layout(self, show):
        if show:
            # hidden -> show
            self.action_layout_holder.add_widget(self.action_layout)

            if self.controller.update_available:
                App.get_running_app().info("An new image is available, check settings to download")

        else:
            # showing -> hide
            self.action_layout_holder.clear_widgets()

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
            webbrowser.open_new(self.controller.dockerbuild_url)

        # call the named callback in 2 seconds (delay without freezing)
        Clock.schedule_once(open_browser, 2)

    def run_puppet(self):
        App.get_running_app().info("running puppet on master")
        threading.Thread(target=self.controller.run_puppet).start()

    def log(self, message, level="[info]  "):
        current = self.log_textinput.text
        if message is not None:
            updated = current + level + message + "\n"
            self.log_textinput.text = updated

    def pe_console(self):

        App.get_running_app().info("Launching browser, please accept the certificate.\n"
                  "The username is 'admin' and the password is 'aaaaaaaa'")

        def open_browser(dt):
            webbrowser.open_new(self.controller.pe_url)

        # call the named callback in 2 seconds (delay without freezing)
        Clock.schedule_once(open_browser, 2)
        
    def pe_terminal(self):
        App.get_running_app().info("Launching terminal, please lookout for a new window")

        def open_terminal(dt):
            Utils.docker_terminal("docker exec -ti {name} bash".format(
              name=Controller.DOCKER_CONTAINER,
            ))

        # call the named callback in 2 seconds (delay without freezing)
        Clock.schedule_once(open_terminal, 2)

class MenuScreen(Screen):        
    """Simple menu of helpful links"""
    
    def __init__(self, **kwargs):
        super(MenuScreen, self).__init__(**kwargs)
    
    def about(self):
        App.get_running_app().info("PE_Kit {version}".format(version = PeKitApp.__version__))
        
    def help(self):
        webbrowser.open_new("https://github.com/GeoffWilliams/pe_kit#help")
    
    def report_bug(self):
        def report_bug(x):
            webbrowser.open_new('https://github.com/GeoffWilliams/pe_kit/issues/new')
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

    DOCKER_CONTAINER="pe_kit__"
    PE_HOSTNAME="pe-puppet.localdomain"
    DOCKER_IMAGE_PATTERN="geoffwilliams/pe_master_public_lowmem_r10k_dockerbuild"
    cli = None

    # images avaiable for downloading
    downloadable_images = []

    # images available locally
    local_images = []
    
    # combined local and remote images
    images = []
    
    docker_url = None
    docker_address = "unknown"
    pe_url = None
    dockerbuild_url = None
    pe_console_port = 0
    dockerbuild_port = 0
    app = None
    settings = Settings()
    container_status = False
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

    def delete_image(self, tag):
        self.cli.remove_image(
          self.DOCKER_IMAGE_PATTERN + ":" + tag
        )
        self.refresh_images()

    def download_image(self, tag):
        self.active_downloads.append(tag)
        for line in self.cli.pull(
          repository = self.DOCKER_IMAGE_PATTERN,
          tag = tag,
          stream = True,
        ):
            if self.running and tag in self.active_downloads:
                self.logger.debug(line)
            else:
                raise Exception("Aborting download because quit/cancel!")
        self.stop_download()
        self.refresh_images()
        
    def stop_download(self, tag):
        """abort a download by removing it from the list of active downloads"""
        if tag in self.active_downloads:
            self.active_downloads.remove(tag)
        self.refresh_images()

    def update_status(self):
        """daemon thread to check if docker and container are alive"""
        while (self.running):
            self.daemon_status = self.daemon_alive()

            if self.daemon_status == "running":
                self.container_status = self.container_alive()
            else:
                self.container_status = False
            time.sleep(1)

    def pe_status(self):
        """return status of PE master: running, loading, stopped"""

        # turn off SSL cert verifcation since we're using puppets self-signed certs
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

        if self.pe_url:
            try:
                code = urllib2.urlopen(self.pe_url, context=ctx).getcode()
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
                  pe_url = self.pe_url,
                  message = e.reason,
                ))
                status = "loading"
        else:
            status = "error"

        return status


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
                try:
                    if self.cli.inspect_container(self.DOCKER_CONTAINER):
                        if self.settings.kill_orphans:
                            self.logger.info("killing orphaned container")
                            self.cli.remove_container(self.DOCKER_CONTAINER, force=True)
                        else:
                            self.logger.info("inspecting existing container")
                            self.container = self.cli.inspect_container(self.DOCKER_CONTAINER)
                            if self.container["State"]["Running"]:
                                self.munge_urls()
                            # else container exists but has not yet been started, leave it
                            # alone until its started by the start_automatically flag or 
                            # a user manually pressing the play button
                except docker.errors.NotFound:
                    self.logger.info("container not running, OK to start new one")

                # update downloadble and local images on the settings page
                self.refresh_images()

                if self.settings.start_automatically:
                    self.start_pe()

                # potiential segfault here? - should probably do something similar to above
                # ready for action, enable buttons
                self.app.toggle_action_layout(True)

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

    def container_alive(self):
        """
        Return container uptime or false if its dead
        """
        alive = False
        if self.cli:
            try:
                inspection = self.cli.inspect_container(self.DOCKER_CONTAINER)
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

    def toggle_docker_container(self):
        self.logger.debug("toggle_docker_container clicked")
        if self.container_alive():
            # !FIXME - double validation here
            self.stop_docker_containers()
        else:
            self.start_pe()

    def stop_docker_containers(self):
        if self.container_alive():
            self.cli.remove_container(container=self.container.get('Id'), force=True)

    def start_docker_daemon(self):
        # docker startup in own thread
        self.logger.info("starting docker_init in own thread")
        threading.Thread(target=self.docker_init).start()

        # self-monitoring/status in own thread
        self.logger.info("starting update_status in own thread")
        threading.Thread(target=self.update_status).start()

    def port_bindings(self):
        return {
          22: None,
          8140: 8140 if self.settings.expose_ports else None,
          61613: 61613 if self.settings.expose_ports else None,
          61616: None,
          443: None,
          9000: None,
        }

    def start_pe(self):
        status = False
        tag = self.app.get_selected_image()

        if self.container_alive():
            status = True
        else:
            if tag:
                selected_image = self.DOCKER_IMAGE_PATTERN + ":" + tag
                port_bindings = self.port_bindings()
                try:
                    self.container = self.cli.create_container(
                      image=selected_image,
                      name=self.DOCKER_CONTAINER,
                      hostname=self.PE_HOSTNAME,
                      detach=True,
                      volumes = [
                          "/sys/fs/cgroup",
                      ],
                      ports = port_bindings.keys(),
                      host_config=self.cli.create_host_config(port_bindings=port_bindings)
                    )
                except docker.errors.APIError as e:
                    if e.response.status_code == 409:
                        self.logger.error("Container exists - starting it")
                        self.container = self.cli.inspect_container(self.DOCKER_CONTAINER)
                        #self.app.info("Starting existing container...")
                        
                    else:
                        self.logger.error("Unknown Docker error follows")
                        self.logger.exception(e)
                        self.app.error("Unknown Docker error:  " + e.message)
                    
                self.logger.info("starting container " + self.container.get('Id'))
                resp = self.cli.start(
                  container=self.container.get('Id'),
                  privileged=True,
                  port_bindings=port_bindings

                )
                self.logger.info(self.container)
                self.munge_urls()

                status = True
            else:
                self.app.error("No image selected, check settings")

        return status

    def munge_urls(self):

        # inspect the container and get the port mapping
        container_info = self.cli.inspect_container(self.container.get("Id"))
        pp = pprint.PrettyPrinter()
        pp.pprint(container_info)
        self.pe_console_port = container_info["NetworkSettings"]["Ports"]["443/tcp"][0]["HostPort"]
        self.dockerbuild_port = container_info["NetworkSettings"]["Ports"]["9000/tcp"][0]["HostPort"]
        parsed = urlparse(self.docker_url)

        print "*(***********D*D**D*D*D**D*)"
        pp.pprint(parsed)
        self.docker_address = parsed.netloc.split(":")[0]

        # update the URL to browse to for PE console
        self.pe_url = parsed._replace(
          netloc="{}:{}".format(parsed.hostname, self.pe_console_port)
        ).geturl()

        # update the URL for dockerbuild
        self.dockerbuild_url = parsed._replace(
          scheme='http',
          netloc="{}:{}".format(parsed.hostname, self.dockerbuild_port)
        ).geturl()

    def refresh_images(self):
        """Update the lists of downloadable and locally available images,
        then de-duplicate the list and produce a map combining both lists
        so that the image managment grid can be built"""

        # First build lists...
        self.update_local_images()
        self.update_downloadable_images()

        # since PE releases are somewhat ISO 8601 format (not really) we
        # can sort alphabetically to see if we are up to date
        newest_download_tag = self.downloadable_images[0]

        # there may be no local images yet if this is a fresh docker install
        if len(self.local_images):
            newest_local_tag = self.local_images[0]
        else:
            newest_local_tag = None

        # set flag here and pick it up in the render code
        if newest_download_tag > newest_local_tag:
            self.update_available = True
        else:
            self.update_available = False


        # now combine into a hash
        self.images = []
        for tag in self.downloadable_images:
            self.images.append({
              "name": tag,
              "status": "downloadable",
              "selected": False
            })

        for tag in self.local_images:
            self.images.append({
              "name": tag,
              "status": "local",
              "selected": False
            })

        self.images_refreshed = True


    def update_local_images(self):
        """
        re-create the list of locally downloaded images that are ready to
        run.  Updates the self.local_images array to be a list of tags
        present locally
        """
        if self.cli is not None:
            docker_images = self.cli.images()

            self.local_images = []

            for docker_image in docker_images:
                image_name = docker_image["RepoTags"][0]

                # split off the image name and just get the tag
                tag = image_name.split(":")[-1]

                #self.log("found image " + image_name)
                if image_name.startswith(self.DOCKER_IMAGE_PATTERN):
                    self.local_images.append(tag)
            self.local_images.sort(reverse=True)

    # images available for download
    def update_downloadable_images(self):
        """
        re-create the list of image tags available for download.  Updates
        self.downloadable_images to be a list of the available tags (strings)
        """
        self.downloadable_images = []
        try:
            images = json.load(
              urllib2.urlopen(
                "https://registry.hub.docker.com/v2/repositories/%s/tags/" %
                self.DOCKER_IMAGE_PATTERN
              )
            )
            for tags in images["results"]:
                # if image is already downloaded, don't list it as available for download
                tag = tags["name"]
                if not self.tag_exists_locally(tag):
                    self.downloadable_images.append(tag)
        except urllib2.URLError:
            self.logger.error("failed to reach docker hub - no internet?")
        self.downloadable_images.sort(reverse=True)

    # test if a tag has already been downloaded
    def tag_exists_locally(self, tag):
        """determine if a given tag exists locallay"""
        found = False
        i = 0
        while not found and i < len(self.local_images):
            image = self.local_images[i]
            image_split = image.split(":")
            local_tag = image_split[len(image_split) - 1]
            if tag == local_tag:
                found = True
            i += 1

        return found

    def run_puppet(self):
        """Run puppet on the master"""
        self.cli.exec_start(self.cli.exec_create(
          container=self.DOCKER_CONTAINER,
          cmd="puppet agent -t"
        ))

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
    __version__ = "v0.1.7"
    
    def check_update(self):
        """check for new release of the app"""
        try:
            r = json.loads(
                urllib2.urlopen("https://api.github.com/repos/geoffwilliams/pe_kit/releases", timeout=5).read()
            )
            latest_tag = r[0]["tag_name"]
            if latest_tag != self.__version__:
                self.info(
                    "A new version of PE_Kit is available ({latest_tag}), you are running {version}\n" "please go to https://github.com/GeoffWilliams/pe_kit/releases to download the\n"
                    "new version".format(latest_tag=latest_tag, version=self.version))
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

        # hide action buttons until we have loaded the system
        self.root.get_screen("main").toggle_action_layout(False)

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
            self.controller.stop_docker_containers()

    def get_selected_image(self):
        if len(self.controller.local_images) == 0:
            # error loading local images or none available
            selected = None
        elif self.settings.use_latest_image:
            selected = self.controller.local_images[0]
        else:
            try:
                current = [t for t in ToggleButton.get_widgets('selected_image') if t.state=='down'][0]
                selected = current.image_name
            except IndexError:
                selected = None
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
        x = self.popup(
            title="Question", 
            message=message, 
            question=True, 
            yes_callback=yes_callback,
            no_callback=no_callback
        )
    
    def info(self, message):
        return self.popup(title='Information', message=message)

    def toggle_action_layout(self, show):
        self.root.get_screen("main").toggle_action_layout(show)

    def daemon_monitor(self, x):
        container_status = "not running"
        container_icon = "icons/play.png"
        pe_status = "stopped"

        if self.controller.daemon_status == "running":
            self.logger.debug("docker daemon ok :)")
            daemon_icon = "icons/ok.png"

            # docker is alive, lets check the container too
            uptime = self.controller.container_status
            if uptime:
                container_status = "up {uptime} seconds".format(uptime=uptime)
                container_icon = "icons/delete.png"
                pe_status = self.controller.pe_status()
        elif self.controller.daemon_status == "loading":
            self.logger.error("docker daemon starting!")
            daemon_icon = "icons/wait.png"                   
        else:
            self.logger.error("docker daemon dead!")
            daemon_icon = "icons/error.png"

        if pe_status == "running":
            pe_status_icon = "icons/puppet.png"
            self.root.get_screen("main").console_button.disabled = False
            self.root.get_screen("main").terminal_button.disabled = False
            self.root.get_screen("main").run_puppet_button.disabled = False
            self.root.get_screen("main").dockerbuild_button.disabled = False     
        elif pe_status == "loading":
            pe_status_icon = "icons/wait.png"
            self.root.get_screen("main").console_button.disabled = True
            self.root.get_screen("main").terminal_button.disabled = False
            self.root.get_screen("main").run_puppet_button.disabled = False
            self.root.get_screen("main").dockerbuild_button.disabled = False        
        else:
            pe_status_icon = "icons/disabled.png"
            self.root.get_screen("main").console_button.disabled = True
            self.root.get_screen("main").terminal_button.disabled = True
            self.root.get_screen("main").run_puppet_button.disabled = True
            self.root.get_screen("main").dockerbuild_button.disabled = True

        self.root.get_screen("main").docker_status_button.background_normal = daemon_icon
        self.root.get_screen("main").container_delete_button.background_normal = container_icon
        self.root.get_screen("main").container_status_label.text = container_status
        self.root.get_screen("main").pe_status_button.background_normal = pe_status_icon


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
