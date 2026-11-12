#!/usr/bin/env python3
"""
Claude Code PreToolUse guard: ROBOT-MOTION SAFETY.   FAIL-CLOSED.

Rule: Claude must never run anything that could move the robot, directly or
indirectly. This hook is ONE layer of several (see SAFETY.md). It is pattern
based, so it cannot see inside arbitrary programs. Therefore it works by
DEFAULT-DENY for anything that can reach ROS / the containers / the robot,
with a short, user-controlled allowlist (robot_allowlist.txt, next to this file).

Protocol: reads the hook JSON on stdin. Exit 0 = allow. Exit 2 = block (stderr is
shown to Claude). Any internal error also blocks (exit 2).
"""
import glob
import json
import os
import re
import shlex
import sys

HERE = os.path.dirname(os.path.realpath(__file__))
ALLOWLIST_FILE = os.path.join(HERE, "robot_allowlist.txt")
MAX_SCAN_BYTES = 2_000_000

HELP = (
    "\nSAFETY RULE: Claude must NEVER run anything that could move the robot, directly or "
    "indirectly (including programs/launch files/scripts that call code that moves it).\n"
    "Do NOT retry, rephrase, wrap or work around this. Tell the user exactly what you wanted "
    "to run and why, and let the user run it in their own terminal if they decide to.\n"
)

I = re.I


def rx(p):
    return re.compile(p, I)


# --- Things that are never OK for Claude to run (also scanned inside script files) -------
HARD = [
    (rx(r"robot[_-]?(en|dis)able"), "robot enable/disable service"),
    (rx(r"joint[_-]?(path|ft|trajectory|command)|follow_joint_trajectory|execute_trajectory|trajectory_action"),
     "robot joint-command / trajectory interface"),
    (rx(r"\b(rosservice\s+call|rostopic\s+pub|rosrun|rosbag\s+play|actionlib|axclient|rqt)\b"),
     "ROS command that can publish/call/act"),
    (rx(r"moveit_planning_execution|robot_interface_streaming|motoman_driver|_streaming\.launch|robot_ip|"
        r"controller:=|fs100|random_mover|plan_to_gaol|bringup"),
     "real-robot driver / motion launch or script"),
    (rx(r"moveit_commander|movegroup|move_group_commander|\.go\s*\(|\.execute\s*\(|\.move\s*\(|"
        r"set_pose_target|set_joint_value_target|set_named_target|compute_cartesian_path|/move_group/goal"),
     "MoveIt motion API"),
    (rx(r"192\.168\.255\."), "robot subnet (192.168.255.x)"),
    (rx(r":(11000|50240|50241|50242)\b"), "robot controller TCP port"),
    (rx(r"\bnmcli\b.*\b(up|down|add|modify|mod|delete|reload|connect|disconnect|edit)\b"),
     "changes to network connections"),
    (rx(r"\bip\s+(-\S+\s+)*(addr|address|link|route|neigh|neighbor|rule)\s+(add|del|delete|set|flush|change|replace)\b"),
     "changes to network interfaces"),
    (rx(r"\b(ifconfig|ifup|ifdown|netplan\s+(apply|set|try))\b"), "changes to network interfaces"),
]
# Extra things that must not appear inside scripts we are about to run (indirect launching).
FILE_EXTRA = [
    (rx(r"\b(roslaunch|rosrun|rosservice|rostopic|rosnode|rosparam|rosbag|roscore)\s+\S"),
     "script launches/uses ROS nodes or services"),
]

# Anything that executes inside the robot-capable environment is default-deny unless allowlisted.
DOMAIN_EXEC = rx(
    r"\bdistrobox(-enter|-host-exec)?\s+(enter|run|enter-host)\b|\bdistrobox-(enter|host-exec)\b|"
    r"\b(docker|podman)\s+(container\s+)?(exec|run|start|restart|compose|cp|attach|unpause|kill)\b|"
    r"\bros(launch|run|service|topic|node|param|bag|core|console|lib)\b|\brviz\b|\brqt|"
    r"catkin_ws/(devel|build|install)/"
)
# Programs/constructs that execute other files or commands.
EXECUTORS = rx(r"(\b(python[0-9.]*|bash|sh|dash|zsh|perl|ruby|node|source|exec|env|xargs|parallel|nohup|setsid|"
               r"timeout|watch|script)\b|(^|\s)\./|(^|\s)\.\s)")
CHDIR = re.compile(r"\b(cd|pushd|chdir)\b|\s-C\s|--directory|--chdir|--workdir|--cwd")
DOMAIN_WORDS = rx(r"(ros|rviz|moveit|motoman|catkin|robot|joint|trajectory|distrobox|docker|podman|"
                  r"192\.168\.255|zed|bota|rokubi|ethercat|yaskawa|fs100|gaol)")
