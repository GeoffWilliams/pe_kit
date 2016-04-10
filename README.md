# OSX Usage
1. Download and install [Docker Toolbox](https://www.docker.com/products/docker-toolbox)
2. In a terminal, run the following commands to increase the disk space in boot2docker
```
docker-machine rm -f default
docker-machine create -d virtualbox --virtualbox-disk-size "50000" default
``` 
3. Download the latest [DMG Installer](https://github.com/GeoffWilliams/pe_kit/releases)
4. Run the installer, drag and drop the application into your application
  folder, then click the top middle button to create symlinks

The application is now installed, you can start PE_Kit from spotlight or the 
applications menu.  You will need to download a PE Docker image (approx 3.5GB)
before the application is usable.  This can be done from the settings menu by
clicking the blue container icon next to the name of the image you want to 
download.

# Developing
## Prerequisites
See http://www.pyladies.com/blog/Get-Your-Mac-Ready-for-Python-Programming/ for
how to install python on a mac 
* Python 2.7.x (brew install python)
* Python virtualenv (pip install virtualenv)
* Xcode 

## Setup
1.  Install Docker (https://www.docker.com/products/docker-toolbox)
  * After install, make a bigger boot2docker image to avoid running out of space, eg:  
  ```shell
  docker-machine rm -f default
  docker-machine create -d virtualbox --virtualbox-disk-size "50000" default
  ```
2.  Install Kivy (GUI/Python support) https://kivy.org/#download
  * Follow the MAC setup instructions at https://kivy.org/docs/installation/installation-osx.html
  * Kivy installs all its libraries into a virtualenv shipped in its own 
    installer.  The docker api needs to be installed into this environment:
    1.  cd /Applications/Kivy.app/Contents/Resources/venv 
    2.  source bin/activate
    3.  pip install docker-py python-dateutil

**IMPORTANT! do not use zshell!!!**

# Running
```
./main.py
```


