# Installation
Installing PE_Kit is really easy!  Please follow the instructions for your OS to get started, once installed please read the [Quickstart instructions](help.md#quickstart) to find out how to get up and running as quickly as possible.

You will need to download a PE Docker image (approx 3.5GB) and an agent image (approx 1GB) before PE_Kit is usable.  This can be done from the [settings screen](help.md#settings-screen).

## OSX
1. Install [Docker for OSX](https://www.docker.com/products/docker-toolbox)
2. You need use the docker icon in the menu bar at the top of the screen to reserve more resources for docker:
  * At least 2 cores
  * About 4 GB RAM
  * Diskspace is used directly on the host now :)
  * DO NOT use boot2docker - its no longer used
3. Test docker is working by running `Docker Quickstart Terminal` from your applications group by using spotlight.  The first run will take a while as [boot2docker](http://boot2docker.io/) needs to be started
4. Download the latest [PE_Kit installer](https://github.com/GeoffWilliams/pe_kit/releases)
5. Run the `dmg` file you downloaded to install the application:
    1. Drag and drop the `pe_kit` icon into `Applications`
    2. Double click the `Exec/Make Symlinks` icon (top middle)

PE_Kit is now installed, you may run `pe_kit` from your applications group by using spotlight search

## Linux
There are no packages for Linux yet but the code works fine straight out of git.  Please follow the [developer instructions](develop.md#linux-instructions) to get things working on Linux. 
