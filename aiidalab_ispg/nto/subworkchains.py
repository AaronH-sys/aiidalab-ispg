from aiida.engine import WorkChain, calcfunction, ToContext, run_get_node
from aiida.orm import SinglefileData, StructureData, Dict, FolderData, Str, load_code
from aiida.plugins import CalculationFactory
from aiida_shell import launch_shell_job
import io
import os
from cubehandler import Cube

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

        

    