#
# Copyright (c) 2025 Clint Kolodziej
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
#

#
# repal: Reverse Engineering tool for PAL devices
# 
#     usage: 
#
#         py repal.py <options> <dump file name>
#
#     examples:
#
#         py repal.py "C:\dumps\igs-pgm-svg-hh-u15.bin"
#
#         py repal.py --truthtable --polarity="negative" --oepolarity="positive" --devicetype="pal22v10" --profiles="C:\repal\custom-profiles.config" "C:\dumps\igs-pgm-svg-hh-u15.bin"
#
#     options:
#
#         Option Name:                           Default Value:         Descrition:
#         =====================================  =====================  ==============================================================================================
#         --devicetype=<device>                  auto                   Specify a device type [auto, pal16v8, pal22v10, etc]
#
#         --oepolarity=<polarity>                auto                   Specify polarity for output enable pin equations [auto, both, positive, negative]
#
#         --polarity=<polarity>                  auto                   Specify polarity for output pin equations [auto, both, positive, negative]
#
#         --profiles=<profiles config filename>  profiles.config        Allows a json formatted file name containing device profile information to be input, profiles.config
#                                                                       is shipped with this software with pal16v8 and pal22v10 support, others can be added here
#             
#         --truthtable                                                  Flag to output a separate truthtable file for verfiying the raw equations for each pin before
#                                                                       they are simplified into the final outputs
#

import argparse
import boolexprsimplifier
import datetime
import json
import os
import pathlib
import re
import tqdm

#
# Constants
#

ANDSTR = '&'                                                                                            # string to use for logical AND in the PLD output file
ORSTR = '#'                                                                                             # string to use for logical OR in the PLD output file
NOTSTR = '!'                                                                                            # string to use for logical NOT in the PLD output file

#
# Pin Classes (for both input and output pins)
#

class Pin:

    def __init__(self):
        self.name = ""                                                                                  # name for the pin from the device mapping
        self.number = 0                                                                                 # pin number of the device
        self.bitpos = 0                                                                                 # bit position of the pin in the eprom data
        self.bitmask = 0                                                                                # bit mask for the pin, related to bitpos (0 > 00000001, 1 > 00000010, ..., 6 > 01000000, 7 > 10000000)
        self.hizprobebitpos = 0                                                                         # bit position of the hi-z probe pin in the eprom data
        self.hizprobebitmask = 0                                                                        # bit mask for the hi-z pin, related to hizprobebitpos (0 > 00000001, 1 > 00000010, ..., 6 > 01000000, 7 > 10000000)
        self.seenlow = 0                                                                                # has this pin ever been seen in a low state? (0: no, 1: yes)
        self.seenhigh = 0                                                                               # has this pin ever been seen in a high state? (0: no, 1: yes)
        self.depends = PinDependencies()                                                                # pins that this pin depends on
        self.oe_depends = PinDependencies()                                                             # oe pins that this pin depends on
        self.dontcareconditions = []                                                                    # list of don't care conditions, for output to truthtable
        self.negativeconditions = []                                                                    # list of negative conditions, for output to truthtable
        self.positiveconditions = []                                                                    # list of positive conditions, for output to truthtable
        self.dontcareterms = []                                                                         # list of don't care minterms, for building output equations
        self.negminterms = []                                                                           # list of negative minterms, for building output equations
        self.posminterms = []                                                                           # list of positive minterms, for building output equations
        self.oenegativeconditions = []                                                                  # list of negative oe conditions, for output to truthtable
        self.oepositiveconditions = []                                                                  # list of positive oe conditions, for output to truthtable
        self.oenegminterms = []                                                                         # list of negative oe minterms, for building oe equations
        self.oeposminterms = []                                                                         # list of positive oe minterms, for building oe equations

class PinDependencies:

    def __init__(self):
        self.bitmap = 0                                                                                 # map of input bits that this output pin depends on
        self.bits = []                                                                                  # list of input bits that this output pin depends on
        self.pinnames = []                                                                              # list of pin names that this output pin depends on

#
# get_command_arguments:
#   Get arguments from the command line
#

def get_command_arguments():

    #
    # Create the parser object with information on the program
    #

    parser = argparse.ArgumentParser(prog = 'repal', description = 'Process an EPROM dump of a PAL device and produce a compatible PLD file')

    parser.add_argument('--devicetype', dest = 'devicetype', default = 'auto' , help = 'Device type: auto, pal16v8, pal22v10')
    parser.add_argument('--oepolarity', dest = 'oepolarity', default = 'auto' , choices=['auto', 'both', 'positive', 'negative'], help = 'Output enable equation polarity')
    parser.add_argument('--polarity', dest = 'polarity', default = 'auto' , choices=['auto', 'both', 'positive', 'negative'],  help = 'Output equation polarity')
    parser.add_argument('--profiles', dest = 'profiles', default = 'profiles.config' , help = 'Json file containing device profiles')
    parser.add_argument('--truthtable', dest = 'truthtable', default = False , help = 'Enable truth table output', action=argparse.BooleanOptionalAction)
    parser.add_argument('filename')

    return parser.parse_args()

#
# load_device_profiles:
#   Load device profiles from a json configuration file
#

def load_device_profiles():

    #
    # Create the device dictionary that devices will be added to as they are discovered
    #

    devices = {}

    #
    # Output information on the device profiles file being used
    #

    print(f"Loading device profiles: {args.profiles}")

    #
    # Get the path to the profiles.config file from the command arguments, start by assuming it is a full path
    #

    json_path = pathlib.Path(args.profiles)

    #
    # Check if the path to the profiles.config is a file, if not then try looking for it in the script directory (default 'profiles.config' file shipped with the software)
    #

    if not json_path.is_file():

        json_path = pathlib.Path(os.path.join(os.path.dirname(os.path.abspath(__file__)), args.profiles))

    #
    # Try opening the profiles json file to load the device profiles
    #

    try:

        with open(json_path, 'r') as file:

            #
            # Set up a regex pattern to remove single line comments where the line begins with whitespace then a # character (python style comments, yes these are illegal in json so we'll remove them first)
            #

            comment_pattern = r'^\s*[#]'

            #
            # Load the json from the file after removing lines with comments
            #

            profiles = json.loads(''.join(line for line in file if not re.match(comment_pattern, line)))

            #
            # Insert the device profiles from the json file into the devices object that is used in the program
            #

            for profile in profiles:

                #
                # Print out the device we're importing and add it to the device list
                #

                print(f"Device profile added: {profile}")

                #
                # Add the device profile to the device list object
                #

                devices[profile] = profiles[profile]

    #
    # If there is a FileNotFoundError let the user know the file wasn't found, this might trigger a downstream error with being able to find a device
    #

    except FileNotFoundError:

        print(f"No device profiles found, specified file doesn't exist: '{json_path}'")
    
    #
    # Return the devices object populated with device profiles from the json file
    #

    return devices

