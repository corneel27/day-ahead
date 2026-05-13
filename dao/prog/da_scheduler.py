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
    def __init__(self, file_name: str = None):
        super().__init__(file_name)
        self.active = self.config.scheduler.active
        self.scheduler_tasks = {entry.time: entry.action for entry in self.config.scheduler.schedule}

        # Heartbeat monitored by watchdog.sh.
        self._heartbeat_path = Path("/tmp/dao_scheduler_heartbeat")

        # Poll interval while waiting for subprocess completion.
        self._poll_s = 5

        # Generic timeout for all tasks, with a single override for ML training.
        self._default_timeout_s = 10 * 60
        self._train_timeout_s = 30 * 60

        # Only lock ML training: on watchdog restarts (config change / heartbeat) it's the only task where a
        # concurrent second run is both plausible and costly; other tasks are short and safe to re-run.
        self._no_overlap_actions = {"train_ml_predictions"}
        self._lock_dir = Path("/tmp/dao_scheduler_locks")
        self._lock_dir.mkdir(parents=True, exist_ok=True)

        # Inherit run.sh environment and current workdir.
        self._env = os.environ.copy()
        self._workdir = os.getcwd()

    def _touch_heartbeat(self):
        # Best effort: watchdog signal only; must not break scheduling.
        try:
            self._heartbeat_path.write_text(str(time.time()))
        except Exception:
            # Don't let heartbeat failures break scheduling.
            pass

    def _timeout_for_action(self, action: str) -> int:
        if action == "train_ml_predictions":
            return self._train_timeout_s
        return self._default_timeout_s

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

        timeout_s = int(self._timeout_for_action(action))
        start_ts = time.time()

        logging.info(
            f"scheduler: start action={action} task_key={task_key} timeout_s={timeout_s} cmd={cmd}"
        )

        # New process group so we can kill the full tree (joblib/loky).
        proc = subprocess.Popen(
            cmd,
            cwd=self._workdir,
            env=self._env,
            preexec_fn=os.setsid,
        )

        # Poll-loop keeps heartbeat alive during long tasks and enables soft timeout handling (try SIGTERM before SIGKILL).
        while True:
            self._touch_heartbeat()

            exit_code = proc.poll()
            if exit_code is not None:
                dur = int(time.time() - start_ts)
                logging.info(
                    f"scheduler: done action={action} exit_code={exit_code} duration_s={dur}"
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

            # heartbeat at least once per minute (even when inactive)
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
                if action in self._no_overlap_actions:
                    lock_f = self._acquire_action_lock(action)
                    if lock_f is None:
                        logging.warning(f"scheduler: skip action={action} (already running)")
                        continue

                try:
                    self._run_action_subprocess(action)
                except KeyboardInterrupt:
                    sys.exit()
                except Exception:
                    logging.exception(f"scheduler: exception action={action}")
                finally:
                    if lock_f is not None:
                        self._release_action_lock(lock_f)


def main():
    da_sched = DaScheduler("../data/options.json")
    da_sched.scheduler()


if __name__ == "__main__":
    main()
