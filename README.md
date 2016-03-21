# Prerequisites
See http://www.pyladies.com/blog/Get-Your-Mac-Ready-for-Python-Programming/ for
how to install python on a mac 
* Python 2.7.x
* Xcode 

# Setup
1.  Install Docker (https://www.docker.com/products/docker-toolbox)
2.  Install Kivy (GUI/Python support) https://kivy.org/#download
  * Follow the MAC setup instructions at https://kivy.org/docs/installation/installation-osx.html
  * Kivy installs all its libraries into a virtualenv shipped in its own 
    installer.  The docker api needs to be installed into this environment:
      i.    cd /Applications/Kivy.app/Contents/Resources/venv 
      ii.   source bin/activate
      iii.  pip install docker-py