#
# select_device:
#   Select the device profile either from input argument or auto-detection based on file size
#

def select_device(eprom_dump_filepath):

    #
    # Load device profiles needed to select the device
    #

    devices = load_device_profiles()

    #
    # If the device type argument isn't 'auto' then attempt to find the specified device in the devices list and return it if found
    #

    if args.devicetype != "auto":

        #
        # If the device specified doesn't exist then error out
        #

        if args.devicetype not in devices:
            raise RuntimeError(f"Device detection failed, no device profile with device type '{args.devicetype}' found")
                
        #
        # Print out information for the user to see which device we selected and return the device to be used during dump processing
        #

        print(f"Device detected: {args.devicetype}")

        #
        # Return the device from the devices list with the specified type
        #

        return devices[args.devicetype]

    #
    # Get the size of the dump file that we'll use for auto-detection
    #

    dumpsize = eprom_dump_filepath.stat().st_size

    #
    # Loop through all device profiles to auto-detect the device based on dump size
    #

    for devicetype in devices:

        #
        # Get the expected file size for this device type
        #

        databytes = int(devices[devicetype]["eprom_data_width"] / 8)
        datawidth = devices[devicetype]["eprom_address_width"]
        expected_file_size = (2 ** datawidth) * databytes

        #
        # If the dump size for the device matches the dump size in the dump file then we have a match
        #

        if expected_file_size == dumpsize:

            #
            # Print out information for the user to see which device we selected and return the device to be used during dump processing
            #

            print(f"Device detected: {devicetype}")

            #
            # Return the device from the devices list with the matching device type
            #

            return devices[devicetype]
        
    #
    # If we get here we had "auto" device select but we didn't find a device with a matching dump file size, error out
    #

    raise RuntimeError(f"Device detection failed or bad dump, device with {dumpsize} 'eprom_filesize' expected")
        
#
# read_eprom_dump:
#   Read the eprom dump file and output an array of data
#

def read_eprom_dump(eprom_dump_filepath):
         
    #
    # Set up the output data array and the number of bytes (convert from bit width in device config) to read for each output
    #

    dataarray = []
    databytes = int(device["eprom_data_width"] / 8)

    #
    # Open the eprom dump for reading
    #

    f = eprom_dump_filepath.open("rb")

    #
    # Read each output and store it into the data array for that input combination, keeping in mind endianness of the eprom dump
    #

    while True:
        data = f.read(databytes)
        if not data:
            break
        dataarray.append(int.from_bytes(data, byteorder=device["eprom_endianness"]))

    #
    # We're done reading the file, close it
    #

    f.close()

    #
    # Check if the file that was read has the expected number of bytes, if not then error out
    #

    expected_file_size = (2 ** device["eprom_address_width"]) * databytes

    if len(dataarray) * databytes != expected_file_size:
        raise RuntimeError(f"File with {expected_file_size} bytes expected")

    #
    # Return the complete array of outputs
    #

    return dataarray

#
# epromaddrbitpos_to_palpinnum:
#   Convert an eprom address bit position to a PAL pin number (A0 > Pin 1, A9 > Pin 11, based on device pin mapping)
#

def epromaddrbitpos_to_palpinnum(epromaddrbitpos):

    #
    # Try to return the PAL pin number for the given eprom address pin
    #

    try:

        return device["eprom_address_pins"][epromaddrbitpos]
    
    #
    # If there is no PAL pin number for the eprom address pin then return None
    #

    except ValueError:

        return None

#
# epromdatabitpos_to_palpinnum:
#   Convert an eprom data bit position to a PAL pin number (D0 > Pin 12, D7 > Pin 19, based on device pin mapping)
#

def epromdatabitpos_to_palpinnum(epromdatabitpos):

    #
    # Try to return the PAL pin number for the given eprom data pin
    #

    try:
        return device["eprom_data_pins"][epromdatabitpos]
    
    #
    # If there is no PAL pin number for the eprom data pin then return None
    #
    
    except ValueError:
        return None

#
# palpinnum_to_epromaddrbitpos:
#   Convert a PAL pin number to an eprom address bit position (Pin 1 > A0, Pin 11 > A9, based on device pin mapping)
#

def palpinnum_to_epromaddrbitpos(palpinnum):

    #
    # Try to return the eprom address pin for the given PAL pin number
    #

    try:
        return device["eprom_address_pins"].index(int(palpinnum))
    
    #
    # If there is no eprom address pin for the PAL pin number then return None
    #
    
    except ValueError:
        return None

#
# palpinnum_to_epromdatabitpos:
#   Convert a PAL pin number to an eprom data bit position (Pin 12 > D0, Pin 19 > D7, based on device pin mapping)
#

def palpinnum_to_epromdatabitpos(palpinnum):

    #
    # Try to return the eprom data pin for the given PAL pin number
    #

    try:
        return device["eprom_data_pins"].index(int(palpinnum))
    
    #
    # If there is no eprom data pin for the PAL pin number then return None
    #

    except ValueError:
        return None


#
# get_max_pin_name_length:
#   Return the longest pin name for use with alignment in equation files (ex: if "pin10" is the longest pin name then this will be 5)
#

def get_max_pin_name_length():

    #
    # Return the longest pin name in the pal_pin_names list
    #

    return max((len(s) for s in device["pal_pin_names"].values()))

#
# iterate_mask:
#   Generate bit mask iterations for all binary combinations of a specific input mask
#       Example: 
#
#           iterate_mask(0b1010) 
#               
#           returns:
#               0b0000
#               0b0010
#               0b1000
#               0b1010
# 

def iterate_mask(mask):

    #
    # If there is no mask then return as there are no combinations
    #

    if mask < 1:
        return

    #
    # Set up the bits array and start at bit 1
    #

    bits = []
    bit = 1   

    #
    # Loop on each bit in the mask and build a list of the bits that are high in the mask
    #

    while bit <= mask:

        if (mask & bit) != 0:
            bits.append(bit) 

        bit <<= 1

    #
    # Loop and generate input combinations for each high bit in the input mask, yield each result
    #

    for n in range(2 ** len(bits)):

        r = 0
        srcmask = 1

        for bit in bits:

            if (n & srcmask) != 0:
                r |= bit

            srcmask <<= 1

        yield r

