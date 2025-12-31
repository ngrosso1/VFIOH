import subprocess
import shutil
import xml.etree.ElementTree as ET
import libvirt
import os

GREEN = '\033[92m'
RED = '\033[91m'
RESET = '\033[0m'

def restart_libvirt_service():
    # Check if systemd is present by verifying if `systemctl` exists
    if shutil.which("systemctl"):
        # If systemctl is available, use it to restart libvirtd
        print("Using systemd, restarting libvirtd with systemctl...")
        try:
            subprocess.run(["systemctl", "restart", "libvirtd"], check=True)
        except subprocess.CalledProcessError as e:
            print(f"Error restarting libvirtd with systemctl: {e}")
    
    elif shutil.which("service"):
        # If systemctl isn't available, check for `service` command
        print("systemctl not found, using service command...")
        try:
            subprocess.run(["service", "libvirtd", "restart"], check=True)
        except subprocess.CalledProcessError as e:
            print(f"Error restarting libvirtd with service: {e}")
    
    else:
        print("Neither systemctl nor service command found. Please check your init system")

def setup_libvirt_hooks(vm_name: str):
    try:
        # Get the directory where this script is located
        script_dir = os.path.dirname(os.path.abspath(__file__))
        
        #Creating hooks directory
        subprocess.run(["mkdir", "-p", "/etc/libvirt/hooks"], check=True)

        #Downloads the qemu hook script
        #subprocess.run([
        #    "wget",
        #    "https://raw.githubusercontent.com/PassthroughPOST/VFIO-Tools/master/libvirt_hooks/qemu",
        #    "-O", "/etc/libvirt/hooks/qemu"
        #], check=True)

        #Making the qemu script executable
        subprocess.run(["chmod", "+x", "/etc/libvirt/hooks/qemu"], check=True)

        #Restarting libvirtd
        restart_libvirt_service()

        #Creating prepare and release hook directories
        prepare_dir = f"/etc/libvirt/hooks/qemu.d/{vm_name}/prepare/begin"
        release_dir = f"/etc/libvirt/hooks/qemu.d/{vm_name}/release/end"
        subprocess.run(["mkdir", "-p", prepare_dir], check=True)
        subprocess.run(["mkdir", "-p", release_dir], check=True)

        #Copying start.sh and revert.sh from hooks directory
        start_sh_source = os.path.join(script_dir, "start.sh")
        revert_sh_source = os.path.join(script_dir, "revert.sh")
        
        subprocess.run(["cp", start_sh_source, prepare_dir], check=True)
        subprocess.run(["cp", revert_sh_source, release_dir], check=True)
        subprocess.run(["chmod", "+x", f"{prepare_dir}/start.sh"], check=True)
        subprocess.run(["chmod", "+x", f"{release_dir}/revert.sh"], check=True)

        print("Libvirt hook setup completed successfully")

    except subprocess.CalledProcessError as e:
        print(f"🚨 Error 🚨 occurred during setup: {RED}{e}{RESET}")

def get_gpu_pci_ids():
    """Returns the PCI IDs for the NVIDIA GPU (VGA and Audio)"""
    try:
        output = subprocess.check_output(["lspci", "-nnk"], text=True).splitlines()

        vga_id = None
        audio_id = None

        for line in output:
            if "VGA compatible controller" in line and "NVIDIA" in line:
                vga_id = line.split()[0]
            elif "Audio device" in line and "NVIDIA" in line:
                audio_id = line.split()[0]

        if vga_id and audio_id:
            print(f"Found GPU PCI IDs: VGA = {GREEN}{vga_id}{RESET}, Audio = {GREEN}{audio_id}{RESET}")
        else:
            print("Could not find both GPU and Audio IDs")
        
        return vga_id, audio_id

    except subprocess.CalledProcessError as e:
        print(f"Failed to run lspci: {RED}{e}{RESET}")
        return None, None

def format_pci_id(raw_id):
    return f"pci_0000_{raw_id.replace(':', '_').replace('.', '_')}"

