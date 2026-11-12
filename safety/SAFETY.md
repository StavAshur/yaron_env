# Robot-motion safety layers

**Rule:** Claude must never run anything that could move the robot, directly or indirectly.
Each layer below works independently; any one of them failing leaves the others in place.
Layers 0 and 1 do not depend on Claude, software or hooks at all, so they are the real guarantee.

| # | Layer | Who controls it | What it stops | Weakness |
|---|-------|-----------------|---------------|----------|
| 0 | **Physical**: servo power OFF / pendant in TEACH mode / E-stop within reach | you | Any motion command, from anyone | needs you to do it |
| 1 | **Network air gap**: `robot-enp2s0` link DOWN unless you are actively working with the robot | you (`nmcli`) | Nothing on this PC can reach the controller at all | needs you to do it |
| 2 | **Isolated ROS graph**: Claude's sim runs on ROS master port 11999, never the default 11311 | allowlist | Claude's runs can never join/disturb a real-robot session | only covers allowlisted launches |
| 3 | **Managed policy (root-owned)**: guard hook + deny rules in `/etc/claude-code/` | you, via `sudo` | Claude cannot edit/disable them (no sudo password) | you must install it (`install_safety.sh`) |
| 4 | **Guard hook** (`robot_safety_guard.py`), fail-closed, default-deny + allowlist, also user-level copy in `~/.claude/hooks/` | you | Pattern-based blocking, script-content scanning, self-protection | pattern based: cannot see inside arbitrary programs, so it is default-deny |
| 5 | **Permission deny rules** (separate engine from the hook) | settings | Blocks key command strings even if the hook is broken | string matching, evadable by wrappers (hook covers those) |
| 6 | **Instructions**: `~/.claude/CLAUDE.md`, `~/catkin_ws/CLAUDE.md`, saved memory | files | Claude's own checks before acting | model compliance, so never the only layer |
| 7 | **Project code** (to build): launch files default to `sim:=true`; real robot needs an explicit arm switch you create | code | Accidental real-robot launch by anyone | not built yet |

## How the guard decides (layer 4)
1. Plain read-only commands (`ls`, `cat`, `grep`, `git status`...) with no shell tricks: allowed.
2. Exact match with `robot_allowlist.txt`: allowed (scripts it names are still scanned).
3. Touches the safety files themselves: blocked.
4. Contains robot-motion patterns (`robot_enable`, `rosservice call`, `rostopic pub`, `rosrun`,
   `robot_ip`, `moveit_commander`, `.go(`, `192.168.255.x`, joint-trajectory topics, `nmcli up`...): blocked.
5. Shell tricks (`eval`, `base64`, `$(..)`, `$VAR`, braces, `find -exec`, `xargs`) next to robot-related
   words, or `cd` + run something: blocked (cannot be verified).
6. Anything that runs inside the ROS/robot environment (`distrobox enter`, `docker exec`, `roslaunch`...)
   that is not allowlisted: blocked.
7. Scripts/launch files named in the command (globs expanded, followed recursively) are scanned for the
   same patterns. Everything else: allowed.
Also: Claude may not start commands in your terminal panel, and any internal error, missing script or
timeout **blocks** (`onFailure: block`, exit 2).

## Operating it
- Test: `python3 -I ~/catkin_ws/env/safety/test_guard.py` (86 cases).
- Approve a new Claude-runnable command: add an exact regex to `robot_allowlist.txt`, then
  `sudo bash ~/catkin_ws/env/safety/install_safety.sh` (this also re-runs the tests).
- If the guard blocks something legitimate, run that command yourself in your own terminal.
- To remove everything: delete `/etc/claude-code/` and the `hooks`/`permissions` entries in `~/.claude/settings.json`.

## Recommended routine
1. Robot not in use / you are away: `nmcli connection down robot-enp2s0` and servo power OFF.
2. Working with the robot (read-only monitoring by Claude): link up, pendant in TEACH or servo off.
3. Moving the robot: **you** run the launch in your own terminal; Claude only observes.

## Honest limits
Software layers cannot prove that an arbitrary program is harmless. That is why layers 0 and 1 exist and
why layer 4 is default-deny. Treat layers 3-6 as strong guard rails, and 0-1 as the actual guarantee.
