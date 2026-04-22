from aiida.engine import WorkChain, calcfunction, ToContext, run_get_node
from aiida.orm import SinglefileData, StructureData, Dict, FolderData, Str, load_code
from aiida.plugins import CalculationFactory
from aiida_shell import launch_shell_job
import io
import os
from cubehandler import Cube


OrcaCalculation = CalculationFactory("orca.orca")
# Workchain for a basic ORCA calculation.
class OrcaWorkChain(WorkChain):
    @classmethod
    def define(cls, spec):
        super().define(spec)
        #spec.input("geometry", valid_type = SinglefileData, help="Test geometry (.xyz file)")
        spec.input("parameters", valid_type = Dict, help = "Dictionary of orca parameters")
        spec.output("nto_folder", valid_type=FolderData, help="ORCA output files.")
        spec.outline(
            cls.submit_orca_calc
        )
    
    def submit_orca_calc(self):
        #Create a builder object for the orca plugin.
        builder = OrcaCalculation.get_builder()
        #Load orca
        builder.code = load_code("orca@localhost")
        #Construct a test molecule (acrolein)
        structure = StructureData()
        structure.append_atom(position=(-0.58780, -0.39670, -0.00030), symbols="C")
        structure.append_atom(position=(-1.68290, 0.12550, -0.00000), symbols="O")
        structure.append_atom(position=(0.61750, 0.43190, 0.00020), symbols="C")
        structure.append_atom(position=(1.82210, -0.14250, -0.00010), symbols="C")
        structure.append_atom(position=(-0.50290, -1.47330, 0.00350), symbols="H")
        structure.append_atom(position=(0.53260, 1.50860, 0.00090), symbols="H")
        structure.append_atom(position=(1.90700, -1.21920, -0.00080), symbols="H")
        structure.append_atom(position=(2.71210, 0.46930, 0.00030), symbols="H")
        structure.pbc = (False, False, False)
        #Pass structure to the builder object
        builder.structure = structure
        #set parameters
        builder.parameters = self.inputs.parameters

        #adding metadata.
        builder.metadata.options = {
            "additional_retrieve_list": ["*.nto", "aiida.out"],
            "resources": {'num_machines': 1, 'num_mpiprocs_per_machine': 1},
        }
        #Run ORCA (requires RabbitMQ, not configured by default on the "presto" profile)
        #Also I cannot get it to work at all at the moment so using run_get_node instead.
        # process = self.submit(builder)
        # return ToContext(calc=process)
        
        #Run without RabbitMQ
        results, node = run_get_node(builder)
        #Return the output folder.
        self.out("nto_folder", results["retrieved"])

    

#WorkChain to convert to and compress .cube files.
class NTOProcessingWorkChain(WorkChain):
    @classmethod
    def define(cls, spec):
        super().define(spec)
        spec.input("nto_folder", valid_type=FolderData, help="Folder containing the ORCA output from OrcaWorkChain.")
        spec.input("s", valid_type=Str, help="Desired excitation.")
        spec.input("mo", valid_type=Str, help="Desired orbital number.")
        spec.output("compressed_cube", valid_type=SinglefileData, help="Compressed cube file")
        spec.outline(
            cls.nto_to_cube,
            cls.cube_compress
        )

    def nto_to_cube(self):
        #load orca_plot
        orca_plot = load_code("orca_plot@localhost")
        #Define folder with NTOs
        folder = self.inputs.nto_folder
        #Define electronic transition.
        s=(self.inputs.s).value
        #Define the specific molecular orbital to plot.
        mo=(self.inputs.mo).value
        #Create SinglefileData node with orca_plot options (wrapped in a temporary BytesIO file).
        plot_options_node = SinglefileData(file=io.BytesIO(("1\n1\n3\n0\n5\n7\n2\n"+mo+"\n10\n11\n").encode("utf-8")), filename="plot_input.txt")
        #Define NTO filename.
        nto_filename = "aiida.s"+s+".nto"        
        #Create SinglefileData node with NTO data.
        with folder.open(nto_filename, mode="rb") as nto_file:
            nto_data_node = SinglefileData(file=nto_file, filename=nto_filename)


        #Run orca_plot
        results, node = launch_shell_job(
            "orca_plot", 
            arguments=["{nto_data}", "-i"], 
            nodes={"nto_data": nto_data_node, "plot_options": plot_options_node},
            metadata={"options": {"filename_stdin": plot_options_node.filename}},
            outputs=["*.cube"]
        )
        #Extract the cube file from the results.
        self.ctx.uncompressed_cube = results["aiida_s"+(s)+"_mo"+(mo)+"a_cube"]

    def cube_compress(self):
        #Defining the original cube file.
        orig_file = self.ctx.uncompressed_cube
        
        #calcfunction required to create the new cube file "In order to preserve data provenance" apparently.
        compressed_node = calc_compression(orig_file)
        

        #Output the result
        self.out("compressed_cube", compressed_node)


@calcfunction
def calc_compression(orig_file):
    #Cubehandler requires a local file to read from, so we create a temporary file (bit of a bodge).
    temp_in = "temp.cube"
    #Opening the original cube file.
    with orig_file.open(mode="rb") as orig_handle:
        with open(temp_in, "wb") as temp_handle:
            temp_handle.write(orig_handle.read())
    
    #Reading the original cube data.
    orig_cube = Cube.from_file(temp_in)

    #Compress the file
    orig_cube.reduce_data_density_slicing(points_per_angstrom=2)

    #Create another temporary file to export the compressed file.
    temp_out = "temp2.cube"
    orig_cube.write_cube_file(temp_out, low_precision=False)

    #Read the temporary output file back in as a SinglefileData node.
    with open(temp_out, "rb") as temp2_handle:
        compressed_node = SinglefileData(temp2_handle, filename="compressed.cube")
    
    #Clean up temp files.
    if os.path.exists(temp_in):
        os.remove(temp_in)
    if os.path.exists(temp_out):
        os.remove(temp_out)
    return(compressed_node)

        

    