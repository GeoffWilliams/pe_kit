#!/usr/bin/env kivy 
from kivy.app import App
from kivy.clock import Clock
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput
from kivy.uix.dropdown import DropDown
from kivy.uix.popup import Popup
from docker import Client
from docker.utils import kwargs_from_env
import webbrowser
from urlparse import urlparse
import pprint
from utils import Utils


class MainScreen(GridLayout):
  DOCKER_CONTAINER="pe_kit__"
  PE_HOSTNAME="pe-puppet.localdomain"
  DOCKER_IMAGE_PATTERN="geoffwilliams/pe_master_public_lowmem"
  cli = None
  docker_url = None
  pe_url = None
  pe_console_port = 0

  def __init__(self, **kwargs):
    super(MainScreen, self).__init__(**kwargs)

    self.cols = 2
    self.spacing = 30,30
    
    # banner
    self.add_widget(Label(text="PE Kit"))
    
    # PE image selection
    self.add_widget(Label(text="PE Version"))
    self.docker_image_button = Button(text='Available images', size_hint=(1, 1))
    self.add_widget(self.docker_image_button)

    # terminal 
    self.pe_terminal_button = Button(text="Terminal")
    self.pe_terminal_button.bind(on_press=self.pe_terminal)
    self.add_widget(self.pe_terminal_button)

    # console
    self.pe_console_button = Button(text="Console")
    self.pe_console_button.bind(on_press=self.pe_console)
    self.add_widget(self.pe_console_button)

    # log messages
    self.log_textinput = TextInput(row=20, col=60, text="")
    self.add_widget(self.log_textinput)

  def log(self, message, level="[info]  "):
    current = self.log_textinput.text
    if message is not None:
      updated = current + level + message + "\n"
      print("****" + updated)
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

        
        # update the URL to browse to
        parsed = urlparse(self.docker_url)
        self.pe_url = parsed._replace(
          netloc="{}:{}".format(parsed.hostname, self.pe_console_port)
        ).geturl()
      else:
        self.error("Please select an image from the list first")
    return self.container_running

  def error(self, message):
    self.popup(title='Error!', message=message)

  def popup(self, title, message):
    popup = Popup(
      title=title, 
      content=Label(text=message), 
      size_hint=(0.8,0.5),
      text_size=self.size
    )
    popup.open()

  def info(self, message):
    self.popup(title='Information', message=message)

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

  def update_docker_images(self):
    if self.cli is None:
      self.docker_init()
 
    if self.cli is not None: 
      dropdown = DropDown()
      docker_images = self.cli.images()
      pp = pprint.PrettyPrinter()
      pp.pprint(docker_images)
      for docker_image in docker_images:
        image_name = docker_image["RepoTags"][0]
        self.log("found image " + image_name)
        if image_name.startswith(self.DOCKER_IMAGE_PATTERN):
          btn = Button(text=image_name, size_hint_y=None, height=44)
          btn.bind(on_release=lambda btn: dropdown.select(btn.text))
          dropdown.add_widget(btn)


      #self.docker_image_button = Button(text='Available images', size_hint=(1, 1))
      self.docker_image_button.bind(on_release=dropdown.open)
      #self.add_widget(self.docker_image_button)
      dropdown.bind(on_select=lambda instance, x: setattr(self.docker_image_button, 'text', x))  


class PeKitApp(App):
  def build(self):
    self.app = MainScreen()
    return self.app

  def on_start(self):
    self.app.update_docker_images()
  
  def on_stop(self):
    self.app.log("SHUTTING DOWN...")
    self.app.stop_pe()

PeKitApp().run()
