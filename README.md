[![DOI](https://zenodo.org/badge/100620945.svg)](https://zenodo.org/badge/latestdoi/100620945)

# ``catkit`` -- The Control and Automation for Testbeds Kit TEST
This is a collection of ``python`` hardware controllers. This project started
from the Makidon Lab as an effort to separate the hardware controllers we use
for the HiCAT testbed and make something less specific to our experiments. 


# Installation

### Clone the catkit repository
 * git clone https://github.com/spacetelescope/catkit

### Install catkit dependencies
 * cd catkit
 * conda env update --name \<env-name\> --file environment.yml
 * conda activate \<env-name\>

### Install catkit in editable mode
 * python setup.py develop

# A few things to keep in mind
Some of these controllers require fairly specific hardware installs on your machine
before they run as expected. 

This is still very much a work in progress. The hardware controllers don't all
match in style or class inheritance. Use or contribute at your own risk.
