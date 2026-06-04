import datetime
import fcntl
import logging
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from da_base import DaBase


class DaScheduler(DaBase):
    """Scheduler with selective subprocess execution and watchdog heartbeat.

    ``watchdog.sh`` restarts the scheduler child on crash (process gone) or on a stale
    heartbeat file (process still alive but hangs).
    
    Actions listed in ``_SUBPROCESS_ACTIONS`` run in a child process; all other
    scheduled actions run inline in this process (``run_task_function``).

    We use a subprocess when a task can be long-running: the parent stays in a poll
    loop, refreshes the heartbeat about every ``_poll_s`` seconds, and can stop the child
    on timeout (SIGTERM/SIGKILL on the process group) without killing the scheduler.
    
    We use inline for short or frequent tasks (e.g. quarterly ``calc``): each
    start of a subprocess forks a new Python interpreter and adds some overhead,
    which might add up when the same action runs frequently.

    Trade-off for inline tasks: no heartbeat updates while the task runs, so a
    task longer than the watchdog ``MAX_HEARTBEAT_AGE_S`` can look like a hang and cause
    a watchdog restart.
    """

    # Subprocess actions; flock per action so we never start a duplicate long job (e.g. after watchdog
    # restart).
    _SUBPROCESS_ACTIONS = ("train_ml_predictions", "calc_baseloads")

    def __init__(self, file_name: str = None):
        super().__init__(file_name)
        self.active = self.config.scheduler.active
        self.scheduler_tasks = {entry.time: entry.action for entry in self.config.scheduler.schedule}
        
        # Heartbeat monitored by watchdog.sh.
        self._heartbeat_path = Path("/tmp/dao_scheduler_heartbeat")
        
        # Poll interval while waiting for subprocess completion.
        self._poll_s = 5

        # Generic timeout for all tasks in subprocesses.
        self._subprocess_timeout_s = 30 * 60

        # Lock directory for per-action locks.
        self._lock_dir = Path("/tmp/dao_scheduler_locks")
        self._lock_dir.mkdir(parents=True, exist_ok=True)

        # Inherit run.sh environment and current workdir.
        self._env = os.environ.copy()
        self._workdir = os.getcwd()

    def _touch_heartbeat(self):
        try:
            self._heartbeat_path.write_text(str(time.time()))
        except Exception:
            # Don't let heartbeat failures break scheduling.
            pass

    def _task_key_for_action(self, action: str) -> str | None:
        for task_key, task in self.tasks.items():
            if task.get("function") == action:
                return task_key
        return None

    def _acquire_action_lock(self, action: str):
        lock_path = self._lock_dir / f"{action}.lock"
        f = open(lock_path, "w")
        try:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            f.close()
            return None

        f.seek(0)
        f.truncate()
        f.write(f"pid={os.getpid()}\n")
        f.write(f"action={action}\n")
        f.write(f"ts={time.time()}\n")
        f.flush()
        return f

    @staticmethod
    def _release_action_lock(f):
        try:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        finally:
            f.close()

    def _run_action_subprocess(self, action: str):
        task_key = self._task_key_for_action(action)
        if task_key is None:
            logging.error(f"scheduler: no task found for action={action}")
            return

        task = self.tasks.get(task_key) or {}
        cmd = task.get("cmd")
        if not cmd:
            logging.error(f"scheduler: task_key={task_key} has no cmd for action={action}")
            return

        timeout_s = int(self._subprocess_timeout_s)
        start_ts = time.time()

        logging.info(
            f"scheduler: start subprocess action={action} task_key={task_key} "
            f"timeout_s={timeout_s} cmd={cmd}"
        )

        # New process group so we can kill the full tree (joblib/loky).
        proc = subprocess.Popen(
            cmd,
            cwd=self._workdir,
            env=self._env,
            preexec_fn=os.setsid,
        )

        # Poll-loop keeps heartbeat alive during long tasks and enables timeout handling (try SIGTERM before SIGKILL).
        while True:
            self._touch_heartbeat()

            exit_code = proc.poll()
            if exit_code is not None:
                dur = int(time.time() - start_ts)
                if exit_code == 0:
                    logging.info(
                        f"scheduler: done action={action} exit_code={exit_code} duration_s={dur}"
                    )
                else:
                    logging.error(
                        f"scheduler: failed action={action} exit_code={exit_code} duration_s={dur}"
                    )
                return

            runtime_s = time.time() - start_ts
            if runtime_s > timeout_s:
                dur = int(runtime_s)
                logging.error(
                    f"scheduler: timeout action={action} pid={proc.pid} duration_s={dur} -> SIGTERM"
                )
                try:
                    os.killpg(proc.pid, signal.SIGTERM)
                except ProcessLookupError:
                    return

                grace_start = time.time()
                while True:
                    self._touch_heartbeat()
                    exit_code = proc.poll()
                    if exit_code is not None:
                        logging.error(
                            f"scheduler: terminated action={action} exit_code={exit_code}"
                        )
                        return
                    if time.time() - grace_start > 15:
                        break
                    time.sleep(1)

                logging.error(
                    f"scheduler: still running action={action} pid={proc.pid} -> SIGKILL"
                )
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    return
                exit_code = proc.wait()
                logging.error(f"scheduler: killed action={action} exit_code={exit_code}")
                return

            time.sleep(self._poll_s)

    def _run_action_inline(self, action: str):
        task_key = self._task_key_for_action(action)
        if task_key is None:
            logging.error(f"scheduler: no task found for action={action}")
            return

        logging.info(f"scheduler: start inline action={action} task_key={task_key}")
        self.run_task_function(task_key)
        logging.info(f"scheduler: done inline action={action} task_key={task_key}")

    def _run_action(self, action: str):
        if action in self._SUBPROCESS_ACTIONS:
            self._run_action_subprocess(action)
        else:
            self._run_action_inline(action)

    def scheduler(self):
        # if not (self.notification_entity is None) and self.notification_opstarten:
        #     self.set_value(self.notification_entity, "DAO scheduler gestart " +
        #                    datetime.datetime.now().strftime('%d-%m-%Y %H:%M:%S'))

        while True:
            t = datetime.datetime.now()
            next_min = t - datetime.timedelta(
                minutes=-1, seconds=t.second, microseconds=t.microsecond
            )
            # wacht tot hele minuut 0% cpu
            time.sleep((next_min - t).total_seconds())

            # heartbeat once per minute
            self._touch_heartbeat()
            if not self.active:
                continue

            hour = next_min.hour
            minute = next_min.minute
            key0 = str(hour).zfill(2) + str(minute).zfill(2)
            # ieder uur in dezelfde minuut voorbeeld xx15
            key1 = "xx" + str(minute).zfill(2)
            # iedere minuut in een uur voorbeeld 02xx
            key2 = str(hour).zfill(2) + "xx"
            actions = []
            for key in self.scheduler_tasks:
                if key == key0:
                    actions.append(self.scheduler_tasks[key])
                elif key == key1:
                    actions.append(self.scheduler_tasks[key])
                elif key == key2:
                    actions.append(self.scheduler_tasks[key])

            for action in actions:
                lock_f = None
                if action in self._SUBPROCESS_ACTIONS:
                    lock_f = self._acquire_action_lock(action)
                    if lock_f is None:
                        logging.warning(f"scheduler: skip action={action} (already running)")
                        continue

                try:
                    self._run_action(action)
                except KeyboardInterrupt:
                    sys.exit()
                except Exception:
                    logging.exception(f"scheduler: exception action={action}")
                finally:
                    if lock_f is not None:
                        self._release_action_lock(lock_f)


def main():
    da_sched = DaScheduler("../data/options.json")
    # Touch heartbeat as soon as init finishes; doing it later can trigger watchdog restart on stale file.
    da_sched._touch_heartbeat()
    da_sched.scheduler()


if __name__ == "__main__":
    main()
