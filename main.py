#!/usr/bin/env kivy
import logging
logging.basicConfig(level=logging.DEBUG)


from kivy.app import App
from kivy.clock import Clock
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.anchorlayout import AnchorLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput
from kivy.uix.dropdown import DropDown
from kivy.uix.popup import Popup
from kivy.uix.checkbox import CheckBox
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

class Settings:
  __shared_state = {}
  start_automatically = True
  kill_orphans = True
  use_latest_image = True

  def __init__(self):
    self.__dict__ = self.__shared_state  

class DockerMachine():
  """
  DockerMachine
  
  Control the default docker-machine instance (boot2docker)
  """

  logger = logging.getLogger(__name__)

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
    if self.status() != "Running":
      try:
        out = subprocess.check_output(["docker-machine", "start"])
        if self.status() == "Running":
          self.logger.info("docker-machine started OK")
          started = True
      except CalledProcessError as e:
        self.logger.error("failed to start docker", e)
        
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

    return started

class SettingsScreen(Screen):
  
  logger = logging.getLogger(__name__)
  download_images_layout = ObjectProperty(None)
  selected_image_button = ObjectProperty(None)
  settings                = Settings()

  
  def __init__(self, **kwargs):
    super(SettingsScreen, self).__init__(**kwargs)
    self.controller = Controller()
    
  def on_download_checkbox(self, checkbox, value):
    if value:
      self.controller.download_images.append(checkbox.tag)
    else:
      self.controller.download_images.remove(checkbox.tag)    
    

    
#    self.orientation = "vertical"
#    self.spacing = 30,30  
  def update_ui_images(self):
    # remove any existing children to handle multiple calls
    self.download_images_layout.clear_widgets()

    if len(self.controller.downloadable_images) > 0:
      for tag in self.controller.downloadable_images:
        row_layout = BoxLayout()

        # checkbox
        checkbox = CheckBox()
        checkbox.bind(active=self.on_download_checkbox)
        checkbox.tag = tag
        row_layout.add_widget(checkbox)


        # label
        image_label = Label(text=tag)
        row_layout.add_widget(image_label)
        self.logger.info(tag)

        self.download_images_layout.add_widget(row_layout)

      download_button = Button(text="Download selected")
      download_button.bind(on_press=self.controller.download_selected_images)
      self.download_images_layout.add_widget(download_button)
    else:    
      self.download_images_layout.add_widget(Label(text="All images up-to-date"))
      
    # close the updating message or it will hang around waiting for user
    # to click OK
    #popup[0].dismiss()

    # --------
    dropdown = DropDown()
    for image_name in self.controller.local_images:
      btn = Button(text=image_name, size_hint_y=None, height=44)
      btn.bind(on_release=lambda btn: dropdown.select(btn.text))
      dropdown.add_widget(btn)

    self.selected_image_button.bind(on_release=dropdown.open)
    #self.add_widget(self.docker_image_button)
    dropdown.bind(on_select=lambda instance, x: setattr(self.selected_image_button, 'text', x))  

    # select the first image in the list (most recent)
    if len(self.controller.local_images) > 0:
      self.logger.debug("selecting image " + self.controller.local_images[0])
      self.selected_image_button.text = self.controller.local_images[0]
      
      # start automatically if configured
      if self.settings.start_automatically:
        self.logger.debug("automatically starting container (settings)")
        self.controller.start_pe()
      
    else:
      self.error("no images available")
    

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
  container_delete_image  = ObjectProperty(None)
  docker_status_image     = ObjectProperty(None)
  action_layout_holder    = ObjectProperty(None)
  action_layout           = ObjectProperty(None)
  pe_status_image         = ObjectProperty(None)
  console_button          = ObjectProperty(None)
  terminal_button         = ObjectProperty(None)
  settings                = Settings()

  def __init__(self, **kwargs):
    super(MainScreen, self).__init__(**kwargs)
    self.controller = Controller()
    
  def toggle_action_layout(self, show):
    if show:
      # hidden -> show
      self.action_layout_holder.add_widget(self.action_layout)    
    else:
      # showing -> hide
      self.action_layout_holder.clear_widgets()
    
  def toggle_advanced(self):
    if self.advanced_layout in self.advanced_layout_holder.children:
      # showing -> hide
      self.advanced_layout_holder.clear_widgets()
    else:
      # hidden -> show
      self.advanced_layout_holder.add_widget(self.advanced_layout)

  def toggle_log(self, x):
    if self.log_textinput in self.advanced_layout.children:
      self.advanced_layout.remove_widget(self.log_textinput)
    else :
      self.advanced_layout.add_widget(self.log_textinput)

      
  def on_download_checkbox(self, checkbox, value):
    if value:
      self.download_images.append(checkbox.tag)
    else:
      self.download_images.remove(checkbox.tag)

  def download_selected_images(self, x):
    for image in self.download_images:
      self.log("download " + image)
      self.cli.pull(
        repository = self.DOCKER_IMAGE_PATTERN,
        tag = image
      )
      
    # update the list of images still available for download/available for use
    self.update_downloadable_images()
    self.update_local_images()
    

      
  # images available for download    
