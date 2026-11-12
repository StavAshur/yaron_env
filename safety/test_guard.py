#!/usr/bin/env python3
"""Self-test for robot_safety_guard.py.  Run:  python3 -I ~/catkin_ws/env/safety/test_guard.py
It only calls the guard's decide() on strings; it never executes any of the sample commands."""
import importlib.util
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.realpath(__file__))
spec = importlib.util.spec_from_file_location("guard", os.path.join(HERE, "robot_safety_guard.py"))
g = importlib.util.module_from_spec(spec)
spec.loader.exec_module(g)

tmp = tempfile.mkdtemp(prefix="guardtest_")


def mk(name, text):
    p = os.path.join(tmp, name)
    with open(p, "w") as f:
        f.write(text)
    return p


evil_py = mk("evil.py", "import moveit_commander\nmoveit_commander.MoveGroupCommander('arm_left').go()\n")
evil_sh = mk("evil.sh", "#!/bin/bash\nroslaunch some_pkg some.launch\n")
calls_evil = mk("calls_evil.sh", "#!/bin/bash\nbash %s\n" % evil_sh)
clean_sh = mk("clean.sh", "#!/bin/bash\necho hello\nls /tmp\n")
os.makedirs(os.path.join(tmp, "scripts"))
mk("scripts/random_walk_xyz.py", "from geometry_msgs.msg import Pose\nimport rospy\nrospy.Publisher('/joint_path_command', X)\n")

H = "/home/roblab"
DEMO = "distrobox enter noetic -- bash -l -c 'roslaunch -p 11999 motoman_sda10f_moveit_config demo.launch'"

BASH_CASES = [
    # ---------- must be DENIED ----------
    (False, "roslaunch motoman_sda10f_moveit_config moveit_planning_execution.launch robot_ip:=192.168.255.3 controller:=fs100"),
    (False, "distrobox enter noetic -- bash -l -c 'rosservice call /robot_enable'"),
    (False, "rosservice call /robot_enable"),
    (False, "rostopic pub /joint_path_command trajectory_msgs/JointTrajectory '{}'"),
    (False, "rosrun yaron_plan_to_gaol random_mover.py"),
    (False, "python3 %s/catkin_ws/src/yaron_plan_to_gaol/scripts/random_mover.py" % H),
    (False, "python3 %s/catkin_ws/src/yaron_plan_to_gaol/scripts/ran*.py" % H),
    (False, "python3 %s/catkin_ws/src/yaron_plan_to_gaol/scripts/random_{mover,x}.py" % H),
    (False, "bash -c \"$(echo cm9zc2VydmljZQ== | base64 -d) call /x\""),
    (False, "ro''sservice call /robot_''enable"),
    (False, "A=ros; ${A}service call /x"),
    (False, "for f in ~/catkin_ws/src/*/scripts/*.py; do python3 $f; done"),
    (False, "find %s/catkin_ws/src -name '*.py' -exec python3 {} ;" % H),
    (False, "cd %s/catkin_ws/src/yaron_plan_to_gaol/scripts && python3 ./add_walls.py" % H),
    (False, "distrobox enter noetic -- bash -l -c 'roslaunch motoman_sda10f_moveit_config demo.launch'"),   # not isolated
    (False, "distrobox enter noetic -- bash -l -c 'roslaunch -p 11311 motoman_sda10f_moveit_config demo.launch'"),
    (False, "distrobox enter noetic"),
    (False, "docker exec noetic bash -c 'echo hi'"),
    (False, "docker run --rm -it ubuntu:20.04 bash"),
    (False, "nmcli connection up robot-enp2s0"),
    (False, "nmcli con modify robot-enp2s0 ipv4.addresses 1.2.3.4/24"),
    (False, "ip addr add 192.168.255.100/24 dev enp2s0"),
    (False, "ping -c 3 192.168.255.4"),
    (False, "ping -c 3 192.168.255.3; rosservice call /x"),
    (False, "nc 192.168.255.3 50240"),
    (False, "python3 -c \"import moveit_commander; moveit_commander.MoveGroupCommander('arm_left').go()\""),
    (False, "python3 %s" % evil_py),
    (False, "bash %s" % evil_sh),
    (False, "bash %s" % calls_evil),                                  # indirect: script calls bad script
    (False, "python3 %s/scripts/random_walk_xyz.py" % tmp),           # joint_path_command inside
    (False, "python3 %s/scripts/random_*.py" % tmp),
    (False, "docker exec noetic pkill -f demo.launch; rosservice call /robot_enable"),
    (False, "distrobox enter noetic -- bash -l %s/catkin_ws/env/safety/something.sh" % H),   # subdir not allowed
    (False, "distrobox enter noetic -- bash -l %s" % evil_sh),         # not in allowed script dirs
    (False, "sed -i 's/x/y/' ~/.claude/settings.json"),
    (False, "echo '{}' > ~/.claude/settings.json"),
    (False, "rm %s/.claude/hooks/robot_safety_guard.py" % H),
    (False, "mv %s/catkin_ws/env/safety/robot_allowlist.txt /tmp/x" % H),
    (False, "echo disableAllHooks"),
    (False, "echo 'rosservice call /robot_enable'"),                  # even printing it: refuse, no ambiguity
    # ---------- must be ALLOWED ----------
    (True, "ls -la %s/catkin_ws" % H),
    (True, "cat %s/catkin_ws/src/README.md" % H),
    (True, "grep -rn robot_enable %s/catkin_ws/src/README.md" % H),
    (True, "cat %s/.claude/settings.json" % H),
    (True, "git status"),
    (True, "git -C %s/catkin_ws/src log --oneline" % H),
    (True, "git add README.md"),
    (True, "git submodule status"),
    (True, "docker ps"),
    (True, "docker images"),
    (True, "docker build -t local/ros-noetic-motoman:latest %s/catkin_ws/env" % H),
    (True, "docker save local/ros-noetic-motoman:latest | gzip > /tmp/x.tar.gz"),
    (True, "distrobox list"),
    (True, "distrobox assemble create --file %s/catkin_ws/env/distrobox.ini" % H),
    (True, "nmcli connection show"),
    (True, "ip -4 addr show enp2s0"),
    (True, "ethtool enp2s0"),
    (True, "ping -c 3 -W 1 192.168.255.3"),
    (True, "ping -c 3 192.168.255.3"),
    (True, DEMO),
    (True, "nohup " + DEMO + " > /tmp/demo.log 2>&1 &"),
    (True, "docker exec noetic pgrep -a rviz|move_group"),
    (True, "docker exec noetic pkill -f demo.launch"),
    (True, "distrobox enter noetic -- bash -l %s/catkin_ws/env/build_ws.sh" % H),
    (True, "bash %s" % clean_sh),
    (True, "python3 --version"),
    (True, "curl -sI https://example.com"),
    (True, "apt list --installed"),
    (True, "cd %s/catkin_ws && ls" % H),
    (True, "python3 -I %s/catkin_ws/env/safety/test_guard.py" % H),
]

