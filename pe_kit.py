#!/usr/bin/env kivy 
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

class MainScreen(BoxLayout):
  DOCKER_CONTAINER="pe_kit__"
  PE_HOSTNAME="pe-puppet.localdomain"
  DOCKER_IMAGE_PATTERN="geoffwilliams/pe_master_public_lowmem_r10k_dockerbuild"
  cli = None
  docker_url = None
  pe_url = None
  dockerbuild_url = None
  pe_console_port = 0
  dockerbuild_port = 0

  # images to download
  download_images = []

  # locally available images
  local_images = []

  def __init__(self, **kwargs):
    super(MainScreen, self).__init__(**kwargs)

    self.orientation = "vertical"
    self.spacing = 30,30
    
    # banner
    banner_layout = AnchorLayout(size_hint=(1, 0.2))
    banner_layout.add_widget(Label(text="PE Kit", font_size="40sp", size_hint=(0.8,1)))
    self.add_widget(banner_layout)    

    # image downloading
    self.download_images_layout = BoxLayout(size_hint=(1, 0.3), padding=20, orientation="vertical")
    self.add_widget(self.download_images_layout)
    #self.download_images_layout.borders = (2, 'solid', (1,1,1,1.))

    # PE image selection
    images_layout = BoxLayout(size_hint=(1, 0.3), padding=20)
    images_layout.add_widget(Label(text="PE Version", size_hint=(0.3, 0.5)))
    self.docker_image_button = Button(text='Available images', size_hint=(0.6, 0.5))
    images_layout.add_widget(self.docker_image_button)
    self.add_widget(images_layout)

    # actions (contains terminal and console)
    actions_layout = BoxLayout(size_hint=(1, 0.3), padding=20, spacing=50)

    # terminal 
    self.pe_terminal_button = Button(text="Terminal", size_hint=(0.3, 0.5))
    self.pe_terminal_button.bind(on_press=self.pe_terminal)
    actions_layout.add_widget(self.pe_terminal_button)

    # console
    self.pe_console_button = Button(text="Console", size_hint=(0.3, 0.5))
    self.pe_console_button.bind(on_press=self.pe_console)
    actions_layout.add_widget(self.pe_console_button)
  
    # run puppet
    self.run_puppet_button = Button(text="Run Puppet", size_hint=(0.3, 0.5))
    self.run_puppet_button.bind(on_press=self.run_puppet)
    actions_layout.add_widget(self.run_puppet_button)
  
    self.add_widget(actions_layout)
    
    # advanced (not for sales ;-)
    self.advanced_layout = BoxLayout(size_hint=(1, 0.3), padding=20, spacing=50)
    
    # dockerbuild
    self.dockerbuild_button = Button(text="Dockerbuild", size_hint=(0.3, 0.5))
    self.dockerbuild_button.bind(on_press=self.dockerbuild)
    self.advanced_layout.add_widget(self.dockerbuild_button)
    
    # log messages
    self.log_textinput = TextInput(row=20, col=60, text="")
    toggle_log_button = Button(text="Show/Hide debug log", size_hint=(0.3, 0.5))
    toggle_log_button.bind(on_press=self.toggle_log)
    self.advanced_layout.add_widget(toggle_log_button)
    
    self.add_widget(self.advanced_layout)

  def run_puppet(self, x):
    if self.start_pe():
      self.info("running puppet on master")
      self.cli.exec_start(self.cli.exec_create(
        container=self.DOCKER_CONTAINER,
        cmd="puppet agent -t"
      ))

      
    
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
      
  # images available for download    
  def update_downloadable_images(self):
    popup = [None]
    
    def update_message():
      popup[0] = self.info("Checking for updates...")
      
    t = threading.Thread(target=update_message)
    t.start()
    time.sleep(1)

    
    # remove any existing children to handle multiple calls
    self.download_images_layout.clear_widgets()
    
    new_images = False
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
        new_images = True
        row_layout = BoxLayout()
      
        # checkbox
        checkbox = CheckBox()
        checkbox.bind(active=self.on_download_checkbox)
        checkbox.tag = tag
        row_layout.add_widget(checkbox)


        # label
        image_label = Label(text=tag)
        row_layout.add_widget(image_label)
        self.log(tag)

        self.download_images_layout.add_widget(row_layout)
    
    if new_images:
      download_button = Button(text="Download selected")
      download_button.bind(on_press=self.download_selected_images)
      self.download_images_layout.add_widget(download_button)
    else:    
      self.download_images_layout.add_widget(Label(text="All images up-to-date"))
      
    # close the updating message or it will hang around waiting for user
    # to click OK
    popup[0].dismiss()

  def log(self, message, level="[info]  "):
    current = self.log_textinput.text
    if message is not None:
      updated = current + level + message + "\n"
      self.log_textinput.text = updated
      

  def start_pe(self):
    if not self.container_running:
      if self.get_selected_image().startswith(self.DOCKER_IMAGE_PATTERN):
        self.container = self.cli.create_container(
          image=self.get_selected_image(),
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
        self.log(resp)
        self.container_running = True

        # inspect the container and get the port mapping
        container_info = self.cli.inspect_container(self.container.get("Id"))
        pp = pprint.PrettyPrinter()
        pp.pprint(container_info)
        self.log(pp.pformat(container_info))

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
      else:
        self.error("Please select an image from the list first")
    return self.container_running

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
      text_size=self.size
    )
    popup.open()
    return popup

  def info(self, message):
    return self.popup(title='Information', message=message)

  def stop_pe(self):
    if self.container_running:
      self.cli.remove_container(container=self.container.get('Id'), force=True)
      self.container_running = False

  def get_selected_image(self):
    return self.docker_image_button.text

  def pe_terminal(self, instance):
    if self.start_pe():
      self.info("Launching terminal, please lookout for a new window")

      def open_terminal(dt):
        Utils.docker_terminal("docker exec -ti {name} bash".format(
          name=self.DOCKER_CONTAINER,
        ))
      
      # call the named callback in 2 seconds (delay without freezing)
      Clock.schedule_once(open_terminal, 2)

  def dockerbuild(self, instance):
    if self.start_pe():
      self.info("Launching dockerbuild - have fun :)")

      def open_browser(dt):
        webbrowser.open_new(self.dockerbuild_url)

      # call the named callback in 2 seconds (delay without freezing)
      Clock.schedule_once(open_browser, 2)    
    
  def pe_console(self, instance):
    if self.start_pe():
      self.info("Launching browser, please accept the certificate and wait approximately 2 minutes.\n  When the console loads, the username is 'admin' and the password is 'aaaaaaaa'")

      def open_browser(dt):
        webbrowser.open_new(self.pe_url)

      # call the named callback in 2 seconds (delay without freezing)
      Clock.schedule_once(open_browser, 2)


  def docker_init(self):
    #  boot2docker specific hacks in use - see:  http://docker-py.readthedocs.org/en/latest/boot2docker/
    self.log("***DOCKER INIT***")
    kwargs = kwargs_from_env()

    if 'tls' not in kwargs:
      self.error("Couldn't find docker!  Please run from Docker Quickstart Terminal!")
    else:  
      kwargs['tls'].assert_hostname = False

      # save the boot2docker IP for use when we open browser windows
      self.docker_url = kwargs['base_url'] 

      self.cli = Client(**kwargs)
    self.container_running = False

  # local images already downloaded (drop down list)  
  def update_local_images(self):
    if self.cli is None:
      self.docker_init()
 
    if self.cli is not None: 
      dropdown = DropDown()
      docker_images = self.cli.images()
      pp = pprint.PrettyPrinter()
      pp.pprint(docker_images)

      self.local_images = []

      for docker_image in docker_images:
        image_name = docker_image["RepoTags"][0]
        self.log("found image " + image_name)
        if image_name.startswith(self.DOCKER_IMAGE_PATTERN):
          self.local_images.append(image_name)
      self.local_images.sort(reverse=True)

      # create widgets based on the sorted list of appropriate images
      for image_name in self.local_images:
        btn = Button(text=image_name, size_hint_y=None, height=44)
        btn.bind(on_release=lambda btn: dropdown.select(btn.text))
        dropdown.add_widget(btn)

      # select the first image in the list (most recent)
      if len(self.local_images) > 0:
        self.log("selecting image " + self.local_images[0])
        self.docker_image_button.text = self.local_images[0]
      else:
        self.error("no images available")

      #self.docker_image_button = Button(text='Available images', size_hint=(1, 1))
      self.docker_image_button.bind(on_release=dropdown.open)
      #self.add_widget(self.docker_image_button)
      dropdown.bind(on_select=lambda instance, x: setattr(self.docker_image_button, 'text', x))  


class PeKitApp(App):
  def build(self):
    self.app = MainScreen()
    return self.app

  def on_start(self):
    self.app.update_local_images()
    self.app.update_downloadable_images()  

  def on_stop(self):
    self.app.log("SHUTTING DOWN...")
    self.app.stop_pe()

PeKitApp().run()
