# Guide for running the tip/tilt interface.

* Make sure you're in a computer with `pyUSB` installed and pointing to the
  tip/tilt. (If you're using RMOLStation1 you're g2g.)
  * If you are running from RMOLStation1 you need to instantiate the conda 
    environment with `go` in a command prompt. 
* Navigate into this directory `/path/to/your/repo/instrument-interface-library`.

* In your `ipython/python/notebook/script` you can run the controller normally
  or with context managers :
  * Ex without context manager 
  ```
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
  ```
  
  * Or with context manager :
  ```
    # same import
    from controller_interface import Controller
    with Controller() as ctrl:
        # do some things
        ctrl.command("loop", 1, 1)
        # run some experiment
    # And when the loop closes it will reset to basic settings.
  ```




# Guide for running the instrument-interface library


Setup
-----
First off -- get this bad boy going. Install this on your machine to your
`python` libararies with : 

    >>> python setup.py install 
Or, to pull from local files and continue developing with : 
    
    >>> python setup.py develop

The latter option is suggested while we're still tweaking and developing. 

Example
-------
Now, we can import the package as `interfaces` and go hamm. 

* nPoint piezo Tip/Tilt Close Loop Controller.

```python  
from interfaces import npoint_tiptilt
tiptilt = npoint_tiptilt.nPointTipTilt()
tiptilt.command("p_gain", 1, .003)
tiptilt.get_status(1)
tiptilt.command("loop", 1, 1)
tiptilt.close()
```

* Newport Picomotor Controllers.

```python
from interfaces import newport_picomotor
pico = newport_picomotor.NewportPicomotor()
pico.command("relative_move", 1, 400)
pico.get_status(1)
pico.close()
```

* ZWO Cameras.

```python
 from interfaces import zwo_camera
 cam = zwo_camera.ZWOCamera()
 cam.open_camera()
 print(cam.name)
 cam.take_exposure(exp_time=100)
 cam.close()
```