FILE_CASES = [
    (False, "Write", {"file_path": "%s/.claude/settings.json" % H}),
    (False, "Edit", {"file_path": "%s/.claude/hooks/robot_safety_guard.py" % H}),
    (False, "Write", {"file_path": "%s/catkin_ws/env/safety/robot_allowlist.txt" % H}),
    (False, "Write", {"file_path": "/etc/claude-code/managed-settings.json"}),
    (False, "Write", {"file_path": "%s/catkin_ws/CLAUDE.md" % H}),
    (False, "Edit", {"file_path": "%s/.claude/CLAUDE.md" % H}),
    (False, "Write", {"file_path": "%s/.claude/projects/-home-roblab-catkin-ws/memory/feedback_robot_never_move_safety.md" % H}),
    (True, "Write", {"file_path": "%s/catkin_ws/env/Dockerfile" % H}),
    (True, "Edit", {"file_path": "%s/catkin_ws/src/README.md" % H}),
    (True, "Write", {"file_path": "%s/.claude/projects/-home-roblab-catkin-ws/memory/MEMORY.md" % H}),
]

TOOL_CASES = [
    (False, "mcp__terminal__run_in_terminal", {"command": "ls"}),
    (False, "mcp__terminal__open_terminal_tab", {"command": "ls"}),
    (False, "Bash", {}),
    (False, "Bash", {"command": 123}),
]

fails = 0


def check(expect, tool, inp, label):
    global fails
    allowed, why = g.decide(tool, inp, "/home/roblab/catkin_ws")
    ok = (allowed == expect)
    if not ok:
        fails += 1
    print("%s  expect=%-5s got=%-5s  %s%s" % ("ok  " if ok else "FAIL", "allow" if expect else "deny",
                                              "allow" if allowed else "deny", label[:110],
                                              "" if allowed else "   [" + why[:70] + "]"))


for expect, cmd in BASH_CASES:
    check(expect, "Bash", {"command": cmd}, cmd)
for expect, tool, inp in FILE_CASES:
    check(expect, tool, inp, "%s %s" % (tool, inp.get("file_path")))
for expect, tool, inp in TOOL_CASES:
    check(expect, tool, inp, "%s %s" % (tool, inp))

# End-to-end: the real hook entry point must exit 2 on garbage input and when the allowlist is missing.
guard = os.path.join(HERE, "robot_safety_guard.py")
r = subprocess.run([sys.executable, "-I", guard], input=b"not json", capture_output=True)
print("%s  garbage stdin -> exit %d (want 2)" % ("ok  " if r.returncode == 2 else "FAIL", r.returncode))
fails += r.returncode != 2
r = subprocess.run([sys.executable, "-I", guard],
                   input=b'{"tool_name":"Bash","tool_input":{"command":"rosservice call /robot_enable"}}',
                   capture_output=True)
print("%s  hard-blocked command via real entry point -> exit %d (want 2)" % ("ok  " if r.returncode == 2 else "FAIL", r.returncode))
fails += r.returncode != 2

print("\n%d failure(s)" % fails)
sys.exit(1 if fails else 0)
