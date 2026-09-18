import datetime
import logging
import sys
import time

from PIL.ImageChops import offset

from da_base import DaBase
from subprocess import Popen, PIPE, STDOUT


class DaScheduler(DaBase):
    def __init__(self, file_name: str = None):
        super().__init__(file_name)
        self.active = self.config.scheduler.active
        self.offset_start = self.config.scheduler.offset
        logging.info(f"Offset tasks {self.offset_start} sec")
        self.scheduler_tasks = {
            entry.time: entry.action for entry in self.config.scheduler.schedule
        }

    def run_task_process(self, key_task):
        run_task = self.tasks[key_task]
        proc = Popen(run_task["cmd"])
        proc.wait()
        if proc.returncode != 0 and proc.returncode is not None:
            print(f"Task {key_task} crashed with exit code {proc.returncode}")
            return False
        return True

    def scheduler(self):
        # if not (self.notification_entity is None) and self.notification_opstarten:
        #     self.set_value(self.notification_entity, "DAO scheduler gestart " +
        #                    datetime.datetime.now().strftime('%d-%m-%Y %H:%M:%S'))
        last_minute = -1
        while True:
            t = datetime.datetime.now()
            logging.debug(f"Entry loop at {t}")
            next_min = t.replace(second=0, microsecond=0) + datetime.timedelta(minutes=1)
            if next_min.minute == last_minute:
                time.sleep(max(0, (next_min - t).total_seconds()))
                continue
            last_minute = next_min.minute
            logging.debug(f"Next minute {next_min}")
            start_at = next_min - datetime.timedelta(seconds=self.offset_start)
            logging.debug(f"Geplande start at {start_at}")
            time.sleep(max(0, (start_at - t).total_seconds()))
            if not self.active:
                continue
            logging.debug(f"Gestart op {datetime.datetime.now()}")
            hour = next_min.hour
            minute = next_min.minute
            key0 = str(hour).zfill(2) + str(minute).zfill(2)
            # ieder uur in dezelfde minuut voorbeeld xx15
            key1 = "xx" + str(minute).zfill(2)
            # iedere minuut in een uur voorbeeld 02xx
            key2 = str(hour).zfill(2) + "xx"
            tasks = []
            for key in self.scheduler_tasks:
                if key == key0:
                    tasks.append(self.scheduler_tasks[key])
                elif key == key1:
                    tasks.append(self.scheduler_tasks[key])
                elif key == key2:
                    tasks.append(self.scheduler_tasks[key])
            for task in tasks:
                for key_task in self.tasks:
                    if self.tasks[key_task]["function"] == task:
                        try:
                            self.run_task_process(key_task)
                        except KeyboardInterrupt:
                            sys.exit()
                            pass
                        except Exception as e:
                            print(e)
                            continue
                        break


def main():
    da_sched = DaScheduler("../data/options.json")
    da_sched.scheduler()


if __name__ == "__main__":
    main()
