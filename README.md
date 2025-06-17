# instrumentserver for Remote Entanglement Experiments

A tool for managing qcodes in a server environment

## Installation

For installing, use a developer pip install:
```bash
pip install --no-deps -e /folder/to/instrumentserver/
```

## Usage

### Starting the Server

Start the instrument server with:
```bash
instrumentserver
```

This will launch the server GUI with the following features:
- Device initialization and management
- Parameter management
- Instrument monitoring
- Logging capabilities

### Device Initialization

The server supports device initialization through configuration files:

1. Default Configuration:
   - Place your device configuration in `instrumentserver/instrumentserver/config/devices.json`
   - The server will automatically use this file when initializing devices

2. Configuration File Format:
   ```json
   {
       "device_name": {
           "instrument_class": "path.to.instrument.class",
           "parameter1": "value1",
           "parameter2": "value2"
       }
   }
   ```

3. Using the GUI:
   - Click "Devices" → "Initialize Devices" to load devices
   - Click "Devices" → "Show Device Status" to view initialized devices
   - The server will automatically use the default configuration if available


## Regarding ArtyS7 drivers

The supporting drivers can be found in `instrumentserver/instrumentserver/device/ArtyS7/`
When importing them to be used in an experiment code, make sure to import as

```python
from instrumentserver.device.ArtyS7.SequencerProgram_v1_07 import SequencerProgram, reg
import instrumentserver.device.ArtyS7.SequencerUtility_v1_01 as su
from instrumentserver.device.ArtyS7.ArtyS7 import ArtyS7
from instrumentserver.device.ArtyS7.HardwareDefinition_v4_03 import *
```

Make sure to notify when these drivers are updated in the instrumentserver.