#
# get_set_bits:
#   Get the bits that are set in a given binary input value with maximum bit count
#       Example: 
#           bitcount:   5
#           bits:       0b01011
#           returns:    0, 1, 3
#

def get_set_bits(bitcount, bits):

    #
    # Set up the starting bit number and bit being interrogated
    #

    bitnum = 0
    bit = 1

    #
    # Loop through each bit until reaching the bit count, if the bit is set then yield it, else increment and continue looping
    #

    while bitnum < bitcount:

        if (bits & bit) != 0:
            yield bitnum

        bitnum += 1
        bit <<= 1

#
# build_inputpins_configuration:
#   Build a list of pins for each potential input pin on the pal and populate details for the pin based on the device configuration
#

def build_inputpins_configuration():

    #
    # Create an empty list for all the potential input pins
    #

    inputpins = [ Pin() for i in range(device["eprom_address_width"]) ]

    #
    # Loop through all potential input pins
    #

    for inputpinbitpos in range(0, device["eprom_address_width"]):

        #
        # Get a reference to the current pin
        #

        inputpin = inputpins[inputpinbitpos]

        #
        # Set up the input pin configuration
        #

        inputpin.bitpos = inputpinbitpos
        inputpin.bitmask = 1 << inputpin.bitpos                                                     # Convert the input pin bit position to a bit mask (0 > 00000001, 1 > 00000010, ..., 6 > 01000000, 7 > 10000000)
        inputpin.number = epromaddrbitpos_to_palpinnum(inputpin.bitpos)                             # get the input pin number on the PAL chip from the current input bit position
        inputpin.name = device["pal_pin_names"][str(inputpin.number)]                               # get the input pin name on the PAL chip for the current input pin number
        
    #
    # Return the completed input pin list
    #

    return inputpins

#
# build_outputpins_configuration:
#   Build a list of pins for each potential output pin on the pal and populate details for the pin based on the device configuration
#

def build_outputpins_configuration():

    #
    # Create an empty list for all the potential output pins
    #

    outputpins = [ Pin() for i in range(device["pal_output_pins"]) ]

    #
    # Loop through all potential output pins
    #

    for outputpinbitpos in range(0, device["pal_output_pins"]):

        #
        # Get a reference to the current pin
        #

        outputpin = outputpins[outputpinbitpos]

        #
        # Populate details on the pin, where it is in the output data, the pin name/number, and information on the hi-z probe pins in the input combination address
        #

        outputpin.bitpos = outputpinbitpos
        outputpin.bitmask = 1 << outputpin.bitpos                                                       # Convert the output pin bit position to a bit mask (0 > 00000001, 1 > 00000010, ..., 6 > 01000000, 7 > 10000000)
        outputpin.number = epromdatabitpos_to_palpinnum(outputpin.bitpos)                               # get the output pin number on the PAL chip from the current output bit position
        outputpin.name = device["pal_pin_names"][str(outputpin.number)]                                 # get the output pin name on the PAL chip for the current output pin number
        outputpin.hizprobebitpos = palpinnum_to_epromaddrbitpos(outputpin.number)                       # get the hi-z probe bit position for the output pin
        outputpin.hizprobebitmask = 1 << outputpin.hizprobebitpos if outputpin.hizprobebitpos != None else 0

    #
    # Return the completed output pin list
    #

    return outputpins

#
# build_outputpins_dependencies:
#   Build a list of all input pin and output enable (oe) dependencies for each output pin on the pal and whether the pin was ever seen high or low
#

def build_outputpins_dependencies(input_pin_mappings, output_pin_mappings):

    #
    # Print out what we're doing as we'll display a progress bar
    #

    print("Building output pin dependencies...")

    #
    # Loop through all input combinations stored in the eprom dump, including high address hi-z probe pins (for output pins that are treated as bidirectional or as inputs)
    #

    for eprom_address in tqdm.tqdm(range(2 ** device["eprom_address_width"])):
        
        #
        # Loop through each input pin bit in the current input combination, including high address hi-z probe pins
        #

        for inputpin in input_pin_mappings:

            #
            # If the input bit is high skip it and continue the loop, we'll manually read the high pin state along with the low state shortly
            #

            if eprom_address & inputpin.bitmask > 0:
                continue

            #
            # Get the eprom address for both the low and high state on the current input pin (for the current input pin combination)
            #

            eprom_address_when_input_0 = eprom_address                                                  # same as the eprom address since we skip addresses that have this input pin enabled
            eprom_address_when_input_1 = eprom_address | inputpin.bitmask                               # second address is the address with the bit position as 1 (10100001 -> 10110001, for bit 00010000)

            #
            # Read the output pin data for both the low and high input pin states
            #

            data_when_input_0 = dumpdata[eprom_address_when_input_0]                                    # get the data for the address with current input pin bit 0 (10100001 for bit 00010000)
            data_when_input_1 = dumpdata[eprom_address_when_input_1]                                    # get the data for the address with current input pin bit 1 (10110001 for bit 00010000)

            #
            # Loop through each output pin to check how it is affected by the current input pin combination
            #

            for outputpin in output_pin_mappings:

                #
                # Check whether the hi-z pin on the input combination is enabled (for 0 or 1 input combinations), if so we can skip processing 
                # this pin again since we already checked the hi-z on a previous input combination where the hi-z pin was disabled
                #

                if eprom_address_when_input_0 & outputpin.hizprobebitmask > 0:
                    continue

                if eprom_address_when_input_1 & outputpin.hizprobebitmask > 0:
                    continue

                #
                # Get the output value for the current output pin in the current data for when the input is high and low
                #

                output_when_input_0 = data_when_input_0 & outputpin.bitmask
                output_when_input_1 = data_when_input_1 & outputpin.bitmask

                #
                # Check if the output pin is impacted by the hi-z probe pin when the input pin is high and low, if there is no hi-z probe pin for the adapter the hi-z is false as we can't check it
                #
                
                if outputpin.hizprobebitpos == None:
                    
                    is_hiz_when_input_0 = False
                    is_hiz_when_input_1 = False

                else:                

                    data_when_input_0_and_hiz_1 = dumpdata[eprom_address_when_input_0 ^ outputpin.hizprobebitmask] 
                    data_when_input_1_and_hiz_1 = dumpdata[eprom_address_when_input_1 ^ outputpin.hizprobebitmask] 

                    is_hiz_when_input_0 = (data_when_input_0 & outputpin.bitmask) != (data_when_input_0_and_hiz_1 & outputpin.bitmask)
                    is_hiz_when_input_1 = (data_when_input_1 & outputpin.bitmask) != (data_when_input_1_and_hiz_1 & outputpin.bitmask)

                #
                # If the the hi-z states for the output pin aren't the same when the input pin is high and low then this output pin is enabled by the input pin, add it to the output enable (oe) dependencies
                #

                if (
                    is_hiz_when_input_0 != is_hiz_when_input_1 and 
                    inputpin.name not in outputpin.oe_depends.pinnames
                ):
                    outputpin.oe_depends.pinnames.append(inputpin.name)
                    outputpin.oe_depends.bits.append(inputpin.bitmask)
                    outputpin.oe_depends.bitmap |= inputpin.bitmask 

                #
                # If the value of the output pin differs when the input pin is high or low, but isn't in a hi-z state then this output pin is dependent on the input pin, add it to the input pin dependencies
                #

                if (
                    not is_hiz_when_input_0 and 
                    not is_hiz_when_input_1 and 
                    output_when_input_0 != output_when_input_1 and 
                    inputpin.name not in outputpin.depends.pinnames
                ):
                    outputpin.depends.pinnames.append(inputpin.name)
                    outputpin.depends.bits.append(inputpin.bitmask)
                    outputpin.depends.bitmap |= inputpin.bitmask

                #
                # If the output pin isn't in hi-z when the input is low, record if the output pin is seen as high or low
                # 
                        
                if not is_hiz_when_input_0:
                    if (output_when_input_0) == 0:
                        outputpin.seenlow = 1
                    else:
                        outputpin.seenhigh = 1

                #
                # If the output pin isn't in hi-z when the input is high, record if the output pin is seen as high or low
                # 

                if not is_hiz_when_input_1:
                    if (output_when_input_1) == 0:
                        outputpin.seenlow = 1
                    else:
                        outputpin.seenhigh = 1

