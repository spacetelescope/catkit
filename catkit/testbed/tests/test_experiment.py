import time

import pytest

from catkit.testbed.experiment import Experiment, SafetyException, SafetyTest, Testbed


def interruptible_sleep(seconds):
    counter = 0
    while counter < seconds:
        time.sleep(1)
        counter += 1


class ExperimentTest(Experiment):
    name = "Test Experiment"

    def __init__(self, *args, sleep=2, **kwargs):
        super().__init__(*args, **kwargs)
        self.test_sleep = sleep

    def experiment(self, *args, **kwargs):
        t0 = time.time()
        interruptible_sleep(self.test_sleep)
        t1 = time.time()
        assert t1 - t0 < self.test_sleep * 1.1  # 10%


class NonFailingSafetyTest(SafetyTest):
    def check(self):
        pass


@pytest.mark.dont_own_exception_handler
def test_monitor(tmpdir):
    with Testbed(safety_tests=[NonFailingSafetyTest], output_path=tmpdir):
        experiment = ExperimentTest(output_path=tmpdir)
        experiment.start()
        experiment.join()


class FailingSafetyTest(SafetyTest):
    def check(self):
        raise SafetyException("FAIL")


@pytest.mark.dont_own_exception_handler
def test_initial_safety_fail_during_setup(tmpdir):
    with pytest.raises(SafetyException, match="FAIL"):
        with Testbed(safety_tests=[FailingSafetyTest], output_path=tmpdir):
            pass


class DelayedFailingSafetyTest(SafetyTest):
    def __init__(self):
        super().__init__()
        self.call_counter = 0

    def check(self):
        self.call_counter += 1
        if self.call_counter > 2:
            raise SafetyException(f"FAILING (on {self.call_counter} fail)")


@pytest.mark.dont_own_exception_handler
def test_safety_fail_during_run(tmpdir):
    sleep = 10
    experiment = ExperimentTest(sleep=sleep, output_path=tmpdir)
    with pytest.raises(SafetyException, match="FAILING \\(on 3 fail\\)"):
        with Testbed(safety_tests=[DelayedFailingSafetyTest], output_path=tmpdir, safety_check_interval=1):
            experiment.start()
            with pytest.raises(SafetyException, match="Event monitor detected a SAFETY event before experiment completed"):
                experiment.join()
