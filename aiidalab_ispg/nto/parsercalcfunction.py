# Modified from https://github.com/radi0sus/orca_st

from aiida.engine import calcfunction
from aiida.orm import Dict

import re

@calcfunction
def parse_orca_output(nto_folder, filename="aiida.out", threshold=0, states="all"):    
                                                        
    #Convert from Aiida nodes to python datatypes if required.
    filename = filename.value
    threshold = threshold.value
    states = states.value

    # global constants
    state_string_start = 'TD-DFT/TDA EXCITED STATES'                                         #check for states from here
    state_string_end = 'TD-DFT/TDA-EXCITATION SPECTRA'                                       #stop reading states from here
    nto_string_start ='NATURAL TRANSITION ORBITALS'                                          #NTOs start here
    found_nto = False                                                                        #found NTOs in orca.out

    #global lists
    orblist = list()              #list of orbital -> orbital transition
    statedict = dict()            #dictionary of states with all transitions
    selected_statedict = dict()   #dictionary of selected states with all transitions and or with those above the threshold

    #for NTO
    nto_orblist=list()            #list of orbital -> orbital transition for NTOs
    nto_statedict=dict()          #dictionary of states with all transitions for NTOs

    #check if threshold is between 0 and 100%, reset if not
    if threshold:
        if threshold > 100 or threshold < 0:
            print("Warning! Threshold out of range. Reset to 0.")
            threshold=0
            
    #open a file
    #check existence
    try:
        with nto_folder.open(filename) as input_file:
            for line in input_file:
                #start exctract text 
                if state_string_start in line:
                    for line in input_file:
                        #build the state - with several transitions dict: dict[state]=list(orb1 -> orb2, xx%), list(orb3 -> orb4, xx%)
                        #first the state
                        if re.search(r"STATE\s{1,}(\d{1,}):",line):
                            match_state=re.search(r"STATE\s{1,}(\d{1,}):",line)
                        #transitions here in orblist
                        elif re.search(r"\d{1,}[a,b]\s{1,}->\s{1,}\d{1,}[a,b]",line):
                            match_orbs=re.search(r"(\d{1,}[a,b]\s{1,}->\s{1,}\d{1,}[a,b])\s{1,}:\s{1,}(\d{1,}.\d{1,})",line)
                            orblist.append((match_orbs.group(1).replace("  "," "),match_orbs.group(2)))
                        #add orblist to statedict and clear orblist for next state
                        elif re.search(r"^\s*$",line):
                            if orblist:
                                statedict[match_state.group(1)] = orblist
                                orblist=[] 
                                                            
                        #exit here
                        elif nto_string_start in line:
                            break
                        elif state_string_end in line:
                            break
                
                #same for NTOs
                if re.search(r"FOR STATE\s{1,}(\d{1,})",line):
                    #found NTO in orca.out
                    found_nto = True
                    match_state_nto=re.search(r"FOR STATE\s{1,}(\d{1,})",line)
                elif re.search(r"\d{1,}[a,b]\s{1,}->\s{1,}\d{1,}[a,b]",line):
                    match_orbs_nto=re.search(r"(\d{1,}[a,b]\s{1,}->\s{1,}\d{1,}[a,b])\s{1,}: n=\s{1,}(\d{1,}.\d{1,})",line)
                    nto_orblist.append((match_orbs_nto.group(1).replace(" ","").split("->"),match_orbs_nto.group(2)))
                    
                #add orblist to statedict and clear orblist for next state
                elif re.search(r"^\s*$",line):
                    if nto_orblist:
                        nto_statedict[match_state_nto.group(1)] = nto_orblist
                        nto_orblist=[] 
                
    #file not found -> exit here
    except IOError:
        print(f"'{filename}'" + " not found")
        return {}
        
    #no NTO data in orca.out -> exit here
    if found_nto == False:
        print(f"'{nto_string_start}'" + " not found in " + f"'{filename}'")
        return {}

    #build selected_statedict from statedict with selected states
    try:
        if states == 'all':
            selected_statedict = nto_statedict

        elif re.search(r"\d",states):
            matchstateslist=(re.findall(r"\d+",states))
            for elements in matchstateslist:
                selected_statedict[elements]=nto_statedict[elements]

    except KeyError:
        print("Warning! State(s) not present. Exit.")
        return {}
                
    #remove transitions below threshold from selected_statedict
    for elements in selected_statedict:
        transition_list=[]
        for v in selected_statedict[elements]:
            if float(v[1])*100 >= threshold:
                transition_list.append(v)
        selected_statedict[elements]=transition_list    

    return Dict(selected_statedict)