#
# build_outputpin_conditions:
#   Build a list of conditions given a set of dependencies and eprom address with input combinations
#

def build_outputpin_conditions(dependencies, epromaddr):
                
    #
    # Set up an array and bit mask for the current output enable combination
    #

    conditions = []

    #
    # For the current input combination, record the dependant output bit combination (ex: pins 1, 3, 6, 7 that show high would be recorded in minterm as 1100101)
    # Example: If this pin depends on pins 4, 5, 6, and 7, with input combination 000000000000001011000, conditions = [' i4', ' i5', '!i6', ' i7']
    #

    for pinidx in range(len(dependencies.bits)):

        #
        # If the current pin in the input address combination is low then append it with a !NOT prefix to the conditions list
        #

        if (epromaddr & dependencies.bits[pinidx]) == 0:

            conditions.append(f"{NOTSTR}{dependencies.pinnames[pinidx]}")

        #
        # Else the current pin is high so append it with a positive polarity to the conditions list
        #

        else:

            conditions.append(f" {dependencies.pinnames[pinidx]}")

    return conditions

#
# build_outputpin_minterm:
#   Build a minified term object given a set of dependencies and eprom address with input combinations
#

def build_outputpin_minterm(dependencies, epromaddr):
                
    #
    # Set up an array and bit mask for the current input combination
    #

    minterm = 0

    #
    # For the current input combination, record the dependant input bit combination (ex: pins 1, 3, 6, 7 that show high would be recorded in minterm as 1100101)
    # Example: If this pin depends on pins 4, 5, 6, and 7, with input combination 000000000000001011000, minterm = 1011
    #

    for pinidx in range(len(dependencies.bits)):

        #
        # If the current pin is high enable the bit in the minified term bitmask (if only bit position 3 was on this would be 0100)
        #

        if (epromaddr & dependencies.bits[pinidx]) != 0:

            minterm |= (1 << pinidx)

    return minterm

#
# check_input_combination_is_relevent:
#   Check the input combination to ensure it doesn't result in a hi-z condition
#
#   Pins 12-19 on a PAL16L8 can act as output and input at the same time; when a certain
#   combination of input levels is applied, one or more of pins 12-19 might be driven by
#   the PAL itself, overriding an external input on such pins; testing for such a "PAL
#   internal override" is possible by comparing A10..A17 to D0..D7 of the EPROM dump;
#   given the currently checked input pin configuration ("epromaddr & depends_on"), we
#   need to combine this configuration with ALL input pin configuration of the other
#   pins; if A10..A17 does NOT equal to D0..D7 for ALL this combinations, then the
#   input combination is irrelevant, meaning "don't care" in boolean algebra
#

def check_input_combination_is_relevent(outputpin, epromaddr):

    #
    # Build masks for comparing hi-z data
    #

    hiz_input_mask = ((2 ** device["eprom_hiz_probe_pins"]) - 1) << (device["eprom_address_width"] - device["eprom_hiz_probe_pins"])    # mask to get only hi-z values from an eeprom input address (pal22v10: 111111111000000000000, pal16v8: 111111110000000000)
                                                                                                                                        # pal22v10: 12 low address bits tied to input pins on the pal, 9 high address bits as hi-z probe pins (note: 1 hi-z probe pin is missing as there aren't enough pins on the 27C322 eprom device)
                                                                                                                                        # pal16v8: 10 low address bits tied to input pins on the pal, 8 high address bits as hi-z probe pins

    hiz_data_mask = ((2 ** (device["eprom_data_width"] - device["eprom_hiz_probe_pins"])) - 1) << device["eprom_hiz_probe_pins"]        # used to convert data bits for comparison to highz address bits (pal22v10: 1111111000000000, pal16v8: 00000000)
                                                                                                                                        # pal22v10: since data is 16-bit width but only 10-bit significant, the high bits show as 1's in the dump, this mask will allow them to be turned off
                                                                                                                                        # pal16v8: since data is 8-bit and there are only 8 output pins no mask is needed

    #
    # Get the inverse of the output pin's dependencies bitmap field (bitmap: 00001101101, inverse: 11110010010)
    #

    inversebitmap = ((2 ** device["eprom_address_width"]) - 1) ^ outputpin.depends.bitmap

    #
    # Iterate on all other pins that aren't listed in the output pin depends map
    #

    # for otherepromaddrbits in iterate_mask(inversebitmap):

    #
    # Iterate on all other hi-z probe pins that aren't listed in the output pin depends map
    #

    for otherepromaddrbits in iterate_mask(inversebitmap & hiz_input_mask):

        #
        # Combine the original input combination with the current iteration of the other pins
        #

        epromaddr2 = epromaddr | otherepromaddrbits
        
        #
        # Get only the hi-z input bit values from the complete address 
        # pal16v8: 101101110001000101 > 10110111 - with high 8 bits as hi-z probe pins
        # pal22v10: 101101111000100010001 > 101101111 - with high 9 bits as hi-z probe pins
        #

        hiz_data = ((epromaddr2 & hiz_input_mask) >> (device["eprom_address_width"] - device["eprom_hiz_probe_pins"]))

        #
        # Turn off any non-relevant data bits in the data output (to fix 16-bit output for pal22v10 where insignificant bits are high in dump)
        # pal16v8: 10110111 > 10110111 - with high 8 bits as hi-z probe pins
        # pal22v10: 1111111101101111 > 101101111 - with high 9 bits as hi-z probe pins
        #

        relevant_data = dumpdata[epromaddr2] & ~hiz_data_mask

        #
        # Compare the hi-z probe pin input values with the output pin values, if they match then the input is relevant, otherwise the combination results in a hi-z condition
        # pal16v8: A17..A10 to D7..D0 - with high 8 bits as hi-z probe pins
        # pal22v10: A20..A12 to D8..D0 - with high 9 bits as hi-z probe pins
        #

        if hiz_data == relevant_data:

            return True

    #
    # If there was no matching combination of hi-z inputs that result in the same output data as what was input then the input combination is not relevant
    #

    return False