#  def update_downloadable_images(self):
#    popup = [None]
#    
#    def update_message():
#      popup[0] = self.info("Checking for updates...")
#      
#    t = threading.Thread(target=update_message)
#    t.start()
#    time.sleep(1)
#
#      # if image is already downloaded, don't list it as available for download
#      tag = tags["name"]
#      if not self.tag_exists_locally(tag):
#        new_images = True
#        row_layout = BoxLayout()
#      
#        # checkbox
#        checkbox = CheckBox()
#        checkbox.bind(active=self.on_download_checkbox)
#        checkbox.tag = tag
#        row_layout.add_widget(checkbox)
#
#
#        # label
#        image_label = Label(text=tag)
#        row_layout.add_widget(image_label)
#        self.log(tag)
#
#        self.download_images_layout.add_widget(row_layout)
#    
#    if new_images:
#      download_button = Button(text="Download selected")
#      download_button.bind(on_press=self.download_selected_images)
#      self.download_images_layout.add_widget(download_button)
#    else:    
#      self.download_images_layout.add_widget(Label(text="All images up-to-date"))
#      
#    # close the updating message or it will hang around waiting for user
#    # to click OK
#    popup[0].dismiss()

  def log(self, message, level="[info]  "):
    current = self.log_textinput.text
    if message is not None:
      updated = current + level + message + "\n"
      self.log_textinput.text = updated
          
  def pe_console(self, instance):

    self.info("Launching browser, please accept the certificate and wait approximately 2 minutes.\n  When the console loads, the username is 'admin' and the password is 'aaaaaaaa'")

    def open_browser(dt):
      webbrowser.open_new(self.controller.pe_url)

    # call the named callback in 2 seconds (delay without freezing)
    Clock.schedule_once(open_browser, 2)

    
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
  
  # images to download
  download_images = []
  
  # images available locally
  local_images = []
  docker_url = None
  pe_url = None
  dockerbuild_url = None
  pe_console_port = 0
  dockerbuild_port = 0
  app = None
  settings = Settings()
  
  def __init__(self):
    self.__dict__ = self.__shared_state
    
  def pe_status(self):
    """return status of PE master: running, loading, stopped"""

    # turn off SSL cert verifcation since we're using puppets self-signed certs
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE    
    
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
        status = "stopped"

    return status

  
  def docker_init(self):
    #  boot2docker specific hacks in use - see:  http://docker-py.readthedocs.org/en/latest/boot2docker/

    dm = DockerMachine()
    if dm.start():
      print "***************" + os.environ["DOCKER_CERT_PATH"]
      kwargs = kwargs_from_env()

      if 'tls' not in kwargs:
        # daemon not setup/running
        self.app.error("Couldn't find docker!  Please run from Docker Quickstart Terminal!")
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
              self.logger.info("reusing existing container")
        except docker.errors.NotFound:
          self.logger.info("container not running, OK to start new one")
                
        self.refresh_images()
        self.app.update_ui_images()
        
        # ready for action, enable buttons
        self.app.toggle_action_layout(True)
        
    else:
      # no docker machine
      self.app.error("Unable to start docker :*(")

  def daemon_alive(self):
    if self.cli:
      try:
        version_info = self.cli.version()
        if "Version" in version_info:
          alive = True
        else:
          alive = False
      except requests.exceptions.ConnectionError:
        self.logger.error("urllib3 error talking to docker daemon")
        alive = False
    else:
      alive = False
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
    t = threading.Thread(target=self.docker_init)
    t.start()
    
  def download_selected_images(self, x):
    for image in self.download_images:
      self.logger.info("download " + image)
      
      #t = threading.Thread(target=update_message)
