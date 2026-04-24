from aiida.engine import calcfunction
from aiida.orm import Dict, Float, Str, Bool

@calcfunction
def parse_orca_output(nto_folder, filename, threshold=0, states="all", nto=True):    
    # -*- coding: utf-8 -*-
    '''
    # orca-st
    '''

    import sys                              #system
    import re                               #regular expressions

    #remove comment in case you get an encoding error when saving the output to a file with ">" under windows
    #alternatively replace 'cm⁻¹' with 'cm-1' in the table header (close to the end of script)
    #alternatively you can configure the windows console with "set PYTHONIOENCODING=utf-8" before starting the script
    #replace 'cm⁻¹' with 'cm-1' for pdf file conversion with pandoc in case of unicode issues
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')                                                     

    #Convert from Aiida nodes to python datatypes if required.
    if hasattr(filename, "value"):
        filename = filename.value
    if hasattr(threshold, "value"):
        threshold = threshold.value
    if hasattr(states, "value"):
        states = states.value
    if hasattr(nto, "value"):
        nto = nto.value

    # global constants
    found_uv_section = False                                                                 #check for uv data in out
    specstring_start = 'ABSORPTION SPECTRUM VIA TRANSITION ELECTRIC DIPOLE MOMENTS'          #check orca.out from here
    specstring_end = 'ABSORPTION SPECTRUM VIA TRANSITION VELOCITY DIPOLE MOMENTS'            #stop reading orca.out from here
    state_string_start = 'TD-DFT/TDA EXCITED STATES'                                         #check for states from here
    state_string_end = 'TD-DFT/TDA-EXCITATION SPECTRA'                                       #stop reading states from here
    nto_string_start ='NATURAL TRANSITION ORBITALS'                                          #NTOs start here
    found_nto = False                                                                        #found NTOs in orca.out
    #for ORCA 6
    state = 0                                                                                #ORCA 6 does not list the state in the table
    orca6 = False                                                                            #for including transitions in case of ORCA 6 on request

    #global lists
    statelist = list()            #mode
    energylist = list()           #energy cm-1
    intenslist = list()           #fosc
    nmlist = list()               #wavelength 
    orblist = list()              #list of orbital -> orbital transition
    statedict = dict()            #dictionary of states with all transitions
    selected_statedict = dict()   #dictionary of selected states with all transitions and or with those above the threshold
    md_table = list()             #table for the markdown output
    #for ORCA 6
    #in ORCA 6 there is no state given in the list
    translist = list()
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
                
                if specstring_start in line:
                #found UV data in orca.out
                    found_uv_section=True
                    for line in input_file:
                        #stop exctract text 
                        if specstring_end in line:
                            break
                        #only recognize lines that start with number
                        #split line into 4 lists state, energy, nm, intensities
                        #line should start with a number
                        if re.search(r"^\s{1,}\d+\s{1,}\d",line): 
                            statelist.append(int(line.strip().split()[0])) 
                            energylist.append(float(line.strip().split()[1]))
                            nmlist.append(float(line.strip().split()[2]))
                            intenslist.append(float(line.strip().split()[3]))

    #file not found -> exit here
    except IOError:
        print(f"'{filename}'" + " not found")
        return {}

    #no UV data in orca.out -> exit here
    if found_uv_section == False:
        print(f"'{specstring_start}'" + " not found in " + f"'{filename}'")
        return {}
        
    #no NTO data in orca.out -> exit here
    if nto == True and found_nto == False:
        print(f"'{nto_string_start}'" + " not found in " + f"'{filename}'")
        return {}

    #build selected_statedict from statedict with selected states
    try:
        if states == 'all':
            if nto:
                selected_statedict = nto_statedict
            else:
                selected_statedict = statedict
        elif re.search(r"\d",states):
            matchstateslist=(re.findall(r"\d+",states))
            for elements in matchstateslist:
                if nto:
                    selected_statedict[elements]=nto_statedict[elements]
                else:
                    selected_statedict[elements]=statedict[elements]
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