def update_start_sh(vm_name: str):
    """Appends virsh nodedev-detach lines to start.sh before modprobe vfio-pci"""
    vga_id, audio_id = get_gpu_pci_ids()

    if not vga_id or not audio_id:
        print("Could not find GPU or audio PCI IDs")
        return

    pci_vga = format_pci_id(vga_id)
    pci_audio = format_pci_id(audio_id)

    start_sh_path = f"/etc/libvirt/hooks/qemu.d/{vm_name}/prepare/begin/start.sh"

    try:
        with open(start_sh_path, "r") as file:
            lines = file.readlines()

        insert_index = next((i for i, line in enumerate(lines) if "modprobe vfio-pci" in line), None)
        if insert_index is None:
            print(f"modprobe vfio-pci not found in {start_sh_path}")
            return

        #Inserts detachment lines just before the modprobe
        lines.insert(insert_index, f"virsh nodedev-detach {pci_audio}\n\n")
        lines.insert(insert_index, f"virsh nodedev-detach {pci_vga}\n")
        lines.insert(insert_index, f"#Unbind the GPU from display driver\n")

        #Writes updated lines back
        with open(start_sh_path, "w") as file:
            file.writelines(lines)

        print(f"Updated {start_sh_path} with GPU detach commands")

    except FileNotFoundError:
        print(f"{start_sh_path} not found")
    except PermissionError:
        print(f"Permission denied while editing {start_sh_path}")

def update_revert_sh(vm_name: str):
    """Prepends virsh nodedev-reattach lines to revert.sh after set -x"""
    vga_id, audio_id = get_gpu_pci_ids()

    if not vga_id or not audio_id:
        print("Could not find GPU or audio PCI IDs")
        return

    pci_vga = format_pci_id(vga_id)
    pci_audio = format_pci_id(audio_id)

    revert_sh_path = f"/etc/libvirt/hooks/qemu.d/{vm_name}/release/end/revert.sh"

    try:
        with open(revert_sh_path, "r") as file:
            lines = file.readlines()

        #Finds the index right after "set -x"
        insert_index = next(
            (i + 1 for i, line in enumerate(lines) if line.strip() == "set -x"),
            0
        )

        #Insert reattach commands (audio first)
        lines.insert(insert_index, f"virsh nodedev-reattach {pci_vga}\n")
        lines.insert(insert_index, f"virsh nodedev-reattach {pci_audio}\n")
        lines.insert(insert_index, f"\n#Re-Bind GPU to Nvidia Driver\n")

        with open(revert_sh_path, "w") as file:
            file.writelines(lines)

        print(f"Updated {revert_sh_path} with GPU reattach commands")

    except FileNotFoundError:
        print(f"{revert_sh_path} not found")
    except PermissionError:
        print(f"Permission denied while editing {revert_sh_path}")

def add_gpu_passthrough_devices(vm_name):
    """Attach GPU and audio PCI devices to a libvirt VM"""
    vga_id, audio_id = get_gpu_pci_ids()

    if not vga_id or not audio_id:
        print("GPU or Audio PCI IDs not found. Exiting...")
        return

    conn = libvirt.open("qemu:///system")
    if conn is None:
        print("Failed to open libvirt connection")
        return

    try:
        dom = conn.lookupByName(vm_name)
        xml = dom.XMLDesc()
        tree = ET.fromstring(xml)

        devices_elem = tree.find("devices")

        def pci_hostdev_element(pci_id):
            if pci_id.count(':') == 2:
                domain, bus, slot_func = pci_id.split(':')
            elif pci_id.count(':') == 1:
                domain = "0000"
                bus, slot_func = pci_id.split(':')
            else:
                raise ValueError(f"Unexpected PCI ID format: {pci_id}")

            slot, func = slot_func.split('.')
            return ET.Element("hostdev", {
                "mode": "subsystem",
                "type": "pci",
                "managed": "yes"
            }), {
                "domain": f"0x{domain}",
                "bus": f"0x{bus}",
                "slot": f"0x{slot}",
                "function": f"0x{func}"
            }
    
        for pci_id in [vga_id, audio_id]:
            hostdev, address_attrs = pci_hostdev_element(pci_id)
            source = ET.SubElement(hostdev, "source")
            ET.SubElement(source, "address", address_attrs)
            devices_elem.append(hostdev)

        new_xml = ET.tostring(tree).decode()
        conn.defineXML(new_xml)
        print(f"Added GPU passthrough devices to VM '{vm_name}' ✅")
        print("⚠️  Note ⚠️ : Lastly you need to passthrough your USB devices")
        print("To do this open up Virt-manager, " \
        "\n      ➡️  Open the windows VM"
        "\n      ➡️  Open the tab show virtual hardware details"
        "\n      ➡️  Click add hardware"
        "\n      ➡️  Open USB Host Device"
        "\n      ➡️  Click the device you want to be passed through"
        "\n      ➡️  Click finish")

    except libvirt.libvirtError as e:
        print(f"Libvirt error: {RED}{e}{RESET}")
    finally:
        conn.close()