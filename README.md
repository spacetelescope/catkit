## -- Guide for running the tip/tilt interface.

* Make sure you're in a computer with `pyUSB` installed and pointing to the
  tip/tilt. (If you're using RMOLStation1 you're g2g.)
  * If you are running from RMOLStation1 you need to instantiate the conda 
    environment with `go` in a command prompt. 
* Navigate into this directory `/path/to/your/repo/instrument-interface-library`.

* In your `ipython/python/notebook/script` you can run the controller normally
  or with context managers :
  * Ex without context manager 
    # import function
    from controller_interface import Controller
    # start up controller
    ctrl = Controller()
    # close the loop for channel 1
    ctrl.command("loop", 1, 1)
    # change the P gain for channel 2
    ctrl.command("p_gain", 2, 3.3)
    # and check the status of 1, 2
    status_1, status_2 = ctrl.get_status(1), ctrl.get_status(2)

  * Or with context manager :
    # Same import
    from controller_interface import Controller
    with Controller() as ctrl:
        # do some things
        ctrl.command("loop", 1, 1)
        # run some experiment
    # And when the loop closes it will reset to basic settings.



