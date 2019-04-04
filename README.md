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