#
# get_output_pin_data:
#   Get output pin data for the given input combination, if that is hi-z then search pin combinations utilizing output enable pin dependencies to find a valid combination
#

def get_output_pin_data(outputpin, epromaddr):

    #
    # If the initial input combination doesn't result in a hi-z condition then return the data for it
    #

    if (dumpdata[epromaddr] & outputpin.bitmask) == (dumpdata[epromaddr ^ outputpin.hizprobebitmask] & outputpin.bitmask):

        return dumpdata[epromaddr]
    
    #
    # Iterate on all other pins that aren't listed in the output pin depends map
    #

    # inversebitmap = ((2 ** device["eprom_address_width"]) - 1) ^ outputpin.depends.bitmap   # get the inverse of the output pin's dependencies bitmap field (bitmap: 00001101101, inverse: 11110010010)

    # for otherepromaddrbits in iterate_mask(inversebitmap):
    
    #
    # Iterate on all output enable pins that could be combined to produce an output
    #
    
    for otherepromaddrbits in iterate_mask(outputpin.oe_depends.bitmap):

        #
        # Combine the original input combination with the current iteration of the other pins
        #

        epromaddr2 = epromaddr | otherepromaddrbits

        #
        # If the output data for this pin doesn't change by toggling the hi-z probe pin then the pin is an active output pin, return it
        #

        if (dumpdata[epromaddr2] & outputpin.bitmask) == (dumpdata[epromaddr2 ^ outputpin.hizprobebitmask] & outputpin.bitmask):

            return dumpdata[epromaddr2]

    #
    # If there is no combination of inputs that don't result in a hi-z condition then we'll throw a runtime error
    #

    raise RuntimeError(f'Could not find input combination which does not lead to hi-z for pin {outputpin.name}')

#
# build_outputpins_equations:
#   Build a the output pin equations based on the pre-processed dependencies
#

def build_outputpins_equations(outputpins):

    #
    # Print out what we're doing as we'll display a progress bar
    #

    print("Building output pin equations...")

    #
    # Iterate on each output pin using data accumulated above to produce the truthtable and equations for each
    #

    for outputpin in tqdm.tqdm(outputpins):

        #
        # Sort the depends on arrays (bits / pin names) together to ensure the correct order for output (https://stackoverflow.com/questions/9764298/given-parallel-lists-how-can-i-sort-one-while-permuting-rearranging-the-other)
        #

        if (len(outputpin.depends.bits) > 0):
            outputpin.depends.bits, outputpin.depends.pinnames = zip(*sorted(zip(outputpin.depends.bits, outputpin.depends.pinnames)))
            outputpin.depends.bits, outputpin.depends.pinnames = (list(t) for t in zip(*sorted(zip(outputpin.depends.bits, outputpin.depends.pinnames))))

        #
        # Sort the oe depends on arrays (bits / pin names) together to ensure the correct order for output (https://stackoverflow.com/questions/9764298/given-parallel-lists-how-can-i-sort-one-while-permuting-rearranging-the-other)
        #

        if (len(outputpin.oe_depends.bits) > 0):
            outputpin.oe_depends.bits, outputpin.oe_depends.pinnames = zip(*sorted(zip(outputpin.oe_depends.bits, outputpin.oe_depends.pinnames)))
            outputpin.oe_depends.bits, outputpin.oe_depends.pinnames = (list(t) for t in zip(*sorted(zip(outputpin.oe_depends.bits, outputpin.oe_depends.pinnames))))

        #
        # If the output pin has dependencies then build the conditions and terms for the dependent input pins
        #

        if outputpin.depends.bitmap != 0:
    
            #
            # Loop on each possible input combination that the current output pin could depend on, based on pin dependency information found earlier
            #
            
            for epromaddr in iterate_mask(outputpin.depends.bitmap):

                #
                # Get the conditions and minterms for the current output pin
                #

                conditions = build_outputpin_conditions(outputpin.depends, epromaddr)
                minterm = build_outputpin_minterm(outputpin.depends, epromaddr)

                #
                # Check if the current input combination produces a relevant output, if not add it to the don't care terms and continue on
                #

                if not check_input_combination_is_relevent(outputpin, epromaddr):

                    outputpin.dontcareconditions.append(conditions)
                    outputpin.dontcareterms.append(minterm)
                    continue

                #
                # If the value of the output pin value is low then add it as a negative polarity condition
                #

                if (get_output_pin_data(outputpin, epromaddr) & outputpin.bitmask) == 0:

                    outputpin.negativeconditions.append(conditions)
                    outputpin.negminterms.append(minterm)

                #
                # Else add the condition to the positive polarity lists
                #

                else:

                    outputpin.positiveconditions.append(conditions)
                    outputpin.posminterms.append(minterm)

        #
        # If the output pin has output enable dependencies then build the conditions and terms for the dependent output enable pins
        #

        if outputpin.oe_depends.bitmap != 0:

            #
            # Loop on each possible output enable combination that the current output pin could depend on, based on pin dependency information found earlier
            #

            for epromaddr in iterate_mask(outputpin.oe_depends.bitmap):

                #
                # Get the conditions and minified terms for the current output pin's oe dependencies and current input combination
                #

                conditions = build_outputpin_conditions(outputpin.oe_depends, epromaddr)
                minterm = build_outputpin_minterm(outputpin.oe_depends, epromaddr)

                #
                # If the value of the output pin value doesn't match the output pin value with hi-z probe applied then add it as a negative polarity condition
                #

                if (dumpdata[epromaddr] & outputpin.bitmask) != (dumpdata[epromaddr ^ outputpin.hizprobebitmask] & outputpin.bitmask):

                    outputpin.oenegativeconditions.append(conditions)
                    outputpin.oenegminterms.append(minterm)

                #
                # Else add the condition to the positive polarity lists
                #

                else:

                    outputpin.oepositiveconditions.append(conditions)
                    outputpin.oeposminterms.append(minterm)

