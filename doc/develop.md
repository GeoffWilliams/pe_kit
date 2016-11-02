# Developing
Follow the instructions below to setup your OS if your interested in developing this application

## Linux Instructions
1. [Install Kivy](https://kivy.org/docs/installation/installation-linux.html)
2. [Install Docker](https://docs.docker.com/engine/installation/)
3. `pip install docker-py python-dateutil`
4. To run:
```
python main.py
```

## OSX Instructions

### Prerequisites
Your machine must be setup with Python 2.7 before you can run any code, see [pyladies article](http://www.pyladies.com/blog/Get-Your-Mac-Ready-for-Python-Programming/) for details of how to setup your system.  You will need:
* Python 2.7.x `brew install python`
* Python virtualenv `pip install virtualenv`
* Xcode

### Setup
1. Install [Docker for Mac](https://www.docker.com/products/docker#/mac)
2. Install [Kivy](https://kivy.org/#download) (GUI/Python support)
  * Follow the OSX setup instructions at https://kivy.org/docs/installation/installation-osx.html
  * Kivy installs all its libraries into a virtualenv shipped in its own installer.  The docker api needs to be installed into this environment:
```shell
cd /Applications/Kivy.app/Contents/Resources/venv
source bin/activate
pip install docker-py python-dateutil
```
4.  To run:
```
./main.py
```

**IMPORTANT! do not use zshell for any step of this process!!!**

## Packaging
* OSX packages are produced using [buildozer](https://kivy.org/docs/guide/packaging-osx.html#using-buildozer).  The `dmg` file is produced by running:
```
buildozer osx debug
```


## Project conventions
* If you need to use a new library via pip, please update this page
* tab width 4 spaces, expand tabs to spaces