DYNAMIC = rx(r"(\$\(|\$\{|`|\beval\b|base64|\bxxd\b|\\x[0-9a-f]{2}|<\(|\$[A-Za-z_]|\{[^}]*[,.][^}]*\})")
EXEC_SPAWN = rx(r"(^|\s)-(exec|execdir|ok|okdir)\b|\b(xargs|parallel)\b")

# Code built or decoded at run time can hide ANY command (with or without robot words): always deny.
INLINE_EXEC = rx(r"\b(bash|sh|dash|zsh|python[0-9.]*|perl|ruby|node)\b\s+-\w*[ce]\w*\s|\beval\b|\bsource\s+<|(^|\s)\.\s+<")
DECODERS = rx(r"\bbase64\s+(-d|--decode)|\bxxd\s+-r|\bopenssl\s+enc\s+-d")

# Files that must never be modified by Claude (the safety system itself).
PROTECTED = rx(
    r"(\.claude/(settings|hooks|CLAUDE)|/etc/claude-code|managed-settings|robot_safety_guard|robot_allowlist|"
    r"env/safety|catkin_ws/CLAUDE\.md|disableAllHooks|memory/\S*never_move)"
)

# --- Simple read-only commands (single command, no shell metacharacters) ------------------
META = re.compile(r"[;&|<>`\n]|\$\(")
RO_PROG = rx(r"^(cat|head|tail|ls|stat|file|wc|grep|egrep|fgrep|rg|diff|sha256sum|md5sum|readlink|realpath|du|df|"
             r"which|pwd|id|date|uname|lsblk|lsusb|lspci|nproc|free|pgrep|tree|jq|sort|uniq|cut|basename|dirname)( |$)")
FIND_OK = rx(r"^find ")
FIND_BAD = rx(r"(^| )-(exec|execdir|ok|okdir|delete|fprint\w*|fls)\b")
GIT_OK = rx(r"^git( -C \S+)? (status|log|diff|show|ls-tree|ls-files|add|commit|rev-parse|branch|remote -v|"
            r"submodule (status|init|update( --init)?)|config --get \S+)\b")