#
# simplify_minterms:
#   Simplify pin equations by calling the boolean expression simplifier utility
#

def simplify_minterms(pin_names, minterms, dontcareminterms = []):

    return boolexprsimplifier.simplify_minterms(len(pin_names), minterms, dontcareminterms, debug=False)

#
# write_equations_newline:
#   Write a newline into the equations file
#

def write_equations_newline():

    equations.write(f"\n")

#
# write_equations_section_title:
#   Write a section header with a given title into the equations file
#

def write_equations_section_title(title):

    equations.write("\n")
    equations.write(f"/* {title} */\n")
    equations.write("\n")

#
# write_pin_truthtable:
#   Generate a truth table in a readable format
#

def write_pin_truthtable(signedname, conditionslist):

    #
    # Initialize that we're starting as the first output product
    #

    isfirstline = True

    #
    # Compute the indention length depending on the length of the pin name
    #

    indent = len(signedname)

    #
    # Get the maximum length of any pin in the pin name list
    #

    pin_name_maxlen = get_max_pin_name_length()

    #
    # Enumerate the conditions list to be output (the list that gets OR'ed together)
    #

    for list_i, conditions in enumerate(conditionslist):

        #
        # If it's the first equation line write out the signed pin name with the equals sign justified by the indent
        #

        if isfirstline:

            line = f'{signedname.ljust(indent)} = '
            isfirstline = False

        #
        # Else, indent the line with the OR symbol
        #

        else:
            line = ' ' * indent + f' {ORSTR} '

        #
        # Enumerate the conditions for the specific equation (the list that gets AND'ed together)
        #

        for cond_i, cond in enumerate(conditions):

            #
            # If the condition isn't the first then append an AND string
            #

            if cond_i != 0:
                line += f' {ANDSTR} '

            #
            # Any pin before the end append the condition justified with the max pin length (so columns are nice any tidy, all the same size)
            #

            if cond_i < len(conditions) - 1:

                line += cond.ljust(pin_name_maxlen + 1)

            #
            # Else, just append the condition
            #

            else:

                line += cond

        #
        # If the line isn't the last line append a newline
        #

        if list_i < len(conditionslist) - 1:

            truthtable.write(line + ' \n')

        #
        # Else, append a newline and end of line character (;)
        #

        else:
            truthtable.write(line + ';\n')

#
# write_pin_equations:
#   Write equations in the output PLD file in a sorted order
#

def write_pin_equations(name, pinnames, results, polarity):
    
    #
    # If the polarity is positive leave the name as is
    #

    if polarity == "positive":

        signedname = name

    #
    # Else, add the NOT string as pin name prefix
    #

    else:

        signedname = f"{NOTSTR}{name}"

    #
    # If the results reduced to True then write out a static high output equation
    #

    if results is True:

        equations.write(signedname + " = 'b'1;\n")

    #
    # Else, if the results reduced to False then write out a static low output equation
    #

    elif results is False:

        equations.write(signedname + " = 'b'0;\n")

    #
    # Else, if the results reduced to pin equations that need to be output, stored in the first element of the list
    # Process those results in a readable format
    #

    else:

        result = results[0]

        #
        # Initialize that we're starting as the first output product
        #

        isfirstproduct = True

        #
        # Sort the result to allow reproducable results
        #

        result = sorted(result, key=lambda r: tuple(get_set_bits(len(pinnames), r[1])))

        #
        # Enumerate the result list to build the equations output
        #

        for i, p in enumerate(result):

            #
            # Get the bits and mask for the current output combination
            #

            bits = p[0]
            mask = p[1]
            symbols = []
            bit = 1

            #
            # Enumerate the pin names and append each relevant symbol to symbol list
            #

            for bitnum, pinname in enumerate(pinnames):

                #
                # If the pin is relevant in this combination then append it depending if it is high or low
                #

                if (mask & bit) != 0:

                    #
                    # If the pin is high then append the pin name
                    #

                    if (bits & bit) != 0:

                        symbols.append(pinname)

                    #
                    # Else, append the inverse pin name
                    #

                    else:

                        symbols.append('!' + pinname)

                #
                # Shift to the next bit
                #

                bit <<= 1

            #
            # Join the symbols as an AND equation
            #

            line = ' & '.join(symbols)

            #
            # If we're at the end of the results then add an end of line character (;)
            #

            if i == len(result) - 1:
                eol = ";"
            else:
                eol = ""

            #
            # If this is the first product for the equation then write out the signed pin name, equal, and the equation
            #

            if isfirstproduct:

                equations.write(signedname + ' = ' + line + eol + '\n')
                isfirstproduct = False

            #
            # Else, indent the line and output it as a second OR line equation
            #

            else:
                equations.write(f'{' ' * len(signedname)} {ORSTR} ' + line + eol + '\n')

#
# write_equations_file_header:
#   Write the file header for the equations file with the file name and device name
#

def write_equations_file_header(filename, devicename):

    equations.write(f"Name {filename};\n")
    equations.write(f"Device {devicename};\n")
    equations.write(f"Partno ;\n")
    equations.write(f"Revision ;\n")
    equations.write(f"Date {datetime.datetime.now().strftime("%x")};\n")
    equations.write(f"Designer ;\n")
    equations.write(f"Company ;\n")
    equations.write(f"Assembly ;\n")
    equations.write(f"Location ;\n")
    equations.write("\n")

#
# write_equations_pin_aliases:
#   Write the pin aliases section into the equations file
#