#    t.start()
      self.cli.pull(
        repository = self.DOCKER_IMAGE_PATTERN,
        tag = image
      )
      
    # update the list of images still available for download/available for use
    self.update_downloadable_images()
    self.update_local_images()        
    
  def start_pe(self):
    status = False
    selected_image = self.app.get_selected_image()
    if self.container_alive():
      status = True
    else:
      if selected_image.startswith(self.DOCKER_IMAGE_PATTERN):
        self.container = self.cli.create_container(
          image=selected_image,
          name=self.DOCKER_CONTAINER,
          hostname=self.PE_HOSTNAME,
          detach=True,
          volumes = [
              "/sys/fs/cgroup",
          ],
        )
        resp = self.cli.start(
          container=self.container.get('Id'), 
          privileged=True,
          publish_all_ports=True,
        )
        #self.log(resp)

        # inspect the container and get the port mapping
        container_info = self.cli.inspect_container(self.container.get("Id"))
        pp = pprint.PrettyPrinter()
        pp.pprint(container_info)
        #self.log(pp.pformat(container_info))

        self.pe_console_port = container_info["NetworkSettings"]["Ports"]["443/tcp"][0]["HostPort"]
        self.dockerbuild_port = container_info["NetworkSettings"]["Ports"]["9000/tcp"][0]["HostPort"]

        parsed = urlparse(self.docker_url)
        
        # update the URL to browse to for PE console
        self.pe_url = parsed._replace(
          netloc="{}:{}".format(parsed.hostname, self.pe_console_port)
        ).geturl()
        
        # update the URL for dockerbuild
        self.dockerbuild_url = parsed._replace(
          scheme='http',
          netloc="{}:{}".format(parsed.hostname, self.dockerbuild_port)
        ).geturl()
        
        status = True
      else:
        self.app.error("Please select an image from the list first")

    return status

  def refresh_images(self):
    self.update_local_images()
    self.update_downloadable_images()      

  def update_local_images(self):
    if self.cli is not None: 
      docker_images = self.cli.images()

      self.local_images = []

      for docker_image in docker_images:
        image_name = docker_image["RepoTags"][0]
        #self.log("found image " + image_name)
        if image_name.startswith(self.DOCKER_IMAGE_PATTERN):
          self.local_images.append(image_name)
      self.local_images.sort(reverse=True)

  # images available for download    
  def update_downloadable_images(self):
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
      print("internet failed!")
          
  # test if a tag has already been downloaded    
  def tag_exists_locally(self, tag):
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
  
  def run_puppet():
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
  app_running = True
  
  
  def toggle_advanced(self):
    self.root.get_screen("main").toggle_advanced()
    
  def update_ui_images(self):
    from pprint import pprint
    pprint (vars(self))
    self.root.get_screen("settings").update_ui_images()
    
    
  def pe_console(self):
    print("pe_console clicked!")
    self.info("Launching browser, please accept the certificate! \nThe username is 'admin' and the password is 'aaaaaaaa'")

    def open_browser(dt):
      webbrowser.open_new(self.controller.pe_url)

    # call the named callback in 2 seconds (delay without freezing)
    Clock.schedule_once(open_browser, 2)

  def pe_terminal(self):
    self.info("Launching terminal, please lookout for a new window")

    def open_terminal(dt):
      Utils.docker_terminal("docker exec -ti {name} bash".format(
        name=Controller.DOCKER_CONTAINER,
      ))

    # call the named callback in 2 seconds (delay without freezing)
    Clock.schedule_once(open_terminal, 2)

  def dockerbuild(self):
    self.info("Launching dockerbuild - have fun :)")

    def open_browser(dt):
      webbrowser.open_new(self.controller.dockerbuild_url)

    # call the named callback in 2 seconds (delay without freezing)
    Clock.schedule_once(open_browser, 2)
        
  def run_puppet(self):
    self.info("running puppet on master")
    self.controller.run_puppet()

  def build(self):
    self.controller = Controller()
    self.controller.start_docker_daemon()
    self.controller.app = self

    return Builder.load_file("main.kv")

  def on_start(self):
    # hide advanced by default
    self.root.get_screen("main").toggle_advanced()
    
    # hide action buttons until we have loaded the system
    self.root.get_screen("main").toggle_action_layout(False)

    # monitor the docker daemon and container
    Clock.schedule_interval(self.daemon_monitor, 5)

  def on_stop(self):
    self.app_running = False
    self.controller.stop_docker_containers()
    
  def get_selected_image(self):
    return self.root.get_screen("settings").selected_image_button.text    

  def error(self, message):
    return self.popup(title='Error!', message=message)

  def popup(self, title, message):
    def close(x):
      popup.dismiss()

    popup_content = BoxLayout(orientation="vertical")
    popup_content.add_widget(Label(text=message))
    button_layout = AnchorLayout()
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

  def info(self, message):
    return self.popup(title='Information', message=message)
  
  def toggle_action_layout(self, show):
    self.root.get_screen("main").toggle_action_layout(show)
  
  def daemon_monitor(self, x):
    alive = self.controller.daemon_alive()
    container_status = "not running"
    container_icon = "icons/play.png"
    pe_status = "stopped"
    
    if alive:
      self.logger.debug("docker daemon ok :)")
      daemon_icon = "icons/ok.png"
      
      # docker is alive, lets check the container too
      uptime = self.controller.container_alive()
      if uptime:
        container_status = "up {uptime} seconds".format(uptime=uptime)
        container_icon = "icons/delete.png"
        pe_status = self.controller.pe_status()

    else:
      self.logger.error("docker daemon dead!")
      daemon_icon = "icons/error.png"

    if pe_status == "running":
      pe_status_icon = "icons/puppet.png"
      self.root.get_screen("main").console_button.disabled = False
      self.root.get_screen("main").terminal_button.disabled = False      
    elif pe_status == "loading":
      pe_status_icon = "icons/wait.png"
      self.root.get_screen("main").console_button.disabled = True
      self.root.get_screen("main").terminal_button.disabled = False
    else:
      pe_status_icon = "icons/disabled.png"
      self.root.get_screen("main").console_button.disabled = True
      self.root.get_screen("main").terminal_button.disabled = True

    
      
    self.root.get_screen("main").docker_status_image.source = daemon_icon
    self.root.get_screen("main").container_delete_image.source = container_icon
    self.root.get_screen("main").container_status_label.text = container_status
    self.root.get_screen("main").pe_status_image.source = pe_status_icon
  
PeKitApp().run()
# App.get_running_app()