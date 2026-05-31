Lab Imaging Portable - Start Here
=================================

Daily startup
-------------

1. Open this LabImagingPortable folder.
2. Double-click Start Lab Imaging.bat.
3. Wait for the dashboard to open in your default browser.
4. Leave the black console window open while Lab Imaging is running.
5. To stop Lab Imaging, return to the console window and press Ctrl+C.

Do not move or edit files inside the _internal folder.


First run
---------

On first launch, Lab Imaging creates config\settings.json from
config\settings.json.example.

If cameras have not been configured yet, the dashboard opens the Cameras page.
Use the dashboard to detect cameras, preview each one, assign station labels,
save the camera setup, and verify cameras before starting a long experiment.


Where files are saved
---------------------

By default, experiment folders are saved in:

  experiments\

You can choose a different future save location from the dashboard Settings page.

Runtime files stay beside this portable app:

  config\settings.json
  config\cameras.json
  config\running_state.json
  experiments\
  logs\


Troubleshooting
---------------

If the browser does not open, look at the console window. You can also open:

  http://127.0.0.1:5000

If the console says the port is already in use, close the other Lab Imaging
window or ask the developer before changing config\settings.json.

If a camera is unavailable, check the USB cable, replug the camera, and verify
the camera from the dashboard before starting a long run.

If storage is full or not writable, free disk space or choose another save
location from Settings, then start a new run.
