# repal (Reverse engineering software for PAL/GAL devices)

  

This software is designed as a modular platform for reverse engineering PAL/GAL type devices that are brute-force dumped using EPROM adapters to produce raw combinatorial dumps of pin input/outputs. Initially this has been tested with PAL16V8 and PAL22V10 devices and their corresponding adapters. Devices are configured via a config file so this will allow other device support to be easily added and tested. The software name is based on the idea of reproduction game cartridges (aka "repro"s), but for PAL devices. :)

  

# Usage

  ## Basic Workflow

1. Download the latest release from the project's releases page:

    https://github.com/clintkolodziej/repal/releases

3. Extract the zip archive to a local folder on your machine (ex: C:\repal\)

4. Install python (https://www.python.org/downloads/), and restart your computer after installation to ensure all commands are available at a command terminal

5. From the folder where you extracted the repal software, run the following basic command to process a dump file:

   ``
   py repal.py "C:\dumps\rom-dump.bin"
   ``
  
6. This will generate the following file, in the same location as the dump file:
  
    ``
    rom-dump.repal.pld
    ``
  
7. Install WinCUPL (or comparable software) to process the .pld file and produce a .jed file:

    ``
    rom-dump.repal.jed
    ``

8. Write the .jed file to the GAL using a compatible programmer and test the device works as expected
  

## Command Options

```
py repal.py <options> <dump file name>
```

### Available Options:

   `--devicetype=<device>`, default: `auto`, devices: `[auto, pal16v8, pal22v10, etc]`

   Specify a device type to be selected from the `profiles.config` file

   `--oepolarity=<polarity>`, default: `auto`, polarity: `[auto, both, positive, negative]`

   Specify polarity for output enable pin equations

   `--polarity=<polarity>`, default: `auto`, polarity: `[auto, both, positive, negative]`

   Specify polarity for output pin equations
   
   `--profiles=<filename>`, default: `profiles.config`

   Allows a json formatted file name containing device profile information to be input, `profiles.config`
   Note: the default `profiles.config` ships with PAL16V8 and PAL22V10 support
   
   `--truthtable`
   
  Flag to output a separate truthtable file for verifying the raw equations for each pin before
    
### Some examples of more advanced usage:  

Basic example that reads a dump at `C:\dumps\igs-pgm-svg-hh-u15.bin` and will write out a `pld` file named `igs-pgm-svg-hh-u15.repal.pld` in the same folder as the `bin` file:
```
py repal.py "C:\dumps\igs-pgm-svg-hh-u15.bin"
```

Adding onto the basic example, but also outputting a `igs-pgm-svg-hh-u15.repal.truthtable.txt`in the same folder as the `bin` file (for problem solving any troublesome pins, or debugging):
```
py repal.py --truthtable "C:\dumps\igs-pgm-svg-hh-u15.bin"
```

Similar to the basic example, but will output the equations in the `pld` file with negative polarity and the output enable equations with positive polarity:
```
py repal.py --polarity="negative" --oepolarity="positive" "C:\dumps\igs-pgm-svg-hh-u15.bin"
```

An advanced example with all options that will read the same file as above, but it will output an additional `igs-pgm-svg-hh-u15.repal.truthtable.txt` in the same folder as the `bin` file.  It will output the equations in the `pld` file with negative polarity and the output enable equations with positive polarity.  This command also will load devices from a `custom-profiles.config` file and load a device type `pal22v10` from that file:
```
py repal.py --truthtable --polarity="negative" --oepolarity="positive" --devicetype="pal22v10" --profiles="C:\repal\custom-profiles.config" "C:\dumps\igs-pgm-svg-hh-u15.bin"
```

  

# Credits

  

Thanks to the following people:

  

- Johann Hanne for creating the excellent palrvs tool for pal16v8 that this software is based upon (https://github.com/jonnyh64/palrvs)

- Charles MacDonald for the inital EPROM adapter idea, schematics, and pa.exe tool (http://techno-junk.org/readpal.php)

- Aaron Giles for creating jedutil, which is included with MAME, a great resource for verifying equations from raw JED files (https://aarongiles.com/)

- Tim Merrell ("gc8tech") for the great idea to write this for the purpose of dumping larger GAL/PAL chips from IGS PGM game cartridges to aid in preservation, and listening to all my questions and rants when things were breaking during development (https://igspgm.com/)

- "twistedsymphony" for help with the pal16v8 dumper and how to use the dumping software (http://solid-orange.com/2358)

- "Fluffy" from Arcade Projects for the initial schematics for the PAL22V10 EPROM dumper

- User "rodney" and from the vcfed forums for providing pal dumps that have aided in testing this project (https://forum.vcfed.org/index.php?threads/project-to-create-an-atx-80286-mainboard-based-on-the-ibm-5170.1243108/)

- Contributors at the PLD Archive for a great source for PAL images to test with (https://wiki.pldarchive.co.uk/index.php?title=Arcade)

