# Installation
Installing PE_Kit is really easy!  Please follow the instructions for your OS to get started, once installed please read the [Quickstart instructions](help.md#quickstart) to find out how to get up and running as quickly as possible.

You will need to download a PE Docker image (approx 3.5GB) and an agent image (approx 1GB) before PE_Kit is usable.  This can be done from the [settings screen](help.md#settings-screen).

## OSX
1. Install [Docker for Mac](https://www.docker.com/products/docker#/mac)
2. Test docker is working by running `Docker` from your applications group by using spotlight.
3. Once docker has loaded, You need use the docker whale icon in the menu bar at the top of the screen to reserve more resources for docker (via preferences):
  * At least 2 cores
  * About 4 GB RAM
  * Diskspace is used directly from your laptop now :)
4. Download the latest [PE_Kit installer](https://github.com/GeoffWilliams/pe_kit/releases)
5. Run the `dmg` file you downloaded to install the application:
    1. Drag and drop the `pe_kit` icon into `Applications`
    2. Double click the `Exec/Make Symlinks` icon (top middle)

### OSX Notes
* PE_Kit v0.5.0 and above only support Docker for Mac, NOT Docker Toolbox.  If you need to use Docker Toolbox you must use an earlier version
* If you previously installed [Docker Toolbox for OSX](https://www.docker.com/products/docker-toolbox), you should remove your previous boot2docker VM to avoid confusion:


```shell
docker-machine stop
docker-machine rm
```

PE_Kit is now installed, you may run `pe_kit` from your applications group by using spotlight search

## Linux
There are no packages for Linux yet but the code works fine straight out of git.  Please follow the [developer instructions](develop.md#linux-instructions) to get things working on Linux.
