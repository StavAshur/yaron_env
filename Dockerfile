# ROS 1 Noetic dev environment for the Yaskawa SDA10F project.
# Meant to be used as a Distrobox container (see distrobox.ini), not run standalone.
#
# Build:  docker build -t local/ros-noetic-motoman:latest ~/catkin_ws/env
FROM ubuntu:20.04

ENV DEBIAN_FRONTEND=noninteractive \
    TZ=Asia/Jerusalem \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8

# --- Base tools + what Distrobox expects (pre-installed so first start is fast) ---
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates curl wget gnupg2 lsb-release tzdata locales \
        sudo bash-completion less vim nano git openssh-client \
        procps util-linux findutils mount diffutils passwd pinentry-curses \
        libnss-myhostname libvte-2.91-0 iproute2 iputils-ping net-tools ethtool \
        mesa-utils libgl1-mesa-dri libglx-mesa0 x11-apps \
        build-essential cmake python3-pip \
    && rm -rf /var/lib/apt/lists/*

# --- ROS Noetic apt repo. Key is fetched fresh (the 2025 key rotation broke old images). ---
RUN curl -sSL https://raw.githubusercontent.com/ros/rosdistro/master/ros.key \
        | gpg --dearmor -o /usr/share/keyrings/ros-archive-keyring.gpg \
 && echo "deb [signed-by=/usr/share/keyrings/ros-archive-keyring.gpg] http://packages.ros.org/ros/ubuntu focal main" \
        > /etc/apt/sources.list.d/ros1.list

# --- ROS + MoveIt + Motoman driver deps + build tooling ---
RUN apt-get update && apt-get install -y --no-install-recommends \
        ros-noetic-desktop-full \
        ros-noetic-moveit \
        ros-noetic-industrial-core \
        ros-noetic-joint-state-publisher-gui \
        ros-noetic-tf2-ros ros-noetic-cv-bridge \
        python3-rosdep python3-rosinstall python3-wstool \
        python3-catkin-tools python3-osrf-pycommon python3-vcstool \
        python3-opencv python3-numpy \
    && rm -rf /var/lib/apt/lists/*

RUN rosdep init && rosdep update --rosdistro noetic || true

# --- Auto-source ROS and the workspace (login shells, which `distrobox enter` uses) ---
RUN printf '%s\n' \
  '# ROS Noetic environment' \
  'if [ -n "$BASH_VERSION" ] && [ -f /opt/ros/noetic/setup.bash ]; then' \
  '  . /opt/ros/noetic/setup.bash' \
  '  [ -f "$HOME/catkin_ws/devel/setup.bash" ] && . "$HOME/catkin_ws/devel/setup.bash"' \
  'fi' > /etc/profile.d/ros-noetic.sh

# Passwordless sudo inside the container (host `docker` group is already root-equivalent).
# Named zz-* so it sorts after the sudoers.d file that distrobox creates at init.
RUN echo '%sudo ALL=(ALL) NOPASSWD:ALL' > /etc/sudoers.d/zz-nopasswd && chmod 440 /etc/sudoers.d/zz-nopasswd

# --- Bota F/T sensor (EtherCAT): driver, capability helper, and the library path file capabilities need ---
# (file capabilities make binaries ignore LD_LIBRARY_PATH, hence the ld.so.conf entry; see src/README.md)
RUN apt-get update && apt-get install -y --no-install-recommends \
        ros-noetic-bota-driver ros-noetic-ethercat-grant libxmlrpcpp-dev librosconsole-dev \
    && rm -rf /var/lib/apt/lists/* \
 && echo /opt/ros/noetic/lib > /etc/ld.so.conf.d/ros-noetic.conf && ldconfig

# The container hostname (noetic.<host>) does not resolve, which breaks ROS master lookups between terminals.
# Default to localhost; override ROS_HOSTNAME/ROS_IP yourself if a ROS node on another machine must connect.
RUN echo 'export ROS_HOSTNAME="${ROS_HOSTNAME:-localhost}"' >> /etc/profile.d/ros-noetic.sh