def write_equations_pin_aliases(pinnames, outputpins):

    #
    # Write out the pin mappings section header
    #

    write_equations_section_title("Pin mappings")

    #
    # Loop for each pin and write the pin number and alias
    #

    for number, name in pinnames.items():

        #
        # Get the output index for the current pal pin number
        #

        outputindex = palpinnum_to_epromdatabitpos(number)

        #
        # If there is no output index then the pin is a dedicated input pin
        #

        if outputindex == None:

            equations.write(f'pin {number} = {name};  /* Dedicated input */ \n')

        else:

            #
            # Get the output pin related to the output pin index
            #

            outputpin = outputpins[outputindex]

            #
            # If there is no output enable for the pin then it's either in input mode or a combinatorial output
            #

            if outputpin.oe_depends.bitmap == 0:

                #
                # If the pin doesn't depend on any others it is a fixed output, or an input
                #

                if outputpin.depends.bitmap == 0:

                    #
                    # If the pin was ever seen high then it is a fixed high output
                    #

                    if outputpin.seenhigh:

                        equations.write(f'pin {number} = {name};  /* Fixed high output */ \n')

                    #
                    # If the pin was ever seen low then it is fixed low output
                    #

                    elif outputpin.seenlow:

                        equations.write(f'pin {number} = {name};  /* Fixed low output */ \n')

                    #
                    # Else, the pin was always in hi-z mode so it is configured as an input
                    #

                    else:

                        equations.write(f'pin {number} = {name};  /* Input */ \n')

                #
                # Else, the pin is a combinatorial output
                #

                else:

                    equations.write(f'pin {number} = {name};  /* Combinatorial output */ \n')

            #
            # Else, there is an output enable for the pin so it could be fixed high/low or a combinatorial output
            #

            else:

                #
                # If the pin doesn't depend on any others it is a fixed output
                #

                if outputpin.depends.bitmap == 0:

                    #
                    # If the pin was seen high then it is a fixed high output
                    #

                    if outputpin.seenhigh:

                        equations.write(f'pin {number} = {name};  /* Fixed high output w/ output enable */ \n')

                    #
                    # Else, the pin is a fixed low output
                    #

                    else:
                        
                        equations.write(f'pin {number} = {name};  /* Fixed low output w/ output enable */ \n')

                #
                # Else, the pin is a combinatorial output
                #

                else:

                    equations.write(f'pin {number} = {name};  /* Combinatorial output w/ output enable */ \n')

    #
    # Write a new line at the end of the section
    #

    write_equations_newline()

#
# write_equations_pin_name_value:
#   Write the equations for a given pin given a name / value to the truth table and equations files
#

def write_equations_pin_name_value(name, value, polarity):

    #
    # If the output value for the pin is low then write out truthtable and equations for a low pin output
    #

    if value == 0:

        #
        # If the truthtable is enabled write the positive and negative results to the truthtable file
        #

        if args.truthtable:
            truthtable.write(f" {name:12s} = 0;\n")                                                     # output to the truth table a positive pin value yields 1 ( B0 = 'b'0;)
            truthtable.write(f"{NOTSTR}{name:12s} = 1;\n")                                              # output to the truth table a negative pin value yields 0 (!B0 = 'b'1;)

        #
        # Depending on the polarity selected either write positive, negative, or both equations
        #

        match polarity:
            
            case 'auto' | 'positive':
                equations.write(f"{name} = 'b'0;\n")                                                    # output to the truth table a positive pin value yields 1 ( B0 = 'b'0;)

            case 'negative':
                equations.write(f"{NOTSTR}{name} = 'b'1;\n")                                            # output to the truth table a negative pin value yields 0 (!B0 = 'b'1;)

            case 'both':
                equations.write(f"{name} = 'b'0;\n")                                                    # output to the truth table a positive pin value yields 1 ( B0 = 'b'0;)
                equations.write(f"{NOTSTR}{name} = 'b'1;\n")                                            # output to the truth table a negative pin value yields 0 (!B0 = 'b'1;)

    #
    # Else, if the output value for the pin is high then write out truthtable and equations for a high pin output
    #

    elif value == 1:

        #
        # If the truthtable is enabled write the positive and negative results to the truthtable file
        #

        if args.truthtable:
            truthtable.write(f" {name:12s} = 1;\n")                                                     # output to the truth table a positive pin value yields 1 ( B0 = 'b'1;)
            truthtable.write(f"{NOTSTR}{name:12s} = 0;\n")                                              # output to the truth table a negative pin value yields 0 (!B0 = 'b'0;)

        #
        # Depending on the polarity selected either write positive, negative, or both equations
        #

        match polarity:
            
            case 'auto' | 'positive':
                equations.write(f"{name} = 'b'1;\n")                                                    # output to the equations a positive pin value yields 1 (B0 = 'b'1;)

            case 'negative':
                equations.write(f"{NOTSTR}{name} = 'b'0;\n")                                            # output to the truth table a negative pin value yields 0 (!B0 = 'b'0;)

            case 'both':
                equations.write(f"{name} = 'b'1;\n")                                                    # output to the equations a positive pin value yields 1 (B0 = 'b'1;)
                equations.write(f"{NOTSTR}{name} = 'b'0;\n")                                            # output to the truth table a negative pin value yields 0 (!B0 = 'b'0;)

#
# write_equations_pin_output_equations:
#   Write equations for each pin to the truthtable and equations files
#

