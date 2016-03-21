#!/usr/bin/env kivy 
from kivy.app import App
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput
from kivy.uix.dropdown import DropDown
from docker import Client
from docker.utils import kwargs_from_env


class MainScreen(GridLayout):
  def __init__(self, **kwargs):
    super(MainScreen, self).__init__(**kwargs)
    self.docker_init()

    self.cols = 2
    self.add_widget(Label(text="PE Kit"))
    
    self.add_widget(Label(text="PE Version"))
    self.add_docker_pe_images()

    self.pe_terminal_button = Button(text="Terminal")
    self.pe_terminal_button.bind(on_press=self.pe_terminal)
    self.add_widget(self.pe_terminal_button)

    self.pe_console_button = Button(text="Console")
    self.pe_console_button.bind(on_press=self.pe_console)
    self.add_widget(self.pe_console_button)


  def pe_terminal(self, instance):
    print("TERM clicked")

  def pe_console(self, instance):
    print("CONSOLE clicked")

  def docker_init(self):
    #  boot2docker specific hacks in use - see:  http://docker-py.readthedocs.org/en/latest/boot2docker/
    print("***DOCKER INIT***")
    kwargs = kwargs_from_env()
    kwargs['tls'].assert_hostname = False
    self.cli = Client(**kwargs)

  def add_docker_pe_images(self):
    dropdown = DropDown()
    docker_images = self.cli.images()
    import pprint
    pp = pprint.PrettyPrinter()
    pp.pprint(docker_images)
    for docker_image in docker_images:
      image_name = docker_image["RepoTags"][0]
      print("found image " + image_name)
      if image_name.startswith("geoffwilliams/pe_master_public_lowmem"):
        btn = Button(text=image_name, size_hint_y=None, height=44)
        btn.bind(on_release=lambda btn: dropdown.select(btn.text))
        dropdown.add_widget(btn)


    docker_image_button = Button(text='Available images', size_hint=(1, 1))
    docker_image_button.bind(on_release=dropdown.open)
    self.add_widget(docker_image_button)
    dropdown.bind(on_select=lambda instance, x: setattr(docker_image_button, 'text', x))  

class PeKitApp(App):
  def build(self):
    return MainScreen()

PeKitApp().run()
