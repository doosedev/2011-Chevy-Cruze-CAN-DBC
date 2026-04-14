# DBC file generator from CSV

import csv
import json
import re

# Load file of abbreviations from CSV
def load_abbreviations(file_path):
    abbreviations = {}
    with open(file_path, mode='r') as csvfile:
        reader = csv.reader(csvfile)
        for row in reader:
            if len(row) >= 2:
                abbreviations[row[0].strip().lower()] = row[1].strip()
    return abbreviations

# Replace strings with abbreviations in a given text, defaulting to the original word if no abbreviation is found
def string_to_dbc_name(text, abbreviations):
    words = text.split()
    replaced_words = [abbreviations.get(word.lower(), word) if word.lower() in abbreviations else word for word in words]
    return ''.join(replaced_words)

# Load the message and signal definitions file
with open('definition.csv', mode='r') as csvfile:
    reader = csv.DictReader(csvfile)
    input_lines = list(reader)

# Load abbreviations
abbreviations = load_abbreviations('abbreviations.csv')

# Load definition file into JSON dict
messages = {}
message_name = ""
nodes = set()

# Iterate over all lines from input file
for line in input_lines:
    # If line contains message definition, store a new message entry in the JSON dict and update the current message name
    # Also, add the message sender to the set of nodes
    if line['Message']:
        message_name = line['Message']
        message_sender = re.split(r'[,/]', line['Transmitter'])[0].strip() if line['Transmitter'] else 'Vector__XXX'
        messages[message_name] = {
            'ID': int(line['ID'].replace('$', ''), 16),
            'Sender': message_sender,
            'Signals': [],
            'DLC': 0
        }
        nodes.add(message_sender)

    # If line contains signal definition, store a new signal entry under the current message in the JSON dict
    if line['Signal']:
        # Skip packet signals (they're not actual signals)
        if line['Data Type'] == 'Packet':
            continue
        
        # Get the common signal data
        signal = {
            'Name': line['Signal'],
            'Start Bit': (int(line['Start Byte']) * 8) + (int(line['Start Bit'])),
            'Length': int(line['Length']),
            'Unit': line['Unit']
        }

        # If abbreviated name is longer than 32 characters, throw exception
        name_len = len(string_to_dbc_name(signal['Name'], abbreviations))
        if name_len > 32:
            raise ValueError(f"Abbreviated signal name '{string_to_dbc_name(signal['Name'], abbreviations)}' exceeds 32 characters limit at {name_len}.")

        # Calculate the byte this signal ends on and update the message DLC if necessary
        end_byte = signal['Start Bit'] // 8 + (signal['Length'] - 1) // 8
        if end_byte + 1 > messages[message_name]['DLC']:
            messages[message_name]['DLC'] = end_byte + 1

        # If message length is greater than 8 bytes, throw exception
        if messages[message_name]['DLC'] > 8:
            raise ValueError(f"Message '{message_name}' has a DLC of {messages[message_name]['DLC']} which exceeds the 8 byte limit.")

        # Determine the signal type based on the data type
        if line['Data Type'] in ['Unsigned Numeric', 'Boolean', 'Enumeration']:
            signal['Type'] = 'Unsigned'
        elif line['Data Type'] in ['Signed Numeric']:
            signal['Type'] = 'Signed'
        else:
            signal['Type'] = 'Unsigned'  # Default to unsigned if data type is unrecognized

        # Get the minimum and maximum values, if provided
        signal['Minimum'] = float(line['Min']) if line['Min'] else 0.0
        signal['Maximum'] = float(line['Max']) if line['Max'] else 0.0

        # Get the scale and offset, defaulting to 1.0 and 0.0 if not provided
        signal['Scale'] = float(eval(line['Scale'])) if line['Scale'] else 1.0
        signal['Offset'] = float(eval(line['Offset'])) if line['Offset'] else 0.0

        # If signal is an enum, parse the enumeration values from the conversion field
        if line['Data Type'] == 'Enumeration':
            signal['Values'] = {}
            for value in re.split(r'[;\n]', line['Conversion'].replace('$', '')):
                # Skip any values that don't contain an '=' sign (invalid format), and skip any lines that cause exceptions
                try:
                    if '=' in value:
                        key, val = value.split('=')
                        signal['Values'][int(key.strip(), 16)] = val.strip()
                except:
                    continue

        # Store signal receiver (currently Vector__XXX for all)
        signal['Receiver'] = 'Vector__XXX'

        # Store the signal to the current message
        messages[message_name]['Signals'].append(signal)

# Store the messages and set of nodes to a JSON dict
dbc_def = {
    'Messages': messages,
    'Nodes': list(nodes)
}

# Save the JSON dict to a file
with open('output.json', mode='w') as jsonfile:
    json.dump(dbc_def, jsonfile, indent=4)

# Write the DBC file
with open('2011-cruze-iso15765-4.dbc', mode='w') as dbcfile:
    # Write headers
    dbcfile.write('VERSION "Generated DBC File"\n\n')
    
    dbcfile.write('NS_ :\n\tNS_DESC_\n\tCM_\n\tBA_DEF_\n\tBA_\n\tVAL_\n\tCAT_DEF_\n\tCAT_\n\tFILTER\n\tBA_DEF_DEF_\n\tEV_DATA_\n\tENVVAR_DATA_\n\tSGTYPE_\n\tSGTYPE_VAL_\n\tBA_DEF_SGTYPE_\n\tBA_SGTYPE_\n\tSIG_TYPE_REF_\n\tVAL_TABLE_\n\tSIG_GROUP_\n\tSIG_VALTYPE_\n\tSIGTYPE_VALTYPE_\n\tBO_TX_BU_\n\tBA_DEF_REL_\n\tBA_REL_\n\tBA_DEF_DEF_REL_\n\tBU_SG_REL_\n\tBU_EV_REL_\n\tBU_BO_REL_\n\tSG_MUL_VAL_\n\nBS_:\n\n')

    # Write node list
    dbcfile.write('BU_:')
    for node in dbc_def['Nodes']:
        dbcfile.write(f' {node}')
    dbcfile.write('\n\n')

    # Write signal list
    for message_name, message in dbc_def['Messages'].items():
        dbcfile.write(f'BO_ {message["ID"]} {string_to_dbc_name(message_name, abbreviations)}: {message["DLC"]} {message["Sender"]}\n')
        
        for signal in message['Signals']:
            dbcfile.write(f'\tSG_ {string_to_dbc_name(signal["Name"], abbreviations)} : {signal["Start Bit"]}|{signal["Length"]}@0')
            
            if signal['Type'] == 'Signed':
                dbcfile.write('-')
            else:
                dbcfile.write('+') 

            dbcfile.write(f' ({signal["Scale"]:g},{signal["Offset"]:g})')

            if signal["Minimum"] is not None or signal["Maximum"] is not None:
                dbcfile.write(f' [{signal["Minimum"]:g}|{signal["Maximum"]:g}]')
                
            dbcfile.write(f' "{signal["Unit"]}" {signal["Receiver"]}\n')

        dbcfile.write('\n')

    # Write value tables
    for message_name, message in dbc_def['Messages'].items():
        for signal in message['Signals']:
            if signal['Type'] == 'Unsigned' and 'Values' in signal:
                dbcfile.write(f'VAL_ {message["ID"]} {string_to_dbc_name(signal["Name"], abbreviations)}')
                for key, val in reversed(sorted(signal['Values'].items())):
                    dbcfile.write(f' {key} "{val}"')
                dbcfile.write(';\n')