def write_equations_pin_output_equations(outputpins):

    #
    # Print out what we're doing as we'll display a progress bar
    #

    print("Writing output pin equations...")

    #
    # Write out the output equations section header
    #

    write_equations_section_title("Output equations")

    #
    # Iterate on each output pin using data accumulated above to produce the truthtable and equations for each
    #

    for outputpin in tqdm.tqdm(outputpins):

        #
        # If the output pin has no dependencies (always has the same output level) then write a static equation depending on if it was ever seen high or low
        #

        if outputpin.depends.bitmap == 0:

            if outputpin.seenhigh:

                write_equations_pin_name_value(outputpin.name, 1, args.polarity)
                write_equations_newline()

            elif outputpin.seenlow:

                write_equations_pin_name_value(outputpin.name, 0, args.polarity)
                write_equations_newline()

            # else PIN is always in hi-z mode

        #
        # Else build a list of input combinations that the pin depends on for output and write out the equations for it
        #

        else:

            #
            # Write out the truthtable entries for the positive, negative, and dont-care conditions for debugging purposes
            #

            if args.truthtable:
                write_pin_truthtable(f' {outputpin.name}', outputpin.positiveconditions)
                write_pin_truthtable(f'{NOTSTR}{outputpin.name}', outputpin.negativeconditions)
                write_pin_truthtable(f'{outputpin.name}_DC', outputpin.dontcareconditions)

            #
            # Simplify the positive and negative minterm equations
            #

            simplified_terms_pos = simplify_minterms(outputpin.depends.pinnames, outputpin.posminterms, outputpin.dontcareterms)
            simplified_terms_neg = simplify_minterms(outputpin.depends.pinnames, outputpin.negminterms, outputpin.dontcareterms)

            #
            # If the user wants both polarity output then write both sets of pin equations
            #

            if args.polarity == "both":

                write_pin_equations(outputpin.name, outputpin.depends.pinnames, simplified_terms_pos, "positive")
                write_pin_equations(outputpin.name, outputpin.depends.pinnames, simplified_terms_neg, "negative")   

            #
            # Else if the user wants either a positive polarity, or uses auto and the terms simplified to a boolean or there were fewer positive terms then write out the positive equations
            #

            elif (
                args.polarity == "positive" or
                (
                    args.polarity == "auto" and
                    (
                        isinstance(simplified_terms_pos, bool) or len(simplified_terms_pos[0]) <= len(simplified_terms_neg[0])
                    )
                )
            ):
                                               
                write_pin_equations(outputpin.name, outputpin.depends.pinnames, simplified_terms_pos, "positive")

            #
            # Otherwise write out the negative equations
            #

            else:

                write_pin_equations(outputpin.name, outputpin.depends.pinnames, simplified_terms_neg, "negative")           

            #
            # Write out a new line to have some visual separation between pin equations in the file
            #

            write_equations_newline()

#
# write_equations_pin_output_enable_equations:
#   Write output enable equations for each pin to the truthtable and equations files
#

def write_equations_pin_output_enable_equations(outputpins):

    #
    # Print out what we're doing as we'll display a progress bar
    #
    
    print("Writing output pin oe equations...")

    #
    # Write out the output equations section header
    #

    write_equations_section_title("Output enable equations")

    #
    # Iterate on each output pin using data accumulated above to produce the truthtable and equations for each
    #

    for outputpin in tqdm.tqdm(outputpins):

        #
        # If the output pin has no output enable dependencies (always has the same output level) then write a static equation depending on if it was ever seen high or low
        #

        if outputpin.oe_depends.bitmap == 0:

            if outputpin.seenhigh or outputpin.seenlow:

                write_equations_pin_name_value(outputpin.name + ".oe", 1, args.oepolarity)
                write_equations_newline()

            else:

                write_equations_pin_name_value(outputpin.name + ".oe", 0, args.oepolarity)
                write_equations_newline()

        #
        # Else build a list of output enable combinations that the pin depends on for output and write out the equations for it
        #

        else:

            #
            # Write out the truthtable entries for the positive and negative conditions for debugging purposes
            #

            if args.truthtable:
                write_pin_truthtable(f' {outputpin.name + ".oe"}', outputpin.oepositiveconditions)
                write_pin_truthtable(f'{NOTSTR}{outputpin.name + ".oe"}', outputpin.oenegativeconditions)

            #
            # Simplify the positive and negative minterm equations
            #

            simplified_terms_pos = simplify_minterms(outputpin.oe_depends.pinnames, outputpin.oeposminterms)
            simplified_terms_neg = simplify_minterms(outputpin.oe_depends.pinnames, outputpin.oenegminterms)

            #
            # If the user wants both polarity output then write both sets of pin oe equations
            #

            if args.oepolarity == "both":

                write_pin_equations(outputpin.name + ".oe", outputpin.oe_depends.pinnames, simplified_terms_pos, "positive")
                write_pin_equations(outputpin.name + ".oe", outputpin.oe_depends.pinnames, simplified_terms_neg, "negative")   

            #
            # Else if the user wants either a positive polarity, or uses auto and the terms simplified to a boolean or there were fewer positive terms then write out the positive oe equations
            #

            elif (
                args.oepolarity == "positive" or
                (
                    args.oepolarity == "auto" and
                    (
                        isinstance(simplified_terms_pos, bool) or len(simplified_terms_pos[0]) <= len(simplified_terms_neg[0])
                    )
                )
            ):
                                               
                write_pin_equations(outputpin.name + ".oe", outputpin.oe_depends.pinnames, simplified_terms_pos, "positive")

            #
            # Otherwise write out the negative oe equations
            #

            else:

                write_pin_equations(outputpin.name + ".oe", outputpin.oe_depends.pinnames, simplified_terms_neg, "negative")

            #
            # Write out a new line to have some visual separation between pin equations in the file
            #

            write_equations_newline()

# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
#
# MAIN PROGRAM:
#
#   - Get command arguments
#   - Get the dump and use it to autoselect the device (if applicable)
#   - Read the dump into a list of input combinations and output bits
#   - Configure the input and output pin lists
#   - Build output pin dependencies and raw equations
#   - Open output files
#   - Write PLD file (header, pin aliases, output pin equations, oe pin equations)
#   - Close output files
#
# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

#
# Get command line arguments for the program
#

args = get_command_arguments()

#
# Get the path to the dump
#

dumppath = pathlib.Path(args.filename)

#
# Get the current device from the program arguments or by auto-detect based on file size
#

device = select_device(dumppath)

#
# Read the input rom dump to create the dumpdata object
#

dumpdata = read_eprom_dump(dumppath)

#
# Get pin configurations for input and output pins
#

inputpins = build_inputpins_configuration()
outputpins = build_outputpins_configuration()

#
# Build pin dependency maps for each output pin
#

build_outputpins_dependencies(inputpins, outputpins)

#
# Build pin equations for each output pin
#

build_outputpins_equations(outputpins)

#
# Open output files (for equations and truthtable files)
#

equations = (dumppath.parent / (dumppath.stem + '.repal.pld')).open("wt")

if args.truthtable:
    truthtable = (dumppath.parent / (dumppath.stem + '.repal.truthtable.txt')).open("wt")

#
# Write the equations file header, aliases, and output equations sections
#

write_equations_file_header(dumppath.stem, device["pal_device_name"])
write_equations_pin_aliases(device["pal_pin_names"], outputpins)
write_equations_pin_output_equations(outputpins)
write_equations_pin_output_enable_equations(outputpins)

#
# Close output files (for equations and truthtable files)
#

equations.close()

if args.truthtable:
    truthtable.close()
