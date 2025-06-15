# Metar Map

## Installation
Note: for raspberry pi the script needs to be installed as root user to have access to GPIO.

1. Setup a new raspberry pi and connect to the internet (Note: nmutil is much easier than wpa_supplicant method!)
    `apt update`
    `apt install git`
    `apt install python3-pip`
    
2. Clone this repository. (In example files the files are located in /root/metarmap/)
    `sudo su`
    `cd /root`
3. Create a new virtual environment and activate it
    `python -m venv venv`
    `source venv/bin/activate`
4. Install requirements
    `cd metarmap`
    `pip3 install -r requirements.txt`

1. Install metarmap.service in `/etc/systemd/system/`
2. Reload systemd to enable the service

`sudo systemctl daemon-reexec`
`sudo systemctl daemon-reload`
`sudo systemctl enable metarmap.service`

3. Start the service and check status
`sudo systemctl start metarmap.service`
`sudo systemctl status metarmap.service`




## Running
To run the script manually
`sudo su`
`venv/bin/activate`
`python runmap.py`

## Logging
The script logs to a file called metar_led.log

The latest METARs are stored in a file called lates_metars.json

## Debugging
For optional arguments list
    `python runmap.py -h`

To check LED intensity run runmap.py with argumet -- 