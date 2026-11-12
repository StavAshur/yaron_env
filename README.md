# ROS 1 Noetic environment (Distrobox on Ubuntu 24.04)

Host: Ubuntu 24.04. Everything ROS runs in a Ubuntu 20.04 + Noetic container.
The workspace (`~/catkin_ws`) lives on the host and is shared into the container.

## One-time setup (fresh machine)
```bash
sudo apt install docker.io distrobox
sudo usermod -aG docker $USER          # then log out / log in
cd ~/catkin_ws/src && git submodule update --init   # motoman, robotiq, zed-ros-wrapper
docker build -t local/ros-noetic-motoman:latest ~/catkin_ws/env
distrobox assemble create --file ~/catkin_ws/env/distrobox.ini
distrobox enter noetic -- bash -l ~/catkin_ws/env/build_ws.sh
```
RealSense D435 (host, one time): lets a normal user open the camera.
```bash
sudo cp ~/catkin_ws/env/udev/99-realsense.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules && sudo udevadm trigger
```
The camera must link at USB 3 (`lsusb -t` shows 5000M); with a bad/USB 2 cable it re-enumerates and sends no frames.

Back up the image in case the Focal/Noetic repos disappear:
`docker save local/ros-noetic-motoman:latest | gzip > ros-noetic-motoman.tar.gz`

## Daily use
```bash
distrobox enter noetic                      # interactive shell, ROS + workspace already sourced
distrobox enter noetic -- bash -l -c 'roslaunch <pkg> <file>'   # one-shot (needs `bash -l`)
```
Robot network: PC (`eno1`) and the FS100 are both plugged into a switch, which is also uplinked to the
campus network. `eno1` keeps its DHCP address and carries a second static address, 192.168.255.100/24;
the robot controller (FS100) is 192.168.255.3 (verified by ping, MAC 00:20:b5:... = Yaskawa).
Persist with:  nmcli connection modify netplan-eno1 +ipv4.addresses 192.168.255.100/24
`enp2s0` is a separate 100 Mb link to a silent device, probably the Bota EtherCAT sensor: do NOT put the
robot address on it. The old `robot-enp2s0` profile is a mistake and can be deleted.

## Notes
- ZED / robotiq packages are blacklisted in `build_ws.sh` until the ZED SDK and a
  supported GPU are set up (`catkin config --no-blacklist` to undo).
- The container user has passwordless sudo (see Dockerfile).
- Known harmless MoveIt messages with the SDA10F config: "Group 'torso'/'arms'/'sda10f'
  is not a chain" (KDL IK only for single arms) and a stale `MoveGroupExecuteService` capability.