def normalize(s):
    s = s.replace("\\\n", " ")
    s = re.sub(r"[\'\"\\]", "", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def is_readonly_simple(raw, norm):
    if META.search(raw):
        return False
    if RO_PROG.search(norm) or GIT_OK.search(norm):
        return True
    if FIND_OK.search(norm) and not FIND_BAD.search(norm):
        return True
    return False


def load_allowlist():
    pats = []
    with open(ALLOWLIST_FILE, encoding="utf-8") as f:   # missing file -> exception -> block
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                pats.append(re.compile(line))
    return pats


def hard_hit(text, extra=False):
    for pat, why in HARD + (FILE_EXTRA if extra else []):
        if pat.search(text):
            return why
    return None


FILE_EXT = r"(?:py|sh|launch|xml|yaml|yml|cfg|bash)"
REF_RE = re.compile(r"[~/\w.*?\[\]\-]+\.%s\b" % FILE_EXT)
SRC_ROOT = os.path.expanduser("~/catkin_ws/src")
_index = {}


def _basename_index():
    """basename -> [paths] for scripts/launch files in the workspace (for indirect references)."""
    if not _index:
        for root, dirs, files in os.walk(SRC_ROOT):
            dirs[:] = [d for d in dirs if d != ".git"]
            for fn in files:
                if re.search(r"\.%s$" % FILE_EXT, fn):
                    _index.setdefault(fn, []).append(os.path.join(root, fn))
    return _index


def _expand(tok, bases, by_name=True):
    """Existing files a token may refer to (handles ~, relative paths, globs, bare basenames)."""
    p = os.path.expanduser(tok)
    cands = [p] if os.path.isabs(p) else [os.path.join(b, p) for b in bases if b]
    out = []
    for c in cands:
        if any(ch in c for ch in "*?["):
            out += glob.glob(c)[:200]
        elif os.path.isfile(c):
            out.append(c)
    if by_name and not out and os.sep not in tok:
        out += _basename_index().get(tok, [])[:20]
    return out


def scan_file(path, bases, seen, depth):
    if path in seen or depth > 3:
        return None
    seen.add(path)
    rp = os.path.realpath(path)
    if rp.startswith(HERE + os.sep) or "/catkin_ws/env/safety/" in rp:   # user-controlled, Claude cannot edit
        return None
    try:
        with open(path, "rb") as fh:
            data = fh.read(MAX_SCAN_BYTES)
    except OSError:
        return "file %s could not be read for verification" % path
    if b"\0" in data:
        return None
    text = data.decode("utf-8", "ignore")
    why = hard_hit(text, extra=True)
    if why:
        return "file %s contains: %s" % (path, why)
    for ref in set(REF_RE.findall(text)):                 # scripts it calls / sources / includes
        for q in _expand(ref, [os.path.dirname(path)] + bases):
            bad = scan_file(q, bases, seen, depth + 1)
            if bad:
                return bad
    return None


def scan_referenced_files(norm, cwd, explicit_only=False):
    """Scan the content of every script/launch file the command names (recursively).
    explicit_only: (used for allowlisted commands) only existing files named by path, no lookup by name."""
    try:
        toks = shlex.split(norm)
    except ValueError:
        toks = norm.split()
    seen = set()
    for tok in toks:
        if not tok or tok.startswith("-"):
            continue
        if not ((os.sep in tok) or re.search(r"\.%s$" % FILE_EXT, tok)):
            continue
        for p in _expand(tok, [cwd or os.getcwd()], by_name=not explicit_only):
            if os.path.realpath(p).startswith(HERE + os.sep):      # the guard's own (protected) directory
                continue
            bad = scan_file(p, [cwd or os.getcwd()], seen, 0)
            if bad:
                return bad
    return None


def decide(tool_name, tool_input, cwd=""):
    """Return (allowed: bool, reason: str)."""
    # --- file-writing tools: only protect the safety system itself
    if tool_name in ("Edit", "Write", "MultiEdit", "NotebookEdit"):
        path = tool_input.get("file_path") or tool_input.get("notebook_path") or ""
        real = os.path.realpath(os.path.expanduser(path)) if path else ""
        if PROTECTED.search(path) or PROTECTED.search(real):
            return False, "this file is part of the robot-safety system; only the user may change it"
        return True, ""

    # --- terminal MCP tools run commands in the user's own terminal: never allowed for Claude
    if tool_name.startswith("mcp__terminal__"):
        return False, "Claude may not start commands in the user's terminal panel"

    raw = tool_input.get("command")
    if not isinstance(raw, str):
        return False, "could not read the command to verify it"
    norm = normalize(raw)

    # 1. plain read-only commands (cannot start anything)
    if is_readonly_simple(raw, norm):
        return True, ""

    # 2. explicit user-approved allowlist (full match), still scanning any script files it names
    for pat in load_allowlist():
        if pat.fullmatch(norm):
            bad = scan_referenced_files(norm, cwd, explicit_only=True)
            if bad:
                return False, "allowlisted command but " + bad
            return True, ""

    # 3. protect the safety system from being rewritten via the shell
    if PROTECTED.search(norm):
        return False, "command touches the robot-safety system files; only the user may change them"

    # 4. things that are never OK
    why = hard_hit(norm)
    if why:
        return False, "command involves: " + why

    # 4b. code decoded or assembled at run time: cannot be verified, whatever it says
    if DECODERS.search(raw) or (INLINE_EXEC.search(raw) and DYNAMIC.search(raw)):
        return False, "command decodes or assembles code at run time (base64/eval/bash -c with expansion); cannot be verified"

    # 5. shell tricks that could hide the real command, near robot-related words
    if DYNAMIC.search(raw) and DOMAIN_WORDS.search(norm):
        return False, "command uses shell expansion/encoding next to robot-related words, so it cannot be verified"

    # 5b. commands that spawn other commands (find -exec, xargs, ...) next to robot-related words
    if EXEC_SPAWN.search(norm) and DOMAIN_WORDS.search(norm):
        return False, "command spawns other programs (exec/xargs) near robot-related paths; cannot verify what runs"

    # 6. default-deny anything that executes inside the ROS/robot environment
    if DOMAIN_EXEC.search(norm):
        return False, "command runs inside the ROS/robot environment and is not on the user's allowlist"

    # 6b. changing directory and then executing something: relative paths cannot be verified
    if CHDIR.search(norm) and EXECUTORS.search(norm):
        return False, "command changes directory and then runs something; use absolute paths so it can be verified"

    # 7. scripts/launch files named in the command must be clean
    bad = scan_referenced_files(norm, cwd)
    if bad:
        return False, bad

    return True, ""


def main():
    try:
        data = json.load(sys.stdin)
        allowed, reason = decide(
            data.get("tool_name", ""), data.get("tool_input") or {}, data.get("cwd", "")
        )
    except Exception as e:                      # FAIL CLOSED
        sys.stderr.write("ROBOT-SAFETY GUARD ERROR (blocking for safety): %r\n" % (e,))
        sys.exit(2)
    if allowed:
        sys.exit(0)
    sys.stderr.write("ROBOT-SAFETY GUARD BLOCKED THIS: " + reason + "\n" + HELP)
    sys.exit(2)


if __name__ == "__main__":
    main()
