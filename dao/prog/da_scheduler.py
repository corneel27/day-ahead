import datetime
import sys
import time
from da_base import DaBase


class DaScheduler(DaBase):
    def __init__(self, file_name: str = None):
        super().__init__(file_name)
        self.scheduler_tasks = self.config.get(["scheduler"])
        self.active = True
        if "active" in self.scheduler_tasks:
            self.active = not (self.scheduler_tasks["active"].lower() == "false")

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
            if not self.active:
                continue
            hour = next_min.hour
            minute = next_min.minute
            key1 = str(hour).zfill(2) + str(minute).zfill(2)
            # ieder uur in dezelfde minuut voorbeeld xx15
            key2 = "xx" + str(minute).zfill(2)
            # iedere minuut in een uur voorbeeld 02xx
            key3 = str(hour).zfill(2) + "xx"
            task = None
            if key1 in self.scheduler_tasks:
                task = self.scheduler_tasks[key1]
            elif key2 in self.scheduler_tasks:
                task = self.scheduler_tasks[key2]
            elif key3 in self.scheduler_tasks:
                task = self.scheduler_tasks[key3]
            if task is not None:
                for key_task in self.tasks:
                    if self.tasks[key_task]["function"] == task:
                        try:
                            # self.run_task_cmd(key_task)
                            self.run_task_function(key_task, True)
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
