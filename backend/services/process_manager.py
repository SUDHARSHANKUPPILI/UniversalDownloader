"""Process management for yt-dlp and FFmpeg subprocesses."""

import os
import signal
import platform
import subprocess
import sys
from pathlib import Path


def is_windows() -> bool:
    """Check if running on Windows."""
    return platform.system() == "Windows"


def is_unix() -> bool:
    """Check if running on a Unix-like system."""
    return platform.system() != "Windows"


def create_process_group(proc: subprocess.Popen) -> None:
    """Set up process group for safe termination on Unix systems.

    On Unix, we set the process group ID to the process's own PID so that
    killing the parent terminates all child processes. On Windows, we rely
    on subprocess.Popen behavior and CREATE_NO_WINDOW flag.
    """
    if not is_windows():
        try:
            # Set the process group ID to the process's own PID
            # This makes the process the session leader
            os.setpgid(proc.pid, proc.pid)
        except OSError:
            pass


def terminate_subprocess(proc: subprocess.Popen, timeout: float = 5.0) -> dict:
    """Terminate a subprocess and all child processes safely.

    On Windows, uses taskkill /F /T /PID to terminate the process tree.
    On Unix, kills the process group with SIGTERM then SIGKILL.

    Args:
        proc: The subprocess.Popen to terminate
        timeout: Maximum time to wait before killing

    Returns:
        dict with 'killed' bool and 'reason' string
    """
    if proc.poll() is not None:
        return {"killed": True, "reason": "Process already terminated"}

    if is_windows():
        # On Windows: use taskkill to kill the process tree
        try:
            result = subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                capture_output=True, text=True, timeout=timeout,
            )
            if result.returncode == 0:
                return {"killed": True, "reason": "Process tree terminated via taskkill"}
        except Exception:
            pass

        # Fallback: terminate then kill
        try:
            proc.terminate()
            proc.wait(timeout=timeout)
            return {"killed": True, "reason": "Terminated via Popen.terminate"}
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
            return {"killed": True, "reason": "Killed via Popen.kill"}

    else:
        # On Unix: kill the process group
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            proc.wait(timeout=timeout)
            return {"killed": True, "reason": "Terminated via SIGTERM (process group)"}
        except subprocess.TimeoutExpired:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                proc.wait()
                return {"killed": True, "reason": "Killed via SIGKILL (process group)"}
            except ProcessLookupError:
                pass
            proc.wait()
            return {"killed": True, "reason": "Killed via SIGKILL"}
        except ProcessLookupError:
            return {"killed": True, "reason": "Process already terminated"}
        except Exception as e:
            try:
                proc.kill()
                proc.wait()
                return {"killed": True, "reason": f"Killed via SIGKILL ({e})"}
            except Exception:
                return {"killed": False, "reason": f"Error: {e}"}


def cancel_subprocess(proc: subprocess.Popen) -> dict:
    """Cancel a subprocess immediately.

    Attempts SIGTERM first, then SIGKILL.

    Args:
        proc: The subprocess.Popen to cancel

    Returns:
        dict with 'killed' bool and 'reason' string
    """
    return terminate_subprocess(proc)


def resume_subprocess(proc: subprocess.Popen) -> dict:
    """Resume a paused download.

    For yt-dlp downloads, this typically means just letting the process continue
    if it was stopped gracefully (e.g., via signal stop, not killed).

    Args:
        proc: The subprocess.Popen to resume

    Returns:
        dict with success status and reason
    """
    if proc.poll() is not None:
        # Process already ended; can't resume
        return {"success": False, "reason": "Process already terminated, cannot resume"}

    # yt-dlp supports resume with -r/--resume
    # The process should already be running; no special action needed if it's just paused
    return {"success": True, "reason": "Process already running"}


def get_process_info(proc: subprocess.Popen) -> dict:
    """Get readable info about a running process."""
    return {
        "pid": proc.pid,
        "returncode": proc.returncode,
        "poll": proc.poll(),
        "windows": platform.system() == "Windows",
    }


def get_process_status(process: subprocess.Popen) -> dict:
    """Get the current status of a download process.

    Returns a dict with:
        - running: bool
        - progress: float (0-100) or None
        - speed: str or None
        - eta: str or None
        - total_size: str or None
        - completed_size: str or None
    """
    result = process.poll()
    if result is not None:
        return {"running": False, "exit_code": result, "progress": None, "speed": None, "eta": None, "total_size": None, "completed_size": None}

    # Process is still running; we can't get real progress without reading stdout
    # In a production system, you'd parse yt-dlp's progress output or use --progress-json
    return {"running": True, "progress": None, "speed": None, "eta": None, "total_size": None, "completed_size": None}


def kill_process_tree(pid: int, timeout: float = 5.0) -> dict:
    """Kill an entire process tree by PID (Windows only implementation for now).

    Args:
        pid: The process ID to kill
        timeout: Maximum time to wait before force-killing

    Returns:
        dict with 'killed' bool and 'reason' string
    """
    if not is_windows():
        # Fallback to regular termination for Unix
        try:
            proc = subprocess.Popen(["ps", "-p", str(pid), "-o", "pid="], capture_output=True, text=True)
            if proc.stdout.strip():
                proc.wait(timeout=0.5)
                return terminate_subprocess(proc, timeout)
            else:
                return {"killed": True, "reason": "Process already terminated"}
        except Exception as e:
            return {"killed": False, "reason": f"Error: {e}"}
    else:
        # Windows implementation
        killed = False
        reason = ""
        try:
            # Use taskkill to kill the process and its children
            result = subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(pid)],
                capture_output=True,
                text=True,
                timeout=timeout
            )
            if result.returncode == 0:
                killed = True
                reason = "Killed process tree via taskkill"
            else:
                # Try regular termination first
                try:
                    proc = subprocess.Popen(["cmd", "/c", f"tasklist /FI \"PID eq {pid}\""],
                                          capture_output=True, text=True, timeout=2)
                    if proc.stdout.strip() and str(pid) in proc.stdout:
                        proc.terminate()
                        proc.wait(timeout=timeout)
                        killed = True
                        reason = "Terminated process via SIGTERM"
                    else:
                        killed = True
                        reason = "Process already terminated"
                except Exception:
                    # Force kill with taskkill /F if available
                    try:
                        subprocess.run(["taskkill", "/F", "/PID", str(pid)],
                                     capture_output=True, timeout=2)
                        killed = True
                        reason = "Killed process via taskkill /F"
                    except Exception as e2:
                        reason = f"Error killing process: {e2}"
        except Exception as e:
            reason = f"Error: {e}"

        return {"killed": killed, "reason": reason}